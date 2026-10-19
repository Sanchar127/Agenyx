package recipe

import (
	"fmt"
	"strings"
)

const GuardrailsRecipeKind = "GuardrailsRecipe"

// GuardrailsSpec configures input validation before an agent processes a request.
type GuardrailsSpec struct {
	Input GuardrailsInputSpec `yaml:"input"`
}

// GuardrailsInputSpec defines the guardrails applied to incoming user input.
type GuardrailsInputSpec struct {
	Enabled     bool             `yaml:"enabled"`
	OnError     string           `yaml:"onError"`
	MaxInputLen int              `yaml:"maxInputLength"`
	Detectors   []GuardrailEntry `yaml:"detectors"`
}

// GuardrailEntry configures one input detector.
type GuardrailEntry struct {
	Type        string   `yaml:"type"`
	Enabled     bool     `yaml:"enabled"`
	OnViolation string   `yaml:"onViolation"`
	Categories  []string `yaml:"categories,omitempty"`
	Patterns    []string `yaml:"patterns,omitempty"`
}

func LoadGuardrailsSpec(path string) (GuardrailsSpec, error) {
	doc, err := LoadFile(path)
	if err != nil {
		return GuardrailsSpec{}, err
	}

	if doc.Kind != GuardrailsRecipeKind {
		return GuardrailsSpec{}, fmt.Errorf(
			"expected recipe kind %q, got %q",
			GuardrailsRecipeKind,
			doc.Kind,
		)
	}

	var spec GuardrailsSpec
	if err := doc.DecodeSpec(&spec); err != nil {
		return GuardrailsSpec{}, err
	}

	if err := spec.Validate(); err != nil {
		return GuardrailsSpec{}, fmt.Errorf("validate guardrails recipe: %w", err)
	}

	return spec, nil
}

func (s GuardrailsSpec) Validate() error {
	if !s.Input.Enabled {
		// A disabled stage is valid; detector configuration is retained so
		// operators can disable enforcement without deleting their settings.
		return nil
	}

	if s.Input.MaxInputLen <= 0 {
		return fmt.Errorf("input.maxInputLength must be greater than zero")
	}

	if s.Input.OnError != "block" && s.Input.OnError != "allow" {
		return fmt.Errorf(
			"input.onError must be %q or %q",
			"block",
			"allow",
		)
	}

	if len(s.Input.Detectors) == 0 {
		return fmt.Errorf("input.detectors must contain at least one detector")
	}

	seen := make(map[string]struct{}, len(s.Input.Detectors))

	for i, detector := range s.Input.Detectors {
		detector.Type = strings.TrimSpace(detector.Type)

		switch detector.Type {
		case "prompt-injection", "jailbreak", "pii":
		default:
			return fmt.Errorf(
				"input.detectors[%d].type %q is unsupported",
				i,
				detector.Type,
			)
		}

		if _, exists := seen[detector.Type]; exists {
			return fmt.Errorf(
				"input.detectors contains duplicate type %q",
				detector.Type,
			)
		}
		seen[detector.Type] = struct{}{}

		if !detector.Enabled {
			continue
		}

		if detector.OnViolation != "block" &&
			detector.OnViolation != "warn" {
			return fmt.Errorf(
				"input.detectors[%d].onViolation must be %q or %q",
				i,
				"block",
				"warn",
			)
		}

		if detector.Type == "pii" {
			if len(detector.Categories) == 0 {
				return fmt.Errorf(
					"input.detectors[%d].categories must not be empty for pii",
					i,
				)
			}

			seenCategories := make(map[string]struct{}, len(detector.Categories))
			for _, category := range detector.Categories {
				category = strings.TrimSpace(category)
				switch category {
				case "email", "phone", "ip-address", "credit-card":
				default:
					return fmt.Errorf(
						"input.detectors[%d] has unsupported pii category %q",
						i,
						category,
					)
				}

				if _, exists := seenCategories[category]; exists {
					return fmt.Errorf(
						"input.detectors[%d] has duplicate pii category %q",
						i,
						category,
					)
				}
				seenCategories[category] = struct{}{}
			}
		}
	}

	return nil
}
