package gateway

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/netip"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/sanchar127/agenyx/internal/orchestrator"
	"github.com/sanchar127/agenyx/recipe"
)

type GatewayServer struct {
	handler http.Handler
}

// NewGatewayServer creates a gateway without an attached orchestrator.
// This constructor is useful for middleware and health endpoint tests.
func NewGatewayServer(logger *log.Logger) (*GatewayServer, error) {
	return newGatewayServer(logger, nil)
}

// NewGatewayServerWithOrchestrator creates the production gateway.
// All supported agent execution routes are handled directly in Go.
func NewGatewayServerWithOrchestrator(
	logger *log.Logger,
	service *orchestrator.Service,
) (*GatewayServer, error) {
	if service == nil {
		return nil, errors.New("orchestrator service must not be nil")
	}

	return newGatewayServer(logger, service)
}

func newGatewayServer(
	logger *log.Logger,
	service *orchestrator.Service,
) (*GatewayServer, error) {
	recipePath := strings.TrimSpace(os.Getenv("AGENEYX_GATEWAY_RECIPE"))
	if recipePath == "" {
		candidates := []string{
			"recipes/gateway/default.yaml",
			"../../recipes/gateway/default.yaml",
		}

		for _, candidate := range candidates {
			if _, err := os.Stat(candidate); err == nil {
				recipePath = candidate
				break
			}
		}

		if recipePath == "" {
			return nil, errors.New(
				"gateway recipe not found; set AGENEYX_GATEWAY_RECIPE",
			)
		}
	}

	gatewaySpec, err := recipe.LoadGatewaySpec(recipePath)
	if err != nil {
		return nil, fmt.Errorf("load gateway recipe: %w", err)
	}

	apiKey := os.Getenv("AGENEYX_API_KEY")
	if strings.TrimSpace(apiKey) == "" {
		return nil, errors.New(
			"AGENEYX_API_KEY must be set to a non-empty secret",
		)
	}

	permissions, err := parseAPIPermissions(
		os.Getenv("AGENEYX_API_KEY_PERMISSIONS"),
	)
	if err != nil {
		return nil, err
	}

	trustedProxies, err := parseTrustedProxies(
		os.Getenv("AGENEYX_TRUSTED_PROXIES"),
	)
	if err != nil {
		return nil, err
	}

	resolveClientIP := func(r *http.Request) string {
		return resolvedClientIP(r, trustedProxies)
	}

	// Initialize session store (24 hour TTL).
	sessionStore := NewSessionStore(24 * time.Hour)

	// Register OAuth providers from environment variables.
	if googleClientID := os.Getenv("GOOGLE_OAUTH_CLIENT_ID"); googleClientID != "" {
		registerOAuthProvider(
			"google",
			"https://oauth2.googleapis.com/token",
			"https://www.googleapis.com/oauth2/v2/userinfo",
			googleClientID,
			os.Getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
			"openid email profile",
		)
	}
	if githubClientID := os.Getenv("GITHUB_OAUTH_CLIENT_ID"); githubClientID != "" {
		registerOAuthProvider(
			"github",
			"https://github.com/login/oauth/access_token",
			"https://api.github.com/user",
			githubClientID,
			os.Getenv("GITHUB_OAUTH_CLIENT_SECRET"),
			"read:user",
		)
	}

	mux := http.NewServeMux()

	// Liveness only checks whether the Go gateway is running.
	mux.HandleFunc("/health/live", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{
				"error": "method not allowed",
			})
			return
		}

		writeJSON(w, http.StatusOK, map[string]string{
			"status": "alive",
		})
	})

	// Readiness checks whether the gateway can access its task queue.
	readyHandler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{
				"error": "method not allowed",
			})
			return
		}

		if service == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{
				"status": "not_ready",
			})
			return
		}

		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()

		if err := service.Ready(ctx); err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{
				"status": "not_ready",
			})
			return
		}

		writeJSON(w, http.StatusOK, map[string]string{
			"status": "ready",
		})
	}

	mux.HandleFunc("/health/ready", readyHandler)
	mux.HandleFunc("/health/orchestrator", readyHandler)
	mux.HandleFunc("/health/upstream", readyHandler)

	// Preserve the old Python health endpoint's response shape.
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{
				"error": "method not allowed",
			})
			return
		}

		writeJSON(w, http.StatusOK, map[string]string{
			"status": "ok",
		})
	})

	// Register execution routes directly in Go.
	if service != nil {
		orchestratorHandler := orchestrator.HTTPHandler(service)

		mux.Handle("POST /v1/agent/run", orchestratorHandler)
		mux.Handle("GET /v1/agent/runs/{execution_id}", orchestratorHandler)
	}

	// Auth routes forward credential exchanges to the agent service.
	agentUpstream := os.Getenv("AGENEYX_AGENT_URL")
	if agentUpstream == "" {
		agentUpstream = "http://agent:8000"
	}

	agentURL, err := url.Parse(agentUpstream)
	if err != nil {
		return nil, fmt.Errorf("parse AGENEYX_AGENT_URL %q: %w", agentUpstream, err)
	}

	agentProxy := httputil.NewSingleHostReverseProxy(agentURL)
	mux.Handle("POST /auth/email/login", agentProxy)
	mux.Handle("POST /auth/email/signup", agentProxy)

	// OAuth token exchange endpoints (backend handles code exchange).
	mux.HandleFunc("POST /auth/{provider}/token", func(w http.ResponseWriter, r *http.Request) {
		provider := r.PathValue("provider")

		// Only allow configured providers.
		if _, ok := oauthProviders[provider]; !ok {
			writeJSON(w, http.StatusNotFound, map[string]string{
				"error": "OAuth provider not configured",
			})
			return
		}

		var req struct {
			Code        string `json:"code"`
			ClientID    string `json:"client_id"`
			RedirectURI string `json:"redirect_uri"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "invalid request body",
			})
			return
		}

		if req.Code == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "authorization code is required",
			})
			return
		}

		// Exchange the authorization code for an access token.
		tokenResp, err := exchangeCode(provider, req.Code, req.RedirectURI)
		if err != nil {
			writeJSON(w, http.StatusUnauthorized, map[string]string{
				"error": "token exchange failed: " + err.Error(),
			})
			return
		}

		// Fetch user info from the provider.
		subject, email, name, err := fetchUserInfo(provider, tokenResp.AccessToken)
		if err != nil {
			writeJSON(w, http.StatusUnauthorized, map[string]string{
				"error": "user info fetch failed: " + err.Error(),
			})
			return
		}

		// Create a session.
		sessionToken := sessionStore.Create(provider, subject, email, name)

		secure := false
		if r.TLS != nil || r.Header.Get("X-Forwarded-Proto") == "https" {
			secure = true
		}

		writeSessionCookie(w, sessionToken, secure)

		writeJSON(w, http.StatusOK, map[string]string{
			"status":   "authenticated",
			"provider": provider,
			"email":    email,
			"name":     name,
		})
	})

	// No reverse proxy: unsupported API routes return 404.
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	})

	limiter, err := NewRateLimiter(
		gatewaySpec.RateLimit.RequestsPerSecond,
		gatewaySpec.RateLimit.Burst,
	)
	if err != nil {
		return nil, err
	}

	// Guardrails run after authentication/authorization, immediately before
	// the agent execution handler. Configured via AGENEYX_GUARDRAILS_* env vars.
	gm, err := newGuardrailsMiddlewareFromEnv()
	if err != nil {
		return nil, fmt.Errorf("initialize guardrails middleware: %w", err)
	}

	handler := chain(
		mux,
		corsMiddleware,
		requestIDMiddleware,
		securityHeadersMiddleware,
		requestSizeMiddlewareWithLimit(gatewaySpec.Request.MaxBodyBytes),
		accessLogMiddleware(logger),
		limiter.MiddlewareWithClientIP(resolveClientIP),
		apiKeyAuthMiddleware(apiKey),
		authorizationMiddleware(permissions),
		gm.handle,
	)

	return &GatewayServer{handler: handler}, nil
}

func (s *GatewayServer) Handler() http.Handler {
	return s.handler
}

func clientIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}

	if addr, err := netip.ParseAddr(host); err == nil {
		return addr.Unmap().String()
	}

	return host
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
