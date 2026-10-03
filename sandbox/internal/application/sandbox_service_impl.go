package application

import (
	"context"

	"github.com/sanchar127/agenyx/sandbox/internal/domain"
)

type sandboxService struct {
	store domain.SandboxStore
}

func NewSandboxService(store domain.SandboxStore) SandboxService {
	return &sandboxService{
		store: store,
	}
}

func (s *sandboxService) Create(
	ctx context.Context,
	spec domain.SandboxSpec,
	metadata map[string]string,
) (domain.Sandbox, error) {
	if err := spec.Validate(); err != nil {
		return domain.Sandbox{}, err
	}

	sandbox := domain.NewSandbox(metadata, spec)

	if err := sandbox.Validate(); err != nil {
		return domain.Sandbox{}, err
	}

	if err := s.store.Create(ctx, *sandbox); err != nil {
		return domain.Sandbox{}, err
	}

	return *sandbox, nil
}

func (s *sandboxService) Get(
	ctx context.Context,
	id domain.SandboxID,
) (domain.Sandbox, error) {
	return s.store.Get(ctx, id)
}

func (s *sandboxService) List(
	ctx context.Context,
) ([]domain.Sandbox, error) {
	return s.store.List(ctx)
}

func (s *sandboxService) Stop(
	ctx context.Context,
	id domain.SandboxID,
) error {
	sandbox, err := s.store.Get(ctx, id)
	if err != nil {
		return err
	}

	if err := sandbox.State.ValidateTransitionTo(
		domain.SandboxStateStopping,
	); err != nil {
		return err
	}

	sandbox.State = domain.SandboxStateStopping

	if err := s.store.Update(ctx, sandbox); err != nil {
		return err
	}

	return nil
}

func (s *sandboxService) Delete(
	ctx context.Context,
	id domain.SandboxID,
) error {
	sandbox, err := s.store.Get(ctx, id)
	if err != nil {
		return err
	}

	if err := sandbox.Validate(); err != nil {
		return err
	}

	if err := sandbox.State.ValidateTransitionTo(
		domain.SandboxStateDeleted,
	); err != nil {
		return err
	}

	sandbox.State = domain.SandboxStateDeleted

	return s.store.Update(ctx, sandbox)
}

var _ SandboxService = (*sandboxService)(nil)
