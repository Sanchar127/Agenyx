package gateway

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"regexp"
	"sync"
	"testing"
	"time"
)

func TestRequestIDMiddleware(t *testing.T) {
	handler := requestIDMiddleware(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			id := r.Header.Get("X-Request-ID")
			if id == "" {
				t.Fatal("request ID missing from request")
			}
			w.WriteHeader(http.StatusOK)
		},
	))

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/", nil)

	handler.ServeHTTP(rec, req)

	id := rec.Header().Get("X-Request-ID")
	if !regexp.MustCompile(`^[0-9a-f]{32}$`).MatchString(id) {
		t.Fatalf("invalid request ID: %q", id)
	}
}

func TestSecurityHeadersMiddleware(t *testing.T) {
	handler := securityHeadersMiddleware(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
		},
	))

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/", nil)

	handler.ServeHTTP(rec, req)

	expected := map[string]string{
		"X-Content-Type-Options": "nosniff",
		"X-Frame-Options":        "DENY",
		"Referrer-Policy":        "no-referrer",
	}

	for header, want := range expected {
		if got := rec.Header().Get(header); got != want {
			t.Errorf("%s = %q, want %q", header, got, want)
		}
	}
}

func TestRateLimiterAllowsRequestsWithinLimit(t *testing.T) {
	limiter, err := NewRateLimiter(1, 1)
	if err != nil {
		t.Fatal(err)
	}

	handler := limiter.Middleware(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
		},
	))

	req := httptest.NewRequest(http.MethodPost, "/v1/agent/runs/test-execution", nil)

	first := httptest.NewRecorder()
	handler.ServeHTTP(first, req)

	if first.Code != http.StatusOK {
		t.Fatalf("first request status = %d, want %d",
			first.Code, http.StatusOK)
	}

	second := httptest.NewRecorder()
	handler.ServeHTTP(second, req)

	if second.Code != http.StatusTooManyRequests {
		t.Fatalf("second request status = %d, want %d",
			second.Code, http.StatusTooManyRequests)
	}

	if second.Header().Get("Retry-After") == "" {
		t.Error("expected Retry-After header")
	}
}

func TestGatewayDoesNotProxyToOrchestrator(t *testing.T) {
	t.Setenv("ORCHESTRATOR_URL", "http://127.0.0.1:1")
	t.Setenv("AGENEYX_API_KEY", "test-api-key")
	t.Setenv("AGENEYX_API_KEY_PERMISSIONS", "agents:run,tasks:read")

	gateway, err := NewGatewayServer(log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("create gateway: %v", err)
	}

	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/agent/runs/test-execution?limit=5",
		nil,
	)
	req.Header.Set("Authorization", "Bearer test-api-key")

	rec := httptest.NewRecorder()
	gateway.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want %d; body=%s",
			rec.Code, http.StatusNotFound, rec.Body.String())
	}
}

func TestGatewayReturns404ForUnknownRoute(t *testing.T) {
	t.Setenv("ORCHESTRATOR_URL", "http://127.0.0.1:1")

	t.Setenv("AGENEYX_API_KEY", "test-api-key")
	t.Setenv("AGENEYX_API_KEY_PERMISSIONS", "agents:run,tasks:read")
	gateway, err := NewGatewayServer(log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("create gateway: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/unknown", nil)

	gateway.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusNotFound)
	}
}

func TestWriteJSON(t *testing.T) {
	rec := httptest.NewRecorder()

	writeJSON(rec, http.StatusBadRequest, map[string]string{
		"error": "invalid request",
	})

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusBadRequest)
	}

	if got := rec.Header().Get("Content-Type"); got != "application/json" {
		t.Fatalf("Content-Type = %q, want application/json", got)
	}

	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	if body["error"] != "invalid request" {
		t.Errorf("unexpected response body: %v", body)
	}
}

func TestGatewayDoesNotProxyStreamingRequests(t *testing.T) {
	t.Setenv("ORCHESTRATOR_URL", "http://127.0.0.1:1")
	t.Setenv("AGENEYX_API_KEY", "test-api-key")
	t.Setenv("AGENEYX_API_KEY_PERMISSIONS", "agents:run,tasks:read")

	gateway, err := NewGatewayServer(log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("create gateway: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/v1/agent/stream", nil)
	req.Header.Set("Authorization", "Bearer test-api-key")

	rec := httptest.NewRecorder()
	gateway.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want %d; body=%s",
			rec.Code, http.StatusNotFound, rec.Body.String())
	}
}

func TestNewRateLimiterRejectsInvalidConfiguration(t *testing.T) {
	tests := []struct {
		name  string
		rate  int
		burst int
	}{
		{name: "zero rate", rate: 0, burst: 10},
		{name: "negative rate", rate: -1, burst: 10},
		{name: "zero burst", rate: 10, burst: 0},
		{name: "negative burst", rate: 10, burst: -1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			limiter, err := NewRateLimiter(tt.rate, tt.burst)
			if err == nil {
				t.Fatal("expected an error for invalid configuration")
			}
			if limiter != nil {
				t.Fatal("expected nil limiter for invalid configuration")
			}
		})
	}
}

func TestRateLimiterRemovesExpiredBuckets(t *testing.T) {
	limiter, err := NewRateLimiter(10, 20)
	if err != nil {
		t.Fatal(err)
	}

	limiter.maxBuckets = 1
	limiter.buckets["inactive-client"] = &bucket{
		tokens:     10,
		lastUpdate: time.Now().Add(-11 * time.Minute),
	}

	if !limiter.allow("new-client") {
		t.Fatal("expected new client to be allowed after expired bucket cleanup")
	}

	if _, exists := limiter.buckets["inactive-client"]; exists {
		t.Fatal("expected expired bucket to be removed")
	}
	if _, exists := limiter.buckets["new-client"]; !exists {
		t.Fatal("expected new client's bucket to exist")
	}
}

func TestRateLimiterRejectsNewClientsWhenFull(t *testing.T) {
	limiter, err := NewRateLimiter(10, 20)
	if err != nil {
		t.Fatal(err)
	}

	limiter.maxBuckets = 1

	if !limiter.allow("client-a") {
		t.Fatal("expected first client to be allowed")
	}
	if limiter.allow("client-b") {
		t.Fatal("expected new client to be rejected when bucket map is full")
	}
	if _, exists := limiter.buckets["client-a"]; !exists {
		t.Fatal("expected existing client's bucket to remain")
	}
	if !limiter.allow("client-a") {
		t.Fatal("expected existing client to continue using its bucket")
	}
}

func TestRateLimiterConcurrentAccess(t *testing.T) {
	limiter, err := NewRateLimiter(1000, 1000)
	if err != nil {
		t.Fatal(err)
	}

	const requests = 100
	var wg sync.WaitGroup
	wg.Add(requests)

	for i := 0; i < requests; i++ {
		go func() {
			defer wg.Done()
			limiter.allow("same-client")
		}()
	}

	wg.Wait()

	if got := len(limiter.buckets); got != 1 {
		t.Fatalf("expected one bucket, got %d", got)
	}
}

// TestGatewayAPIKeyAuthentication verifies that /v1/ routes require a valid
// bearer token while allowing a correctly authenticated request.
func TestGatewayAPIKeyAuthentication(t *testing.T) {
	t.Setenv("ORCHESTRATOR_URL", "")
	t.Setenv("AGENEYX_API_KEY", "test-api-key")
	t.Setenv("AGENEYX_API_KEY_PERMISSIONS", "agents:run,tasks:read")

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, `{"ok":true}`)
	}))
	defer upstream.Close()

	t.Setenv("ORCHESTRATOR_URL", upstream.URL)

	gateway, err := NewGatewayServer(log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("create gateway: %v", err)
	}

	tests := []struct {
		name       string
		token      string
		wantStatus int
	}{
		{name: "missing token", wantStatus: http.StatusUnauthorized},
		{name: "invalid token", token: "wrong-key", wantStatus: http.StatusUnauthorized},
		{name: "valid token", token: "test-api-key", wantStatus: http.StatusNotFound},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, "/v1/agent/runs/test-execution", nil)
			if tt.token != "" {
				req.Header.Set("Authorization", "Bearer "+tt.token)
			}

			rec := httptest.NewRecorder()
			gateway.Handler().ServeHTTP(rec, req)

			if rec.Code != tt.wantStatus {
				t.Fatalf("status = %d, want %d; body=%s",
					rec.Code, tt.wantStatus, rec.Body.String())
			}

			if tt.wantStatus == http.StatusUnauthorized {
				if got := rec.Header().Get("WWW-Authenticate"); got != "Bearer" {
					t.Errorf("WWW-Authenticate = %q, want %q", got, "Bearer")
				}
				if got := rec.Header().Get("Content-Type"); got != "application/json" {
					t.Errorf("Content-Type = %q, want application/json", got)
				}
			}
		})
	}
}

// TestGatewayRequiresAPIKeyConfiguration verifies that the gateway fails
// to initialize when no API key is configured.
func TestGatewayRequiresAPIKeyConfiguration(t *testing.T) {
	t.Setenv("AGENEYX_API_KEY", "")
	t.Setenv("AGENEYX_API_KEY_PERMISSIONS", "agents:run,tasks:read")

	_, err := NewGatewayServer(log.New(io.Discard, "", 0))
	if err == nil {
		t.Fatal("expected an error when AGENEYX_API_KEY is empty")
	}
}
