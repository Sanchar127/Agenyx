package main

import (
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestGatewayAuthorizationIntegration verifies that the real gateway middleware
// enforces permissions before forwarding requests to the orchestrator.
func TestGatewayAuthorizationIntegration(t *testing.T) {
	tests := []struct {
		name            string
		permissions     string
		method          string
		path            string
		wantStatus      int
		wantUpstreamHit bool
	}{
		{
			name:            "agent run permission allows run endpoint",
			permissions:     "agents:run",
			method:          http.MethodPost,
			path:            "/v1/agent/run",
			wantStatus:      http.StatusOK,
			wantUpstreamHit: true,
		},
		{
			name:        "agent run permission cannot read task status",
			permissions: "agents:run",
			method:      http.MethodGet,
			path:        "/v1/agent/runs/test-execution",
			wantStatus:  http.StatusForbidden,
		},
		{
			name:            "task read permission allows task status",
			permissions:     "tasks:read",
			method:          http.MethodGet,
			path:            "/v1/agent/runs/test-execution",
			wantStatus:      http.StatusOK,
			wantUpstreamHit: true,
		},
		{
			name:        "unknown models endpoint is denied",
			permissions: "agents:run,tasks:read",
			method:      http.MethodGet,
			path:        "/v1/models",
			wantStatus:  http.StatusForbidden,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var upstreamHits int

			upstream := httptest.NewServer(http.HandlerFunc(
				func(w http.ResponseWriter, r *http.Request) {
					upstreamHits++
					w.WriteHeader(http.StatusOK)
					_, _ = io.WriteString(w, `{"ok":true}`)
				},
			))
			defer upstream.Close()

			t.Setenv("ORCHESTRATOR_URL", upstream.URL)
			t.Setenv("AGENEYX_API_KEY", "integration-test-key")
			t.Setenv("AGENEYX_API_KEY_PERMISSIONS", tt.permissions)

			gateway, err := NewGatewayServer(log.New(io.Discard, "", 0))
			if err != nil {
				t.Fatalf("create gateway: %v", err)
			}

			req := httptest.NewRequest(tt.method, tt.path, nil)
			req.Header.Set("Authorization", "Bearer integration-test-key")

			rec := httptest.NewRecorder()
			gateway.Handler().ServeHTTP(rec, req)

			if rec.Code != tt.wantStatus {
				t.Fatalf(
					"status = %d, want %d; body = %s",
					rec.Code,
					tt.wantStatus,
					rec.Body.String(),
				)
			}

			if want := 0; tt.wantUpstreamHit {
				want = 1
				if upstreamHits != want {
					t.Errorf("upstream hits = %d, want %d", upstreamHits, want)
				}
			} else if upstreamHits != 0 {
				t.Errorf("upstream hits = %d, want 0", upstreamHits)
			}
		})
	}
}
