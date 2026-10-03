package domain

import "time"

type ExecutionID string

type ExecutionState string

const (
	ExecutionStateRequested ExecutionState = "REQUESTED"
	ExecutionStateRunning   ExecutionState = "RUNNING"
	ExecutionStateCompleted ExecutionState = "COMPLETED"
	ExecutionStateFailed    ExecutionState = "FAILED"
	ExecutionStateTimeout   ExecutionState = "TIMEOUT"
)

type Execution struct {
	ID        ExecutionID
	SandboxID SandboxID

	Command string
	Args    []string

	State ExecutionState

	ExitCode *int

	StartedAt   *time.Time
	CompletedAt *time.Time

	CreatedAt time.Time
	UpdatedAt time.Time
}

func NewExecution(
	sandboxID SandboxID,
	command string,
	args []string,
) *Execution {
	now := time.Now().UTC()

	return &Execution{
		ID:        ExecutionID(NewSandboxID()),
		SandboxID: sandboxID,
		Command:   command,
		Args:      args,
		State:     ExecutionStateRequested,
		CreatedAt: now,
		UpdatedAt: now,
	}
}
