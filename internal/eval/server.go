package eval

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"time"
)

// Server runs the evaluation HTTP API server.
type Server struct {
	addr    string
	handler http.Handler
	server  *http.Server
	log     *slog.Logger
}

// NewServer creates a new evaluation API server.
func NewServer(cfg Config, handler http.Handler, log *slog.Logger) *Server {
	return &Server{
		addr:    cfg.APIAddr,
		handler: handler,
		log:     log,
	}
}

// Start starts the HTTP server and blocks until ctx is done.
func (s *Server) Start(ctx context.Context) error {
	s.server = &http.Server{
		Addr:         s.addr,
		Handler:      s.handler,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// Graceful shutdown on context cancellation
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := s.server.Shutdown(shutdownCtx); err != nil {
			s.log.Error("server shutdown failed", "error", err)
		}
	}()

	s.log.Info("evaluation API server starting", "addr", s.addr)
	if err := s.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("server failed: %w", err)
	}
	return nil
}

// Run starts the API server and scheduler, handling OS signals for shutdown.
func Run(cfg Config, store Store, log *slog.Logger) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	// Initialize OpenTelemetry
	tp, err := NewTracerProvider("evaluation")
	if err != nil {
		log.Warn("failed to initialize OpenTelemetry", "error", err)
	} else {
		defer tp.Shutdown(context.Background())
	}

	handler := NewAPIHandler(store, log)
	server := NewServer(cfg, handler, log)
	scheduler := NewScheduler(store, cfg, log)

	// Start scheduler in background
	go func() {
		if err := scheduler.Start(ctx); err != nil && err != context.Canceled {
			log.Error("scheduler exited", "error", err)
		}
	}()

	// Start API server
	if err := server.Start(ctx); err != nil {
		return err
	}
	return nil
}
