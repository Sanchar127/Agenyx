package gateway

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestNewRateLimiterValid(t *testing.T) {
	limiter, err := NewRateLimiter(10, 20)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if limiter.rate != 10 {
		t.Errorf("rate = %v, want %v", limiter.rate, 10)
	}
	if limiter.capacity != 20 {
		t.Errorf("capacity = %v, want %v", limiter.capacity, 20)
	}
	if limiter.buckets == nil {
		t.Error("buckets map should be initialized")
	}
}

func TestRateLimiterAllowRefillOverTime(t *testing.T) {
	// rate=1 token/sec, burst=1. After exhausting, need 1 second to refill.
	limiter, err := NewRateLimiter(1, 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Use the only token.
	if !limiter.allow("client-1") {
		t.Error("1st request should be allowed")
	}
	if limiter.allow("client-1") {
		t.Error("2nd request should be denied (bucket empty)")
	}

	// Wait ~1.5 seconds for full refill (1 token/sec).
	time.Sleep(1500 * time.Millisecond)

	if !limiter.allow("client-1") {
		t.Error("request after full refill should be allowed")
	}
	if limiter.allow("client-1") {
		t.Error("second immediate request should be denied")
	}
}

func TestRateLimiterTokensDoNotExceedCapacity(t *testing.T) {
	limiter, err := NewRateLimiter(1000, 1) // high rate, burst 1
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Use the only token.
	if !limiter.allow("client-1") {
		t.Error("1st request should be allowed")
	}

	// Wait a long time - tokens should cap at capacity (1), not accumulate.
	time.Sleep(2 * time.Second)

	if !limiter.allow("client-1") {
		t.Error("after long wait, 1 token should be available (capped at burst)")
	}
	if limiter.allow("client-1") {
		t.Error("2nd token should not be available (capped at burst=1)")
	}
}

func TestRateLimiterSeparateBucketsPerIP(t *testing.T) {
	limiter, err := NewRateLimiter(10, 2)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Exhaust client-1's bucket (burst=2).
	if !limiter.allow("client-1") {
		t.Error("client-1 1st request should be allowed")
	}
	if !limiter.allow("client-1") {
		t.Error("client-1 2nd request should be allowed")
	}

	// client-1 should be rate limited.
	if limiter.allow("client-1") {
		t.Error("client-1 should still be rate limited")
	}

	// client-2 should still have its own full bucket.
	if !limiter.allow("client-2") {
		t.Error("client-2 1st request should be allowed (separate bucket)")
	}
	if !limiter.allow("client-2") {
		t.Error("client-2 2nd request should be allowed (separate bucket)")
	}
	if limiter.allow("client-2") {
		t.Error("client-2 should be rate limited after burst")
	}
}

func TestRateLimiterAllowEmptyIP(t *testing.T) {
	limiter, err := NewRateLimiter(10, 5)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Empty string IP should work like any other IP.
	if !limiter.allow("") {
		t.Error("empty IP should be allowed")
	}
}

func TestRateLimiterMiddlewareReturns429WithRetryAfter(t *testing.T) {
	limiter, err := NewRateLimiter(10, 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	nextCalled := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		nextCalled = true
		w.WriteHeader(http.StatusOK)
	})

	handler := limiter.MiddlewareWithClientIP(func(r *http.Request) string {
		return "test-client"
	})(next)

	// First request should pass.
	req := httptest.NewRequest(http.MethodPost, "/v1/agent/run", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Errorf("first request status = %d, want %d", rec.Code, http.StatusOK)
	}
	if !nextCalled {
		t.Error("next handler should be called for first request")
	}

	// Second request should be rate limited.
	nextCalled = false
	req = httptest.NewRequest(http.MethodPost, "/v1/agent/run", nil)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusTooManyRequests {
		t.Errorf("second request status = %d, want %d; body = %s",
			rec.Code, http.StatusTooManyRequests, rec.Body.String())
	}
	if nextCalled {
		t.Error("next handler should NOT be called when rate limited")
	}
	if rec.Header().Get("Retry-After") != "1" {
		t.Errorf("Retry-After header = %q, want %q", rec.Header().Get("Retry-After"), "1")
	}
	if got := rec.Header().Get("Content-Type"); got != "application/json" {
		t.Errorf("Content-Type = %q, want %q", got, "application/json")
	}

	// Verify the error body is JSON.
	var body map[string]string
	if err := jsonBody(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("invalid JSON body: %v", err)
	}
	if body["error"] != "rate limit exceeded" {
		t.Errorf("error body = %q, want %q", body["error"], "rate limit exceeded")
	}
}

func TestRateLimiterMiddlewareSkipsNonRateLimitedPath(t *testing.T) {
	limiter, err := NewRateLimiter(10, 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	nextCalled := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		nextCalled = true
		w.WriteHeader(http.StatusOK)
	})

	handler := limiter.MiddlewareWithClientIP(func(r *http.Request) string {
		return "test-client"
	})(next)

	// Health endpoint should not be rate limited.
	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Errorf("health endpoint status = %d, want %d", rec.Code, http.StatusOK)
	}
	if !nextCalled {
		t.Error("next handler should be called for non-rate-limited path")
	}
}

func TestRateLimiterMiddlewareIncludesAuthRoutes(t *testing.T) {
	limiter, err := NewRateLimiter(10, 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	nextCalled := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		nextCalled = true
		w.WriteHeader(http.StatusOK)
	})

	handler := limiter.MiddlewareWithClientIP(func(r *http.Request) string {
		return "test-client"
	})(next)

	// /auth/ routes should be rate limited.
	req := httptest.NewRequest(http.MethodPost, "/auth/google/token", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Errorf("first /auth/ request status = %d, want %d", rec.Code, http.StatusOK)
	}

	nextCalled = false
	req = httptest.NewRequest(http.MethodPost, "/auth/google/token", nil)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusTooManyRequests {
		t.Errorf("second /auth/ request status = %d, want %d", rec.Code, http.StatusTooManyRequests)
	}
	if nextCalled {
		t.Error("next handler should NOT be called when rate limited on /auth/ route")
	}
}

// jsonBody parses a JSON response body into the given value.
func jsonBody(body []byte, v any) error {
	dec := json.NewDecoder(strings.NewReader(string(body)))
	return dec.Decode(v)
}
