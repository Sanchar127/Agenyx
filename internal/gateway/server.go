package gateway

import (
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

// NewGatewayServer creates the gateway with the legacy upstream proxy.
func NewGatewayServer(logger *log.Logger) (*GatewayServer, error) {
	return newGatewayServer(logger, nil)
}

// NewGatewayServerWithOrchestrator creates the production gateway with direct
// Go orchestrator routes. Other authorized API routes retain the upstream proxy.
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
		return nil, errors.New("AGENEYX_API_KEY must be set to a non-empty secret")
	}

	permissions, err := parseAPIPermissions(os.Getenv("AGENEYX_API_KEY_PERMISSIONS"))
	if err != nil {
		return nil, err
	}

	trustedProxies, err := parseTrustedProxies(os.Getenv("AGENEYX_TRUSTED_PROXIES"))
	if err != nil {
		return nil, err
	}

	resolveClientIP := func(r *http.Request) string {
		return resolvedClientIP(r, trustedProxies)
	}

	upstream := os.Getenv("ORCHESTRATOR_URL")
	if upstream == "" {
		upstream = "http://orchestrator:8001"
	}

	target, err := url.Parse(upstream)
	if err != nil {
		return nil, err
	}

	if target.Scheme != "http" && target.Scheme != "https" {
		return nil, &url.Error{
			Op:  "parse orchestrator URL",
			URL: upstream,
			Err: errInvalidUpstreamScheme,
		}
	}

	proxy := httputil.NewSingleHostReverseProxy(target)

	originalDirector := proxy.Director
	proxy.Director = func(r *http.Request) {
		originalDirector(r)

		r.Header.Set("X-Forwarded-Proto", "https")

		// Do not forward an arbitrary client-supplied forwarding chain.
		// Forward only the client address resolved using trusted proxies.
		r.Header.Set("X-Forwarded-For", resolveClientIP(r))
	}

	proxy.Transport = &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		DialContext: (&net.Dialer{
			Timeout:   10 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout:   10 * time.Second,
		ResponseHeaderTimeout: 120 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   20,
		IdleConnTimeout:       90 * time.Second,
	}

	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		logger.Printf(
			`{"event":"upstream_error","request_id":%q,"error":%q}`,
			r.Header.Get("X-Request-ID"),
			err.Error(),
		)

		http.Error(
			w,
			`{"error":"upstream unavailable"}`,
			http.StatusBadGateway,
		)
	}

	mux := http.NewServeMux()

	mux.HandleFunc("/health/live", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "alive"})
	})

	mux.HandleFunc("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	orchestratorHealthHandler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}

		r.URL.Path = "/health"
		r.URL.RawPath = ""
		proxy.ServeHTTP(w, r)
	}

	// Gateway health and orchestrator health are separate checks.
	mux.HandleFunc("/health/orchestrator", orchestratorHealthHandler)

	// Keep the previous endpoint for backward compatibility.
	mux.HandleFunc("/health/upstream", orchestratorHealthHandler)

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		r.URL.Path = "/health"
		r.URL.RawPath = ""
		proxy.ServeHTTP(w, r)
	})

	// Migrate only the run and execution-status endpoints to Go.
	// The existing authorization middleware still runs before these handlers.
	if service != nil {
		orchestratorHandler := orchestrator.HTTPHandler(service)
		mux.Handle("POST /v1/agent/run", orchestratorHandler)
		mux.Handle("GET /v1/agent/runs/{execution_id}", orchestratorHandler)
	}

	// Keep other authorized API routes on the existing upstream during migration.
	mux.Handle("/v1/", proxy)

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

	handler := chain(
		mux,
		requestIDMiddleware,
		securityHeadersMiddleware,
		requestSizeMiddlewareWithLimit(gatewaySpec.Request.MaxBodyBytes),
		accessLogMiddleware(logger),
		limiter.MiddlewareWithClientIP(resolveClientIP),
		apiKeyAuthMiddleware(apiKey),
		authorizationMiddleware(permissions),
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
