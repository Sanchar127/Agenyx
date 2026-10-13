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
				t.Fatalf("got status %d, want %d; body=%s",
					rec.Code, tt.wantStatus, rec.Body.String())
			}

			if tt.wantBody != "" && !strings.Contains(rec.Body.String(), tt.wantBody) {
				t.Errorf("body %q does not contain %q", rec.Body.String(), tt.wantBody)
			}
		})
	}
}

func TestResponseRecorderSupportsFlushing(t *testing.T) {
	underlying := httptest.NewRecorder()
	recorder := &responseRecorder{ResponseWriter: underlying}

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
