package router

import "context"

// Message represents a single conversational message.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Constraints restrict the set of models that may be selected.
type Constraints struct {
	RequiredCapabilities []string `json:"required_capabilities,omitempty"`
	AllowedProviders     []string `json:"allowed_providers,omitempty"`
	AllowedModels        []string `json:"allowed_models,omitempty"`
	MinContextWindow     int      `json:"min_context_window,omitempty"`
}

// Request is the normalized input to the routing engine.
type Request struct {
	SessionID   string            `json:"session_id,omitempty"`
	Messages    []Message         `json:"messages"`
	Model       string            `json:"model,omitempty"`
	Task        string            `json:"task,omitempty"`
	Constraints Constraints       `json:"constraints,omitempty"`
	Metadata    map[string]string `json:"metadata,omitempty"`
}

// Model describes an inference model known to the router.
type Model struct {
	Name          string   `json:"name"`
	Provider      string   `json:"provider"`
	Capabilities  []string `json:"capabilities"`
	ContextWindow int      `json:"context_window"`
	Priority      int      `json:"priority"`
	Enabled       bool     `json:"enabled"`
}

// Candidate represents a model considered during routing.
type Candidate struct {
	Model Model   `json:"model"`
	Score float64 `json:"score"`
}

// Decision is the final routing decision.
type Decision struct {
	Model      string      `json:"model"`
	Provider   string      `json:"provider"`
	Score      float64     `json:"score"`
	Strategy   string      `json:"strategy"`
	Candidates []Candidate `json:"candidates"`
}

// Router is the public routing interface.
type Router interface {
	Route(ctx context.Context, request Request) (Decision, error)
}
