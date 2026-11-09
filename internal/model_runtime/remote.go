// Package model_runtime provides embedding model implementations for the
// Agenyx guardrails pipeline.
package model_runtime

import (
	"context"
	"net/http"
	"strings"
	"time"
)

// RemoteClient calls a remote embedding service over HTTP.
//
// Expected request: POST {baseURL}/embed  {"input": "text"}
// Expected response: {"embedding": [0.1, ...]} or {"data":[{"embedding":...}]}
type RemoteClient struct {
	endpoint   string
	apiKey     string
	httpClient *http.Client
}

// NewRemoteClient creates a RemoteClient. baseURL may or may not have a
// trailing slash. timeout defaults to 30 seconds if zero.
func NewRemoteClient(baseURL, apiKey string, timeout time.Duration) *RemoteClient {
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	baseURL = strings.TrimRight(baseURL, "/")
	return &RemoteClient{
		endpoint:   baseURL + "/embed",
		apiKey:     apiKey,
		httpClient: &http.Client{Timeout: timeout},
	}
}

// Embed sends a single text to the remote embedding service and returns its
// vector. ctx is used for cancellation and timeouts.
func (c *RemoteClient) Embed(ctx context.Context, text string) ([]float64, error) {
	return doEmbedRequest(ctx, c.httpClient, c.endpoint, c.apiKey, text)
}

// String returns a description of the client.
func (c *RemoteClient) String() string {
	return "remote-embedding(" + c.endpoint + ")"
}

var _ EmbeddingModel = (*RemoteClient)(nil)
