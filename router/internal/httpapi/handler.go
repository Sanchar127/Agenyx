// Package httpapi provides HTTP handlers for the Agenyx semantic router API.
package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/sanchar127/agenyx/internal/registry"
	"github.com/sanchar127/agenyx/pkg/router"
)

// Handler exposes the Agenyx semantic router over HTTP.
type Handler struct {
	engine   router.Router
	registry *registry.Registry
}

// New creates an HTTP API handler.
func New(
	engine router.Router,
	registry *registry.Registry,
) *Handler {
	return &Handler{
		engine:   engine,
		registry: registry,
	}
}

// RegisterRoutes registers the public HTTP endpoints.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("/health", h.handleHealth)
	mux.HandleFunc("/v1/models", h.handleModels)
	mux.HandleFunc("/v1/router/route", h.handleRoute)
}

type routeRequest struct {
	SessionID   string             `json:"session_id"`
	Messages    []router.Message   `json:"messages"`
	Model       string             `json:"model,omitempty"`
	Task        string             `json:"task,omitempty"`
	Constraints router.Constraints `json:"constraints,omitempty"`
	Metadata    map[string]string  `json:"metadata,omitempty"`
}

type routeResponse struct {
	Model      string             `json:"model"`
	Provider   string             `json:"provider"`
	Score      float64            `json:"score"`
	Strategy   string             `json:"strategy"`
	Candidates []router.Candidate `json:"candidates"`
}

type errorResponse struct {
	Error string `json:"error"`
}

func (h *Handler) handleHealth(
	w http.ResponseWriter,
	r *http.Request,
) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]string{
		"status": "ok",
	})
}

func (h *Handler) handleModels(
	w http.ResponseWriter,
	r *http.Request,
) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"models": h.registry.Enabled(),
	})
}

func (h *Handler) handleRoute(
	w http.ResponseWriter,
	r *http.Request,
) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	defer func() { _ = r.Body.Close() }()

	var input routeRequest

	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()

	if err := decoder.Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON request")
		return
	}

	if len(input.Messages) == 0 {
		writeError(w, http.StatusBadRequest, "messages must not be empty")
		return
	}

	request := router.Request{
		SessionID:   strings.TrimSpace(input.SessionID),
		Messages:    input.Messages,
		Model:       strings.TrimSpace(input.Model),
		Task:        strings.TrimSpace(input.Task),
		Constraints: input.Constraints,
		Metadata:    input.Metadata,
	}

	decision, err := h.engine.Route(r.Context(), request)
	if err != nil {
		status := http.StatusInternalServerError

		switch {
		case errors.Is(err, router.ErrInvalidRequest):
			status = http.StatusBadRequest

		case errors.Is(err, router.ErrNoCandidates):
			status = http.StatusNotFound

		case errors.Is(err, router.ErrModelNotFound):
			status = http.StatusNotFound

		case errors.Is(err, context.Canceled),
			errors.Is(err, context.DeadlineExceeded):
			status = http.StatusRequestTimeout
		}

		writeError(w, status, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, routeResponse{
		Model:      decision.Model,
		Provider:   decision.Provider,
		Score:      decision.Score,
		Strategy:   decision.Strategy,
		Candidates: decision.Candidates,
	})
}

func writeJSON(
	w http.ResponseWriter,
	status int,
	value any,
) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	if err := json.NewEncoder(w).Encode(value); err != nil {
		return
	}
}

func writeError(
	w http.ResponseWriter,
	status int,
	message string,
) {
	writeJSON(w, status, errorResponse{
		Error: message,
	})
}
