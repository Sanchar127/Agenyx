package application

import (
	"context"

	"github.com/sanchar127/agenyx/sandbox/internal/domain"
)

type ExecutionService interface {
	Submit(
		ctx context.Context,
		sandboxID domain.SandboxID,
		command string,
		args []string,
	) (domain.Execution, error)

	Get(
		ctx context.Context,
		id domain.ExecutionID,
	) (domain.Execution, error)
}
