-- Enable pgvector extension for the RAG vector store.
-- This runs automatically on PostgreSQL startup via
-- docker-entrypoint-initdb.d.

CREATE EXTENSION IF NOT EXISTS vector;

-- Evaluation platform schema.
-- All tables use the evaluation_ prefix to avoid production table contention.

-- Evaluations: top-level evaluation configuration snapshots.
CREATE TABLE IF NOT EXISTS evaluation_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    dataset_id UUID REFERENCES evaluation_datasets(id),
    evaluation_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    timeout_seconds INTEGER NOT NULL DEFAULT 3600,
    max_concurrency INTEGER NOT NULL DEFAULT 5,
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_evaluation_evaluations_status
    ON evaluation_evaluations(status);
CREATE INDEX IF NOT EXISTS idx_evaluation_evaluations_created_at
    ON evaluation_evaluations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_evaluations_dataset_id
    ON evaluation_evaluations(dataset_id);

-- Evaluation runs: single model execution within an evaluation.
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID NOT NULL REFERENCES evaluation_evaluations(id) ON DELETE CASCADE,
    model_id VARCHAR(255) NOT NULL REFERENCES evaluation_models(model_id),
    provider_id VARCHAR(255) NOT NULL REFERENCES evaluation_providers(provider_id),
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    success_rate NUMERIC(5,4),
    avg_latency_ms INTEGER,
    p50_latency_ms INTEGER,
    p95_latency_ms INTEGER,
    p99_latency_ms INTEGER,
    total_tokens INTEGER,
    total_cost_usd NUMERIC(10,6),
    error_count INTEGER,
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_evaluation_id
    ON evaluation_runs(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_model_id
    ON evaluation_runs(model_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_status
    ON evaluation_runs(status);

-- Evaluation jobs: schedulable units of work.
CREATE TABLE IF NOT EXISTS evaluation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID NOT NULL REFERENCES evaluation_evaluations(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    worker_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_status
    ON evaluation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_lease_expires_at
    ON evaluation_jobs(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_worker_id
    ON evaluation_jobs(worker_id);

-- Models: registered evaluation models.
CREATE TABLE IF NOT EXISTS evaluation_models (
    model_id VARCHAR(255) PRIMARY KEY,
    provider_id VARCHAR(255) NOT NULL REFERENCES evaluation_providers(provider_id),
    display_name VARCHAR(255),
    context_window INTEGER,
    capabilities JSONB DEFAULT '[]'::jsonb,
    endpoint_config JSONB DEFAULT '{}'::jsonb,
    generation_defaults JSONB DEFAULT '{}'::jsonb,
    timeout_seconds INTEGER NOT NULL DEFAULT 120,
    retry_config JSONB DEFAULT '{}'::jsonb,
    health_status VARCHAR(20) DEFAULT 'unknown',
    health_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_models_provider_id
    ON evaluation_models(provider_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_models_health_status
    ON evaluation_models(health_status);

-- Providers: registered inference providers.
CREATE TABLE IF NOT EXISTS evaluation_providers (
    provider_id VARCHAR(255) PRIMARY KEY,
    display_name VARCHAR(255),
    provider_type VARCHAR(50) NOT NULL,
    endpoint_url VARCHAR(500) NOT NULL,
    auth_ref VARCHAR(255),
    capabilities JSONB DEFAULT '[]'::jsonb,
    health_status VARCHAR(20) DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_providers_type
    ON evaluation_providers(provider_type);
CREATE INDEX IF NOT EXISTS idx_evaluation_providers_health
    ON evaluation_providers(health_status);

-- Datasets: registered evaluation datasets.
CREATE TABLE IF NOT EXISTS evaluation_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    version VARCHAR(100) NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    s3_uri VARCHAR(1000) NOT NULL,
    row_count INTEGER,
    schema_json JSONB DEFAULT '{}'::jsonb,
    description TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluation_datasets_name_version
    ON evaluation_datasets(name, version);
CREATE INDEX IF NOT EXISTS idx_evaluation_datasets_checksum
    ON evaluation_datasets(checksum);

-- Benchmarks: runtime benchmark definitions.
CREATE TABLE IF NOT EXISTS evaluation_benchmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    benchmark_type VARCHAR(50) NOT NULL,
    target_service VARCHAR(100),
    target_url VARCHAR(500),
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Benchmark runs: single benchmark execution.
CREATE TABLE IF NOT EXISTS evaluation_benchmark_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    benchmark_id UUID NOT NULL REFERENCES evaluation_benchmarks(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Benchmark results: individual metric measurements.
CREATE TABLE IF NOT EXISTS evaluation_benchmark_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_benchmark_runs(id) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    metric_value NUMERIC(15,6) NOT NULL,
    metric_unit VARCHAR(50),
    concurrency_level INTEGER,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_benchmark_results_run_id
    ON evaluation_benchmark_results(run_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_benchmark_results_metric
    ON evaluation_benchmark_results(metric_name);

-- Evaluation scores: scored metrics for runs.
CREATE TABLE IF NOT EXISTS evaluation_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    scorer_name VARCHAR(100) NOT NULL,
    score_name VARCHAR(100) NOT NULL,
    score_value NUMERIC(10,6) NOT NULL,
    score_unit VARCHAR(50),
    details JSONB DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_scores_run_id
    ON evaluation_scores(run_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_scores_scorer
    ON evaluation_scores(scorer_name);

-- Evaluation artifacts: stored artifacts for runs.
CREATE TABLE IF NOT EXISTS evaluation_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    artifact_type VARCHAR(50) NOT NULL,
    s3_uri VARCHAR(1000) NOT NULL,
    size_bytes INTEGER,
    checksum VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_artifacts_run_id
    ON evaluation_artifacts(run_id);

-- Model comparisons: comparisons between model runs.
CREATE TABLE IF NOT EXISTS evaluation_model_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Comparison results: individual metric comparisons.
CREATE TABLE IF NOT EXISTS evaluation_comparison_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comparison_id UUID NOT NULL REFERENCES evaluation_model_comparisons(id) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    results JSONB NOT NULL DEFAULT '{}'::jsonb,
    difference NUMERIC(15,6),
    significant BOOLEAN DEFAULT false,
    p_value NUMERIC(10,6),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_comparison_results_comparison
    ON evaluation_comparison_results(comparison_id);

-- Worker status: health and load of evaluation workers.
CREATE TABLE IF NOT EXISTS evaluation_worker_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_type VARCHAR(50) NOT NULL,
    worker_name VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'idle',
    current_job_id UUID,
    capacity INTEGER NOT NULL DEFAULT 1,
    current_load INTEGER NOT NULL DEFAULT 0,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_worker_status_type
    ON evaluation_worker_status(worker_type);
CREATE INDEX IF NOT EXISTS idx_evaluation_worker_status_status
    ON evaluation_worker_status(status);
CREATE INDEX IF NOT EXISTS idx_evaluation_worker_status_heartbeat
    ON evaluation_worker_status(last_heartbeat);
