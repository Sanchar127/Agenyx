package application

import (
	"context"

	"github.com/sanchar127/agenyx/sandbox/internal/domain"
)

type SandboxService interface {
	Create(
		ctx context.Context,
		spec domain.SandboxSpec,
		metadata map[string]string,
	) (domain.Sandbox, error)

	Get(
		ctx context.Context,
		id domain.SandboxID,
	) (domain.Sandbox, error)

	List(
		ctx context.Context,
	) ([]domain.Sandbox, error)

	Stop(
		ctx context.Context,
		id domain.SandboxID,
	) error

	Delete(
		ctx context.Context,
		id domain.SandboxID,
	) error
}
