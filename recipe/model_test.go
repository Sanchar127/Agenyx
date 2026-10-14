package recipe

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeRecipe(t *testing.T, content string) string {
	t.Helper()

	path := filepath.Join(t.TempDir(), "recipe.yaml")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write recipe: %v", err)
	}

	return path
}

func TestLoadFileValidGatewayRecipe(t *testing.T) {
	path := writeRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: GatewayRecipe
metadata:
  name: default-gateway
spec:
  rateLimit:
    requestsPerSecond: 10
    burst: 20
  request:
    maxBodyBytes: 1048576
`)

	doc, err := LoadFile(path)
	if err != nil {
		t.Fatalf("LoadFile() error = %v", err)
	}

	if doc.Kind != GatewayRecipeKind {
		t.Fatalf("kind = %q, want %q", doc.Kind, GatewayRecipeKind)
	}

	var spec GatewaySpec
	if err := doc.DecodeSpec(&spec); err != nil {
		t.Fatalf("DecodeSpec() error = %v", err)
	}

	if err := spec.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}

	if spec.RateLimit.RequestsPerSecond != 10 {
		t.Errorf(
			"requestsPerSecond = %d, want 10",
			spec.RateLimit.RequestsPerSecond,
		)
	}

	if spec.Request.MaxBodyBytes != 1048576 {
		t.Errorf(
			"maxBodyBytes = %d, want 1048576",
			spec.Request.MaxBodyBytes,
		)
	}
}

func TestLoadFileRejectsUnsupportedAPIVersion(t *testing.T) {
	path := writeRecipe(t, `
apiVersion: agenyx.ai/v99
kind: GatewayRecipe
metadata:
  name: invalid
spec:
  rateLimit: {}
`)

	_, err := LoadFile(path)
	if err == nil {
		t.Fatal("expected an error for unsupported API version")
	}
}

func TestLoadFileRejectsMissingName(t *testing.T) {
	path := writeRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: GatewayRecipe
metadata:
  name: ""
spec:
  rateLimit: {}
`)

	_, err := LoadFile(path)
	if err == nil {
		t.Fatal("expected an error for missing recipe name")
	}
}

func TestLoadFileRejectsUnknownTopLevelField(t *testing.T) {
	path := writeRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: GatewayRecipe
metadata:
  name: test
unexpectedField: true
spec:
  rateLimit: {}
`)

	_, err := LoadFile(path)
	if err == nil {
		t.Fatal("expected an error for an unknown top-level field")
	}
}

func TestDecodeSpecRejectsUnknownField(t *testing.T) {
	path := writeRecipe(t, `
apiVersion: agenyx.ai/v1alpha1
kind: GatewayRecipe
metadata:
  name: test
spec:
  rateLimit:
    requestsPerSecond: 10
    burst: 20
    unlimited: true
  request:
    maxBodyBytes: 1048576
`)

	doc, err := LoadFile(path)
	if err != nil {
		t.Fatalf("LoadFile() error = %v", err)
	}

	var spec GatewaySpec
	err = doc.DecodeSpec(&spec)
	if err == nil {
		t.Fatal("expected an error for an unknown spec field")
	}
	if !strings.Contains(err.Error(), "unlimited") {
		t.Fatalf("expected error to mention unknown field, got %v", err)
	}
}

func TestGatewaySpecRejectsInvalidLimits(t *testing.T) {
	tests := []struct {
		name string
		spec GatewaySpec
	}{
		{
			name: "zero rate",
			spec: GatewaySpec{
				RateLimit: GatewayRateLimitSpec{RequestsPerSecond: 0, Burst: 20},
				Request:   GatewayRequestSpec{MaxBodyBytes: 1024},
			},
		},
		{
			name: "zero burst",
			spec: GatewaySpec{
				RateLimit: GatewayRateLimitSpec{RequestsPerSecond: 10, Burst: 0},
				Request:   GatewayRequestSpec{MaxBodyBytes: 1024},
			},
		},
		{
			name: "zero body limit",
			spec: GatewaySpec{
				RateLimit: GatewayRateLimitSpec{RequestsPerSecond: 10, Burst: 20},
				Request:   GatewayRequestSpec{MaxBodyBytes: 0},
			},
		},
		{
			name: "excessive body limit",
			spec: GatewaySpec{
				RateLimit: GatewayRateLimitSpec{RequestsPerSecond: 10, Burst: 20},
				Request:   GatewayRequestSpec{MaxBodyBytes: 1 << 31},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := tt.spec.Validate(); err == nil {
				t.Fatal("expected validation error")
			}
		})
	}
}
