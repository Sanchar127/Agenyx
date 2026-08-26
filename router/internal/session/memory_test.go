package session

import (
	"context"
	"errors"
	"sync"
	"testing"

	"github.com/sanchar127/agenyx/pkg/router"
)

func TestMemoryStoreFirstRequestCreatesSession(t *testing.T) {
	t.Parallel()

	store := NewMemoryStore()
	ctx := context.Background()

	state := router.SessionState{
		SessionID:    "session-1",
		CurrentModel: "qwen2.5:7b",
		TurnCount:    1,
		ModelTurns: map[string]int64{
			"qwen2.5:7b": 1,
		},
	}

	if err := store.CompareAndSwap(ctx, "session-1", 0, state); err != nil {
		t.Fatalf("CompareAndSwap() error = %v", err)
	}

	got, ok, err := store.Get(ctx, "session-1")
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected session to exist")
	}

	if got.Version != 1 {
		t.Fatalf("Version = %d, want 1", got.Version)
	}

	if got.CurrentModel != "qwen2.5:7b" {
		t.Fatalf(
			"CurrentModel = %q, want %q",
			got.CurrentModel,
			"qwen2.5:7b",
		)
	}
}

func TestMemoryStoreCompareAndSwapIncrementsVersion(t *testing.T) {
	t.Parallel()

	store := NewMemoryStore()
	ctx := context.Background()

	initial := router.SessionState{
		SessionID:    "session-1",
		CurrentModel: "qwen2.5:7b",
		TurnCount:    1,
		ModelTurns: map[string]int64{
			"qwen2.5:7b": 1,
		},
	}

	if err := store.CompareAndSwap(ctx, "session-1", 0, initial); err != nil {
		t.Fatalf("initial CompareAndSwap() error = %v", err)
	}

	next := initial
	next.TurnCount = 2
	next.ModelTurns = map[string]int64{
		"qwen2.5:7b": 2,
	}

	if err := store.CompareAndSwap(ctx, "session-1", 1, next); err != nil {
		t.Fatalf("second CompareAndSwap() error = %v", err)
	}

	got, ok, err := store.Get(ctx, "session-1")
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected session to exist")
	}

	if got.Version != 2 {
		t.Fatalf("Version = %d, want 2", got.Version)
	}

	if got.TurnCount != 2 {
		t.Fatalf("TurnCount = %d, want 2", got.TurnCount)
	}

	if got.ModelTurns["qwen2.5:7b"] != 2 {
		t.Fatalf(
			"ModelTurns[qwen2.5:7b] = %d, want 2",
			got.ModelTurns["qwen2.5:7b"],
		)
	}
}

func TestMemoryStoreRejectsStaleVersion(t *testing.T) {
	t.Parallel()

	store := NewMemoryStore()
	ctx := context.Background()

	state := router.SessionState{
		SessionID:    "session-1",
		CurrentModel: "qwen2.5:7b",
	}

	if err := store.CompareAndSwap(ctx, "session-1", 0, state); err != nil {
		t.Fatalf("initial CompareAndSwap() error = %v", err)
	}

	err := store.CompareAndSwap(
		ctx,
		"session-1",
		0,
		state,
	)

	if !errors.Is(err, ErrVersionConflict) {
		t.Fatalf(
			"error = %v, want ErrVersionConflict",
			err,
		)
	}
}

func TestMemoryStoreConcurrentCompareAndSwap(t *testing.T) {
	t.Parallel()

	store := NewMemoryStore()
	ctx := context.Background()

	initial := router.SessionState{
		SessionID:    "session-1",
		CurrentModel: "qwen2.5:7b",
		TurnCount:    1,
		ModelTurns: map[string]int64{
			"qwen2.5:7b": 1,
		},
	}

	if err := store.CompareAndSwap(ctx, "session-1", 0, initial); err != nil {
		t.Fatalf("initial CompareAndSwap() error = %v", err)
	}

	const workers = 32

	var wg sync.WaitGroup
	errs := make(chan error, workers)

	wg.Add(workers)

	for i := 0; i < workers; i++ {
		go func() {
			defer wg.Done()

			state, ok, err := store.Get(ctx, "session-1")
			if err != nil {
				errs <- err
				return
			}

			if !ok {
				errs <- errors.New("session unexpectedly missing")
				return
			}

			state.TurnCount++

			if err := store.CompareAndSwap(
				ctx,
				"session-1",
				state.Version,
				state,
			); err != nil {
				errs <- err
				return
			}

			errs <- nil
		}()
	}

	wg.Wait()
	close(errs)

	var success int
	var conflicts int

	for err := range errs {
		if err == nil {
			success++
			continue
		}

		if errors.Is(err, ErrVersionConflict) {
			conflicts++
			continue
		}

		t.Fatalf("unexpected concurrent error: %v", err)
	}

	if success == 0 {
		t.Fatal("expected at least one successful update")
	}

	if conflicts == 0 {
		t.Fatal("expected at least one version conflict")
	}
}
