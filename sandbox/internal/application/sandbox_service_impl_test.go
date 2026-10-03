package application

import (
	"context"
	"errors"
	"reflect"
	"testing"
	"time"

	"github.com/sanchar127/agenyx/sandbox/internal/domain"
)

type mockSandboxStore struct {
	createCalls int
	getCalls    int
	updateCalls int
	deleteCalls int
	listCalls   int

	createErr error
	getErr    error
	updateErr error
	deleteErr error
	listErr   error

	sandbox   domain.Sandbox
	sandboxes []domain.Sandbox
}

func (m *mockSandboxStore) Create(
	ctx context.Context,
	sandbox domain.Sandbox,
) error {
	m.createCalls++
	m.sandbox = sandbox

	return m.createErr
}

func (m *mockSandboxStore) Get(
	ctx context.Context,
	id domain.SandboxID,
) (domain.Sandbox, error) {
	m.getCalls++

	if m.getErr != nil {
		return domain.Sandbox{}, m.getErr
	}

	return m.sandbox, nil
}

func (m *mockSandboxStore) Update(
	ctx context.Context,
	sandbox domain.Sandbox,
) error {
	m.updateCalls++
	m.sandbox = sandbox

	return m.updateErr
}

func (m *mockSandboxStore) Delete(
	ctx context.Context,
	id domain.SandboxID,
) error {
	m.deleteCalls++

	return m.deleteErr
}

func (m *mockSandboxStore) List(
	ctx context.Context,
) ([]domain.Sandbox, error) {
	m.listCalls++

	if m.listErr != nil {
		return nil, m.listErr
	}

	return m.sandboxes, nil
}

var _ domain.SandboxStore = (*mockSandboxStore)(nil)

func validSpec() domain.SandboxSpec {
	return domain.SandboxSpec{
		ResourceLimits: domain.ResourceLimits{
			MilliCPU:         500,
			MemoryBytes:      512 * 1024 * 1024,
			PIDs:             256,
			DiskBytes:        1024 * 1024 * 1024,
			ExecutionTimeout: 30 * time.Second,
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

func validSandbox() domain.Sandbox {
	now := time.Now().UTC()

	return domain.Sandbox{
		ID:        domain.NewSandboxID(),
		State:     domain.SandboxStateRequested,
		Spec:      validSpec(),
		CreatedAt: now,
		UpdatedAt: now,
	}
}

func TestSandboxServiceCreate(t *testing.T) {
	store := &mockSandboxStore{}
	service := NewSandboxService(store)

	ctx := context.Background()

	metadata := map[string]string{
		"agent_id": "agent-123",
	}

	spec := validSpec()

	sandbox, err := service.Create(ctx, spec, metadata)
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}

	if store.createCalls != 1 {
		t.Fatalf(
			"Create() store calls = %d, want 1",
			store.createCalls,
		)
	}

	if sandbox.ID == "" {
		t.Fatal("Create() returned sandbox with empty ID")
	}

	if sandbox.State != domain.SandboxStateRequested {
		t.Fatalf(
			"Create() state = %q, want %q",
			sandbox.State,
			domain.SandboxStateRequested,
		)
	}

	if sandbox.Spec.ResourceLimits.MilliCPU != spec.ResourceLimits.MilliCPU {
		t.Fatal("Create() did not preserve resource limits")
	}

	if sandbox.Metadata["agent_id"] != "agent-123" {
		t.Fatal("Create() did not preserve metadata")
	}
}

func TestSandboxServiceCreateInvalidSpec(t *testing.T) {
	store := &mockSandboxStore{}
	service := NewSandboxService(store)

	ctx := context.Background()

	spec := validSpec()
	spec.ResourceLimits.MemoryBytes = 0

	_, err := service.Create(ctx, spec, nil)
	if !errors.Is(err, domain.ErrInvalidInput) {
		t.Fatalf(
			"Create() error = %v, want ErrInvalidInput",
			err,
		)
	}

	if store.createCalls != 0 {
		t.Fatalf(
			"store Create() calls = %d, want 0",
			store.createCalls,
		)
	}
}

func TestSandboxServiceCreateStoreError(t *testing.T) {
	storeErr := errors.New("store unavailable")

	store := &mockSandboxStore{
		createErr: storeErr,
	}

	service := NewSandboxService(store)

	_, err := service.Create(
		context.Background(),
		validSpec(),
		nil,
	)

	if !errors.Is(err, storeErr) {
		t.Fatalf(
			"Create() error = %v, want %v",
			err,
			storeErr,
		)
	}
}

func TestSandboxServiceGet(t *testing.T) {
	expected := validSandbox()

	store := &mockSandboxStore{
		sandbox: expected,
	}

	service := NewSandboxService(store)

	got, err := service.Get(
		context.Background(),
		expected.ID,
	)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if got.ID != expected.ID {
		t.Fatalf(
			"Get() ID = %q, want %q",
			got.ID,
			expected.ID,
		)
	}

	if store.getCalls != 1 {
		t.Fatalf(
			"Get() store calls = %d, want 1",
			store.getCalls,
		)
	}
}

func TestSandboxServiceGetStoreError(t *testing.T) {
	storeErr := domain.ErrNotFound

	store := &mockSandboxStore{
		getErr: storeErr,
	}

	service := NewSandboxService(store)

	_, err := service.Get(
		context.Background(),
		domain.NewSandboxID(),
	)

	if !errors.Is(err, domain.ErrNotFound) {
		t.Fatalf(
			"Get() error = %v, want ErrNotFound",
			err,
		)
	}
}

func TestSandboxServiceList(t *testing.T) {
	expected := []domain.Sandbox{
		validSandbox(),
		validSandbox(),
	}

	store := &mockSandboxStore{
		sandboxes: expected,
	}

	service := NewSandboxService(store)

	got, err := service.List(context.Background())
	if err != nil {
		t.Fatalf("List() error = %v", err)
	}

	if len(got) != len(expected) {
		t.Fatalf(
			"List() returned %d sandboxes, want %d",
			len(got),
			len(expected),
		)
	}

	if store.listCalls != 1 {
		t.Fatalf(
			"List() store calls = %d, want 1",
			store.listCalls,
		)
	}
}

func TestSandboxServiceListStoreError(t *testing.T) {
	storeErr := errors.New("database unavailable")

	store := &mockSandboxStore{
		listErr: storeErr,
	}

	service := NewSandboxService(store)

	_, err := service.List(context.Background())
	if !errors.Is(err, storeErr) {
		t.Fatalf(
			"List() error = %v, want %v",
			err,
			storeErr,
		)
	}
}

func TestSandboxServiceStop(t *testing.T) {
	sandbox := validSandbox()
	sandbox.State = domain.SandboxStateReady

	store := &mockSandboxStore{
		sandbox: sandbox,
	}

	service := NewSandboxService(store)

	err := service.Stop(
		context.Background(),
		sandbox.ID,
	)
	if err != nil {
		t.Fatalf("Stop() error = %v", err)
	}

	if store.getCalls != 1 {
		t.Fatalf(
			"Stop() Get calls = %d, want 1",
			store.getCalls,
		)
	}

	if store.updateCalls != 1 {
		t.Fatalf(
			"Stop() Update calls = %d, want 1",
			store.updateCalls,
		)
	}

	if store.sandbox.State != domain.SandboxStateStopping {
		t.Fatalf(
			"Stop() state = %q, want %q",
			store.sandbox.State,
			domain.SandboxStateStopping,
		)
	}
}

func TestSandboxServiceStopInvalidTransition(t *testing.T) {
	sandbox := validSandbox()

	store := &mockSandboxStore{
		sandbox: sandbox,
	}

	service := NewSandboxService(store)

	err := service.Stop(
		context.Background(),
		sandbox.ID,
	)

	if !errors.Is(err, domain.ErrConflict) {
		t.Fatalf(
			"Stop() error = %v, want ErrConflict",
			err,
		)
	}

	if store.updateCalls != 0 {
		t.Fatalf(
			"Stop() Update calls = %d, want 0",
			store.updateCalls,
		)
	}
}

func TestSandboxServiceStopGetError(t *testing.T) {
	store := &mockSandboxStore{
		getErr: domain.ErrNotFound,
	}

	service := NewSandboxService(store)

	err := service.Stop(
		context.Background(),
		domain.NewSandboxID(),
	)

	if !errors.Is(err, domain.ErrNotFound) {
		t.Fatalf(
			"Stop() error = %v, want ErrNotFound",
			err,
		)
	}

	if store.updateCalls != 0 {
		t.Fatalf(
			"Stop() Update calls = %d, want 0",
			store.updateCalls,
		)
	}
}

func TestSandboxServiceDelete(t *testing.T) {
	sandbox := validSandbox()
	sandbox.State = domain.SandboxStateStopped

	store := &mockSandboxStore{
		sandbox: sandbox,
	}

	service := NewSandboxService(store)

	err := service.Delete(
		context.Background(),
		sandbox.ID,
	)
	if err != nil {
		t.Fatalf("Delete() error = %v", err)
	}

	if store.getCalls != 1 {
		t.Fatalf(
			"Delete() Get calls = %d, want 1",
			store.getCalls,
		)
	}

	if store.updateCalls != 1 {
		t.Fatalf(
			"Delete() Update calls = %d, want 1",
			store.updateCalls,
		)
	}

	if store.sandbox.State != domain.SandboxStateDeleted {
		t.Fatalf(
			"Delete() state = %q, want %q",
			store.sandbox.State,
			domain.SandboxStateDeleted,
		)
	}
}

func TestSandboxServiceDeleteInvalidTransition(t *testing.T) {
	sandbox := validSandbox()

	store := &mockSandboxStore{
		sandbox: sandbox,
	}

	service := NewSandboxService(store)

	err := service.Delete(
		context.Background(),
		sandbox.ID,
	)

	if !errors.Is(err, domain.ErrConflict) {
		t.Fatalf(
			"Delete() error = %v, want ErrConflict",
			err,
		)
	}

	if store.updateCalls != 0 {
		t.Fatalf(
			"Delete() Update calls = %d, want 0",
			store.updateCalls,
		)
	}
}

func TestSandboxServiceDeleteGetError(t *testing.T) {
	store := &mockSandboxStore{
		getErr: domain.ErrNotFound,
	}

	service := NewSandboxService(store)

	err := service.Delete(
		context.Background(),
		domain.NewSandboxID(),
	)

	if !errors.Is(err, domain.ErrNotFound) {
		t.Fatalf(
			"Delete() error = %v, want ErrNotFound",
			err,
		)
	}

	if store.updateCalls != 0 {
		t.Fatalf(
			"Delete() Update calls = %d, want 0",
			store.updateCalls,
		)
	}
}

func TestSandboxServiceCreateWorkflow(t *testing.T) {
	store := &mockSandboxStore{}
	service := NewSandboxService(store)

	spec := validSpec()
	metadata := map[string]string{
		"owner": "test",
	}

	sandbox, err := service.Create(
		context.Background(),
		spec,
		metadata,
	)
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}

	if sandbox.ID == "" {
		t.Fatal("Create() returned sandbox with empty ID")
	}

	if sandbox.State != domain.SandboxStateRequested {
		t.Fatalf(
			"Create() state = %q, want %q",
			sandbox.State,
			domain.SandboxStateRequested,
		)
	}

	if !reflect.DeepEqual(sandbox.Spec, spec) {
		t.Fatal("Create() did not preserve spec")
	}

	if sandbox.Metadata["owner"] != "test" {
		t.Fatal("Create() did not preserve metadata")
	}

	if store.createCalls != 1 {
		t.Fatalf(
			"store Create() calls = %d, want 1",
			store.createCalls,
		)
	}

	stored, err := store.Get(
		context.Background(),
		sandbox.ID,
	)
	if err != nil {
		t.Fatalf("store.Get() error = %v", err)
	}

	if stored.State != domain.SandboxStateRequested {
		t.Fatalf(
			"stored sandbox state = %q, want %q",
			stored.State,
			domain.SandboxStateRequested,
		)
	}
}
