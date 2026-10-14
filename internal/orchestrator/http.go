package orchestrator

import (
	"encoding/json"
	"errors"
	"net/http"
)

type runRequest struct {
	Intent string `json:"intent"`
}

// HTTPHandler exposes the orchestrator's execution API.
func HTTPHandler(service *Service) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("POST /v1/agent/run", func(w http.ResponseWriter, r *http.Request) {
		var request runRequest

		decoder := json.NewDecoder(r.Body)
		if err := decoder.Decode(&request); err != nil {
			writeError(w, http.StatusUnprocessableEntity, "Invalid request body")
			return
		}

		result, err := service.Run(r.Context(), request.Intent)
		if err != nil {
			switch {
			case errors.Is(err, ErrInvalidIntent):
				writeError(w, http.StatusUnprocessableEntity, "Intent must not be empty")
			case errors.Is(err, ErrQueueUnavailable):
				writeError(w, http.StatusServiceUnavailable, "Execution state unavailable")
			default:
				writeError(w, http.StatusInternalServerError, "Internal server error")
			}
			return
		}

		writeJSON(w, http.StatusAccepted, result)
	})

	mux.HandleFunc("GET /v1/agent/runs/{execution_id}", func(w http.ResponseWriter, r *http.Request) {
		executionID := r.PathValue("execution_id")

		state, err := service.GetExecution(r.Context(), executionID)
		if err != nil {
			switch {
			case errors.Is(err, ErrExecutionNotFound):
				writeError(w, http.StatusNotFound, "Execution not found")
			case errors.Is(err, ErrStateUnavailable):
				writeError(w, http.StatusServiceUnavailable, "Execution state unavailable")
			default:
				writeError(w, http.StatusInternalServerError, "Internal server error")
			}
			return
		}

		writeJSON(w, http.StatusOK, state)
	})

	return mux
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, status int, detail string) {
	writeJSON(w, status, map[string]string{
		"detail": detail,
	})
}
