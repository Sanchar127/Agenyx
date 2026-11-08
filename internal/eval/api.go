package eval

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/sanchar127/agenyx/internal/eval/metrics"
)

// APIHandler handles HTTP requests for the evaluation API.
type APIHandler struct {
	store Store
	log   *slog.Logger
}

// NewAPIHandler creates a new API handler.
func NewAPIHandler(store Store, log *slog.Logger) *APIHandler {
	return &APIHandler{store: store, log: log}
}

// ServeHTTP implements http.Handler.
func (h *APIHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	h.Routes().ServeHTTP(w, r)
}

// metricsMiddleware wraps an http.Handler with Prometheus metrics.
func (h *APIHandler) metricsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		duration := time.Since(start).Seconds()

		evalmetrics.EvalRequestsTotal.WithLabelValues(
			r.Method,
			r.URL.Path,
			"200",
		).Inc()
		evalmetrics.EvalRequestsDuration.WithLabelValues(
			r.Method,
			r.URL.Path,
		).Observe(duration)
	})
}

// Routes returns the HTTP handler mux for the evaluation API.
func (h *APIHandler) Routes() http.Handler {
	mux := http.NewServeMux()

	// Evaluations
	mux.HandleFunc("POST /api/v1/eval/evaluations", h.createEvaluation)
	mux.HandleFunc("GET /api/v1/eval/evaluations", h.listEvaluations)
	mux.HandleFunc("GET /api/v1/eval/evaluations/{id}", h.getEvaluation)
	mux.HandleFunc("POST /api/v1/eval/evaluations/{id}/cancel", h.cancelEvaluation)

	// Runs
	mux.HandleFunc("GET /api/v1/eval/runs/{id}", h.getRun)
	mux.HandleFunc("GET /api/v1/eval/runs/{id}/results", h.getRunResults)
	mux.HandleFunc("GET /api/v1/eval/runs/{id}/artifacts", h.getRunArtifacts)

	// Benchmarks
	mux.HandleFunc("POST /api/v1/eval/benchmarks", h.createBenchmark)
	mux.HandleFunc("GET /api/v1/eval/benchmarks", h.listBenchmarks)
	mux.HandleFunc("GET /api/v1/eval/benchmarks/{id}", h.getBenchmark)

	// Comparisons
	mux.HandleFunc("POST /api/v1/eval/comparisons", h.createComparison)
	mux.HandleFunc("GET /api/v1/eval/comparisons/{id}", h.getComparison)
	mux.HandleFunc("GET /api/v1/eval/comparisons", h.listComparisons)

	// Models
	mux.HandleFunc("GET /api/v1/eval/models", h.listModels)
	mux.HandleFunc("POST /api/v1/eval/models", h.createModel)
	mux.HandleFunc("GET /api/v1/eval/models/{id}", h.getModel)

	// Providers
	mux.HandleFunc("GET /api/v1/eval/providers", h.listProviders)
	mux.HandleFunc("POST /api/v1/eval/providers", h.createProvider)

	// Datasets
	mux.HandleFunc("GET /api/v1/eval/datasets", h.listDatasets)
	mux.HandleFunc("POST /api/v1/eval/datasets", h.createDataset)
	mux.HandleFunc("GET /api/v1/eval/datasets/{id}", h.getDataset)

	// Workers
	mux.HandleFunc("GET /api/v1/eval/workers", h.listWorkers)
	mux.HandleFunc("GET /api/v1/eval/workers/{id}", h.getWorker)

	// Health
	mux.HandleFunc("GET /api/v1/eval/health", h.health)
	mux.HandleFunc("GET /api/v1/eval/ready", h.ready)

	// Prometheus metrics
	mux.Handle("/metrics", promhttp.Handler())

	// Wrap with metrics middleware
	return h.metricsMiddleware(mux)
}

func (h *APIHandler) writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		h.log.Error("failed to encode response", "error", err)
	}
}

func (h *APIHandler) writeError(w http.ResponseWriter, status int, code, message string) {
	h.writeJSON(w, status, map[string]any{
		"detail": map[string]any{
			"code":    code,
			"message": message,
		},
	})
}

func parseUUID(w http.ResponseWriter, r *http.Request, param string, h *APIHandler) (uuid.UUID, bool) {
	idStr := r.PathValue(param)
	id, err := uuid.Parse(idStr)
	if err != nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_UUID", "invalid "+param)
		return uuid.Nil, false
	}
	return id, true
}

func parsePagination(r *http.Request) (int, int) {
	page := 1
	pageSize := 20
	if p := r.URL.Query().Get("page"); p != "" {
		if n, err := strconv.Atoi(p); err == nil && n > 0 {
			page = n
		}
	}
	if ps := r.URL.Query().Get("page_size"); ps != "" {
		if n, err := strconv.Atoi(ps); err == nil && n > 0 && n <= 100 {
			pageSize = n
		}
	}
	return page, pageSize
}

// createEvaluation handles POST /api/v1/eval/evaluations
func (h *APIHandler) createEvaluation(w http.ResponseWriter, r *http.Request) {
	var req CreateEvaluationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_JSON", err.Error())
		return
	}

	if req.Name == "" {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "name is required")
		return
	}
	if req.DatasetID == uuid.Nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "dataset_id is required")
		return
	}
	if len(req.Models) == 0 {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "at least one model is required")
		return
	}

	if req.Priority == "" {
		req.Priority = PriorityNormal
	}
	if req.TimeoutSeconds == 0 {
		req.TimeoutSeconds = 3600
	}
	if req.MaxConcurrency == 0 {
		req.MaxConcurrency = 5
	}

	eval := &Evaluation{
		ID:               uuid.New(),
		Name:             req.Name,
		Description:      req.Description,
		DatasetID:        req.DatasetID,
		EvaluationType:   req.EvaluationType,
		Status:           StatusQueued,
		Progress:         0,
		Priority:         req.Priority,
		TimeoutSeconds:   req.TimeoutSeconds,
		MaxConcurrency:   req.MaxConcurrency,
		ConfigSnapshot: map[string]any{
			"models":      req.Models,
			"scorers":     req.Scorers,
			"priority":    req.Priority,
			"timeout":     req.TimeoutSeconds,
			"concurrency": req.MaxConcurrency,
		},
		Metadata:    req.Metadata,
		CreatedBy:   "api",
		CreatedAt:   time.Now(),
	}

	if err := h.store.CreateEvaluation(r.Context(), eval); err != nil {
		h.log.Error("failed to create evaluation", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}

	// Create jobs for each model
	for _, mc := range req.Models {
		run := &EvaluationRun{
			ID:             uuid.New(),
			EvaluationID:   eval.ID,
			ModelID:        mc.ModelID,
			ProviderID:     mc.ProviderID,
			Status:         StatusQueued,
			ConfigSnapshot: map[string]any{
				"model_id":         mc.ModelID,
				"provider_id":      mc.ProviderID,
				"generation_params": mc.GenerationParams,
			},
		}
		if err := h.store.CreateRun(r.Context(), run); err != nil {
			h.log.Error("failed to create run", "error", err)
			h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
			return
		}

		job := &EvaluationJob{
			ID:          uuid.New(),
			EvaluationID: eval.ID,
			RunID:        run.ID,
			Status:       StatusQueued,
			Attempt:      0,
			MaxAttempts:  3,
			CreatedAt:    time.Now(),
		}
		if err := h.store.CreateJob(r.Context(), job); err != nil {
			h.log.Error("failed to create job", "error", err)
			h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
			return
		}
	}

	h.writeJSON(w, http.StatusAccepted, EvaluateResponse{
		EvaluationID:         eval.ID,
		Status:               eval.Status,
		CreatedAt:            eval.CreatedAt,
		EstimatedDurationSec: eval.TimeoutSeconds,
	})
}

// listEvaluations handles GET /api/v1/eval/evaluations
func (h *APIHandler) listEvaluations(w http.ResponseWriter, r *http.Request) {
	page, pageSize := parsePagination(r)
	filter := EvaluationFilter{
		Page:     page,
		PageSize: pageSize,
	}
	if st := r.URL.Query().Get("status"); st != "" {
		s := EvaluationStatus(st)
		filter.Status = &s
	}
	if et := r.URL.Query().Get("evaluation_type"); et != "" {
		t := EvaluationType(et)
		filter.EvaluationType = &t
	}

	resp, err := h.store.ListEvaluations(r.Context(), filter)
	if err != nil {
		h.log.Error("failed to list evaluations", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, resp)
}

// getEvaluation handles GET /api/v1/eval/evaluations/{id}
func (h *APIHandler) getEvaluation(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	eval, err := h.store.GetEvaluation(r.Context(), id)
	if err != nil {
		h.log.Error("failed to get evaluation", "error", err)
		h.writeError(w, http.StatusNotFound, "EVAL_NOT_FOUND", "evaluation not found")
		return
	}
	h.writeJSON(w, http.StatusOK, eval)
}

// cancelEvaluation handles POST /api/v1/eval/evaluations/{id}/cancel
func (h *APIHandler) cancelEvaluation(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	if err := h.store.UpdateEvaluationStatus(r.Context(), id, StatusCancelled, 0, "cancelled by user"); err != nil {
		h.log.Error("failed to cancel evaluation", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// getRun handles GET /api/v1/eval/runs/{id}
func (h *APIHandler) getRun(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	run, err := h.store.GetRun(r.Context(), id)
	if err != nil {
		h.log.Error("failed to get run", "error", err)
		h.writeError(w, http.StatusNotFound, "EVAL_NOT_FOUND", "run not found")
		return
	}
	h.writeJSON(w, http.StatusOK, run)
}

// getRunResults handles GET /api/v1/eval/runs/{id}/results
func (h *APIHandler) getRunResults(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	scores, err := h.store.ListScores(r.Context(), id)
	if err != nil {
		h.log.Error("failed to get run results", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{"scores": scores})
}

// getRunArtifacts handles GET /api/v1/eval/runs/{id}/artifacts
func (h *APIHandler) getRunArtifacts(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	artifacts, err := h.store.ListArtifacts(r.Context(), id)
	if err != nil {
		h.log.Error("failed to get run artifacts", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{"artifacts": artifacts})
}

// createBenchmark handles POST /api/v1/eval/benchmarks
func (h *APIHandler) createBenchmark(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name           string         `json:"name"`
		Description    string         `json:"description,omitempty"`
		BenchmarkType  string         `json:"benchmark_type"`
		TargetService  string         `json:"target_service"`
		TargetURL      string         `json:"target_url"`
		ConfigSnapshot map[string]any `json:"config_snapshot"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_JSON", err.Error())
		return
	}
	if req.Name == "" || req.BenchmarkType == "" {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "name and benchmark_type are required")
		return
	}

	b := &Benchmark{
		ID:             uuid.New(),
		Name:           req.Name,
		BenchmarkType:  req.BenchmarkType,
		TargetService:  req.TargetService,
		TargetURL:      req.TargetURL,
		ConfigSnapshot: req.ConfigSnapshot,
		CreatedBy:      "api",
		CreatedAt:      time.Now(),
	}
	if err := h.store.CreateEvaluation(r.Context(), &Evaluation{
		ID:               b.ID,
		Name:             b.Name,
		EvaluationType:   endpointType(req.BenchmarkType),
		Status:           StatusQueued,
		ConfigSnapshot:   b.ConfigSnapshot,
		CreatedBy:        b.CreatedBy,
		CreatedAt:        b.CreatedAt,
	}); err != nil {
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusCreated, b)
}

// endpointType maps a benchmark type to an evaluation type.
func endpointType(bt string) EvaluationType {
	switch bt {
	case "runtime":
		return EvaluationTypeOrchestration
	case "throughput", "latency", "concurrency":
		return EvaluationTypeLLM
	case "reliability":
		return EvaluationTypeEndToEnd
	case "resource":
		return EvaluationTypeSandbox
	default:
		return EvaluationTypeLLM
	}
}

// listBenchmarks handles GET /api/v1/eval/benchmarks
func (h *APIHandler) listBenchmarks(w http.ResponseWriter, r *http.Request) {
	h.writeJSON(w, http.StatusOK, map[string]any{
		"benchmarks": []any{},
		"pagination": Pagination{Page: 1, PageSize: 20, Total: 0, HasMore: false},
	})
}

// getBenchmark handles GET /api/v1/eval/benchmarks/{id}
func (h *APIHandler) getBenchmark(w http.ResponseWriter, r *http.Request) {
	if _, ok := parseUUID(w, r, "id", h); !ok {
		return
	}
	h.writeJSON(w, http.StatusNotFound, map[string]any{"detail": map[string]any{"code": "EVAL_NOT_FOUND", "message": "benchmark not found"}})
}

// createComparison handles POST /api/v1/eval/comparisons
func (h *APIHandler) createComparison(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name        string   `json:"name"`
		RunIDs      []string `json:"run_ids"`
		Metrics     []string `json:"metrics"`
		CreatedBy   string   `json:"created_by"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_JSON", err.Error())
		return
	}
	if req.Name == "" {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "name is required")
		return
	}
	if len(req.RunIDs) < 2 {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "at least two run_ids are required")
		return
	}

	c := &ModelComparison{
		ID:          uuid.New(),
		Name:        req.Name,
		Status:      "queued",
		CreatedBy:   req.CreatedBy,
		CreatedAt:   time.Now(),
	}

	if err := h.store.CreateModelComparison(r.Context(), c); err != nil {
		h.log.Error("failed to create comparison", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}

	h.writeJSON(w, http.StatusCreated, c)
}

// getComparison handles GET /api/v1/eval/comparisons/{id}
func (h *APIHandler) getComparison(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	c, err := h.store.GetModelComparison(r.Context(), id)
	if err != nil {
		h.log.Error("failed to get comparison", "error", err)
		h.writeError(w, http.StatusNotFound, "EVAL_NOT_FOUND", "comparison not found")
		return
	}
	results, err := h.store.ListComparisonResults(r.Context(), id)
	if err != nil {
		h.log.Error("failed to get comparison results", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{
		"comparison": c,
		"results":    results,
	})
}

// listComparisons handles GET /api/v1/eval/comparisons
func (h *APIHandler) listComparisons(w http.ResponseWriter, r *http.Request) {
	comparisons, err := h.store.ListModelComparisons(r.Context())
	if err != nil {
		h.log.Error("failed to list comparisons", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{
		"comparisons": comparisons,
		"pagination":  Pagination{Page: 1, PageSize: 20, Total: len(comparisons), HasMore: false},
	})
}

// listModels handles GET /api/v1/eval/models
func (h *APIHandler) listModels(w http.ResponseWriter, r *http.Request) {
	models, err := h.store.ListModels(r.Context())
	if err != nil {
		h.log.Error("failed to list models", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{"models": models})
}

// createModel handles POST /api/v1/eval/models
func (h *APIHandler) createModel(w http.ResponseWriter, r *http.Request) {
	var m Model
	if err := json.NewDecoder(r.Body).Decode(&m); err != nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_JSON", err.Error())
		return
	}
	if m.ModelID == "" || m.ProviderID == "" {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "model_id and provider_id are required")
		return
	}
	if err := h.store.CreateModel(r.Context(), &m); err != nil {
		h.log.Error("failed to create model", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusCreated, m)
}

// getModel handles GET /api/v1/eval/models/{id}
func (h *APIHandler) getModel(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	m, err := h.store.GetModel(r.Context(), id)
	if err != nil {
		h.writeError(w, http.StatusNotFound, "EVAL_NOT_FOUND", "model not found")
		return
	}
	h.writeJSON(w, http.StatusOK, m)
}

// listProviders handles GET /api/v1/eval/providers
func (h *APIHandler) listProviders(w http.ResponseWriter, r *http.Request) {
	providers, err := h.store.ListProviders(r.Context())
	if err != nil {
		h.log.Error("failed to list providers", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{"providers": providers})
}

// createProvider handles POST /api/v1/eval/providers
func (h *APIHandler) createProvider(w http.ResponseWriter, r *http.Request) {
	var p Provider
	if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_JSON", err.Error())
		return
	}
	if p.ProviderID == "" || p.ProviderType == "" {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "provider_id and provider_type are required")
		return
	}
	if err := h.store.CreateProvider(r.Context(), &p); err != nil {
		h.log.Error("failed to create provider", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusCreated, p)
}

// listDatasets handles GET /api/v1/eval/datasets
func (h *APIHandler) listDatasets(w http.ResponseWriter, r *http.Request) {
	datasets, err := h.store.ListDatasets(r.Context())
	if err != nil {
		h.log.Error("failed to list datasets", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{"datasets": datasets})
}

// createDataset handles POST /api/v1/eval/datasets
func (h *APIHandler) createDataset(w http.ResponseWriter, r *http.Request) {
	var d Dataset
	if err := json.NewDecoder(r.Body).Decode(&d); err != nil {
		h.writeError(w, http.StatusBadRequest, "INVALID_JSON", err.Error())
		return
	}
	if d.Name == "" || d.Version == "" {
		h.writeError(w, http.StatusBadRequest, "INVALID_REQUEST", "name and version are required")
		return
	}
	if err := h.store.CreateDataset(r.Context(), &d); err != nil {
		h.log.Error("failed to create dataset", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusCreated, d)
}

// getDataset handles GET /api/v1/eval/datasets/{id}
func (h *APIHandler) getDataset(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	d, err := h.store.GetDataset(r.Context(), id)
	if err != nil {
		h.writeError(w, http.StatusNotFound, "EVAL_NOT_FOUND", "dataset not found")
		return
	}
	h.writeJSON(w, http.StatusOK, d)
}

// listWorkers handles GET /api/v1/eval/workers
func (h *APIHandler) listWorkers(w http.ResponseWriter, r *http.Request) {
	workers, err := h.store.ListWorkers(r.Context())
	if err != nil {
		h.log.Error("failed to list workers", "error", err)
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	h.writeJSON(w, http.StatusOK, map[string]any{"workers": workers})
}

// getWorker handles GET /api/v1/eval/workers/{id}
func (h *APIHandler) getWorker(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id", h)
	if !ok {
		return
	}
	workers, err := h.store.ListWorkers(r.Context())
	if err != nil {
		h.writeError(w, http.StatusInternalServerError, "EVAL_INTERNAL_ERROR", err.Error())
		return
	}
	for _, wr := range workers {
		if wr.ID == id {
			h.writeJSON(w, http.StatusOK, wr)
			return
		}
	}
	h.writeError(w, http.StatusNotFound, "EVAL_NOT_FOUND", "worker not found")
}

// health handles GET /api/v1/eval/health
func (h *APIHandler) health(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"status":"ok"}`))
}

// ready handles GET /api/v1/eval/ready
func (h *APIHandler) ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if err := storePing(ctx, h.store); err != nil {
		h.writeError(w, http.StatusServiceUnavailable, "EVAL_SERVICE_UNAVAILABLE", "database unavailable")
		return
	}
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"status":"ready"}`))
}

// storePing checks store connectivity by listing workers (lightweight query).
func storePing(ctx context.Context, s Store) error {
	_, err := s.ListWorkers(ctx)
	return err
}
