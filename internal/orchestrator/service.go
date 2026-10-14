package orchestrator

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

var (
	ErrInvalidIntent     = errors.New("intent must not be empty")
	ErrExecutionNotFound = errors.New("execution not found")
	ErrQueueUnavailable  = errors.New("task queue unavailable")
	ErrStateUnavailable  = errors.New("execution state unavailable")
)

type Queue interface {
	Submit(ctx context.Context, executionID, intent string) error
	GetExecution(ctx context.Context, executionID string) (map[string]string, error)
}

type Service struct {
	queue Queue
}

func NewService(queue Queue) *Service {
	return &Service{queue: queue}
}

type RunResult struct {
	ExecutionID string `json:"execution_id"`
	Status      string `json:"status"`
}

func (s *Service) Run(ctx context.Context, intent string) (RunResult, error) {
	intent = strings.TrimSpace(intent)
	if intent == "" {
		return RunResult{}, ErrInvalidIntent
	}

	executionID := uuid.NewString()

	if err := s.queue.Submit(ctx, executionID, intent); err != nil {
		return RunResult{}, fmt.Errorf("%w: %v", ErrQueueUnavailable, err)
	}

	return RunResult{
		ExecutionID: executionID,
		Status:      "queued",
	}, nil
}

func (s *Service) GetExecution(
	ctx context.Context,
	executionID string,
) (map[string]string, error) {
	executionID = strings.TrimSpace(executionID)
	if executionID == "" {
		return nil, ErrExecutionNotFound
	}

	state, err := s.queue.GetExecution(ctx, executionID)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrStateUnavailable, err)
	}

	if len(state) == 0 {
		return nil, ErrExecutionNotFound
	}

	return state, nil
}
