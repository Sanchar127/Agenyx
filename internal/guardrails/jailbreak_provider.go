package guardrails

import (
	"context"
	"fmt"
	"math"
	"sync"
)

// EmbeddingModel converts text into a fixed-length vector embedding.
// Implementations must be stateless and safe for concurrent use.
// Concrete implementations live in internal/model_runtime (stub, remote,
// local) so guardrails remains standalone and dependency-light.
type EmbeddingModel interface {
	Embed(ctx context.Context, text string) ([]float64, error)
}

// BatchEmbedder is an optional interface that models may implement to embed
// multiple texts in a single call (more efficient than one-by-one).
type BatchEmbedder interface {
	EmbedBatch(ctx context.Context, texts []string) ([][]float64, error)
}

// SimilarityMetric selects the distance metric used by JailbreakProvider.
type SimilarityMetric string

const (
	// CosineSimilarity measures the cosine of the angle between vectors
	// (range [-1, 1], higher = more similar).
	CosineSimilarity SimilarityMetric = "cosine"
)

// embeddingCache is a bounded, thread-safe cache keyed by input text.
// When full, the oldest entry is evicted.
type embeddingCache struct {
	mu    sync.RWMutex
	items map[string][]float64
	max   int
	order []string // insertion order for FIFO eviction
}

func newEmbeddingCache(max int) *embeddingCache {
	if max <= 0 {
		max = 1000
	}
	return &embeddingCache{
		items: make(map[string][]float64, max),
		max:   max,
	}
}

func (c *embeddingCache) get(key string) ([]float64, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	v, ok := c.items[key]
	return v, ok
}

func (c *embeddingCache) set(key string, value []float64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if _, exists := c.items[key]; exists {
		c.items[key] = value
		return
	}
	if len(c.items) >= c.max {
		// FIFO eviction of the oldest entry.
		for len(c.order) > 0 {
			oldest := c.order[0]
			c.order = c.order[1:]
			if _, ok := c.items[oldest]; ok {
				delete(c.items, oldest)
				break
			}
		}
	}
	c.items[key] = value
	c.order = append(c.order, key)
}

// JailbreakOption configures a JailbreakProvider.
type JailbreakOption func(*JailbreakProvider)

// WithEmbeddingCache enables an in-memory cache for embeddings, keyed by
// input text. maxEntries caps the number of cached vectors.
func WithEmbeddingCache(maxEntries int) JailbreakOption {
	return func(p *JailbreakProvider) {
		p.cache = newEmbeddingCache(maxEntries)
	}
}

// WithSimilarityMetric sets the distance metric (default CosineSimilarity).
func WithSimilarityMetric(metric SimilarityMetric) JailbreakOption {
	return func(p *JailbreakProvider) {
		p.metric = metric
	}
}

// JailbreakProvider detects jailbreak attempts by comparing the embedding of
// the input text against a reference set of known jailbreak embeddings using
// a similarity metric. If the best similarity meets or exceeds the configured
// threshold, the input is blocked.
//
// Providers run in CheckInput (before the agent/LLM). Provider errors
// propagate; the Manager's failClosed mode decides whether they block the
// request.
type JailbreakProvider struct {
	name            string
	model           EmbeddingModel
	threshold       float64
	metric          SimilarityMetric
	references      [][]float64
	referenceLabels []string
	cache           *embeddingCache
}

// NewJailbreakProvider creates a jailbreak detection provider. It embeds the
// provided reference jailbreak examples at construction time so that Check
// only needs to embed the incoming text and compare.
//
// Options:
//
//	WithEmbeddingCache(maxEntries)  cache embeddings by input text
//	WithSimilarityMetric(metric)    similarity metric (default cosine)
func NewJailbreakProvider(name string, model EmbeddingModel, jailbreakExamples []string, threshold float64, opts ...JailbreakOption) (*JailbreakProvider, error) {
	if model == nil {
		return nil, fmt.Errorf("embedding model is required")
	}
	if len(jailbreakExamples) == 0 {
		return nil, fmt.Errorf("at least one jailbreak example is required")
	}

	references := make([][]float64, 0, len(jailbreakExamples))
	labels := make([]string, 0, len(jailbreakExamples))

	for _, example := range jailbreakExamples {
		emb, err := model.Embed(context.Background(), example)
		if err != nil {
			return nil, fmt.Errorf("failed to embed jailbreak example %q: %w", example, err)
		}
		references = append(references, emb)
		labels = append(labels, example)
	}

	p := &JailbreakProvider{
		name:            name,
		model:           model,
		threshold:       threshold,
		metric:          CosineSimilarity,
		references:      references,
		referenceLabels: labels,
	}

	for _, opt := range opts {
		opt(p)
	}

	return p, nil
}

// Name returns the provider name.
func (p *JailbreakProvider) Name() string {
	return p.name
}

// Check embeds the input text (using cache when enabled), computes the best
// similarity against the reference jailbreak embeddings, and returns Block
// when the best similarity is >= threshold. Otherwise it returns Allow.
//
// If the underlying model implements BatchEmbedder, Check still embeds a
// single text (batch is exposed for callers that want to pre-warm the cache).
func (p *JailbreakProvider) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	input, err := p.embed(ctx, text)
	if err != nil {
		return Result{}, fmt.Errorf("embedding failed: %w", err)
	}

	bestScore := 0.0
	bestLabel := ""

	for i, ref := range p.references {
		score := p.similarity(input, ref)
		if score > bestScore {
			bestScore = score
			bestLabel = p.referenceLabels[i]
		}
	}

	if bestScore >= p.threshold {
		return Result{
			Decision: DecisionBlock,
			Score:    bestScore,
			Reason:   fmt.Sprintf("jailbreak detected (similarity %.2f to %q)", bestScore, bestLabel),
			Rule:     "embedding_jailbreak",
			Meta: map[string]any{
				"provider":        p.name,
				"matched_example": bestLabel,
				"similarity":      bestScore,
				"threshold":       p.threshold,
				"metric":          p.metric,
			},
		}, nil
	}

	return Result{
		Decision: DecisionAllow,
		Score:    bestScore,
		Reason:   "no jailbreak signal detected",
		Meta: map[string]any{
			"provider":   p.name,
			"similarity": bestScore,
			"threshold":  p.threshold,
			"metric":     p.metric,
		},
	}, nil
}

// embed returns the embedding for text, using the cache when enabled.
func (p *JailbreakProvider) embed(ctx context.Context, text string) ([]float64, error) {
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

// EmbedBatch embeds multiple texts using the model's batch capability when
// available, falling back to one-by-one otherwise. Results are written into
// the cache when enabled.
func (p *JailbreakProvider) EmbedBatch(ctx context.Context, texts []string) ([][]float64, error) {
	if batcher, ok := p.model.(BatchEmbedder); ok {
		return batcher.EmbedBatch(ctx, texts)
	}

	results := make([][]float64, 0, len(texts))
	for _, t := range texts {
		e, err := p.embed(ctx, t)
		if err != nil {
			return results, err
		}
		results = append(results, e)
	}
	return results, nil
}

// similarity computes the similarity between two vectors according to p.metric.
func (p *JailbreakProvider) similarity(a, b []float64) float64 {
	switch p.metric {
	case CosineSimilarity:
		return cosineSimilarity(a, b)
	default:
		return cosineSimilarity(a, b)
	}
}

// cosineSimilarity returns the cosine similarity between two vectors.
// It returns 0.0 when either vector is empty, when lengths differ, or when
// either vector has zero norm.
func cosineSimilarity(a, b []float64) float64 {
	if len(a) == 0 || len(b) == 0 || len(a) != len(b) {
		return 0.0
	}

	var dot, normA, normB float64
	for i := range a {
		dot += a[i] * b[i]
		normA += a[i] * a[i]
		normB += b[i] * b[i]
	}

	if normA == 0 || normB == 0 {
		return 0.0
	}

	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}
