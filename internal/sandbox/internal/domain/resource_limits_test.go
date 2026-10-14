package domain

import (
	"testing"
	"time"
)

func validResourceLimits() ResourceLimits {
	return ResourceLimits{
		MilliCPU:         500,
		MemoryBytes:      512 * 1024 * 1024,
		PIDs:             256,
		DiskBytes:        1 * 1024 * 1024 * 1024,
		ExecutionTimeout: 30 * time.Second,
	}
}

func TestResourceLimitsValidate(t *testing.T) {
	limits := validResourceLimits()

	if err := limits.Validate(); err != nil {
		t.Fatalf("expected valid resource limits, got error: %v", err)
	}
}

func TestResourceLimitsValidateRejectsInvalidValues(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*ResourceLimits)
	}{
		{
			name: "zero milliCPU",
			mutate: func(r *ResourceLimits) {
				r.MilliCPU = 0
			},
		},
		{
			name: "negative milliCPU",
			mutate: func(r *ResourceLimits) {
				r.MilliCPU = -1
			},
		},
		{
			name: "zero memory",
			mutate: func(r *ResourceLimits) {
				r.MemoryBytes = 0
			},
		},
		{
			name: "zero PIDs",
			mutate: func(r *ResourceLimits) {
				r.PIDs = 0
			},
		},
		{
			name: "zero disk",
			mutate: func(r *ResourceLimits) {
				r.DiskBytes = 0
			},
		},
		{
			name: "zero timeout",
			mutate: func(r *ResourceLimits) {
				r.ExecutionTimeout = 0
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			limits := validResourceLimits()
			tt.mutate(&limits)

			if err := limits.Validate(); err == nil {
				t.Fatal("expected validation error, got nil")
			}
		})
	}
}
