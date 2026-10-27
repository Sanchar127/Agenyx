package guardrails

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const validRecipeYAML = `
apiVersion: agenyx.ai/v1alpha1
kind: GuardrailsRecipe
metadata:
  name: test-input-guardrails
  version: "1.2.3"
spec:
  input:
    enabled: true
    onError: block
    maxInputLength: 10000
    detectors:
      - type: prompt-injection
        enabled: true
        provider: classifier
        onViolation: block
      - type: pii
        enabled: true
        provider: pattern
        onViolation: redact
        categories: [email, phone]
  execution:
    timeoutMs: 500
    maxConcurrentChecks: 32
  modelRuntime:
    endpoint: "${GUARDRAILS_MODEL_URL}"
    protocol: http
    timeoutMs: 300
  failurePolicy:
    onDetectorError: block
    onTimeout: block
`

func writeTestRecipe(t *testing.T, content string) string {
	t.Helper()

	path := filepath.Join(t.TempDir(), "guardrails.yaml")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write test recipe: %v", err)
	}
	return path
}

func TestLoadResolvesEndpointAndMetadata(t *testing.T) {
	path := writeTestRecipe(t, validRecipeYAML)

	config, err := Load(path, func(key string) (string, bool) {
		if key == "GUARDRAILS_MODEL_URL" {
			return "http://guardrails-model:8080", true
		}
		return "", false
	})
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if config.Name() != "test-input-guardrails" {
		t.Errorf("Name() = %q", config.Name())
	}
	if config.Version() != "1.2.3" {
		t.Errorf("Version() = %q", config.Version())
	}
	if config.Spec().ModelRuntime.Endpoint != "http://guardrails-model:8080" {
		t.Errorf("endpoint = %q", config.Spec().ModelRuntime.Endpoint)
	}
}

func TestLoadRejectsMissingRequiredEnvironmentVariable(t *testing.T) {
	path := writeTestRecipe(t, validRecipeYAML)

	_, err := Load(path, func(string) (string, bool) {
		return "", false
	})
	if err == nil || !strings.Contains(err.Error(), "GUARDRAILS_MODEL_URL") {
		t.Fatalf("expected missing environment variable error, got %v", err)
	}
}

func TestLoadRejectsEmptyRequiredEnvironmentVariable(t *testing.T) {
	path := writeTestRecipe(t, validRecipeYAML)

	_, err := Load(path, func(key string) (string, bool) {
		if key == "GUARDRAILS_MODEL_URL" {
			return "  ", true
		}
		return "", false
	})
	if err == nil || !strings.Contains(err.Error(), "GUARDRAILS_MODEL_URL") {
		t.Fatalf("expected empty environment variable error, got %v", err)
	}
}

func TestLoadRejectsInvalidRecipe(t *testing.T) {
	invalid := strings.Replace(
		validRecipeYAML,
		"maxInputLength: 10000",
		"maxInputLength: 0",
		1,
	)
	path := writeTestRecipe(t, invalid)

	_, err := Load(path, func(string) (string, bool) {
		return "http://guardrails-model:8080", true
	})
	if err == nil || !strings.Contains(err.Error(), "maxInputLength") {
		t.Fatalf("expected validation error, got %v", err)
	}
}

func TestLoadRejectsWrongRecipeKind(t *testing.T) {
	wrongKind := strings.Replace(
		validRecipeYAML,
		"kind: GuardrailsRecipe",
		"kind: GatewayRecipe",
		1,
	)
	path := writeTestRecipe(t, wrongKind)

	_, err := Load(path, func(string) (string, bool) {
		return "http://guardrails-model:8080", true
	})
	if err == nil || !strings.Contains(err.Error(), "expected kind") {
		t.Fatalf("expected wrong-kind error, got %v", err)
	}
}

func TestLoadRejectsMissingRecipe(t *testing.T) {
	_, err := Load(
		filepath.Join(t.TempDir(), "missing.yaml"),
		func(string) (string, bool) { return "", false },
	)
	if err == nil {
		t.Fatal("expected missing recipe error")
	}
}

func TestResolveRecipePathExplicitPathTakesPrecedence(t *testing.T) {
	explicit := writeTestRecipe(t, validRecipeYAML)

	got, err := ResolveRecipePath(explicit, t.TempDir())
	if err != nil {
		t.Fatalf("ResolveRecipePath() error = %v", err)
	}
	if got != explicit {
		t.Fatalf("resolved path = %q, want %q", got, explicit)
	}
}

func TestResolveRecipePathDoesNotFallbackForMissingExplicitPath(t *testing.T) {
	_, err := ResolveRecipePath(
		filepath.Join(t.TempDir(), "does-not-exist.yaml"),
		t.TempDir(),
	)
	if err == nil || !strings.Contains(err.Error(), RecipeEnv) {
		t.Fatalf("expected explicit-path error mentioning %s, got %v", RecipeEnv, err)
	}
}

func TestResolveRecipePathFindsDefault(t *testing.T) {
	root := t.TempDir()
	defaultPath := filepath.Join(root, DefaultRecipePath)

	if err := os.MkdirAll(filepath.Dir(defaultPath), 0o755); err != nil {
		t.Fatalf("create default recipe directory: %v", err)
	}
	if err := os.WriteFile(defaultPath, []byte(validRecipeYAML), 0o600); err != nil {
		t.Fatalf("write default recipe: %v", err)
	}

	got, err := ResolveRecipePath("", root)
	if err != nil {
		t.Fatalf("ResolveRecipePath() error = %v", err)
	}
	if got != defaultPath {
		t.Fatalf("resolved path = %q, want %q", got, defaultPath)
	}
}

func TestConfigSpecReturnsDeepCopy(t *testing.T) {
	path := writeTestRecipe(t, validRecipeYAML)

	config, err := Load(path, func(string) (string, bool) {
		return "http://guardrails-model:8080", true
	})
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	first := config.Spec()
	first.Input.Detectors[1].Categories[0] = "mutated"
	first.Input.Detectors[0].Patterns = []string{"mutated"}

	second := config.Spec()
	if second.Input.Detectors[1].Categories[0] != "email" {
		t.Fatalf("stored categories changed through returned spec: %v", second.Input.Detectors[1].Categories)
	}
	if len(second.Input.Detectors[0].Patterns) != 0 {
		t.Fatalf("stored patterns changed through returned spec: %v", second.Input.Detectors[0].Patterns)
	}
}

func TestLoadDefaultRecipe(t *testing.T) {
	config, err := Load(
		"../../recipes/guardrails/input/default.yaml",
		func(key string) (string, bool) {
			if key == "GUARDRAILS_MODEL_URL" {
				return "http://guardrails-model:8080", true
			}
			return "", false
		},
	)
	if err != nil {
		t.Fatalf("Load(default recipe) error = %v", err)
	}

	spec := config.Spec()
	if !spec.Input.Enabled {
		t.Fatal("expected input guardrails to be enabled")
	}
	if len(spec.Input.Detectors) != 3 {
		t.Fatalf("detector count = %d, want 3", len(spec.Input.Detectors))
	}
	if spec.ModelRuntime.Endpoint != "http://guardrails-model:8080" {
		t.Fatalf("endpoint was not resolved: %q", spec.ModelRuntime.Endpoint)
	}
}
