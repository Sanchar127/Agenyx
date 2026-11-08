package eval

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestMockStoreCreateAndGetEvaluation(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	eval := &Evaluation{
		ID:             uuid.New(),
		Name:           "test-eval",
		Description:    "Test evaluation",
		EvaluationType: EvaluationTypeLLM,
		Status:         StatusQueued,
		Progress:       0,
		Priority:       PriorityNormal,
		TimeoutSeconds: 3600,
		MaxConcurrency: 5,
		ConfigSnapshot: map[string]any{"key": "value"},
		CreatedBy:      "test",
		CreatedAt:      time.Now(),
	}

	require.NoError(t, store.CreateEvaluation(ctx, eval))

	got, err := store.GetEvaluation(ctx, eval.ID)
	require.NoError(t, err)
	require.Equal(t, eval.ID, got.ID)
	require.Equal(t, "test-eval", got.Name)
	require.Equal(t, StatusQueued, got.Status)
	require.Equal(t, PriorityNormal, got.Priority)
	require.Equal(t, "test", got.CreatedBy)
}

func TestMockStoreUpdateEvaluationStatus(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	eval := &Evaluation{
		ID:             uuid.New(),
		Name:           "test-eval",
		EvaluationType: EvaluationTypeLLM,
		Status:         StatusQueued,
		Progress:       0,
		Priority:       PriorityNormal,
		TimeoutSeconds: 3600,
		MaxConcurrency: 5,
		ConfigSnapshot: map[string]any{},
		CreatedBy:      "test",
		CreatedAt:      time.Now(),
	}
	require.NoError(t, store.CreateEvaluation(ctx, eval))

	require.NoError(t, store.UpdateEvaluationStatus(ctx, eval.ID, StatusRunning, 50, ""))

	got, err := store.GetEvaluation(ctx, eval.ID)
	require.NoError(t, err)
	require.Equal(t, StatusRunning, got.Status)
	require.Equal(t, 50, got.Progress)
	require.Nil(t, got.CompletedAt) // Should not be set for running
}

func TestMockStoreListEvaluations(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	for i := 0; i < 5; i++ {
		eval := &Evaluation{
			ID:             uuid.New(),
			Name:           "test-eval",
			EvaluationType: EvaluationTypeLLM,
			Status:         StatusQueued,
			Progress:       0,
			Priority:       PriorityNormal,
			TimeoutSeconds: 3600,
			MaxConcurrency: 5,
			ConfigSnapshot: map[string]any{},
			CreatedBy:      "test",
			CreatedAt:      time.Now(),
		}
		require.NoError(t, store.CreateEvaluation(ctx, eval))
	}

	resp, err := store.ListEvaluations(ctx, EvaluationFilter{Page: 1, PageSize: 2})
	require.NoError(t, err)
	require.Equal(t, 2, len(resp.Evaluations))
	require.Equal(t, 5, resp.Pagination.Total)
	require.True(t, resp.Pagination.HasMore)

	// Filter by status
	queuedStatus := StatusQueued
	resp, err = store.ListEvaluations(ctx, EvaluationFilter{
		Page:          1,
		PageSize:      10,
		Status:        &queuedStatus,
	})
	require.NoError(t, err)
	require.Equal(t, 5, len(resp.Evaluations))
}

func TestMockStoreCreateAndGetRun(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	evalID := uuid.New()
	eval := &Evaluation{
		ID:             evalID,
		Name:           "test-eval",
		EvaluationType: EvaluationTypeLLM,
		Status:         StatusQueued,
		Progress:       0,
		Priority:       PriorityNormal,
		TimeoutSeconds: 3600,
		MaxConcurrency: 5,
		ConfigSnapshot: map[string]any{},
		CreatedBy:      "test",
		CreatedAt:      time.Now(),
	}
	require.NoError(t, store.CreateEvaluation(ctx, eval))

	run := &EvaluationRun{
		ID:             uuid.New(),
		EvaluationID:   evalID,
		ModelID:        "qwen2.5:7b",
		ProviderID:     "ollama-local",
		Status:         StatusQueued,
		ConfigSnapshot: map[string]any{"model": "qwen2.5:7b"},
	}
	require.NoError(t, store.CreateRun(ctx, run))

	got, err := store.GetRun(ctx, run.ID)
	require.NoError(t, err)
	require.Equal(t, run.ID, got.ID)
	require.Equal(t, evalID, got.EvaluationID)
	require.Equal(t, "qwen2.5:7b", got.ModelID)
	require.Equal(t, StatusQueued, got.Status)
}

func TestMockStoreCreateJobAndClaim(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	evalID := uuid.New()
	runID := uuid.New()

	eval := &Evaluation{
		ID:             evalID,
		Name:           "test-eval",
		EvaluationType: EvaluationTypeLLM,
		Status:         StatusQueued,
		Progress:       0,
		Priority:       PriorityNormal,
		TimeoutSeconds: 3600,
		MaxConcurrency: 5,
		ConfigSnapshot: map[string]any{},
		CreatedBy:      "test",
		CreatedAt:      time.Now(),
	}
	require.NoError(t, store.CreateEvaluation(ctx, eval))

	run := &EvaluationRun{
		ID:             runID,
		EvaluationID:   evalID,
		ModelID:        "qwen2.5:7b",
		ProviderID:     "ollama-local",
		Status:         StatusQueued,
		ConfigSnapshot: map[string]any{},
	}
	require.NoError(t, store.CreateRun(ctx, run))

	job := &EvaluationJob{
		ID:          uuid.New(),
		EvaluationID: evalID,
		RunID:        runID,
		Status:       StatusQueued,
		Attempt:      0,
		MaxAttempts:  3,
		CreatedAt:    time.Now(),
	}
	require.NoError(t, store.CreateJob(ctx, job))

	claimed, err := store.ClaimJob(ctx, "worker-1", 300)
	require.NoError(t, err)
	require.Equal(t, job.ID, claimed.ID)
	require.Equal(t, "worker-1", *claimed.WorkerID)
	require.Equal(t, StatusRunning, claimed.Status)
	require.Equal(t, 1, claimed.Attempt)
}

func TestMockStoreModelsAndProviders(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	// Create provider first
	provider := &Provider{
		ProviderID:   "ollama-local",
		DisplayName:  "Ollama Local",
		ProviderType: "ollama",
		EndpointURL:  "http://ollama:11434/v1",
		AuthRef:      "ollama-key",
		Capabilities: []string{"chat", "embedding"},
		HealthStatus: "healthy",
	}
	require.NoError(t, store.CreateProvider(ctx, provider))

	gotProvider, err := store.GetProvider(ctx, "ollama-local")
	require.NoError(t, err)
	require.Equal(t, "ollama-local", gotProvider.ProviderID)
	require.Equal(t, "healthy", gotProvider.HealthStatus)

	providers, err := store.ListProviders(ctx)
	require.NoError(t, err)
	require.Equal(t, 1, len(providers))

	// Create model
	model := &Model{
		ModelID:          "qwen2.5:7b",
		ProviderID:       "ollama-local",
		DisplayName:      "Qwen 2.5 7B",
		ContextWindow:    32768,
		Capabilities:     []string{"chat", "tool_use"},
		EndpointConfig:   map[string]any{"base_url": "http://ollama:11434/v1"},
		GenerationDefaults: map[string]any{"temperature": 0.2},
		TimeoutSeconds:   120,
		RetryConfig:      map[string]any{"max_retries": 3},
		HealthStatus:     "healthy",
	}
	require.NoError(t, store.CreateModel(ctx, model))

	gotModel, err := store.GetModel(ctx, "qwen2.5:7b")
	require.NoError(t, err)
	require.Equal(t, "qwen2.5:7b", gotModel.ModelID)
	require.Equal(t, 32768, gotModel.ContextWindow)

	models, err := store.ListModels(ctx)
	require.NoError(t, err)
	require.Equal(t, 1, len(models))
}

func TestMockStoreDatasets(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	dataset := &Dataset{
		ID:          uuid.New(),
		Name:        "test-dataset",
		Version:     "1.0",
		Checksum:    "abc123",
		S3URI:       "s3://bucket/dataset.jsonl",
		RowCount:    100,
		Description: "Test dataset",
		CreatedBy:   "test",
		CreatedAt:   time.Now(),
	}
	require.NoError(t, store.CreateDataset(ctx, dataset))

	got, err := store.GetDataset(ctx, dataset.ID)
	require.NoError(t, err)
	require.Equal(t, "test-dataset", got.Name)
	require.Equal(t, "1.0", got.Version)
	require.Equal(t, 100, got.RowCount)

	datasets, err := store.ListDatasets(ctx)
	require.NoError(t, err)
	require.Equal(t, 1, len(datasets))
}

func TestMockStoreScoresAndArtifacts(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	runID := uuid.New()

	score := &EvaluationScore{
		ID:         uuid.New(),
		RunID:      runID,
		ScorerName: "task_completion",
		ScoreName:  "accuracy",
		ScoreValue: 0.92,
		ScoreUnit:  "percent",
		Details:    map[string]any{"correct": 92, "total": 100},
		RecordedAt: time.Now(),
	}
	require.NoError(t, store.CreateScore(ctx, score))

	scores, err := store.ListScores(ctx, runID)
	require.NoError(t, err)
	require.Equal(t, 1, len(scores))
	require.Equal(t, 0.92, scores[0].ScoreValue)

	artifact := &EvaluationArtifact{
		ID:          uuid.New(),
		RunID:       runID,
		ArtifactType: "trace",
		S3URI:       "s3://bucket/trace.json",
		SizeBytes:   1024,
		Checksum:    "def456",
		CreatedAt:   time.Now(),
	}
	require.NoError(t, store.CreateArtifact(ctx, artifact))

	artifacts, err := store.ListArtifacts(ctx, runID)
	require.NoError(t, err)
	require.Equal(t, 1, len(artifacts))
	require.Equal(t, "trace", artifacts[0].ArtifactType)
}

func TestMockStoreWorkers(t *testing.T) {
	store := NewMockStore()
	ctx := context.Background()

	workerID := uuid.New()
	worker := &WorkerStatus{
		ID:           workerID,
		WorkerType:   "ai_eval",
		WorkerName:   "worker-1",
		Status:       "idle",
		Capacity:     4,
		CurrentLoad:  0,
		LastHeartbeat: time.Now(),
		Metadata:     map[string]any{"host": "host-1"},
		RegisteredAt: time.Now(),
	}
	require.NoError(t, store.RegisterWorker(ctx, worker))

	workers, err := store.ListWorkers(ctx)
	require.NoError(t, err)
	require.Equal(t, 1, len(workers))
	require.Equal(t, "worker-1", workers[0].WorkerName)

	require.NoError(t, store.HeartbeatWorker(ctx, workerID))
	workers, err = store.ListWorkers(ctx)
	require.NoError(t, err)
	require.Equal(t, "active", workers[0].Status)
}

func TestEvaluationTypeConstants(t *testing.T) {
	assert.Equal(t, EvaluationType("llm"), EvaluationTypeLLM)
	assert.Equal(t, EvaluationType("agent"), EvaluationTypeAgent)
	assert.Equal(t, EvaluationType("tool"), EvaluationTypeTool)
	assert.Equal(t, EvaluationType("orchestration"), EvaluationTypeOrchestration)
	assert.Equal(t, EvaluationType("sandbox"), EvaluationTypeSandbox)
	assert.Equal(t, EvaluationType("e2e"), EvaluationTypeEndToEnd)
}

func TestEvaluationStatusConstants(t *testing.T) {
	assert.Equal(t, EvaluationStatus("queued"), StatusQueued)
	assert.Equal(t, EvaluationStatus("running"), StatusRunning)
	assert.Equal(t, EvaluationStatus("completed"), StatusCompleted)
	assert.Equal(t, EvaluationStatus("failed"), StatusFailed)
	assert.Equal(t, EvaluationStatus("cancelled"), StatusCancelled)
}

func TestPriorityConstants(t *testing.T) {
	assert.Equal(t, Priority("low"), PriorityLow)
	assert.Equal(t, Priority("normal"), PriorityNormal)
	assert.Equal(t, Priority("high"), PriorityHigh)
	assert.Equal(t, Priority("critical"), PriorityCritical)
}
