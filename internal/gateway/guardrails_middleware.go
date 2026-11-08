package gateway

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/sanchar127/agenyx/internal/guardrails"
)

// guardrailsMiddleware runs input guardrails before a request reaches the
// agent/LLM. It only applies to agent execution routes; all other routes pass
// through unchanged.
//
// Configuration is read from environment variables:
//   - AGENEYX_GUARDRAILS_ENABLED   (default: "false")
//   - AGENEYX_GUARDRAILS_FAIL_CLOSED (default: "true")
//   - AGENEYX_GUARDRAILS_KEYWORDS   (comma-separated blocked keywords)
//   - AGENEYX_GUARDRAILS_THRESHOLD  (default: "0.8")
//
// When guardrails are disabled or no providers are configured, the middleware
// is a no-op.
type guardrailsMiddleware struct {
	service *guardrails.Service
	enabled bool
}

func newGuardrailsMiddlewareFromEnv() (*guardrailsMiddleware, error) {
	enabled := parseBoolEnv("AGENEYX_GUARDRAILS_ENABLED", false)
	if !enabled {
		return &guardrailsMiddleware{enabled: false}, nil
	}

	providers := []guardrails.Provider{}

	// Keyword provider from comma-separated env list.
	keywords := splitEnv("AGENEYX_GUARDRAILS_KEYWORDS", []string{
		"ignore previous instructions",
		"system prompt",
	})
	if len(keywords) > 0 {
		threshold := parseFloatEnv("AGENEYX_GUARDRAILS_THRESHOLD", 0.8)
		providers = append(providers,
			guardrails.NewKeywordProvider("blocked_words", keywords, threshold),
		)
	}

	// PII provider with sensible defaults.
	piiThreshold := parseFloatEnv("AGENEYX_GUARDRAILS_PII_THRESHOLD", 0.8)
	pii, err := guardrails.NewPIIProvider("pii", map[string]string{
		"email": `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`,
		"ssn":   `\b\d{3}-?\d{2}-?\d{4}\b`,
		"phone": `\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b`,
	}, piiThreshold)
	if err != nil {
		return nil, err
	}
	providers = append(providers, pii)

	failClosed := parseBoolEnv("AGENEYX_GUARDRAILS_FAIL_CLOSED", true)

	return &guardrailsMiddleware{
		service: guardrails.NewService(providers, failClosed),
		enabled: true,
	}, nil
}

// isExecutionRoute reports whether the request targets an agent execution
// endpoint that should be guarded.
func isExecutionRoute(r *http.Request) bool {
	return r.Method == http.MethodPost &&
		strings.HasPrefix(r.URL.Path, "/v1/agent/run")
}

func (m *guardrailsMiddleware) handle(next http.Handler) http.Handler {
	if !m.enabled || m.service == nil {
		return next
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Only guard agent execution requests with a body.
		if !isExecutionRoute(r) || r.Body == nil {
			next.ServeHTTP(w, r)
			return
		}

		body, err := io.ReadAll(r.Body)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "failed to read request body",
			})
			return
		}

		// Extract the user query from common JSON shapes:
		//   {"query": "..."}   or   {"input": "..."}   or   {"text": "..."}
		query := extractQuery(body)
		if query == "" {
			// No user-facing text to guard; pass through.
			next.ServeHTTP(w, r)
			return
		}

		result, err := m.service.CheckInput(r.Context(), query)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "guardrail check failed",
			})
			return
		}

		if guardrails.IsBlocked(result) {
			writeJSON(w, http.StatusForbidden, map[string]string{
				"error":    "request blocked by guardrails",
				"reason":   result.Reason,
				"rule":     result.Rule,
				"decision": string(result.Decision),
			})
			return
		}

		// Restore the body for downstream handlers.
		r.Body = io.NopCloser(strings.NewReader(string(body)))
		next.ServeHTTP(w, r)
	})
}

// extractQuery pulls a free-text field out of a JSON request body.
func extractQuery(body []byte) string {
	var raw map[string]any
	if err := json.Unmarshal(body, &raw); err != nil {
		return ""
	}
	for _, key := range []string{"query", "input", "text", "prompt", "message"} {
		if v, ok := raw[key]; ok {
			if s, ok := v.(string); ok && s != "" {
				return s
			}
		}
	}
	return ""
}

func parseBoolEnv(key string, def bool) bool {
	v := strings.TrimSpace(getEnv(key))
	if v == "" {
		return def
	}
	switch strings.ToLower(v) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return def
	}
}

func parseFloatEnv(key string, def float64) float64 {
	v := strings.TrimSpace(getEnv(key))
	if v == "" {
		return def
	}
	var f float64
	_, err := fmt.Sscanf(v, "%f", &f)
	if err != nil {
		return def
	}
	return f
}

func splitEnv(key string, def []string) []string {
	v := strings.TrimSpace(getEnv(key))
	if v == "" {
		return def
	}
	parts := strings.Split(v, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if s := strings.TrimSpace(p); s != "" {
			out = append(out, s)
		}
	}
	return out
}

func getEnv(key string) string {
	return strings.TrimSpace(os.Getenv(key))
}
