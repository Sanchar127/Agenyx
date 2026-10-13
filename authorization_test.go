package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestParseAPIPermissions(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantErr bool
	}{
		{
			name:  "both permissions",
			input: "agents:run,tasks:read",
		},
		{
			name:  "whitespace",
			input: " agents:run , tasks:read ",
		},
		{
			name:    "empty configuration",
			input:   "",
			wantErr: true,
		},
		{
			name:    "unknown permission",
			input:   "agents:admin",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := parseAPIPermissions(tt.input)

			if (err != nil) != tt.wantErr {
				t.Fatalf("parseAPIPermissions() error = %v, wantErr %v", err, tt.wantErr)
			}

			if err != nil {
				return
			}

			if len(got) == 0 {
				t.Fatal("expected at least one permission")
			}
		})
	}
}

func TestAuthorizationMiddleware(t *testing.T) {
	permissions, err := parseAPIPermissions("agents:run")
	if err != nil {
		t.Fatal(err)
	}

	handler := authorizationMiddleware(permissions)(
		http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNoContent)
		}),
	)

	tests := []struct {
		name       string
		method     string
		path       string
		wantStatus int
	}{
		{
			name:       "agent run allowed",
			method:     http.MethodPost,
			path:       "/v1/agent/run",
			wantStatus: http.StatusNoContent,
		},
		{
			name:       "agent submit allowed",
			method:     http.MethodPost,
			path:       "/v1/agent/submit",
			wantStatus: http.StatusNoContent,
		},
		{
			name:       "agent stream allowed",
			method:     http.MethodPost,
			path:       "/v1/agent/stream",
			wantStatus: http.StatusNoContent,
		},
		{
			name:       "read permission missing",
			method:     http.MethodGet,
			path:       "/v1/agent/runs/exec-123",
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "unknown route denied",
			method:     http.MethodGet,
			path:       "/v1/models",
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "wrong method denied",
			method:     http.MethodGet,
			path:       "/v1/agent/run",
			wantStatus: http.StatusForbidden,
		},
		{
			name:       "health route passes through",
			method:     http.MethodGet,
			path:       "/health/ready",
			wantStatus: http.StatusNoContent,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(tt.method, tt.path, nil)
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

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

func TestRequiredPermissionRejectsUnrecognizedRoutes(t *testing.T) {
	tests := []struct {
		method string
		path   string
	}{
		{http.MethodGet, "/v1/models"},
		{http.MethodPost, "/v1/agent/unknown"},
		{http.MethodDelete, "/v1/agent/run"},
		{http.MethodGet, "/v1/agent/runs"},
		{http.MethodGet, "/v1/agent//events"},
		{http.MethodGet, "/v1/agent/exec-123/events/extra"},
	}

	for _, tt := range tests {
		t.Run(tt.method+" "+tt.path, func(t *testing.T) {
			if permission, ok := requiredPermission(tt.method, tt.path); ok {
				t.Fatalf("unexpected permission %q for unrecognized route", permission)
			}
		})
	}
}
