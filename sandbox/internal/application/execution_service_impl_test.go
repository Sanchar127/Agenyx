package application

import (
	"context"
	"errors"
	"testing"

	"github.com/sanchar127/agenyx/sandbox/internal/domain"
)

type mockExecutionStore struct {
	createCalls int
	getCalls    int
	updateCalls int

	createErr error
	getErr    error
	updateErr error

	execution domain.Execution
}

func (m *mockExecutionStore) Create(
	ctx context.Context,
	execution domain.Execution,
) error {
	m.createCalls++
	m.execution = execution
	return m.createErr
}

func (m *mockExecutionStore) Get(
	ctx context.Context,
	id domain.ExecutionID,
) (domain.Execution, error) {
	m.getCalls++

	if m.getErr != nil {
		return domain.Execution{}, m.getErr
	}

	return m.execution, nil
}

func (m *mockExecutionStore) Update(
	ctx context.Context,
	execution domain.Execution,
) error {
	m.updateCalls++
	m.execution = execution
	return m.updateErr
}

func validReadySandbox() domain.Sandbox {
	now := domain.NewSandbox(
		nil,
		validExecutionSpec(),
	)

	now.State = domain.SandboxStateReady

	return *now
}

func validExecutionSpec() domain.SandboxSpec {
	return domain.SandboxSpec{
		ResourceLimits: domain.ResourceLimits{
			MilliCPU:         500,
			MemoryBytes:      512 * 1024 * 1024,
			PIDs:             256,
			DiskBytes:        1 * 1024 * 1024 * 1024,
			ExecutionTimeout: 30,
		},
		FilesystemPolicy: domain.FilesystemPolicy{
			Mounts: []domain.FilesystemMount{
				{
					Path:   "/workspace",
					Access: domain.FilesystemAccessReadWrite,
				},
			},
		},
		NetworkPolicy: domain.NetworkPolicy{
			Enabled: true,
			EgressRules: []domain.NetworkRule{
				{
					Host: "api.github.com",
					Port: 443,
				},
			},
		},
	}
}

func TestExecutionServiceSubmit(t *testing.T) {
	sandbox := validReadySandbox()

	sandboxStore := &mockSandboxStore{
		sandbox: sandbox,
	}

	executionStore := &mockExecutionStore{}

	service := NewExecutionService(
		sandboxStore,
		executionStore,
	)

	execution, err := service.Submit(
		context.Background(),
		sandbox.ID,
		"echo",
		[]string{"hello"},
	)
	if err != nil {
		t.Fatalf("Submit() error = %v", err)
	}

	if execution.ID == "" {
		t.Fatal("Submit() returned empty execution ID")
	}

	if execution.SandboxID != sandbox.ID {
		t.Fatalf(
			"SandboxID = %q, want %q",
			execution.SandboxID,
			sandbox.ID,
		)
	}

	if execution.Command != "echo" {
		t.Fatalf(
			"Command = %q, want %q",
			execution.Command,
			"echo",
		)
	}

	if execution.State != domain.ExecutionStateRequested {
		t.Fatalf(
			"State = %q, want %q",
			execution.State,
			domain.ExecutionStateRequested,
		)
	}

	if sandboxStore.getCalls != 1 {
		t.Fatalf(
			"SandboxStore.Get() calls = %d, want 1",
			sandboxStore.getCalls,
		)
	}

	if executionStore.createCalls != 1 {
		t.Fatalf(
			"ExecutionStore.Create() calls = %d, want 1",
			executionStore.createCalls,
		)
	}
}

func TestExecutionServiceSubmitSandboxNotReady(t *testing.T) {
	sandbox := validReadySandbox()
	sandbox.State = domain.SandboxStateRequested

	sandboxStore := &mockSandboxStore{
		sandbox: sandbox,
	}

	executionStore := &mockExecutionStore{}

	service := NewExecutionService(
		sandboxStore,
		executionStore,
	)

	_, err := service.Submit(
		context.Background(),
		sandbox.ID,
		"echo",
		[]string{"hello"},
	)
	if err == nil {
		t.Fatal("Submit() expected error, got nil")
	}

	if !errors.Is(err, domain.ErrConflict) {
		t.Fatalf(
			"Submit() error = %v, want ErrConflict",
			err,
		)
	}

	if executionStore.createCalls != 0 {
		t.Fatalf(
			"ExecutionStore.Create() calls = %d, want 0",
			executionStore.createCalls,
		)
	}
}

func TestExecutionServiceSubmitSandboxNotFound(t *testing.T) {
	sandboxID := domain.NewSandboxID()

	sandboxStore := &mockSandboxStore{
		getErr: domain.ErrNotFound,
	}

	executionStore := &mockExecutionStore{}

	service := NewExecutionService(
		sandboxStore,
		executionStore,
	)

	_, err := service.Submit(
		context.Background(),
		sandboxID,
		"echo",
		[]string{"hello"},
	)
	if !errors.Is(err, domain.ErrNotFound) {
		t.Fatalf(
			"Submit() error = %v, want ErrNotFound",
			err,
		)
	}

	if executionStore.createCalls != 0 {
		t.Fatalf(
			"ExecutionStore.Create() calls = %d, want 0",
			executionStore.createCalls,
		)
	}
}

func TestExecutionServiceSubmitInvalidSandboxID(t *testing.T) {
	sandboxStore := &mockSandboxStore{}
	executionStore := &mockExecutionStore{}

	service := NewExecutionService(
		sandboxStore,
		executionStore,
	)

	_, err := service.Submit(
		context.Background(),
		"",
		"echo",
		[]string{"hello"},
	)
	if !errors.Is(err, domain.ErrInvalidInput) {
		t.Fatalf(
			"Submit() error = %v, want ErrInvalidInput",
			err,
		)
	}

	if sandboxStore.getCalls != 0 {
		t.Fatalf(
			"SandboxStore.Get() calls = %d, want 0",
			sandboxStore.getCalls,
		)
	}
}

func TestExecutionServiceSubmitInvalidCommand(t *testing.T) {
	sandboxStore := &mockSandboxStore{}
	executionStore := &mockExecutionStore{}

	service := NewExecutionService(
		sandboxStore,
		executionStore,
	)

	_, err := service.Submit(
		context.Background(),
		domain.NewSandboxID(),
		"",
		nil,
	)
	if !errors.Is(err, domain.ErrInvalidInput) {
		t.Fatalf(
			"Submit() error = %v, want ErrInvalidInput",
			err,
		)
	}

	if sandboxStore.getCalls != 0 {
		t.Fatalf(
			"SandboxStore.Get() calls = %d, want 0",
			sandboxStore.getCalls,
		)
	}
}

func TestExecutionServiceSubmitStoreError(t *testing.T) {
	sandbox := validReadySandbox()

	storeErr := errors.New("execution store failure")

	sandboxStore := &mockSandboxStore{
		sandbox: sandbox,
	}

	executionStore := &mockExecutionStore{
		createErr: storeErr,
	}

	service := NewExecutionService(
		sandboxStore,
		executionStore,
	)

	_, err := service.Submit(
		context.Background(),
		sandbox.ID,
		"echo",
		[]string{"hello"},
	)
	if !errors.Is(err, storeErr) {
		t.Fatalf(
			"Submit() error = %v, want %v",
			err,
			storeErr,
		)
	}

	if executionStore.createCalls != 1 {
		t.Fatalf(
			"ExecutionStore.Create() calls = %d, want 1",
			executionStore.createCalls,
		)
	}
}

func TestExecutionServiceGet(t *testing.T) {
	execution := domain.NewExecution(
		domain.NewSandboxID(),
		"echo",
		[]string{"hello"},
	)

	executionStore := &mockExecutionStore{
		execution: *execution,
	}

	service := NewExecutionService(
		&mockSandboxStore{},
		executionStore,
	)

	got, err := service.Get(
		context.Background(),
		execution.ID,
	)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if got.ID != execution.ID {
		t.Fatalf(
			"ID = %q, want %q",
			got.ID,
			execution.ID,
		)
	}

	if executionStore.getCalls != 1 {
		t.Fatalf(
			"ExecutionStore.Get() calls = %d, want 1",
			executionStore.getCalls,
		)
	}
}

func TestExecutionServiceGetInvalidID(t *testing.T) {
	executionStore := &mockExecutionStore{}

	service := NewExecutionService(
		&mockSandboxStore{},
		executionStore,
	)

	_, err := service.Get(
		context.Background(),
		"",
	)
	if !errors.Is(err, domain.ErrInvalidInput) {
		t.Fatalf(
			"Get() error = %v, want ErrInvalidInput",
			err,
		)
	}

	if executionStore.getCalls != 0 {
		t.Fatalf(
			"ExecutionStore.Get() calls = %d, want 0",
			executionStore.getCalls,
		)
	}
}

func TestExecutionServiceGetStoreError(t *testing.T) {
	storeErr := errors.New("execution store failure")

	executionStore := &mockExecutionStore{
		getErr: storeErr,
	}

	service := NewExecutionService(
		&mockSandboxStore{},
		executionStore,
	)

	_, err := service.Get(
		context.Background(),
		domain.NewExecutionID(),
	)
	if !errors.Is(err, storeErr) {
		t.Fatalf(
			"Get() error = %v, want %v",
			err,
			storeErr,
		)
	}
}
