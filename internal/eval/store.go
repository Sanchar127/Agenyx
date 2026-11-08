package eval

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// store is the PostgreSQL implementation of the Store interface.
type store struct {
	db DB
}

// DB is the database abstraction used by the store. It is kept minimal so
// the store can be tested with a mock or a real sqlx/database connection.
type DB interface {
	ExecContext(ctx context.Context, query string, args ...any) (Result, error)
	QueryContext(ctx context.Context, query string, args ...any) (Rows, error)
	QueryRowContext(ctx context.Context, query string, args ...any) Row
}

// Result represents a database exec result.
type Result interface {
	LastInsertId() (int64, error)
	RowsAffected() (int64, error)
}

// Rows represents a database query result.
type Rows interface {
	Next() bool
	Scan(...any) error
	Err() error
	Close() error
}

// Row represents a single database row.
type Row interface {
	Scan(...any) error
}

// newStore creates a PostgreSQL-backed store.
func newStore(db DB) *store {
	return &store{db: db}
}

// CreateEvaluation persists a new evaluation configuration.
func (s *store) CreateEvaluation(ctx context.Context, eval *Evaluation) error {
	query := `
		INSERT INTO evaluation_evaluations (
			id, name, description, dataset_id, evaluation_type, status,
			progress, priority, timeout_seconds, max_concurrency,
			config_snapshot, metadata, created_by, created_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
	`
	configSnapshot, err := json.Marshal(eval.ConfigSnapshot)
	if err != nil {
		return fmt.Errorf("marshal config_snapshot: %w", err)
	}
	metadata, err := json.Marshal(eval.Metadata)
	if err != nil {
		return fmt.Errorf("marshal metadata: %w", err)
	}

	_, err = s.db.ExecContext(ctx, query,
		eval.ID, eval.Name, eval.Description, eval.DatasetID, eval.EvaluationType,
		eval.Status, eval.Progress, eval.Priority, eval.TimeoutSeconds,
		eval.MaxConcurrency, string(configSnapshot), string(metadata),
		eval.CreatedBy, eval.CreatedAt,
	)
	if err != nil {
		return fmt.Errorf("insert evaluation: %w", err)
	}
	return nil
}

// GetEvaluation retrieves an evaluation by ID.
func (s *store) GetEvaluation(ctx context.Context, id uuid.UUID) (*Evaluation, error) {
	query := `
		SELECT id, name, description, dataset_id, evaluation_type, status,
			progress, priority, timeout_seconds, max_concurrency,
			config_snapshot, metadata, created_by, created_at,
			completed_at, error_message
		FROM evaluation_evaluations WHERE id = $1
	`
	row := s.db.QueryRowContext(ctx, query, id)
	var e Evaluation
	var configSnapshot, metadata []byte
	var completedAt *time.Time
	err := row.Scan(
		&e.ID, &e.Name, &e.Description, &e.DatasetID, &e.EvaluationType, &e.Status,
		&e.Progress, &e.Priority, &e.TimeoutSeconds, &e.MaxConcurrency,
		&configSnapshot, &metadata, &e.CreatedBy, &e.CreatedAt,
		&completedAt, &e.ErrorMessage,
	)
	if err != nil {
		return nil, fmt.Errorf("scan evaluation: %w", err)
	}
	if err := json.Unmarshal(configSnapshot, &e.ConfigSnapshot); err != nil {
		return nil, fmt.Errorf("unmarshal config_snapshot: %w", err)
	}
	if err := json.Unmarshal(metadata, &e.Metadata); err != nil {
		return nil, fmt.Errorf("unmarshal metadata: %w", err)
	}
	e.CompletedAt = completedAt
	return &e, nil
}

// ListEvaluations returns a paginated, filtered list of evaluations.
func (s *store) ListEvaluations(ctx context.Context, filter EvaluationFilter) (*ListEvaluationsResponse, error) {
	// Build WHERE clause
	where := "WHERE 1=1"
	args := []any{}
	argIdx := 1

	if filter.Status != nil {
		where += fmt.Sprintf(" AND status = $%d", argIdx)
		args = append(args, *filter.Status)
		argIdx++
	}
	if filter.EvaluationType != nil {
		where += fmt.Sprintf(" AND evaluation_type = $%d", argIdx)
		args = append(args, *filter.EvaluationType)
		argIdx++
	}
	if filter.CreatedAfter != nil {
		where += fmt.Sprintf(" AND created_at >= $%d", argIdx)
		args = append(args, *filter.CreatedAfter)
		argIdx++
	}
	if filter.CreatedBefore != nil {
		where += fmt.Sprintf(" AND created_at <= $%d", argIdx)
		args = append(args, *filter.CreatedBefore)
		argIdx++
	}

	page := filter.Page
	if page < 1 {
		page = 1
	}
	pageSize := filter.PageSize
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize

	where += fmt.Sprintf(" ORDER BY created_at DESC LIMIT $%d OFFSET $%d", argIdx, argIdx+1)
	args = append(args, pageSize, offset)

	query := `
		SELECT id, name, description, dataset_id, evaluation_type, status,
			progress, priority, timeout_seconds, max_concurrency,
			config_snapshot, metadata, created_by, created_at,
			completed_at, error_message
		FROM evaluation_evaluations ` + where

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("query evaluations: %w", err)
	}
	defer rows.Close()

	var evaluations []Evaluation
	for rows.Next() {
		var e Evaluation
		var configSnapshot, metadata []byte
		var completedAt *time.Time
		if err := rows.Scan(
			&e.ID, &e.Name, &e.Description, &e.DatasetID, &e.EvaluationType, &e.Status,
			&e.Progress, &e.Priority, &e.TimeoutSeconds, &e.MaxConcurrency,
			&configSnapshot, &metadata, &e.CreatedBy, &e.CreatedAt,
			&completedAt, &e.ErrorMessage,
		); err != nil {
			return nil, fmt.Errorf("scan evaluation: %w", err)
		}
		if err := json.Unmarshal(configSnapshot, &e.ConfigSnapshot); err != nil {
			return nil, fmt.Errorf("unmarshal config_snapshot: %w", err)
		}
		if err := json.Unmarshal(metadata, &e.Metadata); err != nil {
			return nil, fmt.Errorf("unmarshal metadata: %w", err)
		}
		e.CompletedAt = completedAt
		evaluations = append(evaluations, e)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate evaluations: %w", err)
	}

	return &ListEvaluationsResponse{
		Evaluations: evaluations,
		Pagination: Pagination{
			Page:     page,
			PageSize: pageSize,
			HasMore:  len(evaluations) == pageSize,
		},
	}, nil
}

// UpdateEvaluationStatus updates the status and progress of an evaluation.
func (s *store) UpdateEvaluationStatus(ctx context.Context, id uuid.UUID, status EvaluationStatus, progress int, errorMsg string) error {
	query := `
		UPDATE evaluation_evaluations
		SET status = $1, progress = $2, error_message = $3
		WHERE id = $4
	`
	_, err := s.db.ExecContext(ctx, query, status, progress, errorMsg, id)
	if err != nil {
		return fmt.Errorf("update evaluation status: %w", err)
	}
	return nil
}

// CreateRun persists a new evaluation run.
func (s *store) CreateRun(ctx context.Context, run *EvaluationRun) error {
	query := `
		INSERT INTO evaluation_runs (
			id, evaluation_id, model_id, provider_id, status,
			success_rate, avg_latency_ms, p50_latency_ms, p95_latency_ms,
			p99_latency_ms, total_tokens, total_cost_usd, error_count,
			config_snapshot, started_at, completed_at, error_message
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
	`
	configSnapshot, err := json.Marshal(run.ConfigSnapshot)
	if err != nil {
		return fmt.Errorf("marshal config_snapshot: %w", err)
	}

	_, err = s.db.ExecContext(ctx, query,
		run.ID, run.EvaluationID, run.ModelID, run.ProviderID, run.Status,
		run.SuccessRate, run.AvgLatencyMS, run.P50LatencyMS, run.P95LatencyMS,
		run.P99LatencyMS, run.TotalTokens, run.TotalCostUSD, run.ErrorCount,
		string(configSnapshot), run.StartedAt, run.CompletedAt, run.ErrorMessage,
	)
	if err != nil {
		return fmt.Errorf("insert run: %w", err)
	}
	return nil
}

// GetRun retrieves an evaluation run by ID.
func (s *store) GetRun(ctx context.Context, id uuid.UUID) (*EvaluationRun, error) {
	query := `
		SELECT id, evaluation_id, model_id, provider_id, status,
			success_rate, avg_latency_ms, p50_latency_ms, p95_latency_ms,
			p99_latency_ms, total_tokens, total_cost_usd, error_count,
			config_snapshot, started_at, completed_at, error_message
		FROM evaluation_runs WHERE id = $1
	`
	row := s.db.QueryRowContext(ctx, query, id)
	var run EvaluationRun
	var configSnapshot []byte
	err := row.Scan(
		&run.ID, &run.EvaluationID, &run.ModelID, &run.ProviderID, &run.Status,
		&run.SuccessRate, &run.AvgLatencyMS, &run.P50LatencyMS, &run.P95LatencyMS,
		&run.P99LatencyMS, &run.TotalTokens, &run.TotalCostUSD, &run.ErrorCount,
		&configSnapshot, &run.StartedAt, &run.CompletedAt, &run.ErrorMessage,
	)
	if err != nil {
		return nil, fmt.Errorf("scan run: %w", err)
	}
	if err := json.Unmarshal(configSnapshot, &run.ConfigSnapshot); err != nil {
		return nil, fmt.Errorf("unmarshal config_snapshot: %w", err)
	}
	return &run, nil
}

// UpdateRun updates the status and results of an evaluation run.
func (s *store) UpdateRun(ctx context.Context, id uuid.UUID, status EvaluationStatus, result map[string]any) error {
	query := `
		UPDATE evaluation_runs
		SET status = $1, completed_at = $2
		WHERE id = $3
	`
	_, err := s.db.ExecContext(ctx, query, status, time.Now(), id)
	if err != nil {
		return fmt.Errorf("update run: %w", err)
	}
	return nil
}

// CreateJob creates a new evaluation job.
func (s *store) CreateJob(ctx context.Context, job *EvaluationJob) error {
	query := `
		INSERT INTO evaluation_jobs (
			id, evaluation_id, run_id, worker_id, status,
			attempt, max_attempts, lease_expires_at, created_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
	`
	_, err := s.db.ExecContext(ctx, query,
		job.ID, job.EvaluationID, job.RunID, job.WorkerID, job.Status,
		job.Attempt, job.MaxAttempts, job.LeaseExpiresAt, job.CreatedAt,
	)
	if err != nil {
		return fmt.Errorf("insert job: %w", err)
	}
	return nil
}

// ClaimJob claims the next available job for a worker using lease-based ownership.
func (s *store) ClaimJob(ctx context.Context, workerID string, leaseSeconds int) (*EvaluationJob, error) {
	query := `
		UPDATE evaluation_jobs
		SET status = 'claimed', worker_id = $1,
			lease_expires_at = $2, attempt = attempt + 1
		WHERE id = (
			SELECT id FROM evaluation_jobs
			WHERE status = 'queued'
			ORDER BY created_at ASC
			LIMIT 1
			FOR UPDATE SKIP LOCKED
		)
		RETURNING id, evaluation_id, run_id, worker_id, status, attempt,
			max_attempts, lease_expires_at, created_at, started_at, completed_at
	`
	row := s.db.QueryRowContext(ctx, query, workerID, time.Now().Add(time.Duration(leaseSeconds)*time.Second))
	var job EvaluationJob
	if err := row.Scan(
		&job.ID, &job.EvaluationID, &job.RunID, &job.WorkerID, &job.Status,
		&job.Attempt, &job.MaxAttempts, &job.LeaseExpiresAt, &job.CreatedAt,
		&job.StartedAt, &job.CompletedAt,
	); err != nil {
		return nil, fmt.Errorf("claim job: %w", err)
	}
	return &job, nil
}

// CompleteJob marks a job as completed or failed.
func (s *store) CompleteJob(ctx context.Context, id uuid.UUID, status EvaluationStatus) error {
	query := `
		UPDATE evaluation_jobs
		SET status = $1, completed_at = $2
		WHERE id = $3
	`
	_, err := s.db.ExecContext(ctx, query, status, time.Now(), id)
	if err != nil {
		return fmt.Errorf("complete job: %w", err)
	}
	return nil
}

// ReleaseJob releases a job lease (returns it to queued if not completed).
func (s *store) ReleaseJob(ctx context.Context, id uuid.UUID) error {
	query := `
		UPDATE evaluation_jobs
		SET status = 'queued', worker_id = NULL, lease_expires_at = NULL
		WHERE id = $1 AND status = 'claimed'
	`
	_, err := s.db.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("release job: %w", err)
	}
	return nil
}

// CreateModel registers a new model.
func (s *store) CreateModel(ctx context.Context, m *Model) error {
	query := `
		INSERT INTO evaluation_models (
			model_id, provider_id, display_name, context_window, capabilities,
			endpoint_config, generation_defaults, timeout_seconds, retry_config,
			health_status, created_at, updated_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
	`
	caps, _ := json.Marshal(m.Capabilities)
	endpoint, _ := json.Marshal(m.EndpointConfig)
	genDefaults, _ := json.Marshal(m.GenerationDefaults)
	retry, _ := json.Marshal(m.RetryConfig)
	now := time.Now()

	_, err := s.db.ExecContext(ctx, query,
		m.ModelID, m.ProviderID, m.DisplayName, m.ContextWindow, string(caps),
		string(endpoint), string(genDefaults), m.TimeoutSeconds, string(retry),
		m.HealthStatus, now, now,
	)
	if err != nil {
		return fmt.Errorf("insert model: %w", err)
	}
	return nil
}

// GetModel retrieves a model by ID.
func (s *store) GetModel(ctx context.Context, id string) (*Model, error) {
	query := `
		SELECT model_id, provider_id, display_name, context_window, capabilities,
			endpoint_config, generation_defaults, timeout_seconds, retry_config,
			health_status, health_checked_at, created_at, updated_at
		FROM evaluation_models WHERE model_id = $1
	`
	row := s.db.QueryRowContext(ctx, query, id)
	var m Model
	var caps, endpoint, genDefaults, retry []byte
	var healthCheckedAt *time.Time
	err := row.Scan(
		&m.ModelID, &m.ProviderID, &m.DisplayName, &m.ContextWindow, &caps,
		&endpoint, &genDefaults, &m.TimeoutSeconds, &retry,
		&m.HealthStatus, &healthCheckedAt, &m.CreatedAt, &m.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("scan model: %w", err)
	}
	_ = json.Unmarshal(caps, &m.Capabilities)
	_ = json.Unmarshal(endpoint, &m.EndpointConfig)
	_ = json.Unmarshal(genDefaults, &m.GenerationDefaults)
	_ = json.Unmarshal(retry, &m.RetryConfig)
	m.HealthCheckedAt = healthCheckedAt
	return &m, nil
}

// ListModels returns all registered models.
func (s *store) ListModels(ctx context.Context) ([]Model, error) {
	query := `
		SELECT model_id, provider_id, display_name, context_window, capabilities,
			endpoint_config, generation_defaults, timeout_seconds, retry_config,
			health_status, health_checked_at, created_at, updated_at
		FROM evaluation_models ORDER BY model_id
	`
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query models: %w", err)
	}
	defer rows.Close()

	var models []Model
	for rows.Next() {
		var m Model
		var caps, endpoint, genDefaults, retry []byte
		var healthCheckedAt *time.Time
		if err := rows.Scan(
			&m.ModelID, &m.ProviderID, &m.DisplayName, &m.ContextWindow, &caps,
			&endpoint, &genDefaults, &m.TimeoutSeconds, &retry,
			&m.HealthStatus, &healthCheckedAt, &m.CreatedAt, &m.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan model: %w", err)
		}
		_ = json.Unmarshal(caps, &m.Capabilities)
		_ = json.Unmarshal(endpoint, &m.EndpointConfig)
		_ = json.Unmarshal(genDefaults, &m.GenerationDefaults)
		_ = json.Unmarshal(retry, &m.RetryConfig)
		m.HealthCheckedAt = healthCheckedAt
		models = append(models, m)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate models: %w", err)
	}
	return models, nil
}

// CreateProvider registers a new provider.
func (s *store) CreateProvider(ctx context.Context, p *Provider) error {
	query := `
		INSERT INTO evaluation_providers (
			provider_id, display_name, provider_type, endpoint_url, auth_ref,
			capabilities, health_status, created_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`
	caps, _ := json.Marshal(p.Capabilities)
	_, err := s.db.ExecContext(ctx, query,
		p.ProviderID, p.DisplayName, p.ProviderType, p.EndpointURL,
		p.AuthRef, string(caps), p.HealthStatus, time.Now(),
	)
	if err != nil {
		return fmt.Errorf("insert provider: %w", err)
	}
	return nil
}

// GetProvider retrieves a provider by ID.
func (s *store) GetProvider(ctx context.Context, id string) (*Provider, error) {
	query := `
		SELECT provider_id, display_name, provider_type, endpoint_url, auth_ref,
			capabilities, health_status, created_at
		FROM evaluation_providers WHERE provider_id = $1
	`
	row := s.db.QueryRowContext(ctx, query, id)
	var p Provider
	var caps []byte
	err := row.Scan(
		&p.ProviderID, &p.DisplayName, &p.ProviderType, &p.EndpointURL,
		&p.AuthRef, &caps, &p.HealthStatus, &p.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("scan provider: %w", err)
	}
	_ = json.Unmarshal(caps, &p.Capabilities)
	return &p, nil
}

// ListProviders returns all registered providers.
func (s *store) ListProviders(ctx context.Context) ([]Provider, error) {
	query := `
		SELECT provider_id, display_name, provider_type, endpoint_url, auth_ref,
			capabilities, health_status, created_at
		FROM evaluation_providers ORDER BY provider_id
	`
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query providers: %w", err)
	}
	defer rows.Close()

	var providers []Provider
	for rows.Next() {
		var p Provider
		var caps []byte
		if err := rows.Scan(
			&p.ProviderID, &p.DisplayName, &p.ProviderType, &p.EndpointURL,
			&p.AuthRef, &caps, &p.HealthStatus, &p.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan provider: %w", err)
		}
		_ = json.Unmarshal(caps, &p.Capabilities)
		providers = append(providers, p)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate providers: %w", err)
	}
	return providers, nil
}

// CreateDataset registers a new dataset.
func (s *store) CreateDataset(ctx context.Context, d *Dataset) error {
	query := `
		INSERT INTO evaluation_datasets (
			id, name, version, checksum, s3_uri, row_count, schema_json,
			description, created_by, created_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
	`
	schema, _ := json.Marshal(d.SchemaJSON)
	_, err := s.db.ExecContext(ctx, query,
		d.ID, d.Name, d.Version, d.Checksum, d.S3URI, d.RowCount,
		string(schema), d.Description, d.CreatedBy, d.CreatedAt,
	)
	if err != nil {
		return fmt.Errorf("insert dataset: %w", err)
	}
	return nil
}

// GetDataset retrieves a dataset by ID.
func (s *store) GetDataset(ctx context.Context, id uuid.UUID) (*Dataset, error) {
	query := `
		SELECT id, name, version, checksum, s3_uri, row_count, schema_json,
			description, created_by, created_at
		FROM evaluation_datasets WHERE id = $1
	`
	row := s.db.QueryRowContext(ctx, query, id)
	var d Dataset
	var schema []byte
	err := row.Scan(
		&d.ID, &d.Name, &d.Version, &d.Checksum, &d.S3URI, &d.RowCount,
		&schema, &d.Description, &d.CreatedBy, &d.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("scan dataset: %w", err)
	}
	_ = json.Unmarshal(schema, &d.SchemaJSON)
	return &d, nil
}

// ListDatasets returns all registered datasets.
func (s *store) ListDatasets(ctx context.Context) ([]Dataset, error) {
	query := `
		SELECT id, name, version, checksum, s3_uri, row_count, schema_json,
			description, created_by, created_at
		FROM evaluation_datasets ORDER BY name, version
	`
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query datasets: %w", err)
	}
	defer rows.Close()

	var datasets []Dataset
	for rows.Next() {
		var d Dataset
		var schema []byte
		if err := rows.Scan(
			&d.ID, &d.Name, &d.Version, &d.Checksum, &d.S3URI, &d.RowCount,
			&schema, &d.Description, &d.CreatedBy, &d.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan dataset: %w", err)
		}
		_ = json.Unmarshal(schema, &d.SchemaJSON)
		datasets = append(datasets, d)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate datasets: %w", err)
	}
	return datasets, nil
}

// CreateScore persists an evaluation score for a run.
func (s *store) CreateScore(ctx context.Context, score *EvaluationScore) error {
	query := `
		INSERT INTO evaluation_scores (
			id, run_id, scorer_name, score_name, score_value, score_unit,
			details, recorded_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`
	details, _ := json.Marshal(score.Details)
	_, err := s.db.ExecContext(ctx, query,
		score.ID, score.RunID, score.ScorerName, score.ScoreName, score.ScoreValue,
		score.ScoreUnit, string(details), score.RecordedAt,
	)
	if err != nil {
		return fmt.Errorf("insert score: %w", err)
	}
	return nil
}

// ListScores returns all scores for a run.
func (s *store) ListScores(ctx context.Context, runID uuid.UUID) ([]EvaluationScore, error) {
	query := `
		SELECT id, run_id, scorer_name, score_name, score_value, score_unit,
			details, recorded_at
		FROM evaluation_scores WHERE run_id = $1 ORDER BY recorded_at
	`
	rows, err := s.db.QueryContext(ctx, query, runID)
	if err != nil {
		return nil, fmt.Errorf("query scores: %w", err)
	}
	defer rows.Close()

	var scores []EvaluationScore
	for rows.Next() {
		var s EvaluationScore
		var details []byte
		if err := rows.Scan(
			&s.ID, &s.RunID, &s.ScorerName, &s.ScoreName, &s.ScoreValue,
			&s.ScoreUnit, &details, &s.RecordedAt,
		); err != nil {
			return nil, fmt.Errorf("scan score: %w", err)
		}
		_ = json.Unmarshal(details, &s.Details)
		scores = append(scores, s)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate scores: %w", err)
	}
	return scores, nil
}

// CreateArtifact persists an evaluation artifact reference.
func (s *store) CreateArtifact(ctx context.Context, artifact *EvaluationArtifact) error {
	query := `
		INSERT INTO evaluation_artifacts (
			id, run_id, artifact_type, s3_uri, size_bytes, checksum, created_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7)
	`
	_, err := s.db.ExecContext(ctx, query,
		artifact.ID, artifact.RunID, artifact.ArtifactType, artifact.S3URI,
		artifact.SizeBytes, artifact.Checksum, artifact.CreatedAt,
	)
	if err != nil {
		return fmt.Errorf("insert artifact: %w", err)
	}
	return nil
}

// ListArtifacts returns all artifacts for a run.
func (s *store) ListArtifacts(ctx context.Context, runID uuid.UUID) ([]EvaluationArtifact, error) {
	query := `
		SELECT id, run_id, artifact_type, s3_uri, size_bytes, checksum, created_at
		FROM evaluation_artifacts WHERE run_id = $1 ORDER BY created_at
	`
	rows, err := s.db.QueryContext(ctx, query, runID)
	if err != nil {
		return nil, fmt.Errorf("query artifacts: %w", err)
	}
	defer rows.Close()

	var artifacts []EvaluationArtifact
	for rows.Next() {
		var a EvaluationArtifact
		if err := rows.Scan(
			&a.ID, &a.RunID, &a.ArtifactType, &a.S3URI, &a.SizeBytes,
			&a.Checksum, &a.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan artifact: %w", err)
		}
		artifacts = append(artifacts, a)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate artifacts: %w", err)
	}
	return artifacts, nil
}

// RegisterWorker registers a new evaluation worker.
func (s *store) RegisterWorker(ctx context.Context, w *WorkerStatus) error {
	query := `
		INSERT INTO evaluation_worker_status (
			id, worker_type, worker_name, status, capacity, current_load,
			last_heartbeat, metadata, registered_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		ON CONFLICT (worker_name) DO UPDATE SET
			status = EXCLUDED.status,
			current_load = EXCLUDED.current_load,
			last_heartbeat = EXCLUDED.last_heartbeat,
			metadata = EXCLUDED.metadata
	`
	metadata, _ := json.Marshal(w.Metadata)
	_, err := s.db.ExecContext(ctx, query,
		w.ID, w.WorkerType, w.WorkerName, w.Status, w.Capacity, w.CurrentLoad,
		w.LastHeartbeat, string(metadata), w.RegisteredAt,
	)
	if err != nil {
		return fmt.Errorf("upsert worker: %w", err)
	}
	return nil
}

// HeartbeatWorker updates a worker's last heartbeat timestamp.
func (s *store) HeartbeatWorker(ctx context.Context, id uuid.UUID) error {
	query := `
		UPDATE evaluation_worker_status
		SET last_heartbeat = $1, status = 'active'
		WHERE id = $2
	`
	_, err := s.db.ExecContext(ctx, query, time.Now(), id)
	if err != nil {
		return fmt.Errorf("heartbeat worker: %w", err)
	}
	return nil
}

// ListWorkers returns all registered workers.
func (s *store) ListWorkers(ctx context.Context) ([]WorkerStatus, error) {
	query := `
		SELECT id, worker_type, worker_name, status, current_job_id,
			capacity, current_load, last_heartbeat, metadata, registered_at
		FROM evaluation_worker_status ORDER BY worker_name
	`
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query workers: %w", err)
	}
	defer rows.Close()

	var workers []WorkerStatus
	for rows.Next() {
		var w WorkerStatus
		var currentJobID *uuid.UUID
		var metadata []byte
		if err := rows.Scan(
			&w.ID, &w.WorkerType, &w.WorkerName, &w.Status, &currentJobID,
			&w.Capacity, &w.CurrentLoad, &w.LastHeartbeat, &metadata, &w.RegisteredAt,
		); err != nil {
			return nil, fmt.Errorf("scan worker: %w", err)
		}
		w.CurrentJobID = currentJobID
		_ = json.Unmarshal(metadata, &w.Metadata)
		workers = append(workers, w)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate workers: %w", err)
	}
	return workers, nil
}

// CreateModelComparison creates a new model comparison.
func (s *store) CreateModelComparison(ctx context.Context, c *ModelComparison) error {
	query := `
		INSERT INTO evaluation_model_comparisons (
			id, name, status, created_by, created_at
		) VALUES ($1, $2, $3, $4, $5)
	`
	_, err := s.db.ExecContext(ctx, query,
		c.ID, c.Name, c.Status, c.CreatedBy, c.CreatedAt,
	)
	if err != nil {
		return fmt.Errorf("insert model comparison: %w", err)
	}
	return nil
}

// GetModelComparison retrieves a comparison by ID.
func (s *store) GetModelComparison(ctx context.Context, id uuid.UUID) (*ModelComparison, error) {
	query := `
		SELECT id, name, status, created_by, created_at, completed_at
		FROM evaluation_model_comparisons WHERE id = $1
	`
	row := s.db.QueryRowContext(ctx, query, id)
	var c ModelComparison
	var completedAt *time.Time
	err := row.Scan(
		&c.ID, &c.Name, &c.Status, &c.CreatedBy, &c.CreatedAt, &completedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("scan model comparison: %w", err)
	}
	c.CompletedAt = completedAt
	return &c, nil
}

// ListModelComparisons returns all model comparisons.
func (s *store) ListModelComparisons(ctx context.Context) ([]ModelComparison, error) {
	query := `
		SELECT id, name, status, created_by, created_at, completed_at
		FROM evaluation_model_comparisons ORDER BY created_at DESC
	`
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query model comparisons: %w", err)
	}
	defer rows.Close()

	var comparisons []ModelComparison
	for rows.Next() {
		var c ModelComparison
		var completedAt *time.Time
		if err := rows.Scan(
			&c.ID, &c.Name, &c.Status, &c.CreatedBy, &c.CreatedAt, &completedAt,
		); err != nil {
			return nil, fmt.Errorf("scan model comparison: %w", err)
		}
		c.CompletedAt = completedAt
		comparisons = append(comparisons, c)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate model comparisons: %w", err)
	}
	return comparisons, nil
}

// CreateComparisonResult creates a comparison result.
func (s *store) CreateComparisonResult(ctx context.Context, r *ComparisonResult) error {
	query := `
		INSERT INTO evaluation_comparison_results (
			id, comparison_id, metric_name, results, difference,
			significant, p_value, recorded_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`
	results, _ := json.Marshal(r.Results)
	var diff *float64
	if r.Difference != nil {
		diff = r.Difference
	}
	var pval *float64
	if r.PValue != nil {
		pval = r.PValue
	}
	_, err := s.db.ExecContext(ctx, query,
		r.ID, r.ComparisonID, r.MetricName, string(results), diff,
		r.Significant, pval, r.RecordedAt,
	)
	if err != nil {
		return fmt.Errorf("insert comparison result: %w", err)
	}
	return nil
}

// ListComparisonResults returns all comparison results for a comparison.
func (s *store) ListComparisonResults(ctx context.Context, comparisonID uuid.UUID) ([]ComparisonResult, error) {
	query := `
		SELECT id, comparison_id, metric_name, results, difference,
			significant, p_value, recorded_at
		FROM evaluation_comparison_results WHERE comparison_id = $1
		ORDER BY recorded_at
	`
	rows, err := s.db.QueryContext(ctx, query, comparisonID)
	if err != nil {
		return nil, fmt.Errorf("query comparison results: %w", err)
	}
	defer rows.Close()

	var results []ComparisonResult
	for rows.Next() {
		var r ComparisonResult
		var resultsJSON []byte
		var diff *float64
		var pval *float64
		if err := rows.Scan(
			&r.ID, &r.ComparisonID, &r.MetricName, &resultsJSON, &diff,
			&r.Significant, &pval, &r.RecordedAt,
		); err != nil {
			return nil, fmt.Errorf("scan comparison result: %w", err)
		}
		_ = json.Unmarshal(resultsJSON, &r.Results)
		r.Difference = diff
		r.PValue = pval
		results = append(results, r)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate comparison results: %w", err)
	}
	return results, nil
}
