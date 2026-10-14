package gateway

import (
	"fmt"
	"net/http"
	"strings"
)

const (
	permissionAgentRun  = "agents:run"
	permissionTasksRead = "tasks:read"
)

// parseAPIPermissions parses and validates the comma-separated permissions
// configured for the gateway's API key.
func parseAPIPermissions(raw string) (map[string]struct{}, error) {
	permissions := make(map[string]struct{})

	for _, item := range strings.Split(raw, ",") {
		permission := strings.TrimSpace(item)
		if permission == "" {
			continue
		}

		switch permission {
		case permissionAgentRun, permissionTasksRead:
			permissions[permission] = struct{}{}
		default:
			return nil, fmt.Errorf("invalid API permission %q", permission)
		}
	}

	if len(permissions) == 0 {
		return nil, fmt.Errorf("AGENEYX_API_KEY_PERMISSIONS must contain at least one permission")
	}

	return permissions, nil
}

// authorizationMiddleware enforces permissions on /v1/ routes.
// Unknown routes and unsupported methods are denied by default.
func authorizationMiddleware(permissions map[string]struct{}) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !strings.HasPrefix(r.URL.Path, "/v1/") {
				next.ServeHTTP(w, r)
				return
			}

			required, knownRoute := requiredPermission(r.Method, r.URL.Path)
			if !knownRoute {
				writeJSON(w, http.StatusForbidden, map[string]string{
					"error": "forbidden",
				})
				return
			}

			if _, allowed := permissions[required]; !allowed {
				writeJSON(w, http.StatusForbidden, map[string]string{
					"error": "forbidden",
				})
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// requiredPermission maps an HTTP method and exact route shape to a permission.
// Returning false means the route or method is not explicitly authorized.
func requiredPermission(method, requestPath string) (string, bool) {
	segments := strings.Split(requestPath, "/")

	// Exact routes:
	// POST /v1/agent/run
	// POST /v1/agent/submit
	// POST /v1/agent/stream
	if method == http.MethodPost &&
		(len(segments) == 4) &&
		segments[1] == "v1" &&
		segments[2] == "agent" &&
		(segments[3] == "run" ||
			segments[3] == "submit" ||
			segments[3] == "stream") {
		return permissionAgentRun, true
	}

	// GET /v1/agent/runs/{execution_id}
	if method == http.MethodGet &&
		len(segments) == 5 &&
		segments[1] == "v1" &&
		segments[2] == "agent" &&
		segments[3] == "runs" &&
		segments[4] != "" {
		return permissionTasksRead, true
	}

	// GET /v1/agent/{execution_id}/events
	if method == http.MethodGet &&
		len(segments) == 5 &&
		segments[1] == "v1" &&
		segments[2] == "agent" &&
		segments[3] != "" &&
		segments[3] != "runs" &&
		segments[4] == "events" {
		return permissionTasksRead, true
	}

	return "", false
}
