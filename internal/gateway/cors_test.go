package gateway

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func okHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
}

func TestCORSMiddlewarePreflightAllowedOrigin(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "http://localhost:3000")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(
		http.MethodOptions, "http://localhost:8443/auth/email/signup", nil,
	)
	req.Header.Set("Origin", "http://localhost:3000")
	req.Header.Set("Access-Control-Request-Method", http.MethodPost)
	req.Header.Set("Access-Control-Request-Headers", "content-type")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusNoContent)
	}

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://localhost:3000" {
		t.Errorf("Access-Control-Allow-Origin = %q, want %q", got, "http://localhost:3000")
	}
	if got := rec.Header().Get("Access-Control-Allow-Methods"); !strings.Contains(got, http.MethodPost) {
		t.Errorf("Access-Control-Allow-Methods = %q, want it to contain %q", got, http.MethodPost)
	}
	if got := rec.Header().Get("Access-Control-Allow-Headers"); !strings.Contains(got, "content-type") {
		t.Errorf("Access-Control-Allow-Headers = %q, want it to contain %q", got, "content-type")
	}
	if got := rec.Header().Get("Access-Control-Max-Age"); got != corsMaxAge {
		t.Errorf("Access-Control-Max-Age = %q, want %q", got, corsMaxAge)
	}
	if rec.Header().Get("Vary") != "Origin" {
		t.Errorf("Vary = %q, want %q", rec.Header().Get("Vary"), "Origin")
	}
	if rec.Body.Len() != 0 {
		t.Errorf("preflight body = %q, want empty", rec.Body.String())
	}
}

func TestCORSMiddlewarePreflightDisallowedOrigin(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "http://localhost:3000")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(
		http.MethodOptions, "http://localhost:8443/auth/email/signup", nil,
	)
	req.Header.Set("Origin", "http://evil.example.com")
	req.Header.Set("Access-Control-Request-Method", http.MethodPost)

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusNoContent)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("Access-Control-Allow-Origin = %q, want empty", got)
	}
}

func TestCORSMiddlewarePreflightNoOriginHeader(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "http://localhost:3000")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(
		http.MethodOptions, "http://localhost:8443/auth/email/signup", nil,
	)
	req.Header.Set("Access-Control-Request-Method", http.MethodPost)

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusNoContent)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("Access-Control-Allow-Origin = %q, want empty", got)
	}
}

func TestCORSMiddlewareActualRequestAllowedOrigin(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "http://localhost:3000")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("Origin", "http://localhost:3000")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://localhost:3000" {
		t.Errorf("Access-Control-Allow-Origin = %q, want %q", got, "http://localhost:3000")
	}
	if got := rec.Header().Get("Access-Control-Expose-Headers"); got != defaultExposedHeaders {
		t.Errorf("Access-Control-Expose-Headers = %q, want %q", got, defaultExposedHeaders)
	}
	if got := rec.Header().Get("Vary"); got != "Origin" {
		t.Errorf("Vary = %q, want %q", got, "Origin")
	}
}

func TestCORSMiddlewareActualRequestDisallowedOrigin(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "http://localhost:3000")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("Origin", "http://evil.example.com")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("Access-Control-Allow-Origin = %q, want empty", got)
	}
}

func TestCORSMiddlewareWildcardOrigin(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "*")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("Origin", "http://any.example.com")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Errorf("Access-Control-Allow-Origin = %q, want %q", got, "*")
	}
	if got := rec.Header().Get("Vary"); got != "" {
		t.Errorf("Vary = %q, want empty for wildcard", got)
	}
}

func TestCORSMiddlewareNoEnvironment(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("Origin", "http://localhost:3000")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("Access-Control-Allow-Origin = %q, want empty", got)
	}
}

func TestCORSMiddlewareNonPreflightOptionsPassesThrough(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "http://localhost:3000")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(http.MethodOptions, "/health/live", nil)
	req.Header.Set("Origin", "http://localhost:3000")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
}

func TestCORSMiddlewareCredentials(t *testing.T) {
	t.Setenv("AGENEYX_CORS_ORIGIN", "http://localhost:3000")
	t.Setenv("AGENEYX_CORS_ALLOW_CREDENTIALS", "true")

	handler := corsMiddleware(okHandler())

	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("Origin", "http://localhost:3000")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if got := rec.Header().Get("Access-Control-Allow-Credentials"); got != "true" {
		t.Errorf("Access-Control-Allow-Credentials = %q, want %q", got, "true")
	}
	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "http://localhost:3000" {
		t.Errorf("Access-Control-Allow-Origin = %q, want %q", got, "http://localhost:3000")
	}
}
