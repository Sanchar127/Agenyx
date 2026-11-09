package guardrails

import (
	"context"
	"fmt"
	"strings"
)

// KeywordProvider checks text against a list of forbidden keywords.
// It performs case-insensitive substring matching.
type KeywordProvider struct {
	name      string
	keywords  []string
	threshold float64 // always 1.0 for exact keyword match
}

// NewKeywordProvider creates a keyword-based guardrail provider.
func NewKeywordProvider(name string, keywords []string, threshold float64) *KeywordProvider {
	return &KeywordProvider{
		name:      name,
		keywords:  keywords,
		threshold: threshold,
	}
}

// Name returns the provider name.
func (p *KeywordProvider) Name() string {
	return p.name
}

// Check scans the text for any of the configured keywords.
// Returns Block if any keyword is found, Allow otherwise.
func (p *KeywordProvider) Check(ctx context.Context, text string, opts ...CheckOption) (Result, error) {
	lowerText := strings.ToLower(text)

	for _, kw := range p.keywords {
		lowerKw := strings.ToLower(kw)
		if strings.Contains(lowerText, lowerKw) {
			return Result{
				Decision: DecisionBlock,
				Score:    1.0,
				Reason:   fmt.Sprintf("keyword match: %q", kw),
				Meta: map[string]any{
					"matched_keyword": kw,
					"provider":        p.name,
				},
			}, nil
		}
	}

	return Result{
		Decision: DecisionAllow,
		Score:    0.0,
		Reason:   "no keyword match",
		Meta: map[string]any{
			"provider": p.name,
		},
	}, nil
}
