package guardrails

import "context"

// Service is a high-level RAG guardrail service that orchestrates
// multiple guardrail providers for input and output validation.
type Service struct {
	manager *Manager
}

// NewService creates a Guardrail Service from a list of providers.
func NewService(providers []Provider, failClosed bool) *Service {
	return &Service{
		manager: NewManager(providers, failClosed),
	}
}

// CheckInput runs input guardrails against user-provided text.
// Returns Block if any provider rejects the input.
func (s *Service) CheckInput(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	return s.manager.Check(ctx, text, opts...)
}

// CheckOutput runs output guardrails against model-generated text.
// Returns Block if any provider rejects the output.
func (s *Service) CheckOutput(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	return s.manager.Check(ctx, text, opts...)
}

// IsAllowed returns true if the result allows the text to pass.
func IsAllowed(r Result) bool {
	return r.Decision == DecisionAllow
}

// IsBlocked returns true if the result blocks the text.
func IsBlocked(r Result) bool {
	return r.Decision == DecisionBlock
}
