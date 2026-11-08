// Package model_runtime provides embedding model implementations for the
// Agenyx guardrails pipeline.
package model_runtime

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"math"
)

// StubModel is a deterministic, dependency-free embedding model.
// It hashes input text into a fixed-length, L2-normalized vector. Useful for
// development, tests, and as a fallback before a real model is wired into
// model_runtime. Identical inputs always produce identical embeddings.
type StubModel struct {
	dimension int
	seed      []byte
}

// NewStubModel creates a StubModel with the given vector dimension.
func NewStubModel(dimension int) *StubModel {
	if dimension <= 0 {
		dimension = 384
	}
	return &StubModel{
		dimension: dimension,
		seed:      []byte("agenyx-stub-embedding-v1"),
	}
}

// Embed returns a deterministic vector derived from a SHA-256 hash of the
// input text. The vector is L2-normalized so cosine similarity is meaningful.
func (m *StubModel) Embed(ctx context.Context, text string) ([]float64, error) {
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}

	h := sha256.New()
	h.Write(m.seed)
	h.Write([]byte{0})
	h.Write([]byte(text))
	sum := h.Sum(nil)

	vec := make([]float64, m.dimension)
	for i := 0; i < m.dimension; i++ {
		idx := (i * 2) % len(sum)
		val := binary.BigEndian.Uint16(sum[idx:])
		vec[i] = (float64(val)/65535.0)*2.0 - 1.0
	}

	norm := 0.0
	for _, v := range vec {
		norm += v * v
	}
	if norm == 0 {
		return vec, nil
	}
	invNorm := 1.0 / math.Sqrt(norm)
	for i := range vec {
		vec[i] *= invNorm
	}

	return vec, nil
}

// String returns a description of the model.
func (m *StubModel) String() string {
	return fmt.Sprintf("stub-embedding(dim=%d)", m.dimension)
}

var _ EmbeddingModel = (*StubModel)(nil)
