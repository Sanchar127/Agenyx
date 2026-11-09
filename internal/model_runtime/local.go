// Package model_runtime provides embedding model implementations for the
// Agenyx guardrails pipeline.
package model_runtime

import (
	"context"
	"fmt"
)

// LocalModel is a placeholder for a locally-loaded embedding model
// (e.g., sentence-transformers via CGO or a Go binding). Local model loading
// is intentionally not implemented yet; model_runtime will be built out
// separately as planned.
type LocalModel struct {
	path string
}

// NewLocalModel returns an error because local embedding models are not yet
// implemented. Use provider "stub" or "remote" instead.
func NewLocalModel(path string) (*LocalModel, error) {
	return nil, fmt.Errorf("local embedding model not yet implemented: %q", path)
}

// Embed always returns an error because LocalModel is not yet implemented.
func (m *LocalModel) Embed(ctx context.Context, text string) ([]float64, error) {
	return nil, fmt.Errorf("local embedding model not yet implemented")
}

var _ EmbeddingModel = (*LocalModel)(nil)
