package guardrails

import (
	"context"
	"fmt"
)

// Manager orchestrates multiple guardrail providers.
// Providers run in parallel; the most severe decision wins.
type Manager struct {
	providers  []Provider
	failClosed bool
}

// NewManager creates a Guardrail Manager with the given providers.
func NewManager(providers []Provider, failClosed bool) *Manager {
	return &Manager{
		providers:  providers,
		failClosed: failClosed,
	}
}

// Check runs all providers in parallel and returns the most severe decision.
// Priority order: block > rewrite > allow.
// If any provider returns an error and failClosed is true, returns block.
func (m *Manager) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	if len(m.providers) == 0 {
		return Result{Decision: DecisionAllow}, nil
	}

	type result struct {
		provider string
		result   Result
		err      error
	}

	ch := make(chan result, len(m.providers))

	for _, p := range m.providers {
		go func(p Provider) {
			r, err := p.Check(ctx, text, opts...)
			ch <- result{provider: p.Name(), result: r, err: err}
		}(p)
	}

	var firstErr error
	results := make([]result, 0, len(m.providers))
	for i := 0; i < len(m.providers); i++ {
		r := <-ch
		if r.err != nil {
			firstErr = r.err
		}
		results = append(results, r)
	}

	// If any provider errored and failClosed, return block.
	if firstErr != nil && m.failClosed {
		return Result{
			Decision: DecisionBlock,
			Score:    1.0,
			Reason:   fmt.Sprintf("guardrail provider error: %v", firstErr),
		}, nil
	}

	// Merge results: block > rewrite > allow.
	final := Result{Decision: DecisionAllow}
	for _, r := range results {
		if r.err != nil {
			continue
		}
		if r.result.Decision == DecisionBlock {
			return r.result, nil // return first block with its reason
		}
		if r.result.Decision == DecisionRewrite && final.Decision != DecisionBlock {
			final = r.result
		}
		if r.result.Decision == DecisionAllow && final.Decision == DecisionAllow {
			// Keep first allow for metadata, but don't override a rewrite.
			if final.Decision == DecisionAllow && final.Score == 0 {
				final = r.result
			}
		}
	}

	return final, nil
}
