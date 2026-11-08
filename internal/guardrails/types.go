package guardrails

// Decision is the verdict returned by a guardrail provider.
type Decision string

const (
	// Allow means the content passed all checks and can proceed.
	DecisionAllow Decision = "allow"
	// Block means the content was rejected and must not reach the model.
	DecisionBlock Decision = "block"
	// Rewrite means the content should be modified before being sent.
	DecisionRewrite Decision = "rewrite"
)

// Result is the output of a single guardrail provider check.
type Result struct {
	Decision Decision `json:"decision"`
	Reason   string   `json:"reason,omitempty"`
	Score    float64  `json:"score,omitempty"` // confidence 0.0-1.0
	Rule     string   `json:"rule,omitempty"`  // which rule fired
	Meta     map[string]any
}

// Config holds configuration for a single guardrail provider.
type Config struct {
	Name      string         `json:"name"`
	Enabled   bool           `json:"enabled"`
	Threshold float64        `json:"threshold"` // 0.0-1.0, confidence threshold for block
	Params    map[string]any `json:"params,omitempty"`
}

// ServiceConfig is the top-level guardrail configuration.
type ServiceConfig struct {
	Enabled    bool     `json:"enabled"`
	FailClosed bool     `json:"fail_closed"` // if true, provider errors block the request
	Providers  []Config `json:"providers"`
}
