package gateway

import (
	"net/http"
	"os"
	"strings"
)

const (
	// corsOriginEnv holds a comma-separated list of origins the gateway
	// allows for cross-origin requests. The special value "*" allows any
	// origin. When unset, no CORS headers are added (safe default).
	corsOriginEnv = "AGENEYX_CORS_ORIGIN"

	// corsCredentialsEnv enables Access-Control-Allow-Credentials when set
	// to "true". Credentials are incompatible with the "*" origin.
	corsCredentialsEnv = "AGENEYX_CORS_ALLOW_CREDENTIALS"

	corsMaxAge            = "86400"
	defaultAllowedMethods = "GET, POST, OPTIONS"
	defaultAllowedHeaders = "Content-Type, Authorization"
	defaultExposedHeaders = "X-Request-ID"
)

// corsConfig holds the resolved CORS configuration.
type corsConfig struct {
	origins          []string
	wildcard         bool
	allowCredentials bool
}

func loadCORSConfig() corsConfig {
	cfg := corsConfig{}

	raw := strings.TrimSpace(os.Getenv(corsOriginEnv))
	if raw == "" {
		return cfg
	}

	for _, item := range strings.Split(raw, ",") {
		origin := strings.TrimSpace(item)
		if origin == "" {
			continue
		}

		if origin == "*" {
			cfg.wildcard = true
			cfg.origins = nil
			break
		}

		cfg.origins = append(cfg.origins, origin)
	}

	cfg.allowCredentials = strings.EqualFold(
		os.Getenv(corsCredentialsEnv), "true",
	)

	return cfg
}

// allowedOrigin returns the value to emit for the
// Access-Control-Allow-Origin response header for the given request Origin.
// It returns "" when the origin is not allowed, meaning no CORS headers
// should be added to the response.
func (cfg corsConfig) allowedOrigin(origin string) string {
	if cfg.wildcard {
		return "*"
	}

	for _, allowed := range cfg.origins {
		if origin == allowed {
			return origin
		}
	}

	return ""
}

// corsMiddleware adds CORS headers to responses and answers CORS preflight
// OPTIONS requests directly. It is placed at the front of the middleware
// chain so preflight requests are not subject to authentication or rate
// limiting, and CORS headers are committed on every response, including
// error responses from downstream middleware.
func corsMiddleware(next http.Handler) http.Handler {
	cfg := loadCORSConfig()

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		allowOrigin := cfg.allowedOrigin(r.Header.Get("Origin"))

		// A CORS preflight request carries
		// Access-Control-Request-Method. Answer it directly instead of
		// routing it through the mux (auth routes only register POST).
		if r.Method == http.MethodOptions &&
			r.Header.Get("Access-Control-Request-Method") != "" {

			if allowOrigin != "" {
				w.Header().Set("Access-Control-Allow-Origin", allowOrigin)
				w.Header().Set("Access-Control-Allow-Methods", defaultAllowedMethods)
				w.Header().Set("Access-Control-Max-Age", corsMaxAge)

				if requestedHeaders := r.Header.Get(
					"Access-Control-Request-Headers",
				); requestedHeaders != "" {
					w.Header().Set("Access-Control-Allow-Headers", requestedHeaders)
				} else {
					w.Header().Set("Access-Control-Allow-Headers", defaultAllowedHeaders)
				}

				if cfg.allowCredentials {
					w.Header().Set("Access-Control-Allow-Credentials", "true")
				}

				if !cfg.wildcard {
					w.Header().Set("Vary", "Origin")
				}
			}

			w.WriteHeader(http.StatusNoContent)
			return
		}

		// Set CORS headers before the inner handler runs so they are
		// committed with the response, including error responses written
		// by downstream middleware.
		if allowOrigin != "" {
			w.Header().Set("Access-Control-Allow-Origin", allowOrigin)
			w.Header().Set("Access-Control-Expose-Headers", defaultExposedHeaders)
			if cfg.allowCredentials {
				w.Header().Set("Access-Control-Allow-Credentials", "true")
			}
			if !cfg.wildcard {
				w.Header().Set("Vary", "Origin")
			}
		}

		next.ServeHTTP(w, r)
	})
}
