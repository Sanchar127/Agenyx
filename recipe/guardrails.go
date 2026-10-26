package recipe

import (
	"fmt"
	"strings"
)

const GuardrailsRecipeKind = "GuardrailsRecipe"

const (
	GuardrailProviderPattern    = "pattern"
	GuardrailProviderClassifier = "classifier"

	GuardrailActionBlock  = "block"
	GuardrailActionWarn   = "warn"
	GuardrailActionRedact = "redact"
	GuardrailFailureAllow = "allow"
	GuardrailFailureBlock = "block"
	GuardrailProtocolHTTP = "http"
)

// GuardrailsSpec configures input guardrails before an agent processes a request.
// Output guardrails are intentionally outside this schema's initial scope.
type GuardrailsSpec struct {
	Input         GuardrailsInputSpec         `yaml:"input"`
	Execution     GuardrailsExecutionSpec     `yaml:"execution"`
	ModelRuntime  GuardrailsModelRuntimeSpec  `yaml:"modelRuntime"`
	FailurePolicy GuardrailsFailurePolicySpec `yaml:"failurePolicy"`
}

// GuardrailsInputSpec defines guardrails applied to incoming user input.
type GuardrailsInputSpec struct {
	Enabled bool `yaml:"enabled"`
	// OnError is the legacy input-stage error policy. Detector-specific errors
	// and timeouts are configured separately in GuardrailsFailurePolicySpec.
	OnError     string           `yaml:"onError"`
	MaxInputLen int              `yaml:"maxInputLength"`
	Detectors   []GuardrailEntry `yaml:"detectors"`
}

// GuardrailsExecutionSpec bounds input-guardrail execution.
type GuardrailsExecutionSpec struct {
	TimeoutMS           int `yaml:"timeoutMs"`
	MaxConcurrentChecks int `yaml:"maxConcurrentChecks"`
}

// GuardrailsModelRuntimeSpec configures the external Python model-serving runtime.
// Endpoint may contain an environment placeholder, such as ${GUARDRAILS_MODEL_URL};
// resolving placeholders is the responsibility of the runtime integration.
type GuardrailsModelRuntimeSpec struct {
	Endpoint  string `yaml:"endpoint"`
	Protocol  string `yaml:"protocol"`
	TimeoutMS int    `yaml:"timeoutMs"`
}

// GuardrailsFailurePolicySpec defines behavior when a detector fails or times out.
// "block" is fail-closed; "allow" is fail-open and must be chosen deliberately.
type GuardrailsFailurePolicySpec struct {
	OnDetectorError string `yaml:"onDetectorError"`
	OnTimeout       string `yaml:"onTimeout"`
}

// GuardrailEntry configures one input detector independently of its implementation.
type GuardrailEntry struct {
	Type        string   `yaml:"type"`
	Enabled     bool     `yaml:"enabled"`
	Provider    string   `yaml:"provider"`
	OnViolation string   `yaml:"onViolation"`
	Categories  []string `yaml:"categories,omitempty"`
	Patterns    []string `yaml:"patterns,omitempty"`
}

// LoadGuardrailsSpec loads and validates a GuardrailsRecipe.
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

// Validate checks the guardrails configuration without performing detection.
func (s GuardrailsSpec) Validate() error {
	if !s.Input.Enabled {
		// Preserve the existing contract: a disabled stage is valid and retains
		// its configuration so operators can disable enforcement temporarily.
		return nil
	}

	if s.Input.MaxInputLen <= 0 {
		return fmt.Errorf("input.maxInputLength must be greater than zero")
	}

	if !isFailureAction(s.Input.OnError) {
		return fmt.Errorf(
			"input.onError must be %q or %q",
			GuardrailFailureBlock,
			GuardrailFailureAllow,
		)
	}

	if s.Execution.TimeoutMS <= 0 {
		return fmt.Errorf("execution.timeoutMs must be greater than zero")
	}
	if s.Execution.MaxConcurrentChecks <= 0 {
		return fmt.Errorf("execution.maxConcurrentChecks must be greater than zero")
	}

	if !isFailureAction(s.FailurePolicy.OnDetectorError) {
		return fmt.Errorf(
			"failurePolicy.onDetectorError must be %q or %q",
			GuardrailFailureBlock,
			GuardrailFailureAllow,
		)
	}
	if !isFailureAction(s.FailurePolicy.OnTimeout) {
		return fmt.Errorf(
			"failurePolicy.onTimeout must be %q or %q",
			GuardrailFailureBlock,
			GuardrailFailureAllow,
		)
	}

	if len(s.Input.Detectors) == 0 {
		return fmt.Errorf("input.detectors must contain at least one detector")
	}

	seen := make(map[string]struct{}, len(s.Input.Detectors))
	requiresClassifier := false

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

		switch detector.Provider {
		case GuardrailProviderPattern:
		case GuardrailProviderClassifier:
			requiresClassifier = true
		default:
			return fmt.Errorf(
				"input.detectors[%d].provider must be %q or %q",
				i,
				GuardrailProviderPattern,
				GuardrailProviderClassifier,
			)
		}

		switch detector.OnViolation {
		case GuardrailActionBlock, GuardrailActionWarn:
		case GuardrailActionRedact:
			if detector.Type != "pii" {
				return fmt.Errorf(
					"input.detectors[%d].onViolation %q is only supported for pii",
					i,
					GuardrailActionRedact,
				)
			}
		default:
			return fmt.Errorf(
				"input.detectors[%d].onViolation must be %q, %q, or %q",
				i,
				GuardrailActionBlock,
				GuardrailActionWarn,
				GuardrailActionRedact,
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

	if requiresClassifier {
		if strings.TrimSpace(s.ModelRuntime.Endpoint) == "" {
			return fmt.Errorf(
				"modelRuntime.endpoint is required when an enabled detector uses provider %q",
				GuardrailProviderClassifier,
			)
		}
		if s.ModelRuntime.Protocol != GuardrailProtocolHTTP {
			return fmt.Errorf(
				"modelRuntime.protocol must be %q",
				GuardrailProtocolHTTP,
			)
		}
		if s.ModelRuntime.TimeoutMS <= 0 {
			return fmt.Errorf("modelRuntime.timeoutMs must be greater than zero")
		}
	}

	return nil
}

func isFailureAction(action string) bool {
	return action == GuardrailFailureBlock || action == GuardrailFailureAllow
}
