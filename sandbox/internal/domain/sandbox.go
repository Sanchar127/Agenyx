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
	CreatedAt time.Time
	UpdatedAt time.Time
	Metadata  map[string]string
}

func NewSandbox(metadata map[string]string) *Sandbox {
	now := time.Now().UTC()

	return &Sandbox{
		ID:        NewSandboxID(),
		CreatedAt: now,
		UpdatedAt: now,
		Metadata:  metadata,
	}
}
