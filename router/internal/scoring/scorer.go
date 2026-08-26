// Package scoring provides deterministic model scoring components.
package scoring

import "github.com/sanchar127/agenyx/pkg/router"

// Scorer applies a deterministic adjustment to a strategy score.
type Scorer interface {
	Score(model router.Model, baseScore float64) float64
}

// PriorityScorer incorporates model priority into the strategy score.
type PriorityScorer struct {
	Weight float64
}

// NewPriorityScorer creates a priority-based scorer.
//
// A weight of zero disables priority influence.
func NewPriorityScorer(weight float64) PriorityScorer {
	return PriorityScorer{
		Weight: weight,
	}
}

// Score applies the priority adjustment to the base score.
func (s PriorityScorer) Score(
	model router.Model,
	baseScore float64,
) float64 {
	return baseScore + float64(model.Priority)*s.Weight
}
