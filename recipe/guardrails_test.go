package recipe

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadGuardrailsSpec(t *testing.T) {
	spec, err := LoadGuardrailsSpec("../recipes/guardrails/default.yaml")
	if err != nil {
		t.Fatalf("LoadGuardrailsSpec() error = %v", err)
	}

	if !spec.Input.Enabled {
		t.Fatal("expected input guardrails to be enabled")
	}

	if spec.Input.OnError != "block" {
		t.Fatalf("expected onError=block, got %q", spec.Input.OnError)
	}

	if spec.Input.MaxInputLen != 10000 {
		t.Fatalf("expected max input length 10000, got %d", spec.Input.MaxInputLen)
	}

	if len(spec.Input.Detectors) != 3 {
		t.Fatalf("expected 3 detectors, got %d", len(spec.Input.Detectors))
	}
}

func TestGuardrailsSpecRejectsDuplicateDetectors(t *testing.T) {
	spec := GuardrailsSpec{
		Input: GuardrailsInputSpec{
			Enabled:     true,
			OnError:     "block",
			MaxInputLen: 10000,
			Detectors: []GuardrailEntry{
				{Type: "jailbreak", Enabled: true, OnViolation: "block"},
				{Type: "jailbreak", Enabled: true, OnViolation: "block"},
			},
		},
	}

	err := spec.Validate()
	if err == nil || !strings.Contains(err.Error(), "duplicate type") {
		t.Fatalf("expected duplicate detector error, got %v", err)
	}
}

func TestGuardrailsSpecRejectsUnknownDetector(t *testing.T) {
	spec := GuardrailsSpec{
		Input: GuardrailsInputSpec{
			Enabled:     true,
			OnError:     "block",
			MaxInputLen: 10000,
			Detectors: []GuardrailEntry{
				{Type: "unknown", Enabled: true, OnViolation: "block"},
			},
		},
	}

	if err := spec.Validate(); err == nil {
		t.Fatal("expected unsupported detector error")
	}
}

func TestGuardrailsSpecRejectsInvalidPIICategory(t *testing.T) {
	spec := GuardrailsSpec{
		Input: GuardrailsInputSpec{
			Enabled:     true,
			OnError:     "block",
			MaxInputLen: 10000,
			Detectors: []GuardrailEntry{
				{
					Type:        "pii",
					Enabled:     true,
					OnViolation: "block",
					Categories:  []string{"email", "secret-everything"},
				},
			},
		},
	}

	if err := spec.Validate(); err == nil {
		t.Fatal("expected unsupported PII category error")
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
	dir := t.TempDir()
	path := filepath.Join(dir, "wrong-kind.yaml")

	content := `apiVersion: agenyx.ai/v1alpha1
kind: GatewayRecipe
metadata:
  name: wrong-kind
spec:
  input:
    enabled: true
`
	if err := os.WriteFile(path, []byte(content), 0600); err != nil {
		t.Fatal(err)
	}

	if _, err := LoadGuardrailsSpec(path); err == nil {
		t.Fatal("expected wrong recipe kind error")
	}
}
