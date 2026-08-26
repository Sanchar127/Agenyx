package router

import "context"

// CandidateScore is the score produced by a routing strategy.
type CandidateScore struct {
	Model Model
	Score float64
}

// Strategy evaluates eligible models for a request.
//
// Implementations must be safe for concurrent use and must not mutate
// the request or candidate models.
type Strategy interface {
	Name() string

	Evaluate(
		ctx context.Context,
		request Request,
		candidates []Model,
	) ([]CandidateScore, error)
}
