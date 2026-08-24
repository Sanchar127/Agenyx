// Package session provides routing-session state storage implementations.
package session

import (
	"context"
	"errors"
	"sync"

	"github.com/sanchar127/agenyx/pkg/router"
)

// ErrVersionConflict indicates that a compare-and-swap operation encountered a newer session version.
var ErrVersionConflict = errors.New("session version conflict")

// MemoryStore is a concurrent in-memory implementation of router.SessionStore.
//
// It is intended for local development and tests. Production deployments
// should use a distributed implementation such as Redis.
type MemoryStore struct {
	mu       sync.RWMutex
	sessions map[string]router.SessionState
}

// NewMemoryStore creates an empty session store.
func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		sessions: make(map[string]router.SessionState),
	}
}

// Get returns the current routing session state for the given session ID.
func (s *MemoryStore) Get(
	ctx context.Context,
	sessionID string,
) (router.SessionState, bool, error) {
	if err := ctx.Err(); err != nil {
		return router.SessionState{}, false, err
	}

	s.mu.RLock()
	defer s.mu.RUnlock()

	state, ok := s.sessions[sessionID]

	if !ok {
		return router.SessionState{}, false, nil
	}

	return cloneState(state), true, nil
}

// CompareAndSwap updates a session only when the expected version matches the current stored version.
func (s *MemoryStore) CompareAndSwap(
	ctx context.Context,
	sessionID string,
	expectedVersion uint64,
	state router.SessionState,
) error {
	if err := ctx.Err(); err != nil {
		return err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	current, exists := s.sessions[sessionID]

	if !exists {
		if expectedVersion != 0 {
			return ErrVersionConflict
		}

		state.Version = 1
		s.sessions[sessionID] = cloneState(state)

		return nil
	}

	if current.Version != expectedVersion {
		return ErrVersionConflict
	}

	state.Version = expectedVersion + 1

	s.sessions[sessionID] = cloneState(state)

	return nil
}

func cloneState(state router.SessionState) router.SessionState {
	modelTurns := make(map[string]int64, len(state.ModelTurns))

	for model, turns := range state.ModelTurns {
		modelTurns[model] = turns
	}

	state.ModelTurns = modelTurns

	return state
}
