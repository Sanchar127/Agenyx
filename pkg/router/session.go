package router

import (
	"context"
	"time"
)

// SessionState contains routing-specific state for a conversation.
//
// This is deliberately not the agent's conversation state. Messages,
// tool calls, checkpoints, and application memory belong elsewhere.
type SessionState struct {
	SessionID string

	CurrentModel string

	TurnCount int64

	ModelTurns map[string]int64

	SwitchCount int64

	LastDecision string

	LastSeen time.Time

	Version uint64
}

// SessionStore provides shared routing-session state.
//
// Implementations must provide optimistic concurrency semantics through
// CompareAndSwap.
type SessionStore interface {
	Get(
		ctx context.Context,
		sessionID string,
	) (SessionState, bool, error)

	CompareAndSwap(
		ctx context.Context,
		sessionID string,
		expectedVersion uint64,
		state SessionState,
	) error
}
