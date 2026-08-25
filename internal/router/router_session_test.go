package router

import (
	"context"
	"errors"
	"testing"

	"github.com/sanchar127/agenyx/internal/registry"
	"github.com/sanchar127/agenyx/internal/scoring"
	"github.com/sanchar127/agenyx/internal/session"
	"github.com/sanchar127/agenyx/internal/strategy"
	"github.com/sanchar127/agenyx/pkg/router"
)

func newTestEngine(t *testing.T) (
	*Engine,
	*session.MemoryStore,
) {
	t.Helper()

	reg := registry.New()

	models := []router.Model{
		{
			Name:          "qwen",
			Provider:      "ollama",
			Capabilities:  []string{"general", "coding"},
			ContextWindow: 32768,
			Priority:      10,
			Enabled:       true,
		},
		{
			Name:          "llama",
			Provider:      "ollama",
			Capabilities:  []string{"general"},
			ContextWindow: 8192,
			Priority:      5,
			Enabled:       true,
		},
	}

	for _, model := range models {
		if err := reg.Register(model); err != nil {
			t.Fatalf("Register() error = %v", err)
		}
	}

	store := session.NewMemoryStore()

	engine := New(
		reg,
		[]router.Strategy{
			strategy.NewCapabilityStrategy(),
		},
		scoring.NewPriorityScorer(0.01),
		store,
		SessionConfig{
			AffinityWeight:  0.10,
			SwitchThreshold: 0.20,
		},
	)

	return engine, store
}

func testRequest(sessionID string) router.Request {
	return router.Request{
		SessionID: sessionID,
		Task:      "coding",
		Messages: []router.Message{
			{
				Role:    "user",
				Content: "write Go code",
			},
		},
		Constraints: router.Constraints{
			RequiredCapabilities: []string{"coding"},
		},
	}
}

func TestRouteCreatesSession(t *testing.T) {
	t.Parallel()

	engine, store := newTestEngine(t)

	decision, err := engine.Route(
		context.Background(),
		testRequest("session-1"),
	)
	if err != nil {
		t.Fatalf("Route() error = %v", err)
	}

	if decision.Model != "qwen" {
		t.Fatalf(
			"Model = %q, want qwen",
			decision.Model,
		)
	}

	state, ok, err := store.Get(
		context.Background(),
		"session-1",
	)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected session to exist")
	}

	if state.CurrentModel != "qwen" {
		t.Fatalf(
			"CurrentModel = %q, want qwen",
			state.CurrentModel,
		)
	}

	if state.TurnCount != 1 {
		t.Fatalf(
			"TurnCount = %d, want 1",
			state.TurnCount,
		)
	}

	if state.ModelTurns["qwen"] != 1 {
		t.Fatalf(
			"ModelTurns[qwen] = %d, want 1",
			state.ModelTurns["qwen"],
		)
	}

	if state.Version != 1 {
		t.Fatalf(
			"Version = %d, want 1",
			state.Version,
		)
	}
}

func TestRouteSecondRequestSeesPreviousModel(t *testing.T) {
	t.Parallel()

	engine, store := newTestEngine(t)
	ctx := context.Background()

	first, err := engine.Route(
		ctx,
		testRequest("session-1"),
	)
	if err != nil {
		t.Fatalf("first Route() error = %v", err)
	}

	second, err := engine.Route(
		ctx,
		testRequest("session-1"),
	)
	if err != nil {
		t.Fatalf("second Route() error = %v", err)
	}

	if first.Model != second.Model {
		t.Fatalf(
			"model changed unexpectedly: first=%q second=%q",
			first.Model,
			second.Model,
		)
	}

	state, ok, err := store.Get(ctx, "session-1")
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected session to exist")
	}

	if state.CurrentModel != first.Model {
		t.Fatalf(
			"CurrentModel = %q, want %q",
			state.CurrentModel,
			first.Model,
		)
	}

	if state.TurnCount != 2 {
		t.Fatalf(
			"TurnCount = %d, want 2",
			state.TurnCount,
		)
	}

	if state.ModelTurns[first.Model] != 2 {
		t.Fatalf(
			"ModelTurns[%s] = %d, want 2",
			first.Model,
			state.ModelTurns[first.Model],
		)
	}

	if state.Version != 2 {
		t.Fatalf(
			"Version = %d, want 2",
			state.Version,
		)
	}
}

func TestRouteModelSwitchUpdatesSession(t *testing.T) {
	t.Parallel()

	engine, store := newTestEngine(t)
	ctx := context.Background()

	first, err := engine.Route(
		ctx,
		testRequest("session-1"),
	)
	if err != nil {
		t.Fatalf("first Route() error = %v", err)
	}

	// Force the second request to only allow llama.
	request := testRequest("session-1")
	request.Task = "general"
	request.Constraints.RequiredCapabilities = []string{"general"}
	request.Constraints.AllowedModels = []string{"llama"}

	second, err := engine.Route(ctx, request)
	if err != nil {
		t.Fatalf("second Route() error = %v", err)
	}

	if first.Model == second.Model {
		t.Fatalf(
			"expected model switch, both requests used %q",
			first.Model,
		)
	}

	if second.Model != "llama" {
		t.Fatalf(
			"Model = %q, want llama",
			second.Model,
		)
	}

	state, ok, err := store.Get(ctx, "session-1")
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected session to exist")
	}

	if state.CurrentModel != "llama" {
		t.Fatalf(
			"CurrentModel = %q, want llama",
			state.CurrentModel,
		)
	}

	if state.TurnCount != 2 {
		t.Fatalf(
			"TurnCount = %d, want 2",
			state.TurnCount,
		)
	}

	if state.SwitchCount != 1 {
		t.Fatalf(
			"SwitchCount = %d, want 1",
			state.SwitchCount,
		)
	}

	if state.ModelTurns["qwen"] != 1 {
		t.Fatalf(
			"ModelTurns[qwen] = %d, want 1",
			state.ModelTurns["qwen"],
		)
	}

	if state.ModelTurns["llama"] != 1 {
		t.Fatalf(
			"ModelTurns[llama] = %d, want 1",
			state.ModelTurns["llama"],
		)
	}

	if state.Version != 2 {
		t.Fatalf(
			"Version = %d, want 2",
			state.Version,
		)
	}
}

func TestRouterInstancesShareSessionStore(t *testing.T) {
	t.Parallel()

	reg := registry.New()

	for _, model := range []router.Model{
		{
			Name:          "qwen",
			Provider:      "ollama",
			Capabilities:  []string{"general", "coding"},
			ContextWindow: 32768,
			Priority:      10,
			Enabled:       true,
		},
		{
			Name:          "llama",
			Provider:      "ollama",
			Capabilities:  []string{"general"},
			ContextWindow: 8192,
			Priority:      5,
			Enabled:       true,
		},
	} {
		if err := reg.Register(model); err != nil {
			t.Fatalf("Register() error = %v", err)
		}
	}

	sharedStore := session.NewMemoryStore()

	newEngine := func() *Engine {
		return New(
			reg,
			[]router.Strategy{
				strategy.NewCapabilityStrategy(),
			},
			scoring.NewPriorityScorer(0.01),
			sharedStore,
			SessionConfig{
				AffinityWeight:  0.10,
				SwitchThreshold: 0.20,
			},
		)
	}

	ctx := context.Background()

	routerA := newEngine()
	routerB := newEngine()

	first, err := routerA.Route(
		ctx,
		testRequest("shared-session"),
	)
	if err != nil {
		t.Fatalf("routerA Route() error = %v", err)
	}

	second, err := routerB.Route(
		ctx,
		testRequest("shared-session"),
	)
	if err != nil {
		t.Fatalf("routerB Route() error = %v", err)
	}

	if first.Model != second.Model {
		t.Fatalf(
			"shared session lost affinity: first=%q second=%q",
			first.Model,
			second.Model,
		)
	}

	state, ok, err := sharedStore.Get(
		ctx,
		"shared-session",
	)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected shared session to exist")
	}

	if state.TurnCount != 2 {
		t.Fatalf(
			"TurnCount = %d, want 2",
			state.TurnCount,
		)
	}

	if state.Version != 2 {
		t.Fatalf(
			"Version = %d, want 2",
			state.Version,
		)
	}
}

func TestMemoryStoreConcurrentUpdatesTriggerVersionConflict(t *testing.T) {
	t.Parallel()

	store := session.NewMemoryStore()
	ctx := context.Background()

	initial := router.SessionState{
		SessionID:    "concurrent-session",
		CurrentModel: "qwen",
		TurnCount:    1,
		ModelTurns: map[string]int64{
			"qwen": 1,
		},
	}

	if err := store.CompareAndSwap(
		ctx,
		"concurrent-session",
		0,
		initial,
	); err != nil {
		t.Fatalf("initial CompareAndSwap() error = %v", err)
	}

	state, ok, err := store.Get(ctx, "concurrent-session")
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected session to exist")
	}

	if state.Version != 1 {
		t.Fatalf(
			"initial Version = %d, want 1",
			state.Version,
		)
	}

	first := state
	first.ModelTurns = map[string]int64{
		"qwen": state.ModelTurns["qwen"] + 1,
	}
	first.TurnCount++

	second := state
	second.ModelTurns = map[string]int64{
		"qwen": state.ModelTurns["qwen"] + 1,
	}
	second.TurnCount++
	errCh := make(chan error, 2)

	go func() {
		errCh <- store.CompareAndSwap(
			ctx,
			"concurrent-session",
			state.Version,
			first,
		)
	}()

	go func() {
		errCh <- store.CompareAndSwap(
			ctx,
			"concurrent-session",
			state.Version,
			second,
		)
	}()

	var successCount int
	var conflictCount int

	for i := 0; i < 2; i++ {
		err := <-errCh

		switch {
		case err == nil:
			successCount++

		case errors.Is(err, session.ErrVersionConflict):
			conflictCount++

		default:
			t.Fatalf(
				"unexpected CompareAndSwap() error = %v",
				err,
			)
		}
	}

	if successCount != 1 {
		t.Fatalf(
			"successful updates = %d, want 1",
			successCount,
		)
	}

	if conflictCount != 1 {
		t.Fatalf(
			"version conflicts = %d, want 1",
			conflictCount,
		)
	}

	final, ok, err := store.Get(
		ctx,
		"concurrent-session",
	)
	if err != nil {
		t.Fatalf("final Get() error = %v", err)
	}

	if !ok {
		t.Fatal("expected session to exist after concurrent updates")
	}

	if final.Version != 2 {
		t.Fatalf(
			"final Version = %d, want 2",
			final.Version,
		)
	}

	if final.TurnCount != 2 {
		t.Fatalf(
			"final TurnCount = %d, want 2",
			final.TurnCount,
		)
	}

	if final.ModelTurns["qwen"] != 2 {
		t.Fatalf(
			"final ModelTurns[qwen] = %d, want 2",
			final.ModelTurns["qwen"],
		)
	}
}
