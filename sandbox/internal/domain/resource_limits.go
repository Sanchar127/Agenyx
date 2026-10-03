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
		return fmt.Errorf("milliCPU must be greater than 0")
	}

	if r.MemoryBytes <= 0 {
		return fmt.Errorf("memory bytes must be greater than 0")
	}

	if r.PIDs <= 0 {
		return fmt.Errorf("PIDs must be greater than 0")
	}

	if r.DiskBytes <= 0 {
		return fmt.Errorf("disk bytes must be greater than 0")
	}

	if r.ExecutionTimeout <= 0 {
		return fmt.Errorf("execution timeout must be greater than 0")
	}

	return nil
}
