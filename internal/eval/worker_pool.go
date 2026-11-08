package eval

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"
)

// WorkerType defines the type of evaluation worker.
type WorkerType string

const (
	WorkerTypeAI          WorkerType = "ai_eval"       // AI evaluation (Inspect AI)
	WorkerTypeBenchmark   WorkerType = "benchmark"     // Go benchmark execution
	WorkerTypeLoadTest    WorkerType = "load_test"     // k6 load testing
)

// WorkerHealth represents the current health state of a worker.
type WorkerHealth string

const (
	WorkerHealthActive   WorkerHealth = "active"
	WorkerHealthIdle     WorkerHealth = "idle"
	WorkerHealthUnhealthy WorkerHealth = "unhealthy"
	WorkerHealthOffline  WorkerHealth = "offline"
)

// WorkerConfig defines configuration for a worker pool.
type WorkerConfig struct {
	WorkerType      WorkerType `json:"worker_type"`
	MinWorkers      int        `json:"min_workers"`       // Minimum workers to keep running
	MaxWorkers      int        `json:"max_workers"`       // Maximum workers allowed
	CurrentWorkers  int        `json:"current_workers"`   // Currently running workers
	CPULimit        string     `json:"cpu_limit"`         // CPU limit per worker (e.g., "2")
	MemoryLimit     string     `json:"memory_limit"`      // Memory limit per worker (e.g., "4Gi")
	MaxConcurrency  int        `json:"max_concurrency"`   // Max concurrent tasks per worker
	JobTimeout      int        `json:"job_timeout"`       // Job timeout in seconds
}

// WorkerInfo tracks the state of a single worker in the pool.
type WorkerInfo struct {
	ID            string         `json:"id"`
	Name          string         `json:"name"`
	WorkerType    WorkerType     `json:"worker_type"`
	Health        WorkerHealth   `json:"health"`
	CurrentJobID  string         `json:"current_job_id,omitempty"`
	Capacity      int            `json:"capacity"`
	CurrentLoad   int            `json:"current_load"`
	LastHeartbeat time.Time      `json:"last_heartbeat"`
	RegisteredAt  time.Time      `json:"registered_at"`
	Metadata      map[string]any `json:"metadata,omitempty"`
}

// WorkerPool manages a pool of evaluation workers of a specific type.
type WorkerPool struct {
	config   WorkerConfig
	store    Store
	log      *slog.Logger
	workers  map[string]*WorkerInfo
	mu       sync.RWMutex
	ctx      context.Context
	cancel   context.CancelFunc
}

// NewWorkerPool creates a new worker pool.
func NewWorkerPool(config WorkerConfig, store Store, log *slog.Logger) *WorkerPool {
	return &WorkerPool{
		config:  config,
		store:   store,
		log:     log,
		workers: make(map[string]*WorkerInfo),
	}
}

// Start initializes the worker pool with minimum workers.
func (wp *WorkerPool) Start(ctx context.Context) error {
	wp.ctx, wp.cancel = context.WithCancel(ctx)

	// Register initial workers
	for i := 0; i < wp.config.MinWorkers; i++ {
		if err := wp.registerWorker(fmt.Sprintf("%s-%d", wp.config.WorkerType, i)); err != nil {
			wp.log.Warn("failed to register initial worker",
				"worker_type", wp.config.WorkerType,
				"index", i,
				"error", err,
			)
		}
	}

	// Start health check loop
	go wp.healthCheckLoop()

	wp.log.Info("worker pool started",
		"worker_type", wp.config.WorkerType,
		"min_workers", wp.config.MinWorkers,
		"max_workers", wp.config.MaxWorkers,
	)

	return nil
}

// Stop stops the worker pool.
func (wp *WorkerPool) Stop() {
	wp.cancel()
	wp.log.Info("worker pool stopped", "worker_type", wp.config.WorkerType)
}

// registerWorker registers a new worker in the pool.
func (wp *WorkerPool) registerWorker(name string) error {
	worker := &WorkerInfo{
		ID:            generateWorkerID(),
		Name:          name,
		WorkerType:    wp.config.WorkerType,
		Health:        WorkerHealthIdle,
		Capacity:      wp.config.MaxConcurrency,
		CurrentLoad:   0,
		LastHeartbeat: time.Now(),
		RegisteredAt:  time.Now(),
	}

	if err := wp.store.RegisterWorker(wp.ctx, &WorkerStatus{
		ID:             uuid.MustParse(worker.ID),
		WorkerType:     string(worker.WorkerType),
		WorkerName:     worker.Name,
		Status:         string(worker.Health),
		Capacity:       worker.Capacity,
		CurrentLoad:    worker.CurrentLoad,
		LastHeartbeat:  worker.LastHeartbeat,
		Metadata:       map[string]any{},
		RegisteredAt:   worker.RegisteredAt,
	}); err != nil {
		return fmt.Errorf("register worker: %w", err)
	}

	wp.mu.Lock()
	wp.workers[worker.ID] = worker
	wp.mu.Unlock()

	wp.log.Debug("worker registered",
		"worker_id", worker.ID,
		"worker_name", worker.Name,
		"worker_type", worker.WorkerType,
	)

	return nil
}

// healthCheckLoop periodically checks worker health and removes stale workers.
func (wp *WorkerPool) healthCheckLoop() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-wp.ctx.Done():
			return
		case <-ticker.C:
			wp.checkWorkerHealth()
		}
	}
}

// checkWorkerHealth removes workers that haven't heartbeat recently.
func (wp *WorkerPool) checkWorkerHealth() {
	wp.mu.Lock()
	defer wp.mu.Unlock()

	now := time.Now()
	staleThreshold := 2 * time.Minute

	for id, worker := range wp.workers {
		if now.Sub(worker.LastHeartbeat) > staleThreshold {
			worker.Health = WorkerHealthOffline
			if err := wp.store.RegisterWorker(wp.ctx, &WorkerStatus{
				ID:             uuid.MustParse(worker.ID),
				WorkerType:     string(worker.WorkerType),
				WorkerName:     worker.Name,
				Status:         string(worker.Health),
				Capacity:       worker.Capacity,
				CurrentLoad:    worker.CurrentLoad,
				LastHeartbeat:  worker.LastHeartbeat,
				Metadata:       worker.Metadata,
				RegisteredAt:   worker.RegisteredAt,
			}); err != nil {
				wp.log.Error("failed to update worker status",
					"worker_id", worker.ID,
					"error", err,
				)
			}
			delete(wp.workers, id)
			wp.log.Warn("worker removed due to stale heartbeat",
				"worker_id", worker.ID,
				"worker_name", worker.Name,
			)
		}
	}
}

// GetWorkerPoolStatus returns the current status of the worker pool.
func (wp *WorkerPool) GetWorkerPoolStatus() WorkerPoolStatus {
	wp.mu.RLock()
	defer wp.mu.RUnlock()

	active := 0
	idle := 0
	totalLoad := 0
	totalCapacity := 0

	for _, w := range wp.workers {
		switch w.Health {
		case WorkerHealthActive:
			active++
		case WorkerHealthIdle:
			idle++
		}
		totalLoad += w.CurrentLoad
		totalCapacity += w.Capacity
	}

	return WorkerPoolStatus{
		WorkerType:      wp.config.WorkerType,
		TotalWorkers:    len(wp.workers),
		ActiveWorkers:   active,
		IdleWorkers:     idle,
		TotalCapacity:   totalCapacity,
		CurrentLoad:     totalLoad,
		MinWorkers:      wp.config.MinWorkers,
		MaxWorkers:      wp.config.MaxWorkers,
	}
}

// WorkerPoolStatus represents the aggregated status of a worker pool.
type WorkerPoolStatus struct {
	WorkerType      WorkerType `json:"worker_type"`
	TotalWorkers    int        `json:"total_workers"`
	ActiveWorkers   int        `json:"active_workers"`
	IdleWorkers     int        `json:"idle_workers"`
	TotalCapacity   int        `json:"total_capacity"`
	CurrentLoad     int        `json:"current_load"`
	MinWorkers      int        `json:"min_workers"`
	MaxWorkers      int        `json:"max_workers"`
}

// WorkerPoolManager manages multiple worker pools.
type WorkerPoolManager struct {
	pools   map[WorkerType]*WorkerPool
	store   Store
	log     *slog.Logger
	mu      sync.RWMutex
}

// NewWorkerPoolManager creates a new worker pool manager.
func NewWorkerPoolManager(store Store, log *slog.Logger) *WorkerPoolManager {
	return &WorkerPoolManager{
		pools:  make(map[WorkerType]*WorkerPool),
		store:  store,
		log:    log,
	}
}

// RegisterPool registers a new worker pool.
func (wpm *WorkerPoolManager) RegisterPool(config WorkerConfig) error {
	wpm.mu.Lock()
	defer wpm.mu.Unlock()

	if _, exists := wpm.pools[config.WorkerType]; exists {
		return fmt.Errorf("worker pool %s already exists", config.WorkerType)
	}

	pool := NewWorkerPool(config, wpm.store, wpm.log)
	wpm.pools[config.WorkerType] = pool
	return nil
}

// StartPool starts a worker pool.
func (wpm *WorkerPoolManager) StartPool(ctx context.Context, workerType WorkerType) error {
	wpm.mu.RLock()
	pool, exists := wpm.pools[workerType]
	wpm.mu.RUnlock()

	if !exists {
		return fmt.Errorf("worker pool %s not found", workerType)
	}

	return pool.Start(ctx)
}

// StopPool stops a worker pool.
func (wpm *WorkerPoolManager) StopPool(workerType WorkerType) error {
	wpm.mu.RLock()
	pool, exists := wpm.pools[workerType]
	wpm.mu.RUnlock()

	if !exists {
		return fmt.Errorf("worker pool %s not found", workerType)
	}

	pool.Stop()
	return nil
}

// GetPoolStatus returns the status of a worker pool.
func (wpm *WorkerPoolManager) GetPoolStatus(workerType WorkerType) (*WorkerPoolStatus, error) {
	wpm.mu.RLock()
	pool, exists := wpm.pools[workerType]
	wpm.mu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("worker pool %s not found", workerType)
	}

	status := pool.GetWorkerPoolStatus()
	return &status, nil
}

// ListPools returns all registered worker pools.
func (wpm *WorkerPoolManager) ListPools() map[WorkerType]*WorkerPoolStatus {
	wpm.mu.RLock()
	defer wpm.mu.RUnlock()

	result := make(map[WorkerType]*WorkerPoolStatus)
	for wt, pool := range wpm.pools {
		status := pool.GetWorkerPoolStatus()
		result[wt] = &status
	}
	return result
}

// GetPool returns a worker pool by type.
func (wpm *WorkerPoolManager) GetPool(workerType WorkerType) (*WorkerPool, bool) {
	wpm.mu.RLock()
	defer wpm.mu.RUnlock()
	pool, ok := wpm.pools[workerType]
	return pool, ok
}

func generateWorkerID() string {
	return fmt.Sprintf("worker-%d", time.Now().UnixNano())
}
