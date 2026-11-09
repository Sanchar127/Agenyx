package guardrails

import (
	"context"
	"fmt"
)

// HallucinationProvider detects potential hallucinations by comparing the
// embedding of generated text against the embedding of source context using
// cosine similarity. If the best similarity between the text and any context
// passage is below the configured threshold, the text is considered
// unsupported (potentially hallucinated) and is blocked.
//
// Context is supplied via WithRAGContext. If no context is provided, the
// check is skipped (allow) because hallucination cannot be detected without
// source material to compare against.
type HallucinationProvider struct {
	name      string
	model     EmbeddingModel
	threshold float64
	cache     *embeddingCache
}

// HallucinationOption configures a HallucinationProvider.
type HallucinationOption func(*HallucinationProvider)

// NewHallucinationProvider creates a hallucination detection provider.
//
// Options:
//
//	WithEmbeddingCache(maxEntries)  cache embeddings by text
func NewHallucinationProvider(name string, model EmbeddingModel, threshold float64, opts ...HallucinationOption) (*HallucinationProvider, error) {
	if model == nil {
		return nil, fmt.Errorf("embedding model is required")
	}
	if threshold < 0.0 || threshold > 1.0 {
		return nil, fmt.Errorf("threshold must be between 0 and 1, got %f", threshold)
	}

	p := &HallucinationProvider{
		name:      name,
		model:     model,
		threshold: threshold,
	}

	for _, opt := range opts {
		opt(p)
	}

	return p, nil
}

// WithHallucinationCache enables an in-memory cache for embeddings, keyed by
// input text. maxEntries caps the number of cached vectors.
func WithHallucinationCache(maxEntries int) HallucinationOption {
	return func(p *HallucinationProvider) {
		p.cache = newEmbeddingCache(maxEntries)
	}
}

// Name returns the provider name.
func (p *HallucinationProvider) Name() string {
	return p.name
}

// Check compares the embedding of text (the generated answer) against the
// embedding of the RAG context passed via WithRAGContext. If the cosine
// similarity is below the threshold, returns DecisionBlock.
func (p *HallucinationProvider) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	o := &checkOptions{}
	for _, opt := range opts {
		opt(o)
	}

	contextText, _ := o.metadata["rag_context"].(string)

	answer, err := p.embed(ctx, text)
	if err != nil {
		return Result{}, fmt.Errorf("embedding answer failed: %w", err)
	}

	// No context means we cannot verify the answer; allow but note it.
	if contextText == "" {
		return Result{
			Decision: DecisionAllow,
			Score:    0.0,
			Reason:   "no RAG context provided; hallucination check skipped",
			Meta: map[string]any{
				"provider": p.name,
			},
		}, nil
	}

	ctxEmbedding, err := p.embed(ctx, contextText)
	if err != nil {
		return Result{}, fmt.Errorf("embedding context failed: %w", err)
	}

	score := cosineSimilarity(answer, ctxEmbedding)

	if score < p.threshold {
		return Result{
			Decision: DecisionBlock,
			Score:    score,
			Reason:   fmt.Sprintf("potential hallucination: answer not supported by context (similarity %.2f < threshold %.2f)", score, p.threshold),
			Rule:     "hallucination",
			Meta: map[string]any{
				"provider":   p.name,
				"similarity": score,
				"threshold":  p.threshold,
			},
		}, nil
	}

	return Result{
		Decision: DecisionAllow,
		Score:    score,
		Reason:   "answer supported by context",
		Meta: map[string]any{
			"provider":   p.name,
			"similarity": score,
			"threshold":  p.threshold,
		},
	}, nil
}

// embed returns the embedding for text, using the cache when enabled.
func (p *HallucinationProvider) embed(ctx context.Context, text string) ([]float64, error) {
	if p.cache != nil {
		if v, ok := p.cache.get(text); ok {
			return v, nil
		}
	}

	emb, err := p.model.Embed(ctx, text)
	if err != nil {
		return nil, err
	}

	if p.cache != nil {
		p.cache.set(text, emb)
	}
	return emb, nil
}
