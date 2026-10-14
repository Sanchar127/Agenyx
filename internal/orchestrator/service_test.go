package orchestrator

import (
	"context"
	"errors"
	"testing"
)

type fakeQueue struct {
	state           map[string]string
	submitErr       error
	getErr          error
	submittedID     string
	submittedIntent string
}

func (q *fakeQueue) Submit(
	_ context.Context,
	executionID string,
	intent string,
) error {
	q.submittedID = executionID
	q.submittedIntent = intent
	return q.submitErr
}

func (q *fakeQueue) GetExecution(
	_ context.Context,
	_ string,
) (map[string]string, error) {
	return q.state, q.getErr
}

func TestRunQueuesExecution(t *testing.T) {
	queue := &fakeQueue{}
	service := NewService(queue)

	result, err := service.Run(context.Background(), "  summarize this report  ")
	if err != nil {
		t.Fatalf("Run() error = %v", err)
	}

	if result.ExecutionID == "" {
		t.Fatal("expected an execution ID")
	}
	if result.Status != "queued" {
		t.Fatalf("status = %q, want queued", result.Status)
	}
	if queue.submittedID != result.ExecutionID {
		t.Fatalf("submitted ID = %q, want %q", queue.submittedID, result.ExecutionID)
	}
	if queue.submittedIntent != "summarize this report" {
		t.Fatalf("intent = %q", queue.submittedIntent)
	}
}

func TestRunRejectsEmptyIntent(t *testing.T) {
	service := NewService(&fakeQueue{})

	_, err := service.Run(context.Background(), "   ")
	if !errors.Is(err, ErrInvalidIntent) {
		t.Fatalf("error = %v, want ErrInvalidIntent", err)
	}
}

func TestRunReportsQueueFailure(t *testing.T) {
	queue := &fakeQueue{submitErr: errors.New("connection refused")}
	service := NewService(queue)

	_, err := service.Run(context.Background(), "do work")
	if !errors.Is(err, ErrQueueUnavailable) {
		t.Fatalf("error = %v, want ErrQueueUnavailable", err)
	}
}

func TestGetExecution(t *testing.T) {
	queue := &fakeQueue{
		state: map[string]string{
			"execution_id": "test-id",
			"status":       "completed",
			"answer":       "done",
		},
	}
	service := NewService(queue)

	state, err := service.GetExecution(context.Background(), "test-id")
	if err != nil {
		t.Fatalf("GetExecution() error = %v", err)
	}
	if state["status"] != "completed" {
		t.Fatalf("status = %q, want completed", state["status"])
	}
}

func TestGetExecutionNotFound(t *testing.T) {
	service := NewService(&fakeQueue{state: map[string]string{}})

	_, err := service.GetExecution(context.Background(), "missing-id")
	if !errors.Is(err, ErrExecutionNotFound) {
		t.Fatalf("error = %v, want ErrExecutionNotFound", err)
	}
}

func TestGetExecutionQueueFailure(t *testing.T) {
	service := NewService(&fakeQueue{getErr: errors.New("connection refused")})

	_, err := service.GetExecution(context.Background(), "test-id")
	if !errors.Is(err, ErrStateUnavailable) {
		t.Fatalf("error = %v, want ErrStateUnavailable", err)
	}
}
