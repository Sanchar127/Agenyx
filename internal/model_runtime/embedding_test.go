package model_runtime

import (
	"context"
	"testing"
)

func TestStubModelDeterministic(t *testing.T) {
	m := NewStubModel(64)

	a, err := m.Embed(context.Background(), "hello world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	b, err := m.Embed(context.Background(), "hello world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(a) != 64 {
		t.Errorf("expected dimension 64, got %d", len(a))
	}
	if len(b) != 64 {
		t.Errorf("expected dimension 64, got %d", len(b))
	}
	for i := range a {
		if a[i] != b[i] {
			t.Errorf("embedding not deterministic at index %d", i)
		}
	}
}

func TestStubModelDifferentInputsDiffer(t *testing.T) {
	m := NewStubModel(64)

	a, err := m.Embed(context.Background(), "hello world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	b, err := m.Embed(context.Background(), "goodbye world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	same := true
	for i := range a {
		if a[i] != b[i] {
			same = false
			break
		}
	}
	if same {
		t.Error("expected different inputs to produce different embeddings")
	}
}

func TestStubModelL2Normalized(t *testing.T) {
	m := NewStubModel(128)

	vec, err := m.Embed(context.Background(), "normalize me")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var norm float64
	for _, v := range vec {
		norm += v * v
	}
	if norm < 0.999 || norm > 1.001 {
		t.Errorf("expected L2 norm ~1.0, got %f", norm)
	}
}

func TestStubModelDefaultDimension(t *testing.T) {
	m := NewStubModel(0)
	vec, err := m.Embed(context.Background(), "x")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(vec) != 384 {
		t.Errorf("expected default dimension 384, got %d", len(vec))
	}
}

func TestNewModelStub(t *testing.T) {
	m, err := NewModel(ModelConfig{Provider: "stub", Dimension: 16})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	_, err = m.Embed(context.Background(), "test")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestNewModelUnknownProvider(t *testing.T) {
	_, err := NewModel(ModelConfig{Provider: "nope"})
	if err == nil {
		t.Fatal("expected error for unknown provider")
	}
}

func TestNewModelRemoteMissingURL(t *testing.T) {
	_, err := NewModel(ModelConfig{Provider: "remote"})
	if err == nil {
		t.Fatal("expected error for remote without url")
	}
}

func TestContextCancellation(t *testing.T) {
	m := NewStubModel(16)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := m.Embed(ctx, "x")
	if err == nil {
		t.Error("expected error for cancelled context")
	}
}
