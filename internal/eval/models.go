package eval

import (
	"context"
	"time"

	"github.com/google/uuid"
)

// EvaluationType defines the category of an evaluation.
type EvaluationType string

const (
	EvaluationTypeLLM          EvaluationType = "llm"
	EvaluationTypeAgent        EvaluationType = "agent"
	EvaluationTypeTool         EvaluationType = "tool"
	EvaluationTypeOrchestration EvaluationType = "orchestration"
	EvaluationTypeSandbox      EvaluationType = "sandbox"
	EvaluationTypeEndToEnd     EvaluationType = "e2e"
)

// EvaluationStatus defines the lifecycle state of an evaluation.
type EvaluationStatus string

const (
	StatusQueued    EvaluationStatus = "queued"
	StatusRunning   EvaluationStatus = "running"
	StatusCompleted EvaluationStatus = "completed"
	StatusFailed    EvaluationStatus = "failed"
	StatusCancelled EvaluationStatus = "cancelled"
)

// Priority defines the scheduling priority of an evaluation job.
type Priority string

const (
	PriorityLow      Priority = "low"
	PriorityNormal   Priority = "normal"
	PriorityHigh     Priority = "high"
	PriorityCritical Priority = "critical"
)

// Evaluation is the top-level evaluation configuration snapshot.
// It is stored immutably so that the same evaluation can be reproduced later.
type Evaluation struct {
	ID               uuid.UUID      `json:"id" db:"id"`
	Name             string         `json:"name" db:"name"`
	Description      string         `json:"description,omitempty" db:"description"`
	DatasetID        uuid.UUID      `json:"dataset_id" db:"dataset_id"`
	EvaluationType   EvaluationType `json:"evaluation_type" db:"evaluation_type"`
	Status           EvaluationStatus `json:"status" db:"status"`
	Progress         int            `json:"progress" db:"progress"`
	Priority         Priority       `json:"priority" db:"priority"`
	TimeoutSeconds   int            `json:"timeout_seconds" db:"timeout_seconds"`
	MaxConcurrency   int            `json:"max_concurrency" db:"max_concurrency"`
	ConfigSnapshot   map[string]any `json:"config_snapshot" db:"config_snapshot"`
	Metadata         map[string]any `json:"metadata,omitempty" db:"metadata"`
	CreatedBy        string         `json:"created_by,omitempty" db:"created_by"`
	CreatedAt        time.Time      `json:"created_at" db:"created_at"`
	CompletedAt      *time.Time     `json:"completed_at,omitempty" db:"completed_at"`
	ErrorMessage     string         `json:"error_message,omitempty" db:"error_message"`
}

// EvaluationRun is a single model execution within an evaluation.
type EvaluationRun struct {
	ID               uuid.UUID      `json:"id" db:"id"`
	EvaluationID     uuid.UUID      `json:"evaluation_id" db:"evaluation_id"`
	ModelID          string         `json:"model_id" db:"model_id"`
	ProviderID       string         `json:"provider_id" db:"provider_id"`
	Status           EvaluationStatus `json:"status" db:"status"`
	SuccessRate      *float64       `json:"success_rate,omitempty" db:"success_rate"`
	AvgLatencyMS     *int           `json:"avg_latency_ms,omitempty" db:"avg_latency_ms"`
	P50LatencyMS     *int           `json:"p50_latency_ms,omitempty" db:"p50_latency_ms"`
	P95LatencyMS     *int           `json:"p95_latency_ms,omitempty" db:"p95_latency_ms"`
	P99LatencyMS     *int           `json:"p99_latency_ms,omitempty" db:"p99_latency_ms"`
	TotalTokens      *int           `json:"total_tokens,omitempty" db:"total_tokens"`
	TotalCostUSD     *float64       `json:"total_cost_usd,omitempty" db:"total_cost_usd"`
	ErrorCount       *int           `json:"error_count,omitempty" db:"error_count"`
	ConfigSnapshot   map[string]any `json:"config_snapshot" db:"config_snapshot"`
	StartedAt        *time.Time     `json:"started_at,omitempty" db:"started_at"`
	CompletedAt      *time.Time     `json:"completed_at,omitempty" db:"completed_at"`
	ErrorMessage     string         `json:"error_message,omitempty" db:"error_message"`
}

// EvaluationJob is a schedulable unit of work for an evaluation run.
type EvaluationJob struct {
	ID               uuid.UUID      `json:"id" db:"id"`
	EvaluationID     uuid.UUID      `json:"evaluation_id" db:"evaluation_id"`
	RunID            uuid.UUID      `json:"run_id" db:"run_id"`
	WorkerID         *string        `json:"worker_id,omitempty" db:"worker_id"`
	Status           EvaluationStatus `json:"status" db:"status"`
	Attempt          int            `json:"attempt" db:"attempt"`
	MaxAttempts      int            `json:"max_attempts" db:"max_attempts"`
	LeaseExpiresAt   *time.Time     `json:"lease_expires_at,omitempty" db:"lease_expires_at"`
	CreatedAt        time.Time      `json:"created_at" db:"created_at"`
	StartedAt        *time.Time     `json:"started_at,omitempty" db:"started_at"`
	CompletedAt      *time.Time     `json:"completed_at,omitempty" db:"completed_at"`
}

// Model is a registered evaluation model.
type Model struct {
	ModelID          string            `json:"model_id" db:"model_id"`
	ProviderID       string            `json:"provider_id" db:"provider_id"`
	DisplayName      string            `json:"display_name" db:"display_name"`
	ContextWindow    int               `json:"context_window" db:"context_window"`
	Capabilities     []string          `json:"capabilities" db:"capabilities"`
	EndpointConfig   map[string]any    `json:"endpoint_config" db:"endpoint_config"`
	GenerationDefaults map[string]any   `json:"generation_defaults" db:"generation_defaults"`
	TimeoutSeconds   int               `json:"timeout_seconds" db:"timeout_seconds"`
	RetryConfig      map[string]any    `json:"retry_config" db:"retry_config"`
	HealthStatus     string            `json:"health_status" db:"health_status"`
	HealthCheckedAt  *time.Time        `json:"health_checked_at,omitempty" db:"health_checked_at"`
	CreatedAt        time.Time         `json:"created_at" db:"created_at"`
	UpdatedAt        time.Time         `json:"updated_at" db:"updated_at"`
}

// Provider is a registered inference provider.
type Provider struct {
	ProviderID     string            `json:"provider_id" db:"provider_id"`
	DisplayName    string            `json:"display_name" db:"display_name"`
	ProviderType   string            `json:"provider_type" db:"provider_type"`
	EndpointURL    string            `json:"endpoint_url" db:"endpoint_url"`
	AuthRef        string            `json:"auth_ref" db:"auth_ref"`
	Capabilities   []string          `json:"capabilities" db:"capabilities"`
	HealthStatus   string            `json:"health_status" db:"health_status"`
	CreatedAt      time.Time         `json:"created_at" db:"created_at"`
}

// Dataset is a registered evaluation dataset.
type Dataset struct {
	ID          uuid.UUID `json:"id" db:"id"`
	Name        string    `json:"name" db:"name"`
	Version     string    `json:"version" db:"version"`
	Checksum    string    `json:"checksum" db:"checksum"`
	S3URI       string    `json:"s3_uri" db:"s3_uri"`
	RowCount    int       `json:"row_count" db:"row_count"`
	SchemaJSON  map[string]any `json:"schema_json" db:"schema_json"`
	Description string    `json:"description,omitempty" db:"description"`
	CreatedBy   string    `json:"created_by,omitempty" db:"created_by"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
}

// EvaluationScore is a scored metric for a run.
type EvaluationScore struct {
	ID          uuid.UUID `json:"id" db:"id"`
	RunID       uuid.UUID `json:"run_id" db:"run_id"`
	ScorerName  string    `json:"scorer_name" db:"scorer_name"`
	ScoreName   string    `json:"score_name" db:"score_name"`
	ScoreValue  float64   `json:"score_value" db:"score_value"`
	ScoreUnit   string    `json:"score_unit" db:"score_unit"`
	Details     map[string]any `json:"details" db:"details"`
	RecordedAt  time.Time `json:"recorded_at" db:"recorded_at"`
}

// EvaluationArtifact is a stored artifact for a run.
type EvaluationArtifact struct {
	ID          uuid.UUID `json:"id" db:"id"`
	RunID       uuid.UUID `json:"run_id" db:"run_id"`
	ArtifactType string   `json:"artifact_type" db:"artifact_type"`
	S3URI       string    `json:"s3_uri" db:"s3_uri"`
	SizeBytes   int       `json:"size_bytes" db:"size_bytes"`
	Checksum    string    `json:"checksum" db:"checksum"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
}

// WorkerStatus tracks the health and load of an evaluation worker.
type WorkerStatus struct {
	ID          uuid.UUID `json:"id" db:"id"`
	WorkerType  string    `json:"worker_type" db:"worker_type"`
	WorkerName  string    `json:"worker_name" db:"worker_name"`
	Status      string    `json:"status" db:"status"`
	CurrentJobID *uuid.UUID `json:"current_job_id,omitempty" db:"current_job_id"`
	Capacity    int       `json:"capacity" db:"capacity"`
	CurrentLoad int       `json:"current_load" db:"current_load"`
	LastHeartbeat time.Time `json:"last_heartbeat" db:"last_heartbeat"`
	Metadata    map[string]any `json:"metadata" db:"metadata"`
	RegisteredAt time.Time `json:"registered_at" db:"registered_at"`
}

// Benchmark is a runtime benchmark definition.
type Benchmark struct {
	ID              uuid.UUID       `json:"id" db:"id"`
	Name            string          `json:"name" db:"name"`
	BenchmarkType   string          `json:"benchmark_type" db:"benchmark_type"`
	TargetService   string          `json:"target_service" db:"target_service"`
	TargetURL       string          `json:"target_url" db:"target_url"`
	ConfigSnapshot  map[string]any  `json:"config_snapshot" db:"config_snapshot"`
	CreatedBy       string          `json:"created_by,omitempty" db:"created_by"`
	CreatedAt       time.Time       `json:"created_at" db:"created_at"`
}

// BenchmarkRun is a single benchmark execution.
type BenchmarkRun struct {
	ID          uuid.UUID `json:"id" db:"id"`
	BenchmarkID uuid.UUID `json:"benchmark_id" db:"benchmark_id"`
	Status      string    `json:"status" db:"status"`
	ConfigSnapshot map[string]any `json:"config_snapshot" db:"config_snapshot"`
	StartedAt   *time.Time `json:"started_at,omitempty" db:"started_at"`
	CompletedAt *time.Time `json:"completed_at,omitempty" db:"completed_at"`
}

// BenchmarkResult is a single metric measurement from a benchmark run.
type BenchmarkResult struct {
	ID              uuid.UUID `json:"id" db:"id"`
	RunID           uuid.UUID `json:"run_id" db:"run_id"`
	MetricName      string    `json:"metric_name" db:"metric_name"`
	MetricValue     float64   `json:"metric_value" db:"metric_value"`
	MetricUnit      string    `json:"metric_unit" db:"metric_unit"`
	ConcurrencyLevel int      `json:"concurrency_level" db:"concurrency_level"`
	RecordedAt      time.Time `json:"recorded_at" db:"recorded_at"`
}

// ModelComparison is a comparison between model runs.
type ModelComparison struct {
	ID          uuid.UUID `json:"id" db:"id"`
	Name        string    `json:"name" db:"name"`
	Status      string    `json:"status" db:"status"`
	CreatedBy   string    `json:"created_by,omitempty" db:"created_by"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
	CompletedAt *time.Time `json:"completed_at,omitempty" db:"completed_at"`
}

// ComparisonResult is a single metric comparison result.
type ComparisonResult struct {
	ID             uuid.UUID `json:"id" db:"id"`
	ComparisonID   uuid.UUID `json:"comparison_id" db:"comparison_id"`
	MetricName     string    `json:"metric_name" db:"metric_name"`
	Results        map[string]any `json:"results" db:"results"`
	Difference     *float64  `json:"difference,omitempty" db:"difference"`
	Significant    bool      `json:"significant" db:"significant"`
	PValue         *float64  `json:"p_value,omitempty" db:"p_value"`
	RecordedAt     time.Time `json:"recorded_at" db:"recorded_at"`
}

// CreateEvaluationRequest is the request body for creating an evaluation.
type CreateEvaluationRequest struct {
	Name             string                 `json:"name"`
	Description      string                 `json:"description,omitempty"`
	DatasetID        uuid.UUID              `json:"dataset_id"`
	EvaluationType   EvaluationType         `json:"evaluation_type"`
	Models           []ModelConfig          `json:"models"`
	Scorers          []string               `json:"scorers,omitempty"`
	Priority         Priority               `json:"priority,omitempty"`
	TimeoutSeconds   int                    `json:"timeout_seconds,omitempty"`
	MaxConcurrency   int                    `json:"max_concurrency,omitempty"`
	Metadata         map[string]any         `json:"metadata,omitempty"`
}

// ModelConfig configures a single model within an evaluation.
type ModelConfig struct {
	ModelID          string            `json:"model_id"`
	ProviderID       string            `json:"provider_id"`
	GenerationParams map[string]any    `json:"generation_params,omitempty"`
}

// EvaluateResponse is the response for creating an evaluation.
type EvaluateResponse struct {
	EvaluationID         uuid.UUID      `json:"evaluation_id"`
	Status               EvaluationStatus `json:"status"`
	CreatedAt            time.Time      `json:"created_at"`
	EstimatedDurationSec int            `json:"estimated_duration_seconds"`
}

// ListEvaluationsResponse is the paginated list response.
type ListEvaluationsResponse struct {
	Evaluations []Evaluation `json:"evaluations"`
	Pagination  Pagination   `json:"pagination"`
}

// Pagination describes pagination metadata.
type Pagination struct {
	Page       int   `json:"page"`
	PageSize   int   `json:"page_size"`
	Total      int   `json:"total"`
	HasMore    bool  `json:"has_more"`
}

// Store is the data access interface for evaluation entities.
type Store interface {
	// Evaluations
	CreateEvaluation(ctx context.Context, eval *Evaluation) error
	GetEvaluation(ctx context.Context, id uuid.UUID) (*Evaluation, error)
	ListEvaluations(ctx context.Context, filter EvaluationFilter) (*ListEvaluationsResponse, error)
	UpdateEvaluationStatus(ctx context.Context, id uuid.UUID, status EvaluationStatus, progress int, errorMsg string) error

	// Runs
	CreateRun(ctx context.Context, run *EvaluationRun) error
	GetRun(ctx context.Context, id uuid.UUID) (*EvaluationRun, error)
	UpdateRun(ctx context.Context, id uuid.UUID, status EvaluationStatus, result map[string]any) error

	// Jobs
	CreateJob(ctx context.Context, job *EvaluationJob) error
	ClaimJob(ctx context.Context, workerID string, leaseSeconds int) (*EvaluationJob, error)
	CompleteJob(ctx context.Context, id uuid.UUID, status EvaluationStatus) error
	ReleaseJob(ctx context.Context, id uuid.UUID) error

	// Models
	CreateModel(ctx context.Context, m *Model) error
	GetModel(ctx context.Context, id string) (*Model, error)
	ListModels(ctx context.Context) ([]Model, error)

	// Providers
	CreateProvider(ctx context.Context, p *Provider) error
	GetProvider(ctx context.Context, id string) (*Provider, error)
	ListProviders(ctx context.Context) ([]Provider, error)

	// Datasets
	CreateDataset(ctx context.Context, d *Dataset) error
	GetDataset(ctx context.Context, id uuid.UUID) (*Dataset, error)
	ListDatasets(ctx context.Context) ([]Dataset, error)

	// Scores
	CreateScore(ctx context.Context, s *EvaluationScore) error
	ListScores(ctx context.Context, runID uuid.UUID) ([]EvaluationScore, error)

	// Artifacts
	CreateArtifact(ctx context.Context, a *EvaluationArtifact) error
	ListArtifacts(ctx context.Context, runID uuid.UUID) ([]EvaluationArtifact, error)

	// Workers
	RegisterWorker(ctx context.Context, w *WorkerStatus) error
	HeartbeatWorker(ctx context.Context, id uuid.UUID) error
	ListWorkers(ctx context.Context) ([]WorkerStatus, error)

	// Benchmarks
	CreateBenchmark(ctx context.Context, b *Benchmark) error
	GetBenchmark(ctx context.Context, id uuid.UUID) (*Benchmark, error)
	ListBenchmarks(ctx context.Context) ([]Benchmark, error)
	CreateBenchmarkRun(ctx context.Context, run *BenchmarkRun) error
	GetBenchmarkRun(ctx context.Context, id uuid.UUID) (*BenchmarkRun, error)
	ListBenchmarkRuns(ctx context.Context, benchmarkID uuid.UUID) ([]*BenchmarkRun, error)
	CreateBenchmarkResult(ctx context.Context, r *BenchmarkResult) error
	ListBenchmarkResults(ctx context.Context, runID uuid.UUID) ([]BenchmarkResult, error)

	// Model Comparisons
	CreateModelComparison(ctx context.Context, c *ModelComparison) error
	GetModelComparison(ctx context.Context, id uuid.UUID) (*ModelComparison, error)
	ListModelComparisons(ctx context.Context) ([]ModelComparison, error)
	CreateComparisonResult(ctx context.Context, r *ComparisonResult) error
	ListComparisonResults(ctx context.Context, comparisonID uuid.UUID) ([]ComparisonResult, error)
}

// EvaluationFilter is used to filter evaluation list queries.
type EvaluationFilter struct {
	Status           *EvaluationStatus
	EvaluationType   *EvaluationType
	ModelID          *string
	ProviderID       *string
	CreatedAfter     *time.Time
	CreatedBefore    *time.Time
	Page             int
	PageSize         int
}
