package domain

import "time"

type SandboxState string

const (
	SandboxRequested SandboxState = "REQUESTED"
	SandboxCreating  SandboxState = "CREATING"
	SandboxReady     SandboxState = "READY"
	SandboxExecuting SandboxState = "EXECUTING"
	SandboxStopping  SandboxState = "STOPPING"
	SandboxStopped   SandboxState = "STOPPED"
	SandboxFailed    SandboxState = "FAILED"
	SandboxExpired   SandboxState = "EXPIRED"
	SandboxDeleted   SandboxState = "DELETED"
)

type Sandbox struct {
	ID        string
	State     SandboxState
	CreatedAt time.Time
	UpdatedAt time.Time
}

type SandboxSpec struct {
	CPU    int64
	Memory int64
	Disk   int64
	PIDs   int
}
