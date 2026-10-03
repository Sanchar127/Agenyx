package domain

import (
	"errors"
	"testing"
	"time"
)

func validSandboxSpec() SandboxSpec {
	return SandboxSpec{
		ResourceLimits: ResourceLimits{
			MilliCPU:         500,
			MemoryBytes:      512 * 1024 * 1024,
			PIDs:             256,
			DiskBytes:        1 * 1024 * 1024 * 1024,
			ExecutionTimeout: 30 * time.Second,
		},
		FilesystemPolicy: FilesystemPolicy{
			Mounts: []FilesystemMount{
				{
					Path:   "/workspace",
					Access: FilesystemAccessReadWrite,
				},
			},
		},
		NetworkPolicy: NetworkPolicy{
			Enabled: true,
			EgressRules: []NetworkRule{
				{
					Host: "api.github.com",
					Port: 443,
				},
			},
		},
	}
}

func TestSandboxSpecValidate(t *testing.T) {
	spec := validSandboxSpec()

	if err := spec.Validate(); err != nil {
		t.Fatalf("expected valid SandboxSpec, got %v", err)
	}
}

func TestSandboxSpecValidatePropagatesInvalidInput(t *testing.T) {
	spec := validSandboxSpec()
	spec.ResourceLimits.MemoryBytes = 0

	err := spec.Validate()

	if err == nil {
		t.Fatal("expected validation error")
	}

	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("expected ErrInvalidInput, got %v", err)
	}
}
