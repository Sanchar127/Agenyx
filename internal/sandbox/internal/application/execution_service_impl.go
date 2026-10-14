package application

import (
	"context"
	"fmt"

	"github.com/sanchar127/agenyx/sandbox/internal/domain"
)

type executionService struct {
	sandboxStore   domain.SandboxStore
	executionStore domain.ExecutionStore
}

func NewExecutionService(
	sandboxStore domain.SandboxStore,
	executionStore domain.ExecutionStore,
) ExecutionService {
	return &executionService{
		sandboxStore:   sandboxStore,
		executionStore: executionStore,
	}
}

func (s *executionService) Submit(
	ctx context.Context,
	sandboxID domain.SandboxID,
	command string,
	args []string,
) (domain.Execution, error) {
	if sandboxID == "" {
		return domain.Execution{}, fmt.Errorf(
			"%w: sandbox ID must not be empty",
			domain.ErrInvalidInput,
		)
	}

	if command == "" {
		return domain.Execution{}, fmt.Errorf(
			"%w: command must not be empty",
			domain.ErrInvalidInput,
		)
	}

	sandbox, err := s.sandboxStore.Get(ctx, sandboxID)
	if err != nil {
		return domain.Execution{}, err
	}

	if sandbox.State != domain.SandboxStateReady {
		return domain.Execution{}, fmt.Errorf(
			"%w: sandbox is not ready: %s",
			domain.ErrConflict,
			sandbox.State,
		)
	}

	execution := domain.NewExecution(
		sandboxID,
		command,
		args,
	)

	if err := s.executionStore.Create(ctx, *execution); err != nil {
		return domain.Execution{}, err
	}

	return *execution, nil
}

func (s *executionService) Get(
	ctx context.Context,
	id domain.ExecutionID,
) (domain.Execution, error) {
	if id == "" {
		return domain.Execution{}, fmt.Errorf(
			"%w: execution ID must not be empty",
			domain.ErrInvalidInput,
		)
	}

	return s.executionStore.Get(ctx, id)
}

var _ ExecutionService = (*executionService)(nil)
