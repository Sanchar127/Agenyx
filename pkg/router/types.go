package router

import "context"

// Message represents a single conversational message.
type Message struct {
	Role    string
	Content string
}

// Constraints restrict the set of models that may be selected.
type Constraints struct {
	RequiredCapabilities []string
	AllowedProviders     []string
	AllowedModels        []string
	MinContextWindow     int
}

// Request is the normalized input to the routing engine.
type Request struct {
	SessionID   string
	Messages    []Message
	Model       string
	Task        string
	Constraints Constraints
	Metadata    map[string]string
}

// Model describes an inference model known to the router.
type Model struct {
	Name          string
	Provider      string
	Capabilities  []string
	ContextWindow int
	Priority      int
	Enabled       bool
}

// Candidate represents a model considered during routing.
type Candidate struct {
	Model Model
	Score float64
}

// Decision is the final routing decision.
type Decision struct {
	Model      string
	Provider   string
	Score      float64
	Strategy   string
	Candidates []Candidate
}

// Router is the public routing interface.
type Router interface {
	Route(ctx context.Context, request Request) (Decision, error)
}
