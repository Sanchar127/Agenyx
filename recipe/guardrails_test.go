package recipe

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func validGuardrailsSpec() GuardrailsSpec {
	return GuardrailsSpec{
		Input: GuardrailsInputSpec{
			Enabled:     true,
			OnError:     GuardrailFailureBlock,
			MaxInputLen: 10000,
			Detectors: []GuardrailEntry{
				{
					Type:        "prompt-injection",
					Enabled:     true,
					Provider:    GuardrailProviderClassifier,
					OnViolation: GuardrailActionBlock,
				},
				{
					Type:        "jailbreak",
					Enabled:     true,
					Provider:    GuardrailProviderClassifier,
					OnViolation: GuardrailActionBlock,
				},
				{
					Type:        "pii",
					Enabled:     true,
					Provider:    GuardrailProviderPattern,
					OnViolation: GuardrailActionRedact,
					Categories:  []string{"email", "phone", "ip-address", "credit-card"},
				},
			},
		},
		Execution: GuardrailsExecutionSpec{
			TimeoutMS:           500,
			MaxConcurrentChecks: 32,
		},
		ModelRuntime: GuardrailsModelRuntimeSpec{
			Endpoint:  "${GUARDRAILS_MODEL_URL}",
			Protocol:  GuardrailProtocolHTTP,
			TimeoutMS: 300,
		},
		FailurePolicy: GuardrailsFailurePolicySpec{
			OnDetectorError: GuardrailFailureBlock,
			OnTimeout:       GuardrailFailureBlock,
		},
	}
}

func TestLoadGuardrailsSpec(t *testing.T) {
	spec, err := LoadGuardrailsSpec("../recipes/guardrails/default.yaml")
	if err != nil {
		t.Fatalf("LoadGuardrailsSpec() error = %v", err)
	}

	if !spec.Input.Enabled {
		t.Fatal("expected input guardrails to be enabled")
	}
	if spec.Input.OnError != GuardrailFailureBlock {
		t.Fatalf("input.onError = %q, want block", spec.Input.OnError)
	}
	if spec.Input.MaxInputLen != 10000 {
		t.Fatalf("max input length = %d, want 10000", spec.Input.MaxInputLen)
	}
	if len(spec.Input.Detectors) != 3 {
		t.Fatalf("detector count = %d, want 3", len(spec.Input.Detectors))
	}
	if spec.Execution.TimeoutMS != 500 {
		t.Fatalf("execution timeout = %d, want 500", spec.Execution.TimeoutMS)
	}
	if spec.Execution.MaxConcurrentChecks != 32 {
		t.Fatalf("max concurrent checks = %d, want 32", spec.Execution.MaxConcurrentChecks)
	}
	if spec.ModelRuntime.Protocol != GuardrailProtocolHTTP {
		t.Fatalf("model protocol = %q, want http", spec.ModelRuntime.Protocol)
	}
	if spec.FailurePolicy.OnDetectorError != GuardrailFailureBlock {
		t.Fatalf("detector error policy = %q, want block", spec.FailurePolicy.OnDetectorError)
	}
	if spec.FailurePolicy.OnTimeout != GuardrailFailureBlock {
		t.Fatalf("timeout policy = %q, want block", spec.FailurePolicy.OnTimeout)
	}
}

func TestGuardrailsSpecAcceptsValidConfiguration(t *testing.T) {
	if err := validGuardrailsSpec().Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestGuardrailsSpecRejectsDuplicateDetectors(t *testing.T) {
	spec := validGuardrailsSpec()
	spec.Input.Detectors = []GuardrailEntry{
		{Type: "jailbreak", Enabled: true, Provider: GuardrailProviderClassifier, OnViolation: GuardrailActionBlock},
		{Type: "jailbreak", Enabled: true, Provider: GuardrailProviderClassifier, OnViolation: GuardrailActionBlock},
	}

	if err := spec.Validate(); err == nil || !strings.Contains(err.Error(), "duplicate type") {
		t.Fatalf("expected duplicate detector error, got %v", err)
	}
}

func TestGuardrailsSpecRejectsUnknownDetector(t *testing.T) {
	spec := validGuardrailsSpec()
	spec.Input.Detectors = []GuardrailEntry{
		{Type: "unknown", Enabled: true, Provider: GuardrailProviderPattern, OnViolation: GuardrailActionBlock},
	}

	if err := spec.Validate(); err == nil || !strings.Contains(err.Error(), "unsupported") {
		t.Fatalf("expected unsupported detector error, got %v", err)
	}
}

func TestGuardrailsSpecRejectsInvalidPIICategory(t *testing.T) {
	spec := validGuardrailsSpec()
	spec.Input.Detectors = []GuardrailEntry{
		{
			Type:        "pii",
			Enabled:     true,
			Provider:    GuardrailProviderPattern,
			OnViolation: GuardrailActionRedact,
			Categories:  []string{"email", "secret-everything"},
		},
	}

	if err := spec.Validate(); err == nil || !strings.Contains(err.Error(), "unsupported pii category") {
		t.Fatalf("expected unsupported PII category error, got %v", err)
	}
}

func TestGuardrailsSpecRejectsInvalidExecutionSettings(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*GuardrailsSpec)
		want   string
	}{
		{
			name: "zero timeout",
			mutate: func(s *GuardrailsSpec) {
				s.Execution.TimeoutMS = 0
			},
			want: "execution.timeoutMs",
		},
		{
			name: "negative timeout",
			mutate: func(s *GuardrailsSpec) {
				s.Execution.TimeoutMS = -1
			},
			want: "execution.timeoutMs",
		},
		{
			name: "zero concurrency",
			mutate: func(s *GuardrailsSpec) {
				s.Execution.MaxConcurrentChecks = 0
			},
			want: "execution.maxConcurrentChecks",
		},
		{
			name: "negative concurrency",
			mutate: func(s *GuardrailsSpec) {
				s.Execution.MaxConcurrentChecks = -1
			},
			want: "execution.maxConcurrentChecks",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			spec := validGuardrailsSpec()
			tt.mutate(&spec)

			err := spec.Validate()
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Validate() error = %v, want error containing %q", err, tt.want)
			}
		})
	}
}

func TestGuardrailsSpecRejectsInvalidFailurePolicy(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*GuardrailsSpec)
		want   string
	}{
		{
			name: "detector error",
			mutate: func(s *GuardrailsSpec) {
				s.FailurePolicy.OnDetectorError = "ignore"
			},
			want: "failurePolicy.onDetectorError",
		},
		{
			name: "timeout",
			mutate: func(s *GuardrailsSpec) {
				s.FailurePolicy.OnTimeout = "retry-forever"
			},
			want: "failurePolicy.onTimeout",
		},
		{
			name: "legacy input error",
			mutate: func(s *GuardrailsSpec) {
				s.Input.OnError = "ignore"
			},
			want: "input.onError",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			spec := validGuardrailsSpec()
			tt.mutate(&spec)

			err := spec.Validate()
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Validate() error = %v, want error containing %q", err, tt.want)
			}
		})
	}
}

func TestGuardrailsSpecRejectsInvalidModelRuntime(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*GuardrailsSpec)
		want   string
	}{
		{
			name: "missing endpoint",
			mutate: func(s *GuardrailsSpec) {
				s.ModelRuntime.Endpoint = ""
			},
			want: "modelRuntime.endpoint",
		},
		{
			name: "unsupported protocol",
			mutate: func(s *GuardrailsSpec) {
				s.ModelRuntime.Protocol = "ftp"
			},
			want: "modelRuntime.protocol",
		},
		{
			name: "nonpositive timeout",
			mutate: func(s *GuardrailsSpec) {
				s.ModelRuntime.TimeoutMS = 0
			},
			want: "modelRuntime.timeoutMs",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			spec := validGuardrailsSpec()
			tt.mutate(&spec)

			err := spec.Validate()
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Validate() error = %v, want error containing %q", err, tt.want)
			}
		})
	}
}

func TestGuardrailsSpecRejectsUnsupportedProvider(t *testing.T) {
	spec := validGuardrailsSpec()
	spec.Input.Detectors[0].Provider = "magic"

	if err := spec.Validate(); err == nil || !strings.Contains(err.Error(), "provider") {
		t.Fatalf("expected unsupported provider error, got %v", err)
	}
}

func TestGuardrailsSpecRejectsRedactionForNonPIIDetector(t *testing.T) {
	spec := validGuardrailsSpec()
	spec.Input.Detectors[0].OnViolation = GuardrailActionRedact

	if err := spec.Validate(); err == nil || !strings.Contains(err.Error(), "only supported for pii") {
		t.Fatalf("expected invalid redaction action error, got %v", err)
	}
}

func TestGuardrailsSpecAllowsDisabledInputStage(t *testing.T) {
	spec := GuardrailsSpec{
		Input: GuardrailsInputSpec{
			Enabled: false,
		},
	}

	if err := spec.Validate(); err != nil {
		t.Fatalf("disabled input stage should be valid, got %v", err)
	}
}

func TestLoadGuardrailsSpecRejectsWrongKind(t *testing.T) {
	path := writeGuardrailsRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: GatewayRecipe
metadata:
  name: wrong-kind
spec:
  input:
    enabled: true
`)

	if _, err := LoadGuardrailsSpec(path); err == nil {
		t.Fatal("expected wrong recipe kind error")
	}
}

func TestLoadGuardrailsSpecRejectsUnknownSpecField(t *testing.T) {
	path := writeGuardrailsRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: GuardrailsRecipe
metadata:
  name: unknown-field
spec:
  input:
    enabled: false
  unexpected: true
`)

	if _, err := LoadGuardrailsSpec(path); err == nil {
		t.Fatal("expected unknown spec field error")
	}
}

func writeGuardrailsRecipe(t *testing.T, content string) string {
	t.Helper()

	path := filepath.Join(t.TempDir(), "recipe.yaml")
	if err := os.WriteFile(path, []byte(content), 0600); err != nil {
		t.Fatalf("write recipe: %v", err)
	}
	return path
}
