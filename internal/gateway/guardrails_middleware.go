package gateway

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/sanchar127/agenyx/internal/guardrails"
	"github.com/sanchar127/agenyx/internal/model_runtime"
)

// guardrailsMiddleware runs input and output guardrails around agent
// execution requests. Input guardrails run before the agent/LLM; output
// guardrails run on the model's response before it reaches the client.
//
// Configuration is read from environment variables:
//   - AGENEYX_GUARDRAILS_ENABLED   (default: "false")
//   - AGENEYX_GUARDRAILS_FAIL_CLOSED (default: "true")
//   - AGENEYX_GUARDRAILS_KEYWORDS   (comma-separated blocked keywords)
//   - AGENEYX_GUARDRAILS_THRESHOLD  (default: "0.8")
//   - AGENEYX_GUARDRAILS_PII_THRESHOLD (default: "0.8")
//   - AGENEYX_GUARDRAILS_HALLUCINATION_THRESHOLD (default: "0.7")
//   - AGENEYX_GUARDRAILS_ENABLE_OUTPUT (default: "true")
//
// When guardrails are disabled or no providers are configured, the middleware
// is a no-op.
type guardrailsMiddleware struct {
	service     *guardrails.Service
	enabled     bool
	checkOutput bool
}

type responseCapture struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
}

func (rc *responseCapture) WriteHeader(status int) {
	rc.status = status
}

func (rc *responseCapture) Write(data []byte) (int, error) {
	if rc.status == 0 {
		rc.status = http.StatusOK
	}
	return rc.body.Write(data)
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

	// Hallucination provider (embedding-based, compares output vs context).
	hallThreshold := parseFloatEnv("AGENEYX_GUARDRAILS_HALLUCINATION_THRESHOLD", 0.7)
	embedModel := model_runtime.NewStubModel(384)
	hallucination, err := guardrails.NewHallucinationProvider("hallucination", embedModel, hallThreshold, guardrails.WithHallucinationCache(1000))
	if err != nil {
		return nil, err
	}
	providers = append(providers, hallucination)

	failClosed := parseBoolEnv("AGENEYX_GUARDRAILS_FAIL_CLOSED", true)
	checkOutput := parseBoolEnv("AGENEYX_GUARDRAILS_ENABLE_OUTPUT", true)

	return &guardrailsMiddleware{
		service:     guardrails.NewService(providers, failClosed),
		enabled:     true,
		checkOutput: checkOutput,
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
		// ---------- INPUT GUARDRAILS (before agent / LLM) ----------
		if isExecutionRoute(r) && r.Body != nil {
			body, err := io.ReadAll(r.Body)
			if err != nil {
				writeJSON(w, http.StatusBadRequest, map[string]string{
					"error": "failed to read request body",
				})
				return
			}

			// Extract the user query from common JSON shapes.
			query := extractQuery(body)
			if query != "" {
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
			}

			// Restore the body for downstream handlers.
			r.Body = io.NopCloser(strings.NewReader(string(body)))
		}

		// ---------- OUTPUT GUARDRAILS (after agent / LLM, before client) ----------
		recorder := &responseCapture{ResponseWriter: w}
		next.ServeHTTP(recorder, r)

		if m.checkOutput && isExecutionRoute(r) {
			contextText := extractRAGContext(r)
			outputText := recorder.body.String()

			result, err := m.service.CheckOutput(
				r.Context(),
				outputText,
				guardrails.WithRAGContext(contextText),
			)
			if err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]string{
					"error": "output guardrail check failed",
				})
				return
			}

			if guardrails.IsBlocked(result) {
				// Override the handler's response with a block.
				w.WriteHeader(http.StatusForbidden)
				writeJSON(w, http.StatusForbidden, map[string]string{
					"error":    "output blocked by guardrails",
					"reason":   result.Reason,
					"rule":     result.Rule,
					"decision": string(result.Decision),
				})
				return
			}
		}

		// Pass the captured response through to the client.
		for k, v := range recorder.Header() {
			w.Header()[k] = v
		}
		if recorder.status == 0 {
			recorder.status = http.StatusOK
		}
		w.WriteHeader(recorder.status)
		_, _ = w.Write(recorder.body.Bytes())
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

// extractRAGContext pulls the retrieval context from a request header or JSON
// body field so the hallucination provider can compare the output against it.
func extractRAGContext(r *http.Request) string {
	// Prefer the explicit header.
	if v := r.Header.Get("X-RAG-Context"); v != "" {
		return v
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
