package domain

import (
	"time"

	"github.com/google/uuid"
)

type SandboxID string

func NewSandboxID() SandboxID {
	return SandboxID(uuid.NewString())
}

type Sandbox struct {
	ID        SandboxID
	State     SandboxState
	Spec      SandboxSpec
	CreatedAt time.Time
	UpdatedAt time.Time
	Metadata  map[string]string
}

func NewSandbox(metadata map[string]string, spec SandboxSpec) *Sandbox {
	now := time.Now().UTC()

	return &Sandbox{
		ID:        NewSandboxID(),
		State:     SandboxStateRequested,
		Spec:      spec,
		CreatedAt: now,
		UpdatedAt: now,
		Metadata:  metadata,
	}
}
