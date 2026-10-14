package gateway

import (
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGatewayAuthorizationIntegration(t *testing.T) {
	tests := []struct {
		name        string
		permissions string
		method      string
		path        string
		wantStatus  int
	}{
		{
			name:        "run permission allows access to run route",
			permissions: "agents:run",
			method:      http.MethodPost,
			path:        "/v1/agent/run",
			wantStatus:  http.StatusNotFound, // No orchestrator attached in this test.
		},
		{
			name:        "run permission cannot read execution state",
			permissions: "agents:run",
			method:      http.MethodGet,
			path:        "/v1/agent/runs/test-execution",
			wantStatus:  http.StatusForbidden,
		},
		{
			name:        "read permission allows access to status route",
			permissions: "tasks:read",
			method:      http.MethodGet,
			path:        "/v1/agent/runs/test-execution",
			wantStatus:  http.StatusNotFound, // No orchestrator attached in this test.
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
		})
	}
}
