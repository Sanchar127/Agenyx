package domain

import (
	"context"
	"errors"
	"testing"
)

type fakeSandboxStore struct {
	sandboxes map[SandboxID]Sandbox
}

func newFakeSandboxStore() *fakeSandboxStore {
	return &fakeSandboxStore{
		sandboxes: make(map[SandboxID]Sandbox),
	}
}

func (f *fakeSandboxStore) Create(
	ctx context.Context,
	sandbox Sandbox,
) error {
	if _, exists := f.sandboxes[sandbox.ID]; exists {
		return ErrConflict
	}

	f.sandboxes[sandbox.ID] = sandbox
	return nil
}

func (f *fakeSandboxStore) Get(
	ctx context.Context,
	id SandboxID,
) (Sandbox, error) {
	sandbox, exists := f.sandboxes[id]
	if !exists {
		return Sandbox{}, ErrNotFound
	}

	return sandbox, nil
}

func (f *fakeSandboxStore) Update(
	ctx context.Context,
	sandbox Sandbox,
) error {
	if _, exists := f.sandboxes[sandbox.ID]; !exists {
		return ErrNotFound
	}

	f.sandboxes[sandbox.ID] = sandbox
	return nil
}

func (f *fakeSandboxStore) Delete(
	ctx context.Context,
	id SandboxID,
) error {
	if _, exists := f.sandboxes[id]; !exists {
		return ErrNotFound
	}

	delete(f.sandboxes, id)
	return nil
}

func (f *fakeSandboxStore) List(
	ctx context.Context,
) ([]Sandbox, error) {
	sandboxes := make([]Sandbox, 0, len(f.sandboxes))

	for _, sandbox := range f.sandboxes {
		sandboxes = append(sandboxes, sandbox)
	}

	return sandboxes, nil
}

var _ SandboxStore = (*fakeSandboxStore)(nil)

func testSandboxStoreContract(t *testing.T, store SandboxStore) {
	t.Helper()

	ctx := context.Background()
	sandbox := *NewSandbox(nil, validSandboxSpec())

	// Create.
	if err := store.Create(ctx, sandbox); err != nil {
		t.Fatalf("Create() error = %v", err)
	}

	// Duplicate create.
	if err := store.Create(ctx, sandbox); !errors.Is(err, ErrConflict) {
		t.Fatalf(
			"duplicate Create() error = %v, want ErrConflict",
			err,
		)
	}

	// Get.
	got, err := store.Get(ctx, sandbox.ID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if got.ID != sandbox.ID {
		t.Fatalf(
			"Get() ID = %q, want %q",
			got.ID,
			sandbox.ID,
		)
	}

	// Update.
	sandbox.State = SandboxStateCreating

	if err := store.Update(ctx, sandbox); err != nil {
		t.Fatalf("Update() error = %v", err)
	}

	got, err = store.Get(ctx, sandbox.ID)
	if err != nil {
		t.Fatalf("Get() after Update() error = %v", err)
	}

	if got.State != SandboxStateCreating {
		t.Fatalf(
			"Get() state = %q, want %q",
			got.State,
			SandboxStateCreating,
		)
	}

	// List.
	sandboxes, err := store.List(ctx)
	if err != nil {
		t.Fatalf("List() error = %v", err)
	}

	if len(sandboxes) != 1 {
		t.Fatalf(
			"List() returned %d sandboxes, want 1",
			len(sandboxes),
		)
	}

	// Delete.
	if err := store.Delete(ctx, sandbox.ID); err != nil {
		t.Fatalf("Delete() error = %v", err)
	}

	// Get after delete.
	_, err = store.Get(ctx, sandbox.ID)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf(
			"Get() after Delete() error = %v, want ErrNotFound",
			err,
		)
	}

	// Delete missing.
	if err := store.Delete(ctx, sandbox.ID); !errors.Is(err, ErrNotFound) {
		t.Fatalf(
			"Delete() missing error = %v, want ErrNotFound",
			err,
		)
	}
}

func TestFakeSandboxStoreContract(t *testing.T) {
	testSandboxStoreContract(t, newFakeSandboxStore())
}

func TestSandboxStoreMissingUpdate(t *testing.T) {
	ctx := context.Background()
	store := newFakeSandboxStore()

	sandbox := *NewSandbox(nil, validSandboxSpec())

	err := store.Update(ctx, sandbox)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf(
			"Update() missing error = %v, want ErrNotFound",
			err,
		)
	}
}

func TestSandboxStoreMissingGet(t *testing.T) {
	ctx := context.Background()
	store := newFakeSandboxStore()

	_, err := store.Get(ctx, NewSandboxID())
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf(
			"Get() missing error = %v, want ErrNotFound",
			err,
		)
	}
}
