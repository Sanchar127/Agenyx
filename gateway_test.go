package main

import (
	"bufio"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
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
	limiter := NewRateLimiter(1, 1)

	handler := limiter.Middleware(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
		},
	))

	req := httptest.NewRequest(http.MethodPost, "/v1/tasks", nil)

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

func TestGatewayForwardsRequestToOrchestrator(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/v1/tasks" {
				t.Errorf("upstream path = %q, want /v1/tasks", r.URL.Path)
			}

			if r.URL.RawQuery != "limit=5" {
				t.Errorf("upstream query = %q, want limit=5", r.URL.RawQuery)
			}

			if r.Header.Get("X-Forwarded-Proto") != "https" {
				t.Errorf("X-Forwarded-Proto = %q, want https",
					r.Header.Get("X-Forwarded-Proto"))
			}

			w.WriteHeader(http.StatusOK)
			_, _ = io.WriteString(w, `{"ok":true}`)
		},
	))
	defer upstream.Close()

	t.Setenv("ORCHESTRATOR_URL", upstream.URL)

	logger := log.New(io.Discard, "", 0)
	gateway, err := NewGatewayServer(logger)
	if err != nil {
		t.Fatalf("create gateway: %v", err)
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/tasks?limit=5",
		nil,
	)

	gateway.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("gateway status = %d, want %d; body: %s",
			rec.Code, http.StatusOK, rec.Body.String())
	}

	if rec.Header().Get("X-Request-ID") == "" {
		t.Error("gateway response missing X-Request-ID")
	}

	var body map[string]bool
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("invalid JSON response: %v", err)
	}

	if !body["ok"] {
		t.Errorf("unexpected upstream response: %v", body)
	}
}

func TestGatewayReturns404ForUnknownRoute(t *testing.T) {
	t.Setenv("ORCHESTRATOR_URL", "http://127.0.0.1:1")

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

func TestGatewayStreamsUpstreamChunks(t *testing.T) {
	release := make(chan struct{})

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)

		flusher, ok := w.(http.Flusher)
		if !ok {
			t.Error("upstream ResponseWriter does not support flushing")
			return
		}

		if _, err := io.WriteString(w, "data: first\n\n"); err != nil {
			t.Errorf("write first chunk: %v", err)
			return
		}
		flusher.Flush()

		// Keep the upstream response open until the test receives the first chunk.
		<-release

		if _, err := io.WriteString(w, "data: second\n\n"); err != nil {
			t.Errorf("write second chunk: %v", err)
		}
	}))
	defer upstream.Close()

	defer func() {
		select {
		case <-release:
		default:
			close(release)
		}
	}()

	t.Setenv("ORCHESTRATOR_URL", upstream.URL)

	gateway, err := NewGatewayServer(log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatalf("create gateway: %v", err)
	}

	gatewayServer := httptest.NewServer(gateway.Handler())
	defer gatewayServer.Close()

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(gatewayServer.URL + "/v1/stream")
	if err != nil {
		t.Fatalf("request gateway: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want %d", resp.StatusCode, http.StatusOK)
	}

	reader := bufio.NewReader(resp.Body)
	firstLine, err := reader.ReadString('\n')
	if err != nil {
		t.Fatalf("read first streamed chunk before upstream finished: %v", err)
	}
	if firstLine != "data: first\n" {
		t.Fatalf("first streamed line = %q, want %q", firstLine, "data: first\n")
	}

	close(release)

	remaining, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("read remaining stream: %v", err)
	}
	if !strings.Contains(string(remaining), "data: second\n\n") {
		t.Fatalf("second chunk missing from stream: %q", remaining)
	}
}
