package main

import (
	"encoding/json"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"time"
)

type GatewayServer struct {
	handler http.Handler
}

func NewGatewayServer(logger *log.Logger) (*GatewayServer, error) {
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

		if forwardedFor := r.Header.Get("X-Forwarded-For"); forwardedFor != "" {
			r.Header.Set("X-Forwarded-For", forwardedFor+", "+clientIP(r))
		} else {
			r.Header.Set("X-Forwarded-For", clientIP(r))
		}
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

	mux.HandleFunc("/health/upstream", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
			return
		}

		r.URL.Path = "/health"
		r.URL.RawPath = ""
		proxy.ServeHTTP(w, r)
	})

	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		r.URL.Path = "/health"
		r.URL.RawPath = ""
		proxy.ServeHTTP(w, r)
	})

	mux.Handle("/v1/", proxy)

	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	})

	limiter, err := NewRateLimiter(10, 20)
	if err != nil {
		return nil, err
	}

	handler := chain(
		mux,
		requestIDMiddleware,
		securityHeadersMiddleware,
		requestSizeMiddleware,
		accessLogMiddleware(logger),
		limiter.Middleware,
	)

	return &GatewayServer{handler: handler}, nil
}

func (s *GatewayServer) Handler() http.Handler {
	return s.handler
}

func clientIP(r *http.Request) string {
	host := r.RemoteAddr

	if i := strings.LastIndex(host, ":"); i >= 0 {
		host = strings.Trim(host[:i], "[]")
	}

	return host
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
