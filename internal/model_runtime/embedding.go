// Package model_runtime provides embedding model implementations for the
// Agenyx guardrails pipeline. It is intentionally separate from guardrails
// so guardrails remains a standalone, dependency-light module.
//
// The embedding-based jailbreak provider in internal/guardrails depends only
// on the EmbeddingModel interface; model_runtime supplies concrete
// implementations (stub, remote HTTP, and a future local model).
package model_runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// EmbeddingModel converts text into a fixed-length vector embedding.
// Implementations must be stateless and safe for concurrent use.
// This is the same interface consumed by guardrails.JailbreakProvider.
type EmbeddingModel interface {
	// Embed returns a vector embedding for text. ctx is used for
	// cancellation and timeouts.
	Embed(ctx context.Context, text string) ([]float64, error)
}

// BatchEmbedder is an optional interface that models may implement to embed
// multiple texts in a single call (more efficient than one-by-one).
type BatchEmbedder interface {
	EmbedBatch(ctx context.Context, texts []string) ([][]float64, error)
}

// ModelConfig holds configuration for constructing a model runtime.
type ModelConfig struct {
	// Provider selects the backend: "stub", "remote", or "local".
	Provider string `json:"provider" yaml:"provider"`
	// RemoteURL is the base URL of a remote embedding service (provider=remote).
	RemoteURL string `json:"remote_url" yaml:"remote_url"`
	// RemoteAPIKey is an optional API key for the remote service.
	RemoteAPIKey string `json:"remote_api_key,omitempty" yaml:"remote_api_key,omitempty"`
	// Timeout for remote calls.
	Timeout time.Duration `json:"timeout,omitempty" yaml:"timeout,omitempty"`
	// Dimension is the expected embedding dimension (used by stub/local).
	Dimension int `json:"dimension,omitempty" yaml:"dimension,omitempty"`
}

// NewModel constructs an EmbeddingModel from a ModelConfig.
func NewModel(cfg ModelConfig) (EmbeddingModel, error) {
	switch strings.ToLower(cfg.Provider) {
	case "stub", "":
		return NewStubModel(cfg.Dimension), nil
	case "remote":
		if cfg.RemoteURL == "" {
			return nil, fmt.Errorf("remote_url is required for provider=remote")
		}
		return NewRemoteClient(cfg.RemoteURL, cfg.RemoteAPIKey, cfg.Timeout), nil
	case "local":
		return NewLocalModel("") // placeholder; not yet implemented
	default:
		return nil, fmt.Errorf("unknown model_runtime provider %q", cfg.Provider)
	}
}

// embedRequest is the request body sent to a remote embedding service.
type embedRequest struct {
	Input string `json:"input"`
}

// embedResponse is a common response shape for remote embedding services.
type embedResponse struct {
	Embedding []float64 `json:"embedding"`
	Data      []struct {
		Embedding []float64 `json:"embedding"`
	} `json:"data"`
}

// doEmbedRequest posts a single embed request to the given endpoint.
func doEmbedRequest(ctx context.Context, client *http.Client, endpoint, apiKey, text string) ([]float64, error) {
	reqBody, err := json.Marshal(embedRequest{Input: text})
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(string(reqBody)))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("remote embed failed: status %d: %s", resp.StatusCode, string(body))
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	var parsed embedResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, fmt.Errorf("unmarshal response: %w", err)
	}

	if len(parsed.Embedding) > 0 {
		return parsed.Embedding, nil
	}
	if len(parsed.Data) > 0 && len(parsed.Data[0].Embedding) > 0 {
		return parsed.Data[0].Embedding, nil
	}

	return nil, fmt.Errorf("no embedding in response")
}
