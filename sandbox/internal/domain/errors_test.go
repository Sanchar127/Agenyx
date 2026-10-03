package domain

import (
	"errors"
	"testing"
)

func TestDomainErrorsAreDistinct(t *testing.T) {
	if ErrInvalidInput == ErrNotFound {
		t.Fatal("ErrInvalidInput and ErrNotFound must be distinct")
	}

	if ErrInvalidInput == ErrConflict {
		t.Fatal("ErrInvalidInput and ErrConflict must be distinct")
	}

	if ErrNotFound == ErrConflict {
		t.Fatal("ErrNotFound and ErrConflict must be distinct")
	}
}

func TestDomainErrorsSupportErrorsIs(t *testing.T) {
	err := errors.New("wrapped error")

	wrapped := errors.Join(ErrInvalidInput, err)

	if !errors.Is(wrapped, ErrInvalidInput) {
		t.Fatal("expected errors.Is to identify ErrInvalidInput")
	}

	if !errors.Is(wrapped, err) {
		t.Fatal("expected errors.Is to identify wrapped error")
	}
}

func TestValidationErrorsSupportErrorsIs(t *testing.T) {
	tests := []struct {
		name string
		err  error
	}{
		{
			name: "resource limits",
			err:  ResourceLimits{}.Validate(),
		},
		{
			name: "filesystem policy",
			err: FilesystemPolicy{
				Mounts: []FilesystemMount{{Path: "relative", Access: FilesystemAccessReadWrite}},
			}.Validate(),
		},
		{
			name: "network policy",
			err: NetworkPolicy{
				EgressRules: []NetworkRule{{Host: "", Port: 443}},
			}.Validate(),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if !errors.Is(tt.err, ErrInvalidInput) {
				t.Fatalf("expected ErrInvalidInput, got %v", tt.err)
			}
		})
	}
}

func TestTransitionErrorsSupportErrorsIs(t *testing.T) {
	if err := SandboxStateRequested.ValidateTransitionTo(SandboxStateReady); !errors.Is(err, ErrConflict) {
		t.Fatalf("expected ErrConflict, got %v", err)
	}

	if err := ExecutionStateRequested.ValidateTransitionTo(ExecutionStateCompleted); !errors.Is(err, ErrConflict) {
		t.Fatalf("expected ErrConflict, got %v", err)
	}
}
