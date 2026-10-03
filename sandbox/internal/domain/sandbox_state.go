package domain

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
