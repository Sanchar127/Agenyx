package application

import (
	"context"
	"testing"

	"github.com/sanchar127/agenyx/sandbox/internal/domain"
)

type fakeExecutionService struct{}

func (f *fakeExecutionService) Submit(
	ctx context.Context,
	sandboxID domain.SandboxID,
	command string,
	args []string,
) (domain.Execution, error) {
	return domain.Execution{}, nil
}

func (f *fakeExecutionService) Get(
	ctx context.Context,
	id domain.ExecutionID,
) (domain.Execution, error) {
	return domain.Execution{}, nil
}

var _ ExecutionService = (*fakeExecutionService)(nil)

func TestExecutionServiceContract(t *testing.T) {
	var service ExecutionService = &fakeExecutionService{}

	_, err := service.Submit(
		context.Background(),
		domain.NewSandboxID(),
		"echo",
		[]string{"hello"},
	)
	if err != nil {
		t.Fatalf("Submit() error = %v", err)
	}

	_, err = service.Get(
		context.Background(),
		domain.NewExecutionID(),
	)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
}
