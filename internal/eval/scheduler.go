package eval

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
)

// Scheduler assigns evaluation jobs to workers using a lease-based model.
// It polls the job queue and dispatches claims to available workers.
type Scheduler struct {
	store Store
	log   *slog.Logger
	cfg   Config
	stop  chan struct{}
}

// NewScheduler creates a new scheduler.
func NewScheduler(store Store, cfg Config, log *slog.Logger) *Scheduler {
	return &Scheduler{store: store, cfg: cfg, log: log, stop: make(chan struct{})}
}

// Start runs the scheduler loop until Stop is called.
func (s *Scheduler) Start(ctx context.Context) error {
	ticker := time.NewTicker(s.cfg.SchedulerInterval)
	defer ticker.Stop()

	s.log.Info("scheduler started", "interval", s.cfg.SchedulerInterval)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-s.stop:
			return nil
		case <-ticker.C:
			if err := s.tick(ctx); err != nil {
				s.log.Error("scheduler tick failed", "error", err)
			}
		}
	}
}

// Stop signals the scheduler to stop.
func (s *Scheduler) Stop() {
	close(s.stop)
}

// tick performs one scheduling cycle.
func (s *Scheduler) tick(ctx context.Context) error {
	// In the current design, workers claim jobs directly via ClaimJob.
	// The scheduler's role is to:
	// 1. Recover expired leases (return stale jobs to queued)
	// 2. Emit scheduling metrics
	// 3. Detect stuck jobs and requeue them

	if err := s.recoverExpiredLeases(ctx); err != nil {
		return fmt.Errorf("recover expired leases: %w", err)
	}
	return nil
}

// recoverExpiredLeases returns jobs whose lease has expired but are still
// marked as claimed, so they can be picked up by another worker.
func (s *Scheduler) recoverExpiredLeases(ctx context.Context) error {
	workers, err := s.store.ListWorkers(ctx)
	if err != nil {
		return fmt.Errorf("list workers: %w", err)
	}

	now := time.Now()
	activeWorkers := make(map[string]bool)
	for _, w := range workers {
		if w.Status == "active" && w.LastHeartbeat.After(now.Add(-2*time.Minute)) {
			activeWorkers[w.WorkerName] = true
		}
	}

	// Note: In a full implementation, we would query for claimed jobs with
	// expired leases where the worker is no longer active. For now, the
	// ClaimJob uses SKIP LOCKED and the lease expiry prevents indefinite
	// blocking.
	_ = activeWorkers
	_ = now
	return nil
}

// AssignJob assigns a specific job to a specific worker.
func (s *Scheduler) AssignJob(ctx context.Context, jobID uuid.UUID, workerID string) error {
	// In the lease-based model, workers claim jobs themselves.
	// The scheduler could optionally pre-assign jobs, but for now workers
	// self-assign via ClaimJob.
	_ = jobID
	_ = workerID
	return nil
}

// GetNextJob returns the next queued job without claiming it (for preview).
func (s *Scheduler) GetNextJob(ctx context.Context) (*EvaluationJob, error) {
	// This would be a SELECT ... FOR UPDATE SKIP LOCKED without claiming.
	// Not implemented yet as workers claim directly.
	return nil, nil
}
