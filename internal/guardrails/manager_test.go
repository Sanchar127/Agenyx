package guardrails

import (
	"context"
	"errors"
	"testing"
)

// blockingProvider always returns block.
type blockingProvider struct {
	name string
}

func (p *blockingProvider) Name() string { return p.name }
func (p *blockingProvider) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	return Result{Decision: DecisionBlock, Score: 1.0, Reason: "blocked by " + p.name}, nil
}

// allowingProvider always returns allow.
type allowingProvider struct {
	name string
}

func (p *allowingProvider) Name() string { return p.name }
func (p *allowingProvider) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	return Result{Decision: DecisionAllow, Score: 0.0, Reason: "allowed by " + p.name}, nil
}

// failingProvider always returns an error.
type failingProvider struct {
	name string
}

func (p *failingProvider) Name() string { return p.name }
func (p *failingProvider) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	return Result{}, errProviderUnavailable
}

var errProviderUnavailable = errors.New("provider unavailable")

func TestManagerBlocksOnAnyBlockProvider(t *testing.T) {
	m := NewManager([]Provider{
		&allowingProvider{name: "allow1"},
		&blockingProvider{name: "blocker"},
		&allowingProvider{name: "allow2"},
	}, true)

	result, err := m.Check(context.Background(), "some text")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionBlock {
		t.Errorf("expected block, got %s", result.Decision)
	}
	if result.Score != 1.0 {
		t.Errorf("expected score 1.0, got %f", result.Score)
	}
}

func TestManagerAllowsWhenAllAllow(t *testing.T) {
	m := NewManager([]Provider{
		&allowingProvider{name: "allow1"},
		&allowingProvider{name: "allow2"},
	}, true)

	result, err := m.Check(context.Background(), "hello world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow, got %s", result.Decision)
	}
}

func TestManagerFailsClosedOnProviderError(t *testing.T) {
	m := NewManager([]Provider{
		&allowingProvider{name: "allow1"},
		&failingProvider{name: "broken"},
	}, true)

	result, err := m.Check(context.Background(), "test")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionBlock {
		t.Errorf("expected block on provider error with failClosed, got %s", result.Decision)
	}
}

func TestManagerAllowsOnProviderErrorWhenNotFailClosed(t *testing.T) {
	m := NewManager([]Provider{
		&allowingProvider{name: "allow1"},
		&failingProvider{name: "broken"},
	}, false)

	result, err := m.Check(context.Background(), "test")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow when failClosed=false, got %s", result.Decision)
	}
}

func TestManagerEmptyProvidersAllows(t *testing.T) {
	m := NewManager(nil, true)

	result, err := m.Check(context.Background(), "anything")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow with no providers, got %s", result.Decision)
	}
}
