package guardrails

import (
	"context"
	"testing"
)

func TestKeywordProviderName(t *testing.T) {
	p := NewKeywordProvider("test_keywords", []string{"secret", "password"}, 0.8)
	if p.Name() != "test_keywords" {
		t.Errorf("expected name 'test_keywords', got %q", p.Name())
	}
}

func TestKeywordProviderBlocksKeyword(t *testing.T) {
	p := NewKeywordProvider("secrets", []string{"password", "secret", "token"}, 0.8)

	tests := []struct {
		name     string
		text     string
		wantBlock bool
	}{
		{"contains password", "my password is 123", true},
		{"contains secret", "this is a secret message", true},
		{"contains token", "my token is abc123", true},
		{"clean text", "hello world, how are you", false},
		{"case insensitive PASSWORD", "My PASSWORD is secret", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := p.Check(context.Background(), tt.text)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if tt.wantBlock && result.Decision != DecisionBlock {
				t.Errorf("expected block for text %q, got decision %s score=%.2f reason=%s",
					tt.text, result.Decision, result.Score, result.Reason)
			}
			if !tt.wantBlock && result.Decision != DecisionAllow {
				t.Errorf("expected allow for text %q, got decision %s score=%.2f reason=%s",
					tt.text, result.Decision, result.Score, result.Reason)
			}
		})
	}
}

func TestKeywordProviderEmptyText(t *testing.T) {
	p := NewKeywordProvider("test", []string{"secret"}, 0.8)
	result, err := p.Check(context.Background(), "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow for empty text, got %s", result.Decision)
	}
}

func TestPIIProviderName(t *testing.T) {
	p, err := NewPIIProvider("pii_detector", map[string]string{
		"email": `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`,
	}, 0.8)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p.Name() != "pii_detector" {
		t.Errorf("expected name 'pii_detector', got %q", p.Name())
	}
}

func TestPIIProviderDetectsEmail(t *testing.T) {
	p, err := NewPIIProvider("pii", map[string]string{
		"email": `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`,
	}, 0.8)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	result, err := p.Check(context.Background(), "Contact me at alice@example.com")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionBlock {
		t.Errorf("expected block for email, got %s", result.Decision)
	}
	if result.Score != 1.0 {
		t.Errorf("expected score 1.0, got %f", result.Score)
	}
}

func TestPIIProviderDetectsSSN(t *testing.T) {
	p, err := NewPIIProvider("pii", map[string]string{
		"ssn": `\b\d{3}-?\d{2}-?\d{4}\b`,
	}, 0.8)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	result, err := p.Check(context.Background(), "My SSN is 123-45-6789")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionBlock {
		t.Errorf("expected block for SSN, got %s", result.Decision)
	}
}

func TestPIIProviderAllowsCleanText(t *testing.T) {
	p, err := NewPIIProvider("pii", map[string]string{
		"email": `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`,
	}, 0.8)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	result, err := p.Check(context.Background(), "Hello world, this is clean text")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Decision != DecisionAllow {
		t.Errorf("expected allow, got %s", result.Decision)
	}
}

func TestPIIProviderInvalidRegex(t *testing.T) {
	_, err := NewPIIProvider("bad", map[string]string{
		"bad_regex": `[invalid`, // missing closing bracket
	}, 0.8)
	if err == nil {
		t.Fatal("expected error for invalid regex")
	}
}
