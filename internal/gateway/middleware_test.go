package gateway

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestAPIKeyAuthMiddleware(t *testing.T) {
	const expectedKey = "test-api-key"

	tests := []struct {
		name           string
		path           string
		authorization  string
		wantStatus     int
		wantNextCalled bool
	}{
		{
			name:           "valid bearer token",
			path:           "/v1/models",
			authorization:  "Bearer test-api-key",
			wantStatus:     http.StatusOK,
			wantNextCalled: true,
		},
		{
			name:          "missing authorization header",
			path:          "/v1/models",
			authorization: "",
			wantStatus:    http.StatusUnauthorized,
		},
		{
			name:          "invalid API key",
			path:          "/v1/models",
			authorization: "Bearer wrong-key",
			wantStatus:    http.StatusUnauthorized,
		},
		{
			name:          "wrong authorization scheme",
			path:          "/v1/models",
			authorization: "Basic test-api-key",
			wantStatus:    http.StatusUnauthorized,
		},
		{
			name:          "malformed bearer header",
			path:          "/v1/models",
			authorization: "Bearer",
			wantStatus:    http.StatusUnauthorized,
		},
		{
			name:          "extra authorization fields",
			path:          "/v1/models",
			authorization: "Bearer test-api-key extra",
			wantStatus:    http.StatusUnauthorized,
		},
		{
			name:           "health endpoint does not require API key",
			path:           "/health/live",
			authorization:  "",
			wantStatus:     http.StatusOK,
			wantNextCalled: true,
		},
		{
			name:           "non API route does not require API key",
			path:           "/unknown",
			authorization:  "",
			wantStatus:     http.StatusOK,
			wantNextCalled: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			nextCalled := false

			next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				nextCalled = true
				w.WriteHeader(http.StatusOK)
			})

			handler := apiKeyAuthMiddleware(expectedKey)(next)

			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			if tt.authorization != "" {
				req.Header.Set("Authorization", tt.authorization)
			}

			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)

			if rec.Code != tt.wantStatus {
				t.Errorf(
					"status = %d, want %d; body = %s",
					rec.Code,
					tt.wantStatus,
					rec.Body.String(),
				)
			}

			if nextCalled != tt.wantNextCalled {
				t.Errorf(
					"next handler called = %v, want %v",
					nextCalled,
					tt.wantNextCalled,
				)
			}

			if tt.wantStatus == http.StatusUnauthorized {
				if got := rec.Header().Get("WWW-Authenticate"); got != "Bearer" {
					t.Errorf("WWW-Authenticate = %q, want %q", got, "Bearer")
				}

				if got := rec.Header().Get("Content-Type"); got != "application/json" {
					t.Errorf("Content-Type = %q, want %q", got, "application/json")
				}
			}
		})
	}
}

func TestAPIKeyAuthMiddlewareAcceptsCaseInsensitiveBearerScheme(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	handler := apiKeyAuthMiddleware("test-api-key")(next)

	req := httptest.NewRequest(http.MethodGet, "/v1/models", nil)
	req.Header.Set("Authorization", "bearer test-api-key")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s",
			rec.Code, http.StatusOK, rec.Body.String())
	}
}
