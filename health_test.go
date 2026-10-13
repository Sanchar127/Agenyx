package main

import (
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestGatewayHealthEndpoints(t *testing.T) {
	t.Setenv("ORCHESTRATOR_URL", "http://127.0.0.1:1")

	t.Setenv("AGENEYX_API_KEY", "test-api-key")
	gateway, err := NewGatewayServer(log.New(io.Discard, "", 0))
	if err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		path       string
		method     string
		wantStatus int
		wantBody   string
	}{
		{"/health/live", http.MethodGet, http.StatusOK, `"status":"alive"`},
		{"/health/ready", http.MethodGet, http.StatusOK, `"status":"ready"`},
		{"/health/live", http.MethodPost, http.StatusMethodNotAllowed, ""},
		{"/health/ready", http.MethodPost, http.StatusMethodNotAllowed, ""},
		{"/health/upstream", http.MethodPost, http.StatusMethodNotAllowed, ""},
	}

	for _, tt := range tests {
		t.Run(tt.method+" "+tt.path, func(t *testing.T) {
			req := httptest.NewRequest(tt.method, tt.path, nil)
			rec := httptest.NewRecorder()

			gateway.Handler().ServeHTTP(rec, req)

			if rec.Code != tt.wantStatus {
				t.Fatalf(
					"got status %d, want %d; body=%s",
					rec.Code,
					tt.wantStatus,
					rec.Body.String(),
				)
			}

			if tt.wantBody != "" &&
				!strings.Contains(rec.Body.String(), tt.wantBody) {
				t.Errorf(
					"body %q does not contain %q",
					rec.Body.String(),
					tt.wantBody,
				)
			}
		})
	}
}

func TestResponseRecorderSupportsFlushing(t *testing.T) {
	underlying := httptest.NewRecorder()
	recorder := &responseRecorder{
		ResponseWriter: underlying,
	}

	if _, ok := any(recorder).(http.Flusher); !ok {
		t.Fatal("responseRecorder does not implement http.Flusher")
	}

	if _, err := recorder.Write([]byte("token")); err != nil {
		t.Fatalf("write token: %v", err)
	}

	recorder.Flush()

	if !underlying.Flushed {
		t.Fatal("Flush did not reach the underlying ResponseWriter")
	}

	if recorder.Unwrap() != underlying {
		t.Fatal("Unwrap did not return the original ResponseWriter")
	}
}

func TestRequestSizeMiddlewareRejectsOversizedBody(t *testing.T) {
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/tasks",
		strings.NewReader("oversized request"),
	)

	// Simulate a request that declares a body larger than the configured limit.
	req.ContentLength = maxRequestBodyBytes + 1

	rec := httptest.NewRecorder()
	nextCalled := false

	handler := requestSizeMiddleware(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			nextCalled = true
			w.WriteHeader(http.StatusOK)
		},
	))

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf(
			"status = %d, want %d; body=%s",
			rec.Code,
			http.StatusRequestEntityTooLarge,
			rec.Body.String(),
		)
	}

	if nextCalled {
		t.Fatal("next handler was called for an oversized request")
	}

	if got := rec.Header().Get("Content-Type"); got != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", got)
	}

	if !strings.Contains(
		rec.Body.String(),
		`"error":"request body too large"`,
	) {
		t.Errorf("unexpected response body: %s", rec.Body.String())
	}
}

func TestRequestSizeMiddlewareAllowsBodyAtLimit(t *testing.T) {
	body := strings.Repeat("x", int(maxRequestBodyBytes))

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/tasks",
		strings.NewReader(body),
	)

	rec := httptest.NewRecorder()
	nextCalled := false

	handler := requestSizeMiddleware(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			nextCalled = true

			got, err := io.ReadAll(r.Body)
			if err != nil {
				t.Errorf("read request body: %v", err)
				return
			}

			if int64(len(got)) != maxRequestBodyBytes {
				t.Errorf(
					"body length = %d, want %d",
					len(got),
					maxRequestBodyBytes,
				)
			}

			w.WriteHeader(http.StatusOK)
		},
	))

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf(
			"status = %d, want %d; body=%s",
			rec.Code,
			http.StatusOK,
			rec.Body.String(),
		)
	}

	if !nextCalled {
		t.Fatal("next handler was not called for a body at the limit")
	}
}

func TestRequestSizeMiddlewareRejectsUnknownLengthOversizedBody(t *testing.T) {
	body := strings.Repeat("x", int(maxRequestBodyBytes)+1)

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/tasks",
		strings.NewReader(body),
	)
	req.ContentLength = -1

	rec := httptest.NewRecorder()
	nextCalled := false

	handler := requestSizeMiddleware(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			nextCalled = true

			_, err := io.ReadAll(r.Body)
			if err != nil {
				if _, ok := err.(*http.MaxBytesError); ok {
					writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{
						"error": "request body too large",
					})
					return
				}

				writeJSON(w, http.StatusBadRequest, map[string]string{
					"error": "failed to read request body",
				})
				return
			}

			w.WriteHeader(http.StatusOK)
		},
	))

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf(
			"status = %d, want %d; body=%s",
			rec.Code,
			http.StatusRequestEntityTooLarge,
			rec.Body.String(),
		)
	}

	if !nextCalled {
		t.Fatal("handler was not called to consume the unknown-length body")
	}
}
