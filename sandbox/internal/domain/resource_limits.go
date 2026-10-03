package domain

import (
	"fmt"
	"time"
)

type ResourceLimits struct {
	MilliCPU         int64
	MemoryBytes      int64
	PIDs             int64
	DiskBytes        int64
	ExecutionTimeout time.Duration
}

func (r ResourceLimits) Validate() error {
	if r.MilliCPU <= 0 {
		return fmt.Errorf("%w: milliCPU must be greater than 0", ErrInvalidInput)
	}

	if r.MemoryBytes <= 0 {
		return fmt.Errorf("%w: memory bytes must be greater than 0", ErrInvalidInput)
	}

	if r.PIDs <= 0 {
		return fmt.Errorf("%w: PIDs must be greater than 0", ErrInvalidInput)
	}

	if r.DiskBytes <= 0 {
		return fmt.Errorf("%w: disk bytes must be greater than 0", ErrInvalidInput)
	}

	if r.ExecutionTimeout <= 0 {
		return fmt.Errorf("%w: execution timeout must be greater than 0", ErrInvalidInput)
	}

	return nil
}
