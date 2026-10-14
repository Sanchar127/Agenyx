package domain

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestNewExecution(t *testing.T) {
	sandboxID := NewSandboxID()

	args := []string{
		"main.py",
		"--input",
		"data.json",
	}

	before := time.Now().UTC()

	execution := NewExecution(
		sandboxID,
		"python",
		args,
	)

	after := time.Now().UTC()

	if execution == nil {
		t.Fatal("NewExecution() returned nil")
	}

	if execution.ID == "" {
		t.Fatal("execution ID should not be empty")
	}

	if _, err := uuid.Parse(string(execution.ID)); err != nil {
		t.Fatalf("execution ID should be a valid UUID: %v", err)
	}

	if execution.SandboxID != sandboxID {
		t.Fatalf(
			"SandboxID = %q, want %q",
			execution.SandboxID,
			sandboxID,
		)
	}

	if execution.Command != "python" {
		t.Fatalf(
			"Command = %q, want %q",
			execution.Command,
			"python",
		)
	}

	if len(execution.Args) != len(args) {
		t.Fatalf(
			"expected %d args, got %d",
			len(args),
			len(execution.Args),
		)
	}

	for i, expected := range args {
		if execution.Args[i] != expected {
			t.Fatalf(
				"Args[%d] = %q, want %q",
				i,
				execution.Args[i],
				expected,
			)
		}
	}

	if execution.State != ExecutionStateRequested {
		t.Fatalf(
			"State = %q, want %q",
			execution.State,
			ExecutionStateRequested,
		)
	}

	if execution.ExitCode != nil {
		t.Fatal("ExitCode should be nil before execution starts")
	}

	if execution.StartedAt != nil {
		t.Fatal("StartedAt should be nil before execution starts")
	}

	if execution.CompletedAt != nil {
		t.Fatal("CompletedAt should be nil before execution completes")
	}

	if execution.CreatedAt.Before(before) ||
		execution.CreatedAt.After(after) {
		t.Fatalf(
			"CreatedAt is outside expected range: %v",
			execution.CreatedAt,
		)
	}

	if execution.UpdatedAt.Before(before) ||
		execution.UpdatedAt.After(after) {
		t.Fatalf(
			"UpdatedAt is outside expected range: %v",
			execution.UpdatedAt,
		)
	}

	if !execution.CreatedAt.Equal(execution.UpdatedAt) {
		t.Fatal("CreatedAt and UpdatedAt should initially be equal")
	}
}

func TestNewExecutionGeneratesUniqueIDs(t *testing.T) {
	sandboxID := NewSandboxID()

	first := NewExecution(
		sandboxID,
		"python",
		[]string{"first.py"},
	)

	second := NewExecution(
		sandboxID,
		"python",
		[]string{"second.py"},
	)

	if first.ID == second.ID {
		t.Fatal("two executions should not have the same ID")
	}
}
