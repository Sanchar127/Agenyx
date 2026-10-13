package domain

import "context"

type ExecutionStore interface {
	Create(
		ctx context.Context,
		execution Execution,
	) error

	Get(
		ctx context.Context,
		id ExecutionID,
	) (Execution, error)

	Update(
		ctx context.Context,
		execution Execution,
	) error
}
