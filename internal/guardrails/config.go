package guardrails

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/sanchar127/agenyx/recipe"
)

const (
	// RecipeEnv selects the input guardrails recipe.
	RecipeEnv = "AGENEYX_GUARDRAILS_RECIPE"

	// DefaultRecipePath is the canonical input guardrails recipe path.
	DefaultRecipePath = "recipes/guardrails/input/default.yaml"
)

var envPlaceholder = regexp.MustCompile(`\$\{([A-Za-z_][A-Za-z0-9_]*)\}`)

// Config is the validated, effective input guardrails configuration.
//
// Its fields are private. Spec returns a deep copy so callers cannot mutate
// the stored configuration by modifying returned slices.
type Config struct {
	name    string
	version string
	path    string
	spec    recipe.GuardrailsSpec
}

// LoadFromEnv selects and loads the recipe using process environment variables.
func LoadFromEnv() (*Config, error) {
	path, err := ResolveRecipePath(
		os.Getenv(RecipeEnv),
		".",
	)
	if err != nil {
		return nil, err
	}

	return Load(path, os.LookupEnv)
}

// ResolveRecipePath applies explicit-path precedence.
//
// An explicit path is authoritative: if it does not exist, this function
// returns an error instead of silently falling back to a default recipe.
func ResolveRecipePath(explicitPath, workingDir string) (string, error) {
	explicitPath = strings.TrimSpace(explicitPath)
	if explicitPath != "" {
		info, err := os.Stat(explicitPath)
		if err != nil {
			return "", fmt.Errorf(
				"stat guardrails recipe selected by %s (%q): %w",
				RecipeEnv,
				explicitPath,
				err,
			)
		}
		if !info.Mode().IsRegular() {
			return "", fmt.Errorf(
				"guardrails recipe selected by %s is not a regular file: %q",
				RecipeEnv,
				explicitPath,
			)
		}
		return filepath.Clean(explicitPath), nil
	}

	candidates := []string{
		DefaultRecipePath,
		"../../" + DefaultRecipePath,

		// Compatibility with deployments that still use the original path.
		"recipes/guardrails/default.yaml",
		"../../recipes/guardrails/default.yaml",
	}

	for _, candidate := range candidates {
		path := candidate
		if !filepath.IsAbs(path) {
			path = filepath.Join(workingDir, path)
		}

		info, err := os.Stat(path)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return "", fmt.Errorf("inspect guardrails recipe %q: %w", path, err)
		}
		if info.Mode().IsRegular() {
			return filepath.Clean(path), nil
		}
	}

	return "", fmt.Errorf(
		"guardrails recipe not found; set %s to an existing recipe file",
		RecipeEnv,
	)
}

// Load reads a GuardrailsRecipe, resolves required environment placeholders,
// and validates the effective configuration before returning it.
//
// lookupEnv is injected to make environment resolution deterministic in tests.
// Pass os.LookupEnv in production.
func Load(
	path string,
	lookupEnv func(string) (string, bool),
) (*Config, error) {
	if strings.TrimSpace(path) == "" {
		return nil, fmt.Errorf("guardrails recipe path must not be empty")
	}
	if lookupEnv == nil {
		return nil, fmt.Errorf("guardrails environment lookup must not be nil")
	}

	doc, err := recipe.LoadFile(path)
	if err != nil {
		return nil, fmt.Errorf("load guardrails recipe %q: %w", path, err)
	}
	if doc.Kind != recipe.GuardrailsRecipeKind {
		return nil, fmt.Errorf(
			"load guardrails recipe %q: expected kind %q, got %q",
			path,
			recipe.GuardrailsRecipeKind,
			doc.Kind,
		)
	}

	var spec recipe.GuardrailsSpec
	if err := doc.DecodeSpec(&spec); err != nil {
		return nil, fmt.Errorf("decode guardrails recipe %q: %w", path, err)
	}

	if spec.Input.Enabled && requiresClassifier(spec) {
		endpoint, err := resolveRequiredEndpoint(
			spec.ModelRuntime.Endpoint,
			lookupEnv,
		)
		if err != nil {
			return nil, fmt.Errorf("resolve guardrails model endpoint: %w", err)
		}
		spec.ModelRuntime.Endpoint = endpoint
	}

	if err := spec.Validate(); err != nil {
		return nil, fmt.Errorf(
			"validate effective guardrails recipe %q: %w",
			path,
			err,
		)
	}

	return &Config{
		name:    doc.Metadata.Name,
		version: doc.Metadata.Version,
		path:    filepath.Clean(path),
		spec:    cloneSpec(spec),
	}, nil
}

// Name returns the recipe's metadata name.
func (c *Config) Name() string {
	return c.name
}

// Version returns the recipe's metadata version.
func (c *Config) Version() string {
	return c.version
}

// Path returns the selected recipe path.
func (c *Config) Path() string {
	return c.path
}

// Spec returns a deep copy of the effective configuration.
func (c *Config) Spec() recipe.GuardrailsSpec {
	return cloneSpec(c.spec)
}

func requiresClassifier(spec recipe.GuardrailsSpec) bool {
	for _, detector := range spec.Input.Detectors {
		if detector.Enabled && detector.Provider == recipe.GuardrailProviderClassifier {
			return true
		}
	}
	return false
}

func resolveRequiredEndpoint(
	endpoint string,
	lookupEnv func(string) (string, bool),
) (string, error) {
	endpoint = strings.TrimSpace(endpoint)
	if endpoint == "" {
		return "", fmt.Errorf("modelRuntime.endpoint must not be empty")
	}

	missing := ""
	resolved := envPlaceholder.ReplaceAllStringFunc(endpoint, func(placeholder string) string {
		match := envPlaceholder.FindStringSubmatch(placeholder)
		if len(match) != 2 {
			return placeholder
		}

		value, ok := lookupEnv(match[1])
		if !ok || strings.TrimSpace(value) == "" {
			missing = match[1]
			return placeholder
		}
		return strings.TrimSpace(value)
	})

	if missing != "" {
		return "", fmt.Errorf(
			"environment variable %s referenced by modelRuntime.endpoint is unset or empty",
			missing,
		)
	}
	if strings.Contains(resolved, "${") {
		return "", fmt.Errorf(
			"modelRuntime.endpoint contains an invalid or unresolved environment placeholder",
		)
	}
	if strings.TrimSpace(resolved) == "" {
		return "", fmt.Errorf("resolved modelRuntime.endpoint must not be empty")
	}

	return resolved, nil
}

func cloneSpec(spec recipe.GuardrailsSpec) recipe.GuardrailsSpec {
	cloned := spec
	cloned.Input.Detectors = make([]recipe.GuardrailEntry, len(spec.Input.Detectors))

	for i, detector := range spec.Input.Detectors {
		cloned.Input.Detectors[i] = detector
		cloned.Input.Detectors[i].Categories = append(
			[]string(nil),
			detector.Categories...,
		)
		cloned.Input.Detectors[i].Patterns = append(
			[]string(nil),
			detector.Patterns...,
		)
	}

	return cloned
}
