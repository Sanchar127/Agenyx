package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/sanchar127/agenyx/internal/gateway"
	"github.com/sanchar127/agenyx/internal/guardrails"
	"github.com/sanchar127/agenyx/internal/orchestrator"
	taskworker "github.com/sanchar127/agenyx/internal/worker"
)

func main() {
	logger := log.New(os.Stdout, "", 0)

	// Validate the effective input guardrails configuration before starting
	// infrastructure or accepting agent requests.
	guardrailsConfig, err := guardrails.LoadFromEnv()
	if err != nil {
		logger.Fatalf("initialize input guardrails: %v", err)
	}

	guardrailsSpec := guardrailsConfig.Spec()
	logger.Printf(
		"input guardrails configuration loaded: recipe=%s version=%s path=%s enabled=%t",
		guardrailsConfig.Name(),
		guardrailsConfig.Version(),
		guardrailsConfig.Path(),
		guardrailsSpec.Input.Enabled,
	)

	queue, err := orchestrator.NewValkeyQueueFromEnv()
	if err != nil {
		logger.Fatalf("initialize Valkey queue: %v", err)
	}
	defer func() {
		if err := queue.Close(); err != nil {
			logger.Printf("close Valkey queue: %v", err)
		}
	}()

	service := orchestrator.NewService(queue)

	// The worker has its own Valkey client but shares the task stream
	// and execution-state keys with the orchestrator.
	taskWorker, err := taskworker.NewFromEnv(logger)
	if err != nil {
		logger.Fatalf("initialize task worker: %v", err)
	}
	defer func() {
		if err := taskWorker.Close(); err != nil {
			logger.Printf("close task worker: %v", err)
		}
	}()

	server, err := gateway.NewGatewayServerWithOrchestrator(logger, service)
	if err != nil {
		logger.Fatalf("initialize gateway: %v", err)
	}

	httpsServer := &http.Server{
		Addr:              ":443",
		Handler:           server.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		// Streaming responses may outlast a fixed write deadline.
		WriteTimeout: 0,
		IdleTimeout:  60 * time.Second,
	}

	httpServer := &http.Server{
		Addr:              ":80",
		Handler:           http.HandlerFunc(redirectHTTPS),
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	// Run the worker in this same process. A worker startup failure
	// cancels the application context so the gateway shuts down too.
	go func() {
		logger.Println(`{"event":"task_worker_starting"}`)
		if err := taskWorker.Run(ctx); err != nil && ctx.Err() == nil {
			logger.Printf("task worker stopped unexpectedly: %v", err)
			stop()
		}
	}()

	errorsChannel := make(chan error, 2)

	go func() {
		logger.Println(`{"event":"https_server_starting","address":":443"}`)
		errorsChannel <- httpsServer.ListenAndServeTLS(
			"/etc/agenyx/certs/agenyx.crt",
			"/etc/agenyx/certs/agenyx.key",
		)
	}()

	go func() {
		logger.Println(`{"event":"http_redirect_server_starting","address":":80"}`)
		errorsChannel <- httpServer.ListenAndServe()
	}()

	select {
	case <-ctx.Done():
		logger.Println(`{"event":"gateway_shutdown_started"}`)
	case err := <-errorsChannel:
		if err != nil &&
			!errors.Is(err, http.ErrServerClosed) {
			logger.Printf("gateway server error: %v", err)
			stop()
		}
	}

	shutdownCtx, cancel := context.WithTimeout(
		context.Background(),
		10*time.Second,
	)
	defer cancel()

	if err := httpsServer.Shutdown(shutdownCtx); err != nil {
		logger.Printf("HTTPS shutdown error: %v", err)
	}

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		logger.Printf("HTTP shutdown error: %v", err)
	}
}

func redirectHTTPS(w http.ResponseWriter, r *http.Request) {
	target := "https://" + r.Host + r.URL.RequestURI()
	http.Redirect(w, r, target, http.StatusMovedPermanently)
}
