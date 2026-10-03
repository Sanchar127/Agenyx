package domain

import "fmt"

type SandboxState string

const (
	SandboxStateRequested SandboxState = "REQUESTED"
	SandboxStateCreating  SandboxState = "CREATING"
	SandboxStateReady     SandboxState = "READY"
	SandboxStateExecuting SandboxState = "EXECUTING"
	SandboxStateCompleted SandboxState = "COMPLETED"
	SandboxStateFailed    SandboxState = "FAILED"
	SandboxStateStopping  SandboxState = "STOPPING"
	SandboxStateStopped   SandboxState = "STOPPED"
	SandboxStateDeleted   SandboxState = "DELETED"
)

func (s SandboxState) IsTerminal() bool {
	switch s {
	case SandboxStateCompleted, SandboxStateFailed, SandboxStateDeleted:
		return true
	default:
		return false
	}
}

func (s SandboxState) CanTransitionTo(target SandboxState) bool {
	switch s {
	case SandboxStateRequested:
		return target == SandboxStateCreating

	case SandboxStateCreating:
		return target == SandboxStateReady ||
			target == SandboxStateFailed

	case SandboxStateReady:
		return target == SandboxStateExecuting ||
			target == SandboxStateStopping

	case SandboxStateExecuting:
		return target == SandboxStateReady ||
			target == SandboxStateCompleted ||
			target == SandboxStateFailed

	case SandboxStateStopping:
		return target == SandboxStateStopped

	case SandboxStateStopped:
		return target == SandboxStateDeleted

	default:
		return false
	}
}

func (s SandboxState) ValidateTransitionTo(target SandboxState) error {
	if s.CanTransitionTo(target) {
		return nil
	}

	return fmt.Errorf(
		"invalid sandbox state transition: %s -> %s",
		s,
		target,
	)
}
