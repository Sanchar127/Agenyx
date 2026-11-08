package guardrails

import "context"

// Provider is the interface every guardrail provider implements.
// Implementations must be stateless and safe for concurrent use.
type Provider interface {
	// Name returns a unique identifier for the provider.
	Name() string
	// Check evaluates the input text and returns a decision.
	// ctx is for cancellation/timeouts.
	Check(ctx context.Context, text string, opts ...CheckOption) (Result, error)
}

// CheckOption is a functional option for Check calls.
type CheckOption func(*checkOptions)

type checkOptions struct {
	metadata map[string]any
}

// WithMetadata adds arbitrary metadata to the check request.
func WithMetadata(k string, v any) CheckOption {
	return func(o *checkOptions) {
		if o.metadata == nil {
			o.metadata = make(map[string]any)
		}
		o.metadata[k] = v
	}
}

// WithContextValue is a convenience wrapper around WithMetadata.
func WithContextValue(k string, v any) CheckOption {
	return WithMetadata(k, v)
}
