// Package main provides the Agenyx semantic router HTTP service.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/sanchar127/agenyx/internal/registry"
	internalrouter "github.com/sanchar127/agenyx/internal/router"
	"github.com/sanchar127/agenyx/internal/scoring"
	"github.com/sanchar127/agenyx/internal/session"
	"github.com/sanchar127/agenyx/internal/strategy"
	"github.com/sanchar127/agenyx/pkg/router"
)

const (
	defaultAddr      = ":8005"
	defaultValkeyURL = "redis://valkey:6379/0"

	valkeyPingTimeout = 3 * time.Second
	shutdownTimeout   = 5 * time.Second

	readHeaderTimeout = 5 * time.Second
	readTimeout       = 10 * time.Second
	writeTimeout      = 10 * time.Second
	idleTimeout       = 60 * time.Second

	maxRequestBodySize = 1 << 20 // 1 MiB
)

type server struct {
	engine       router.Router
	valkeyClient *redis.Client
}

func main() {
	if err := run(); err != nil {
		log.Printf("fatal: %v", err)
		os.Exit(1)
	}
}

func run() error {
	valkeyClient, err := newValkeyClient()
	if err != nil {
		return fmt.Errorf("create Valkey client: %w", err)
	}

	defer func() {
		if err := valkeyClient.Close(); err != nil {
			log.Printf("failed to close Valkey client: %v", err)
		}
	}()

	if err := pingValkey(valkeyClient); err != nil {
		return fmt.Errorf("valkey is unavailable: %w", err)
	}

	engine, err := buildRouter(valkeyClient)
	if err != nil {
		return fmt.Errorf("build semantic router: %w", err)
	}

	s := &server{
		engine:       engine,
		valkeyClient: valkeyClient,
	}

	mux := http.NewServeMux()

	mux.HandleFunc("/health", s.health)
	mux.HandleFunc("/ready", s.ready)
	mux.HandleFunc("/route", s.route)

	httpServer := &http.Server{
		Addr:              getEnv("AGENTYX_ROUTER_ADDR", defaultAddr),
		Handler:           requestLogger(mux),
		ReadHeaderTimeout: readHeaderTimeout,
		ReadTimeout:       readTimeout,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       idleTimeout,
	}

	return serve(httpServer)
}

func newValkeyClient() (*redis.Client, error) {
	valkeyURL := getEnv(
		"AGENTYX_VALKEY_URL",
		defaultValkeyURL,
	)

	opt, err := redis.ParseURL(valkeyURL)
	if err != nil {
		return nil, fmt.Errorf(
			"invalid AGENTYX_VALKEY_URL: %w",
			err,
		)
	}

	if password := os.Getenv("AGENTYX_VALKEY_PASSWORD"); password != "" {
		opt.Password = password
	}

	return redis.NewClient(opt), nil
}
func pingValkey(client *redis.Client) error {
	ctx, cancel := context.WithTimeout(
		context.Background(),
		valkeyPingTimeout,
	)
	defer cancel()

	return client.Ping(ctx).Err()
}

func buildRouter(valkeyClient *redis.Client) (router.Router, error) {
	reg := registry.New()

	models := []router.Model{
		{
			Name:          "qwen2.5:7b",
			Provider:      "ollama",
			Capabilities:  []string{"general", "coding"},
			ContextWindow: 32768,
			Priority:      10,
			Enabled:       true,
		},
		{
			Name:          "llama3.2",
			Provider:      "ollama",
			Capabilities:  []string{"general"},
			ContextWindow: 8192,
			Priority:      5,
			Enabled:       true,
		},
	}

	for _, model := range models {
		if err := reg.Register(model); err != nil {
			return nil, fmt.Errorf(
				"register model %q: %w",
				model.Name,
				err,
			)
		}
	}

	// Valkey-backed session state allows multiple router
	// instances to share routing-session state.
	store := session.NewValkeyStore(valkeyClient)

	scorer := scoring.NewPriorityScorer(0.01)

	strategies := []router.Strategy{
		strategy.NewCapabilityStrategy(),
	}

	engine := internalrouter.New(
		reg,
		strategies,
		scorer,
		store,
		internalrouter.SessionConfig{
			AffinityWeight:  0.10,
			SwitchThreshold: 0.20,
		},
	)

	return engine, nil
}

func serve(httpServer *http.Server) error {
	serverErrors := make(chan error, 1)

	go func() {
		log.Printf(
			"semantic router listening on %s",
			httpServer.Addr,
		)

		if err := httpServer.ListenAndServe(); err != nil &&
			!errors.Is(err, http.ErrServerClosed) {
			serverErrors <- err
		}
	}()

	shutdownSignal := make(chan os.Signal, 1)

	signal.Notify(
		shutdownSignal,
		syscall.SIGINT,
		syscall.SIGTERM,
	)

	defer signal.Stop(shutdownSignal)

	select {
	case err := <-serverErrors:
		return fmt.Errorf(
			"semantic router server failed: %w",
			err,
		)

	case sig := <-shutdownSignal:
		log.Printf(
			"received shutdown signal: %s",
			sig,
		)
	}

	ctx, cancel := context.WithTimeout(
		context.Background(),
		shutdownTimeout,
	)
	defer cancel()

	if err := httpServer.Shutdown(ctx); err != nil {
		return fmt.Errorf(
			"graceful shutdown failed: %w",
			err,
		)
	}

	log.Println("semantic router stopped gracefully")

	return nil
}

func (s *server) health(
	w http.ResponseWriter,
	r *http.Request,
) {
	if r.Method != http.MethodGet {
		http.Error(
			w,
			"method not allowed",
			http.StatusMethodNotAllowed,
		)
		return
	}

	writeJSON(
		w,
		http.StatusOK,
		map[string]string{
			"status":  "ok",
			"service": "semantic-router",
		},
	)
}

func (s *server) ready(
	w http.ResponseWriter,
	r *http.Request,
) {
	if r.Method != http.MethodGet {
		http.Error(
			w,
			"method not allowed",
			http.StatusMethodNotAllowed,
		)
		return
	}

	if err := pingValkey(s.valkeyClient); err != nil {
		log.Printf(
			"readiness check failed: %v",
			err,
		)

		writeJSON(
			w,
			http.StatusServiceUnavailable,
			map[string]string{
				"status":  "not_ready",
				"service": "semantic-router",
				"reason":  "valkey_unavailable",
			},
		)

		return
	}

	writeJSON(
		w,
		http.StatusOK,
		map[string]string{
			"status":  "ready",
			"service": "semantic-router",
		},
	)
}

func (s *server) route(
	w http.ResponseWriter,
	r *http.Request,
) {
	if r.Method != http.MethodPost {
		http.Error(
			w,
			"method not allowed",
			http.StatusMethodNotAllowed,
		)
		return
	}

	r.Body = http.MaxBytesReader(
		w,
		r.Body,
		maxRequestBodySize,
	)

	defer func() {
		if err := r.Body.Close(); err != nil {
			log.Printf(
				"failed to close request body: %v",
				err,
			)
		}
	}()

	var request router.Request

	decoder := json.NewDecoder(r.Body)

	if err := decoder.Decode(&request); err != nil {
		http.Error(
			w,
			"invalid JSON request",
			http.StatusBadRequest,
		)
		return
	}

	if request.SessionID == "" {
		http.Error(
			w,
			"session_id is required",
			http.StatusBadRequest,
		)
		return
	}

	decision, err := s.engine.Route(
		r.Context(),
		request,
	)
	if err != nil {
		switch {
		case errors.Is(
			err,
			router.ErrInvalidRequest,
		):
			http.Error(
				w,
				err.Error(),
				http.StatusBadRequest,
			)

		case errors.Is(
			err,
			router.ErrNoCandidates,
		):
			http.Error(
				w,
				err.Error(),
				http.StatusServiceUnavailable,
			)

		case errors.Is(
			err,
			router.ErrModelNotFound,
		):
			http.Error(
				w,
				err.Error(),
				http.StatusBadRequest,
			)

		case errors.Is(
			err,
			session.ErrVersionConflict,
		):
			http.Error(
				w,
				"routing session conflict",
				http.StatusConflict,
			)

		default:
			log.Printf(
				"routing error: %v",
				err,
			)

			http.Error(
				w,
				"routing failed",
				http.StatusInternalServerError,
			)
		}

		return
	}

	writeJSON(
		w,
		http.StatusOK,
		decision,
	)
}

func writeJSON(
	w http.ResponseWriter,
	status int,
	value any,
) {
	w.Header().Set(
		"Content-Type",
		"application/json",
	)

	w.WriteHeader(status)

	if err := json.NewEncoder(w).Encode(value); err != nil {
		log.Printf(
			"failed to encode response: %v",
			err,
		)
	}
}

func requestLogger(
	next http.Handler,
) http.Handler {
	return http.HandlerFunc(
		func(
			w http.ResponseWriter,
			r *http.Request,
		) {
			start := time.Now()

			next.ServeHTTP(w, r)

			log.Printf(
				"method=%s path=%s duration=%s",
				r.Method,
				r.URL.Path,
				time.Since(start),
			)
		},
	)
}

func getEnv(
	key string,
	fallback string,
) string {
	value := os.Getenv(key)

	if value == "" {
		return fallback
	}

	return value
}
