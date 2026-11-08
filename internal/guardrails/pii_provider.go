package guardrails

import (
	"context"
	"fmt"
	"regexp"
)

// PIIProvider detects personally identifiable information using regex patterns.
type PIIProvider struct {
	name      string
	patterns  []compiledPattern
	threshold float64
}

type compiledPattern struct {
	name  string
	regex *regexp.Regexp
}

// NewPIIProvider creates a PII detection provider with the given patterns.
func NewPIIProvider(name string, patterns map[string]string, threshold float64) (*PIIProvider, error) {
	p := &PIIProvider{
		name:      name,
		patterns:  make([]compiledPattern, 0, len(patterns)),
		threshold: threshold,
	}

	for name, pattern := range patterns {
		re, err := regexp.Compile(pattern)
		if err != nil {
			return nil, fmt.Errorf("invalid regex for pattern %q: %w", name, err)
		}
		p.patterns = append(p.patterns, compiledPattern{name: name, regex: re})
	}

	return p, nil
}

// Name returns the provider name.
func (p *PIIProvider) Name() string {
	return p.name
}

// Check scans the text for PII patterns. Returns Block if any pattern matches.
func (p *PIIProvider) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	for _, cp := range p.patterns {
		if cp.regex.MatchString(text) {
			return Result{
				Decision: DecisionBlock,
				Score:    1.0,
				Reason:   fmt.Sprintf("PII detected: %s", cp.name),
				Meta: map[string]any{
					"pattern_name": cp.name,
					"provider":     p.name,
				},
			}, nil
		}
	}

	return Result{
		Decision: DecisionAllow,
		Score:    0.0,
		Reason:   "no PII detected",
		Meta: map[string]any{
			"provider": p.name,
		},
	}, nil
}
