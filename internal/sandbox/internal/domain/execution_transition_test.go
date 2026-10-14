package domain

import (
	"testing"
	"time"
)

func TestExecutionTransitionToRunning(t *testing.T) {
	execution := NewExecution(
		NewSandboxID(),
		"python",
		[]string{"main.py"},
	)

	before := time.Now().UTC()

	err := execution.TransitionTo(ExecutionStateRunning)

	after := time.Now().UTC()

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if execution.State != ExecutionStateRunning {
		t.Fatalf(
			"State = %q, want %q",
			execution.State,
			ExecutionStateRunning,
		)
	}

	if execution.StartedAt == nil {
		t.Fatal("StartedAt should be set")
	}

	if execution.StartedAt.Before(before) ||
		execution.StartedAt.After(after) {
		t.Fatalf(
			"StartedAt is outside expected range: %v",
			*execution.StartedAt,
		)
	}

	if execution.CompletedAt != nil {
		t.Fatal("CompletedAt should still be nil")
	}

	if execution.ExitCode != nil {
		t.Fatal("ExitCode should still be nil")
	}
}

func TestExecutionTransitionToCompleted(t *testing.T) {
	execution := NewExecution(
		NewSandboxID(),
		"python",
		[]string{"main.py"},
	)

	if err := execution.TransitionTo(ExecutionStateRunning); err != nil {
		t.Fatalf("failed to transition to running: %v", err)
	}

	before := time.Now().UTC()

	err := execution.TransitionTo(ExecutionStateCompleted)

	after := time.Now().UTC()

	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	if execution.State != ExecutionStateCompleted {
		t.Fatalf(
			"State = %q, want %q",
			execution.State,
			ExecutionStateCompleted,
		)
	}

	if execution.StartedAt == nil {
		t.Fatal("StartedAt should remain set")
	}

	if execution.CompletedAt == nil {
		t.Fatal("CompletedAt should be set")
	}

	if execution.CompletedAt.Before(before) ||
		execution.CompletedAt.After(after) {
		t.Fatalf(
			"CompletedAt is outside expected range: %v",
			*execution.CompletedAt,
		)
	}
}

func TestExecutionTransitionRejectsInvalidTransition(t *testing.T) {
	execution := NewExecution(
		NewSandboxID(),
		"python",
		[]string{"main.py"},
	)

	initialState := execution.State
	initialStartedAt := execution.StartedAt
	initialCompletedAt := execution.CompletedAt
	initialUpdatedAt := execution.UpdatedAt

	err := execution.TransitionTo(ExecutionStateCompleted)

	if err == nil {
		t.Fatal("expected error for invalid transition")
	}

	if execution.State != initialState {
		t.Fatalf(
			"State changed after invalid transition: got %q, want %q",
			execution.State,
			initialState,
		)
	}

	if execution.StartedAt != initialStartedAt {
		t.Fatal("StartedAt changed after invalid transition")
	}

	if execution.CompletedAt != initialCompletedAt {
		t.Fatal("CompletedAt changed after invalid transition")
	}

	if !execution.UpdatedAt.Equal(initialUpdatedAt) {
		t.Fatal("UpdatedAt changed after invalid transition")
	}
}

func TestExecutionTransitionToTerminalStates(t *testing.T) {
	terminalStates := []ExecutionState{
		ExecutionStateCompleted,
		ExecutionStateFailed,
		ExecutionStateTimeout,
	}

	for _, terminalState := range terminalStates {
		t.Run(string(terminalState), func(t *testing.T) {
			execution := NewExecution(
				NewSandboxID(),
				"python",
				[]string{"main.py"},
			)

			if err := execution.TransitionTo(ExecutionStateRunning); err != nil {
				t.Fatalf("failed to transition to running: %v", err)
			}

			err := execution.TransitionTo(terminalState)

			if err != nil {
				t.Fatalf(
					"transition to %q failed: %v",
					terminalState,
					err,
				)
			}

			if execution.State != terminalState {
				t.Fatalf(
					"State = %q, want %q",
					execution.State,
					terminalState,
				)
			}

			if execution.CompletedAt == nil {
				t.Fatal("CompletedAt should be set")
			}
		})
	}
}
