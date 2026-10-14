package domain

import (
	"context"
	"testing"
)

type fakeRuntime struct{}

func (f *fakeRuntime) Create(
	ctx context.Context,
	sandbox Sandbox,
	spec SandboxSpec,
) error {
	return nil
}

func (f *fakeRuntime) Execute(
	ctx context.Context,
	sandboxID SandboxID,
	command string,
	args []string,
) (ExecutionResult, error) {
	return ExecutionResult{}, nil
}

func (f *fakeRuntime) Stop(
	ctx context.Context,
	sandboxID SandboxID,
) error {
	return nil
}

func (f *fakeRuntime) Delete(
	ctx context.Context,
	sandboxID SandboxID,
) error {
	return nil
}

var _ Runtime = (*fakeRuntime)(nil)

func TestRuntimeContract(t *testing.T) {
	var runtime Runtime = &fakeRuntime{}

	ctx := context.Background()
	sandbox := *NewSandbox(nil, validSandboxSpec())
	spec := validSandboxSpec()

	if err := runtime.Create(ctx, sandbox, spec); err != nil {
		t.Fatalf("Create returned error: %v", err)
	}

	result, err := runtime.Execute(
		ctx,
		sandbox.ID,
		"echo",
		[]string{"hello"},
	)
	if err != nil {
		t.Fatalf("Execute returned error: %v", err)
	}

	if result.ExitCode != 0 {
		t.Fatalf("expected exit code 0, got %d", result.ExitCode)
	}

	if err := runtime.Stop(ctx, sandbox.ID); err != nil {
		t.Fatalf("Stop returned error: %v", err)
	}

	if err := runtime.Delete(ctx, sandbox.ID); err != nil {
		t.Fatalf("Delete returned error: %v", err)
	}
}
