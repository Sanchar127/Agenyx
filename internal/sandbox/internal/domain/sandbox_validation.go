package domain

import (
	"fmt"
)

func (s Sandbox) Validate() error {
	if s.ID == "" {
		return fmt.Errorf("%w: sandbox ID must not be empty", ErrInvalidInput)
	}

	switch s.State {
	case SandboxStateRequested,
		SandboxStateCreating,
		SandboxStateReady,
		SandboxStateFailed,
		SandboxStateStopping,
		SandboxStateStopped,
		SandboxStateDeleted:
	default:
		return fmt.Errorf(
			"%w: invalid sandbox state: %s",
			ErrInvalidInput,
			s.State,
		)
	}

	if err := s.Spec.Validate(); err != nil {
		return err
	}

	if s.CreatedAt.IsZero() {
		return fmt.Errorf(
			"%w: createdAt must not be zero",
			ErrInvalidInput,
		)
	}

	if s.UpdatedAt.IsZero() {
		return fmt.Errorf(
			"%w: updatedAt must not be zero",
			ErrInvalidInput,
		)
	}

	if s.UpdatedAt.Before(s.CreatedAt) {
		return fmt.Errorf(
			"%w: updatedAt must not be before createdAt",
			ErrInvalidInput,
		)
	}

	return nil
}
