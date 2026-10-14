package orchestrator

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	defaultTaskStream    = "agenyx:tasks"
	defaultConsumerGroup = "agenyx-workers"
	defaultMaxAttempts   = 4
	defaultExecutionTTL  = 3600
)

type ValkeyQueue struct {
	client      *redis.Client
	stream      string
	maxAttempts int
	ttl         time.Duration
}

func NewValkeyQueueFromEnv() (*ValkeyQueue, error) {
	rawURL := strings.TrimSpace(os.Getenv("AGENTYX_VALKEY_URL"))
	if rawURL == "" {
		rawURL = "redis://valkey:6379/0"
	}

	parsedURL, err := url.Parse(rawURL)
	if err != nil {
		return nil, fmt.Errorf("parse Valkey URL: %w", err)
	}

	if parsedURL.Scheme != "redis" && parsedURL.Scheme != "rediss" {
		return nil, fmt.Errorf("unsupported Valkey URL scheme %q", parsedURL.Scheme)
	}

	options, err := redis.ParseURL(rawURL)
	if err != nil {
		return nil, fmt.Errorf("configure Valkey client: %w", err)
	}

	// Support the same password environment variable used by the
	// existing Python orchestrator configuration.
	if password := os.Getenv("AGENTYX_VALKEY_PASSWORD"); password != "" {
		options.Password = password
	}

	stream := strings.TrimSpace(os.Getenv("AGENTYX_TASK_STREAM"))
	if stream == "" {
		stream = defaultTaskStream
	}

	maxAttempts, err := envInt("AGENTYX_MAX_ATTEMPTS", defaultMaxAttempts)
	if err != nil || maxAttempts < 1 || maxAttempts > 20 {
		return nil, fmt.Errorf("AGENTYX_MAX_ATTEMPTS must be between 1 and 20")
	}

	ttlSeconds, err := envInt("AGENTYX_EXECUTION_TTL_SECONDS", defaultExecutionTTL)
	if err != nil || ttlSeconds < 60 {
		return nil, fmt.Errorf("AGENTYX_EXECUTION_TTL_SECONDS must be at least 60")
	}

	return &ValkeyQueue{
		client:      redis.NewClient(options),
		stream:      stream,
		maxAttempts: maxAttempts,
		ttl:         time.Duration(ttlSeconds) * time.Second,
	}, nil
}

func envInt(name string, fallback int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	return strconv.Atoi(raw)
}

func (q *ValkeyQueue) Ping(ctx context.Context) error {
	if err := q.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("ping Valkey: %w", err)
	}
	return nil
}

func (q *ValkeyQueue) Submit(
	ctx context.Context,
	executionID string,
	intent string,
) error {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	key := "agenyx:execution:" + executionID

	// Keep execution creation and stream publication in one Redis
	// transaction so the worker does not see a task before its
	// initial execution state has been created.
	_, err := q.client.TxPipelined(ctx, func(pipe redis.Pipeliner) error {
		pipe.HSet(ctx, key, map[string]interface{}{
			"execution_id": executionID,
			"status":       "queued",
			"intent":       intent,
			"error":        "",
			"attempt":      "0",
			"max_attempts": strconv.Itoa(q.maxAttempts),
			"queued_at":    now,
		})
		pipe.Expire(ctx, key, q.ttl)

		pipe.XAdd(ctx, &redis.XAddArgs{
			Stream: q.stream,
			Values: map[string]interface{}{
				"execution_id": executionID,
				"intent":       intent,
			},
		})

		return nil
	})
	if err != nil {
		return fmt.Errorf("submit execution to Valkey: %w", err)
	}

	return nil
}

func (q *ValkeyQueue) GetExecution(
	ctx context.Context,
	executionID string,
) (map[string]string, error) {
	state, err := q.client.HGetAll(
		ctx,
		"agenyx:execution:"+executionID,
	).Result()
	if err != nil {
		return nil, fmt.Errorf("read execution state: %w", err)
	}

	return state, nil
}

func (q *ValkeyQueue) Close() error {
	return q.client.Close()
}

// Ensure the queue implements the orchestrator's queue contract.
var _ Queue = (*ValkeyQueue)(nil)
