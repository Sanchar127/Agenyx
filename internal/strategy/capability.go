// Package strategy provides semantic routing strategies for model selection.
package strategy

import (
	"context"
	"strings"

	"github.com/sanchar127/agenyx/internal/registry"
	"github.com/sanchar127/agenyx/pkg/router"
)

// CapabilityStrategy ranks models according to required capabilities.
type CapabilityStrategy struct{}

// NewCapabilityStrategy creates a capability-based strategy.
func NewCapabilityStrategy() CapabilityStrategy {
	return CapabilityStrategy{}
}

// Name returns the strategy identifier.
func (CapabilityStrategy) Name() string {
	return "capability"
}

// Evaluate scores candidates according to their capability match against the requested task and capabilities.
func (CapabilityStrategy) Evaluate(
	ctx context.Context,
	request router.Request,
	candidates []router.Model,
) ([]router.CandidateScore, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}

	results := make([]router.CandidateScore, 0, len(candidates))

	required := request.Constraints.RequiredCapabilities

	for _, model := range candidates {
		if err := ctx.Err(); err != nil {
			return nil, err
		}

		if len(required) == 0 {
			results = append(results, router.CandidateScore{
				Model: model,
				Score: 0,
			})
			continue
		}

		matched := 0

		for _, capability := range required {
			if registry.SupportsCapability(model, capability) {
				matched++
			}
		}

		if matched == 0 {
			continue
		}

		score := float64(matched) / float64(len(required))

		results = append(results, router.CandidateScore{
			Model: model,
			Score: score,
		})
	}

	return results, nil
}

// CapabilityHint provides a lightweight classification signal for future
// semantic strategies. It intentionally performs no LLM inference.
func CapabilityHint(task string) string {
	task = strings.ToLower(strings.TrimSpace(task))

	switch {
	case strings.Contains(task, "code"),
		strings.Contains(task, "program"),
		strings.Contains(task, "golang"),
		strings.Contains(task, "python"):
		return "coding"

	case strings.Contains(task, "reason"),
		strings.Contains(task, "prove"),
		strings.Contains(task, "analyze"):
		return "reasoning"

	default:
		return "general"
	}
}
