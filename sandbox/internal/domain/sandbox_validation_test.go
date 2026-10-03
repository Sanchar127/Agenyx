package domain

import (
	"errors"
	"testing"
	"time"
)

func validSandbox() Sandbox {
	now := time.Now().UTC()

	return Sandbox{
		ID:        NewSandboxID(),
		State:     SandboxStateRequested,
		Spec:      validSandboxSpec(),
		CreatedAt: now,
		UpdatedAt: now,
	}
}

func TestSandboxValidateValid(t *testing.T) {
	sandbox := validSandbox()

	if err := sandbox.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestSandboxValidateMissingID(t *testing.T) {
	sandbox := validSandbox()
	sandbox.ID = ""

	err := sandbox.Validate()

	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf(
			"Validate() error = %v, want ErrInvalidInput",
			err,
		)
	}
}

func TestSandboxValidateInvalidState(t *testing.T) {
	sandbox := validSandbox()
	sandbox.State = SandboxState("UNKNOWN")

	err := sandbox.Validate()

	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf(
			"Validate() error = %v, want ErrInvalidInput",
			err,
		)
	}
}

func TestSandboxValidateInvalidSpec(t *testing.T) {
	sandbox := validSandbox()
	sandbox.Spec.ResourceLimits.MemoryBytes = 0

	err := sandbox.Validate()

	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf(
			"Validate() error = %v, want ErrInvalidInput",
			err,
		)
	}
}

func TestSandboxValidateZeroCreatedAt(t *testing.T) {
	sandbox := validSandbox()
	sandbox.CreatedAt = time.Time{}

	err := sandbox.Validate()

	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf(
			"Validate() error = %v, want ErrInvalidInput",
			err,
		)
	}
}

func TestSandboxValidateZeroUpdatedAt(t *testing.T) {
	sandbox := validSandbox()
	sandbox.UpdatedAt = time.Time{}

	err := sandbox.Validate()

	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf(
			"Validate() error = %v, want ErrInvalidInput",
			err,
		)
	}
}

func TestSandboxValidateUpdatedAtBeforeCreatedAt(t *testing.T) {
	sandbox := validSandbox()
	sandbox.UpdatedAt = sandbox.CreatedAt.Add(-time.Second)

	err := sandbox.Validate()

	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf(
			"Validate() error = %v, want ErrInvalidInput",
			err,
		)
	}
}
