package domain

import "context"

type SandboxStore interface {
	Create(ctx context.Context, sandbox Sandbox) error
	Get(ctx context.Context, id SandboxID) (Sandbox, error)
	Update(ctx context.Context, sandbox Sandbox) error
	Delete(ctx context.Context, id SandboxID) error
	List(ctx context.Context) ([]Sandbox, error)
}
