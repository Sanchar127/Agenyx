package session

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/sanchar127/agenyx/pkg/router"
)

const (
	sessionKeyPrefix = "agenyx:router:session:"
	sessionTTL       = 24 * time.Hour
)

// ValkeyStore is a distributed routing-session store backed by Valkey.
//
// CompareAndSwap uses an atomic Lua script so multiple router instances
// can safely update the same session concurrently.
type ValkeyStore struct {
	client *redis.Client
}

// NewValkeyStore creates a Valkey-backed session store.
func NewValkeyStore(client *redis.Client) *ValkeyStore {
	return &ValkeyStore{
		client: client,
	}
}

func sessionKey(sessionID string) string {
	return sessionKeyPrefix + sessionID
}

// Get returns the current routing session state.
func (s *ValkeyStore) Get(
	ctx context.Context,
	sessionID string,
) (router.SessionState, bool, error) {
	if err := ctx.Err(); err != nil {
		return router.SessionState{}, false, err
	}

	data, err := s.client.Get(ctx, sessionKey(sessionID)).Bytes()
	if errors.Is(err, redis.Nil) {
		return router.SessionState{}, false, nil
	}

	if err != nil {
		return router.SessionState{}, false, err
	}

	var state router.SessionState

	if err := json.Unmarshal(data, &state); err != nil {
		return router.SessionState{}, false,
			fmt.Errorf("decode session state: %w", err)
	}

	if state.ModelTurns == nil {
		state.ModelTurns = make(map[string]int64)
	}

	return state, true, nil
}

// CompareAndSwap atomically updates a session if its version matches.
//
// For a new session expectedVersion must be zero.
func (s *ValkeyStore) CompareAndSwap(
	ctx context.Context,
	sessionID string,
	expectedVersion uint64,
	state router.SessionState,
) error {
	if err := ctx.Err(); err != nil {
		return err
	}

	data, err := json.Marshal(state)
	if err != nil {
		return fmt.Errorf("encode session state: %w", err)
	}

	result, err := compareAndSwapScript.Run(
		ctx,
		s.client,
		[]string{sessionKey(sessionID)},
		expectedVersion,
		string(data),
		int64(sessionTTL/time.Second),
	).Int()

	if err != nil {
		return err
	}

	switch result {
	case 1:
		return nil

	case 0:
		return ErrVersionConflict

	default:
		return fmt.Errorf("unexpected CAS result: %d", result)
	}
}

// Atomic version check + write.
//
// KEYS[1] = session key
// ARGV[1] = expected version
// ARGV[2] = serialized state
// ARGV[3] = TTL in seconds
var compareAndSwapScript = redis.NewScript(`
local key = KEYS[1]
local expected = tonumber(ARGV[1])
local data = ARGV[2]
local ttl = tonumber(ARGV[3])

local current = redis.call("GET", key)

if not current then
	if expected ~= 0 then
		return 0
	end

	local state = cjson.decode(data)
	state["Version"] = 1

	redis.call(
		"SET",
		key,
		cjson.encode(state),
		"EX",
		ttl
	)

	return 1
end

local currentState = cjson.decode(current)
local currentVersion = tonumber(currentState["Version"])

if currentVersion ~= expected then
	return 0
end

local nextState = cjson.decode(data)
nextState["Version"] = expected + 1

redis.call(
	"SET",
	key,
	cjson.encode(nextState),
	"EX",
	ttl
)

return 1
`)
