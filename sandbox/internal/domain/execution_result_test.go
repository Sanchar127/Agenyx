package domain

import (
	"bytes"
	"testing"
	"time"
)

func TestExecutionResult(t *testing.T) {
	result := ExecutionResult{
		ExitCode: 0,
		Stdout:   []byte("hello\n"),
		Stderr:   []byte{},
		Duration: 150 * time.Millisecond,
	}

	if result.ExitCode != 0 {
		t.Fatalf("expected exit code 0, got %d", result.ExitCode)
	}

	if !bytes.Equal(result.Stdout, []byte("hello\n")) {
		t.Fatalf("unexpected stdout: %q", result.Stdout)
	}

	if len(result.Stderr) != 0 {
		t.Fatalf("expected empty stderr, got %q", result.Stderr)
	}

	if result.Duration != 150*time.Millisecond {
		t.Fatalf("expected duration 150ms, got %v", result.Duration)
	}
}

func TestExecutionResultAllowsNonZeroExitCode(t *testing.T) {
	result := ExecutionResult{
		ExitCode: 1,
		Stderr:   []byte("command failed"),
	}

	if result.ExitCode != 1 {
		t.Fatalf("expected exit code 1, got %d", result.ExitCode)
	}

	if !bytes.Equal(result.Stderr, []byte("command failed")) {
		t.Fatalf("unexpected stderr: %q", result.Stderr)
	}
}
