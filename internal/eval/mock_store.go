package eval

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
)

// MockStore is an in-memory implementation of Store for testing and development.
type MockStore struct {
	mu            sync.RWMutex
	evaluations   map[uuid.UUID]*Evaluation
	runs          map[uuid.UUID]*EvaluationRun
	jobs          map[uuid.UUID]*EvaluationJob
	models        map[string]*Model
	providers     map[string]*Provider
	datasets      map[uuid.UUID]*Dataset
	scores        map[uuid.UUID][]EvaluationScore
	artifacts     map[uuid.UUID][]EvaluationArtifact
	workers       map[uuid.UUID]*WorkerStatus
	comparisons   map[uuid.UUID]*ModelComparison
	comparisonResults map[uuid.UUID][]ComparisonResult
}

// NewMockStore creates a new in-memory store.
func NewMockStore() *MockStore {
	return &MockStore{
		evaluations:        make(map[uuid.UUID]*Evaluation),
		runs:               make(map[uuid.UUID]*EvaluationRun),
		jobs:               make(map[uuid.UUID]*EvaluationJob),
		models:             make(map[string]*Model),
		providers:          make(map[string]*Provider),
		datasets:           make(map[uuid.UUID]*Dataset),
		scores:             make(map[uuid.UUID][]EvaluationScore),
		artifacts:          make(map[uuid.UUID][]EvaluationArtifact),
		workers:            make(map[uuid.UUID]*WorkerStatus),
		comparisons:        make(map[uuid.UUID]*ModelComparison),
		comparisonResults:  make(map[uuid.UUID][]ComparisonResult),
	}
}

// CreateEvaluation stores a new evaluation.
func (s *MockStore) CreateEvaluation(ctx context.Context, eval *Evaluation) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.evaluations[eval.ID] = eval
	return nil
}

// GetEvaluation retrieves an evaluation by ID.
func (s *MockStore) GetEvaluation(ctx context.Context, id uuid.UUID) (*Evaluation, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	eval, ok := s.evaluations[id]
	if !ok {
		return nil, fmt.Errorf("evaluation %s not found", id)
	}
	return eval, nil
}

// ListEvaluations returns evaluations with optional filtering.
func (s *MockStore) ListEvaluations(ctx context.Context, filter EvaluationFilter) (*ListEvaluationsResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var result []Evaluation
	for _, e := range s.evaluations {
		if filter.Status != nil && e.Status != *filter.Status {
			continue
		}
		if filter.EvaluationType != nil && e.EvaluationType != *filter.EvaluationType {
			continue
		}
		result = append(result, *e)
	}

	page := filter.Page
	if page < 1 {
		page = 1
	}
	pageSize := filter.PageSize
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}

	start := (page - 1) * pageSize
	if start >= len(result) {
		return &ListEvaluationsResponse{
			Evaluations: []Evaluation{},
			Pagination:  Pagination{Page: page, PageSize: pageSize, Total: len(result), HasMore: false},
		}, nil
	}

	end := start + pageSize
	if end > len(result) {
		end = len(result)
	}

	return &ListEvaluationsResponse{
		Evaluations: result[start:end],
		Pagination:  Pagination{Page: page, PageSize: pageSize, Total: len(result), HasMore: end < len(result)},
	}, nil
}

// UpdateEvaluationStatus updates evaluation status.
func (s *MockStore) UpdateEvaluationStatus(ctx context.Context, id uuid.UUID, status EvaluationStatus, progress int, errorMsg string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	eval, ok := s.evaluations[id]
	if !ok {
		return fmt.Errorf("evaluation %s not found", id)
	}
	eval.Status = status
	eval.Progress = progress
	eval.ErrorMessage = errorMsg
	if status == StatusCompleted || status == StatusFailed || status == StatusCancelled {
		now := time.Now()
		eval.CompletedAt = &now
	}
	return nil
}

// CreateRun creates an evaluation run.
func (s *MockStore) CreateRun(ctx context.Context, run *EvaluationRun) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runs[run.ID] = run
	return nil
}

// GetRun retrieves a run by ID.
func (s *MockStore) GetRun(ctx context.Context, id uuid.UUID) (*EvaluationRun, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	run, ok := s.runs[id]
	if !ok {
		return nil, fmt.Errorf("run %s not found", id)
	}
	return run, nil
}

// UpdateRun updates a run's status and results.
func (s *MockStore) UpdateRun(ctx context.Context, id uuid.UUID, status EvaluationStatus, result map[string]any) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	run, ok := s.runs[id]
	if !ok {
		return fmt.Errorf("run %s not found", id)
	}
	run.Status = status
	now := time.Now()
	run.CompletedAt = &now
	return nil
}

// CreateJob creates a job.
func (s *MockStore) CreateJob(ctx context.Context, job *EvaluationJob) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.jobs[job.ID] = job
	return nil
}

// ClaimJob claims the next queued job.
func (s *MockStore) ClaimJob(ctx context.Context, workerID string, leaseSeconds int) (*EvaluationJob, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, job := range s.jobs {
		if job.Status == StatusQueued {
			job.Status = StatusRunning
			job.WorkerID = &workerID
			now := time.Now()
			job.LeaseExpiresAt = &now
			job.Attempt++
			return job, nil
		}
	}
	return nil, fmt.Errorf("no jobs available")
}

// CompleteJob marks a job complete.
func (s *MockStore) CompleteJob(ctx context.Context, id uuid.UUID, status EvaluationStatus) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.jobs[id]
	if !ok {
		return fmt.Errorf("job %s not found", id)
	}
	job.Status = status
	now := time.Now()
	job.CompletedAt = &now
	return nil
}

// ReleaseJob releases a job back to queued.
func (s *MockStore) ReleaseJob(ctx context.Context, id uuid.UUID) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.jobs[id]
	if !ok {
		return fmt.Errorf("job %s not found", id)
	}
	job.Status = StatusQueued
	job.WorkerID = nil
	job.LeaseExpiresAt = nil
	return nil
}

// CreateModel registers a model.
func (s *MockStore) CreateModel(ctx context.Context, m *Model) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.models[m.ModelID] = m
	return nil
}

// GetModel retrieves a model.
func (s *MockStore) GetModel(ctx context.Context, id string) (*Model, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	m, ok := s.models[id]
	if !ok {
		return nil, fmt.Errorf("model %s not found", id)
	}
	return m, nil
}

// ListModels returns all models.
func (s *MockStore) ListModels(ctx context.Context) ([]Model, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []Model
	for _, m := range s.models {
		result = append(result, *m)
	}
	return result, nil
}

// CreateProvider registers a provider.
func (s *MockStore) CreateProvider(ctx context.Context, p *Provider) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.providers[p.ProviderID] = p
	return nil
}

// GetProvider retrieves a provider.
func (s *MockStore) GetProvider(ctx context.Context, id string) (*Provider, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	p, ok := s.providers[id]
	if !ok {
		return nil, fmt.Errorf("provider %s not found", id)
	}
	return p, nil
}

// ListProviders returns all providers.
func (s *MockStore) ListProviders(ctx context.Context) ([]Provider, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []Provider
	for _, p := range s.providers {
		result = append(result, *p)
	}
	return result, nil
}

// CreateDataset registers a dataset.
func (s *MockStore) CreateDataset(ctx context.Context, d *Dataset) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.datasets[d.ID] = d
	return nil
}

// GetDataset retrieves a dataset.
func (s *MockStore) GetDataset(ctx context.Context, id uuid.UUID) (*Dataset, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	d, ok := s.datasets[id]
	if !ok {
		return nil, fmt.Errorf("dataset %s not found", id)
	}
	return d, nil
}

// ListDatasets returns all datasets.
func (s *MockStore) ListDatasets(ctx context.Context) ([]Dataset, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []Dataset
	for _, d := range s.datasets {
		result = append(result, *d)
	}
	return result, nil
}

// CreateScore persists an evaluation score for a run.
func (s *MockStore) CreateScore(ctx context.Context, score *EvaluationScore) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.scores[score.RunID] = append(s.scores[score.RunID], *score)
	return nil
}

// ListScores returns scores for a run.
func (s *MockStore) ListScores(ctx context.Context, runID uuid.UUID) ([]EvaluationScore, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.scores[runID], nil
}

// CreateArtifact persists an evaluation artifact reference.
func (s *MockStore) CreateArtifact(ctx context.Context, artifact *EvaluationArtifact) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.artifacts[artifact.RunID] = append(s.artifacts[artifact.RunID], *artifact)
	return nil
}

// ListArtifacts returns artifacts for a run.
func (s *MockStore) ListArtifacts(ctx context.Context, runID uuid.UUID) ([]EvaluationArtifact, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.artifacts[runID], nil
}

// RegisterWorker registers a worker.
func (s *MockStore) RegisterWorker(ctx context.Context, w *WorkerStatus) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.workers[w.ID] = w
	return nil
}

// HeartbeatWorker updates worker heartbeat.
func (s *MockStore) HeartbeatWorker(ctx context.Context, id uuid.UUID) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	w, ok := s.workers[id]
	if !ok {
		return fmt.Errorf("worker %s not found", id)
	}
	w.LastHeartbeat = time.Now()
	w.Status = "active"
	return nil
}

// ListWorkers returns all workers.
func (s *MockStore) ListWorkers(ctx context.Context) ([]WorkerStatus, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []WorkerStatus
	for _, w := range s.workers {
		result = append(result, *w)
	}
	return result, nil
}

// CreateBenchmark creates a benchmark definition.
func (s *MockStore) CreateBenchmark(ctx context.Context, b *Benchmark) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.comparisons[b.ID] = &ModelComparison{
		ID:          b.ID,
		Name:        b.Name,
		Status:      "queued",
		CreatedBy:   b.CreatedBy,
		CreatedAt:   b.CreatedAt,
	}
	return nil
}

// GetBenchmark retrieves a benchmark definition.
func (s *MockStore) GetBenchmark(ctx context.Context, id uuid.UUID) (*Benchmark, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	c, ok := s.comparisons[id]
	if !ok {
		return nil, fmt.Errorf("benchmark %s not found", id)
	}
	return &Benchmark{
		ID:           c.ID,
		Name:         c.Name,
		BenchmarkType: c.Status,
		TargetService: "",
		TargetURL:     "",
		ConfigSnapshot: map[string]any{},
		CreatedBy:     c.CreatedBy,
		CreatedAt:     c.CreatedAt,
	}, nil
}

// ListBenchmarks returns all benchmarks.
func (s *MockStore) ListBenchmarks(ctx context.Context) ([]Benchmark, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []Benchmark
	for _, c := range s.comparisons {
		result = append(result, Benchmark{
			ID:           c.ID,
			Name:         c.Name,
			BenchmarkType: c.Status,
		})
	}
	return result, nil
}

// CreateBenchmarkRun creates a benchmark run.
func (s *MockStore) CreateBenchmarkRun(ctx context.Context, run *BenchmarkRun) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return nil
}

// GetBenchmarkRun retrieves a benchmark run.
func (s *MockStore) GetBenchmarkRun(ctx context.Context, id uuid.UUID) (*BenchmarkRun, error) {
	return nil, fmt.Errorf("not implemented")
}

// ListBenchmarkRuns lists benchmark runs.
func (s *MockStore) ListBenchmarkRuns(ctx context.Context, benchmarkID uuid.UUID) ([]*BenchmarkRun, error) {
	return nil, nil
}

// CreateBenchmarkResult creates a benchmark result.
func (s *MockStore) CreateBenchmarkResult(ctx context.Context, r *BenchmarkResult) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return nil
}

// ListBenchmarkResults lists benchmark results.
func (s *MockStore) ListBenchmarkResults(ctx context.Context, runID uuid.UUID) ([]BenchmarkResult, error) {
	return nil, nil
}

// CreateModelComparison creates a model comparison.
func (s *MockStore) CreateModelComparison(ctx context.Context, c *ModelComparison) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.comparisons[c.ID] = c
	return nil
}

// GetModelComparison retrieves a comparison by ID.
func (s *MockStore) GetModelComparison(ctx context.Context, id uuid.UUID) (*ModelComparison, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	c, ok := s.comparisons[id]
	if !ok {
		return nil, fmt.Errorf("comparison %s not found", id)
	}
	return c, nil
}

// ListModelComparisons returns all model comparisons.
func (s *MockStore) ListModelComparisons(ctx context.Context) ([]ModelComparison, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []ModelComparison
	for _, c := range s.comparisons {
		result = append(result, *c)
	}
	return result, nil
}

// CreateComparisonResult creates a comparison result.
func (s *MockStore) CreateComparisonResult(ctx context.Context, r *ComparisonResult) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.comparisonResults[r.ComparisonID] = append(s.comparisonResults[r.ComparisonID], *r)
	return nil
}

// ListComparisonResults returns comparison results for a comparison.
func (s *MockStore) ListComparisonResults(ctx context.Context, comparisonID uuid.UUID) ([]ComparisonResult, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.comparisonResults[comparisonID], nil
}
