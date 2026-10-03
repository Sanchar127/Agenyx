package domain

import "fmt"

func (s ExecutionState) IsTerminal() bool {
	switch s {
	case ExecutionStateCompleted,
		ExecutionStateFailed,
		ExecutionStateTimeout:
		return true
	default:
		return false
	}
}

func (s ExecutionState) CanTransitionTo(target ExecutionState) bool {
	switch s {
	case ExecutionStateRequested:
		return target == ExecutionStateRunning

	case ExecutionStateRunning:
		return target == ExecutionStateCompleted ||
			target == ExecutionStateFailed ||
			target == ExecutionStateTimeout

	default:
		return false
	}
}

func (s ExecutionState) ValidateTransitionTo(target ExecutionState) error {
	if s.CanTransitionTo(target) {
		return nil
	}

	return fmt.Errorf(
		"invalid execution state transition: %s -> %s",
		s,
		target,
	)
}
