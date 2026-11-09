package guardrails

import (
	"context"
	"sync"
	"testing"
)

type hallucinationCountingModel struct {
	delegate EmbeddingModel
	mu       sync.Mutex
	calls    int
}

func (m *hallucinationCountingModel) Embed(ctx context.Context, text string) ([]float64, error) {
	m.mu.Lock()
	m.calls++
	m.mu.Unlock()
	return m.delegate.Embed(ctx, text)
}

func (m *hallucinationCountingModel) Calls() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.calls
}

func TestHallucinationProviderName(t *testing.T) {
	model := &deterministicEmbeddingModel{vectors: map[string][]float64{}}
	p, err := NewHallucinationProvider("hallucination", model, 0.7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p.Name() != "hallucination" {
		t.Errorf("expected name 'hallucination', got %q", p.Name())
	}
}

func TestHallucinationProviderBlocksUnsupportedAnswer(t *testing.T) {
	answerVec := []float64{1.0, 0.0, 0.0}
	contextVec := []float64{0.0, 1.0, 0.0} // orthogonal -> similarity 0.0
	model := &deterministicEmbeddingModel{
		vectors: map[string][]float64{
			"The moon is made of green cheese": answerVec,
			"The moon is a rocky satellite":    contextVec,
		},
	}
	p, err := NewHallucinationProvider("hallucination", model, 0.7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	result, err := p.Check(context.Background(), "The moon is made of green cheese", WithRAGContext("The moon is a rocky satellite"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionBlock {
		t.Errorf("expected block for hallucinated answer, got %s", result.Decision)
	}
	if result.Rule != "hallucination" {
		t.Errorf("expected rule hallucination, got %s", result.Rule)
	}
	if result.Score != 0.0 {
		t.Errorf("expected score 0.0 for orthogonal vectors, got %f", result.Score)
	}
}

func TestHallucinationProviderAllowsSupportedAnswer(t *testing.T) {
	supportedVec := []float64{1.0, 0.0, 0.0}
	model := &deterministicEmbeddingModel{
		vectors: map[string][]float64{
			"The capital of France is Paris": supportedVec,
			"Paris is the capital of France": supportedVec,
		},
	}
	p, err := NewHallucinationProvider("hallucination", model, 0.7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	result, err := p.Check(context.Background(), "The capital of France is Paris", WithRAGContext("Paris is the capital of France"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow for supported answer, got %s", result.Decision)
	}
	if result.Score < 0.7 {
		t.Errorf("expected score >= 0.7, got %f", result.Score)
	}
}

func TestHallucinationProviderAllowsWithoutContext(t *testing.T) {
	model := &deterministicEmbeddingModel{vectors: map[string][]float64{}}
	p, err := NewHallucinationProvider("hallucination", model, 0.7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	result, err := p.Check(context.Background(), "any text at all")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow when no context provided, got %s", result.Decision)
	}
}

func TestHallucinationProviderThresholdBoundary(t *testing.T) {
	identicalVec := []float64{1.0, 0.0}
	model := &deterministicEmbeddingModel{
		vectors: map[string][]float64{
			"answer text":  identicalVec,
			"context text": identicalVec,
		},
	}
	p, err := NewHallucinationProvider("hallucination", model, 1.0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// identical -> similarity 1.0 >= threshold 1.0 -> allow
	result, err := p.Check(context.Background(), "answer text", WithRAGContext("context text"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow at threshold 1.0 with identical vectors, got %s", result.Decision)
	}
}

func TestHallucinationProviderNilModelError(t *testing.T) {
	_, err := NewHallucinationProvider("hallucination", nil, 0.7)
	if err == nil {
		t.Fatal("expected error for nil embedding model")
	}
}

func TestHallucinationProviderInvalidThreshold(t *testing.T) {
	model := &deterministicEmbeddingModel{vectors: map[string][]float64{}}
	_, err := NewHallucinationProvider("hallucination", model, 1.5)
	if err == nil {
		t.Fatal("expected error for threshold > 1")
	}
	_, err = NewHallucinationProvider("hallucination", model, -0.1)
	if err == nil {
		t.Fatal("expected error for threshold < 0")
	}
}

func TestHallucinationProviderCacheAvoidsReEmbedding(t *testing.T) {
	base := &deterministicEmbeddingModel{
		vectors: map[string][]float64{
			"The capital of France is Paris": []float64{1.0, 0.0, 0.0},
			"Paris is the capital of France": []float64{1.0, 0.0, 0.0},
		},
	}
	model := &hallucinationCountingModel{delegate: base}

	p, err := NewHallucinationProvider("hallucination", model, 0.7, WithHallucinationCache(100))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if _, err := p.Check(context.Background(), "The capital of France is Paris", WithRAGContext("Paris is the capital of France")); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// 2 calls: one for answer, one for context
	if model.Calls() != 2 {
		t.Fatalf("expected 2 embed calls after first check, got %d", model.Calls())
	}

	// Same texts again -> cache hit, no new calls
	if _, err := p.Check(context.Background(), "The capital of France is Paris", WithRAGContext("Paris is the capital of France")); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if model.Calls() != 2 {
		t.Errorf("expected embed calls to stay at 2 due to cache, got %d", model.Calls())
	}
}

func TestHallucinationProviderProviderErrorPropagates(t *testing.T) {
	model := &failingEmbeddingModel{failOn: "anything"}
	p, err := NewHallucinationProvider("hallucination", model, 0.7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	_, err = p.Check(context.Background(), "anything")
	if err == nil {
		t.Fatal("expected error from failing model to propagate")
	}
}
