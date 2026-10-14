package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	defaultStream       = "agenyx:tasks"
	defaultGroup        = "agenyx-workers"
	defaultAgentURL     = "http://agent:8000"
	defaultMaxAttempts  = 4
	defaultRetryBase    = 5 * time.Second
	defaultRetryMax     = 60 * time.Second
	defaultPendingIdle  = 10 * time.Second
	defaultPendingBatch = 10
)

type Config struct {
	ValkeyURL    string
	Stream       string
	Group        string
	Consumer     string
	AgentURL     string
	AgentTimeout time.Duration
	MaxAttempts  int
	RetryBase    time.Duration
	RetryMax     time.Duration
	PendingIdle  time.Duration
	BatchSize    int
}

type Worker struct {
	cfg    Config
	client *redis.Client
	http   *http.Client
	logger *log.Logger
}

type agentResponse struct {
	ExecutionID string `json:"execution_id"`
	Status      string `json:"status"`
	Answer      string `json:"answer"`
	Steps       int    `json:"steps"`
	ToolCalls   any    `json:"tool_calls"`
}

func NewFromEnv(logger *log.Logger) (*Worker, error) {
	if logger == nil {
		logger = log.New(os.Stdout, "", log.LstdFlags)
	}

	cfg, err := configFromEnv()
	if err != nil {
		return nil, err
	}
	if err := validateAgentURL(cfg.AgentURL); err != nil {
		return nil, err
	}

	options, err := redis.ParseURL(cfg.ValkeyURL)
	if err != nil {
		return nil, fmt.Errorf("parse Valkey URL: %w", err)
	}

	if password := os.Getenv("AGENTYX_VALKEY_PASSWORD"); password != "" {
		options.Password = password
	}

	client := redis.NewClient(options)

	return &Worker{
		cfg:    cfg,
		client: client,
		http: &http.Client{
			Timeout: cfg.AgentTimeout,
		},
		logger: logger,
	}, nil
}

func configFromEnv() (Config, error) {
	cfg := Config{
		ValkeyURL:    envString("AGENTYX_VALKEY_URL", "redis://valkey:6379/0"),
		Stream:       envString("AGENTYX_TASK_STREAM", defaultStream),
		Group:        envString("AGENTYX_CONSUMER_GROUP", defaultGroup),
		Consumer:     envString("AGENTYX_CONSUMER_NAME", hostname()),
		AgentURL:     strings.TrimRight(envString("AGENTYX_AGENT_URL", defaultAgentURL), "/"),
		AgentTimeout: 120 * time.Second,
		MaxAttempts:  defaultMaxAttempts,
		RetryBase:    defaultRetryBase,
		RetryMax:     defaultRetryMax,
		PendingIdle:  defaultPendingIdle,
		BatchSize:    defaultPendingBatch,
	}

	var err error

	if value := strings.TrimSpace(os.Getenv("AGENTYX_AGENT_TIMEOUT_SECONDS")); value != "" {
		seconds, parseErr := strconv.Atoi(value)
		if parseErr != nil || seconds < 1 {
			return Config{}, fmt.Errorf("AGENTYX_AGENT_TIMEOUT_SECONDS must be positive")
		}
		cfg.AgentTimeout = time.Duration(seconds) * time.Second
	}

	if cfg.MaxAttempts, err = envInt("AGENTYX_MAX_ATTEMPTS", cfg.MaxAttempts); err != nil ||
		cfg.MaxAttempts < 1 {
		return Config{}, fmt.Errorf("AGENTYX_MAX_ATTEMPTS must be positive")
	}

	if cfg.RetryBase, err = envDurationSeconds("AGENTYX_RETRY_BASE_DELAY_SECONDS", cfg.RetryBase); err != nil {
		return Config{}, err
	}

	if cfg.RetryMax, err = envDurationSeconds("AGENTYX_RETRY_MAX_DELAY_SECONDS", cfg.RetryMax); err != nil {
		return Config{}, err
	}

	if cfg.PendingIdle, err = envDurationSeconds("AGENTYX_PENDING_IDLE_SECONDS", cfg.PendingIdle); err != nil {
		return Config{}, err
	}

	if cfg.BatchSize, err = envInt("AGENTYX_PENDING_BATCH_SIZE", cfg.BatchSize); err != nil ||
		cfg.BatchSize < 1 {
		return Config{}, fmt.Errorf("AGENTYX_PENDING_BATCH_SIZE must be positive")
	}

	if cfg.RetryMax < cfg.RetryBase {
		return Config{}, fmt.Errorf("retry maximum must be at least the retry base")
	}

	return cfg, nil
}

func envString(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func envInt(name string, fallback int) (int, error) {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback, nil
	}
	return strconv.Atoi(value)
}

func envDurationSeconds(name string, fallback time.Duration) (time.Duration, error) {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback, nil
	}

	seconds, err := strconv.Atoi(value)
	if err != nil || seconds < 1 {
		return 0, fmt.Errorf("%s must be a positive number of seconds", name)
	}
	return time.Duration(seconds) * time.Second, nil
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || name == "" {
		return "agenyx-go-worker"
	}
	return name
}

func (w *Worker) Close() error {
	return w.client.Close()
}

func (w *Worker) Run(ctx context.Context) error {
	if err := w.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("ping Valkey: %w", err)
	}

	err := w.client.XGroupCreateMkStream(
		ctx,
		w.cfg.Stream,
		w.cfg.Group,
		"0",
	).Err()

	if err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		return fmt.Errorf("create task consumer group: %w", err)
	}

	w.logger.Printf(
		`{"event":"worker_started","consumer":%q,"stream":%q,"group":%q}`,
		w.cfg.Consumer,
		w.cfg.Stream,
		w.cfg.Group,
	)

	for {
		if ctx.Err() != nil {
			return nil
		}

		// Recover tasks that a previous consumer left pending.
		if err := w.recoverPending(ctx); err != nil && ctx.Err() == nil {
			w.logger.Printf("recover pending tasks: %v", err)
			if !sleepContext(ctx, 2*time.Second) {
				return nil
			}
			continue
		}

		// Read new tasks. XREADGROUP's ">" cursor means messages
		// that have not yet been delivered to this consumer group.
		streams, err := w.client.XReadGroup(
			ctx,
			&redis.XReadGroupArgs{
				Group:    w.cfg.Group,
				Consumer: w.cfg.Consumer,
				Streams:  []string{w.cfg.Stream, ">"},
				Count:    1,
				Block:    5 * time.Second,
			},
		).Result()

		if err != nil {
			if errors.Is(err, redis.Nil) {
				continue
			}
			if ctx.Err() != nil {
				return nil
			}

			w.logger.Printf("read task stream: %v", err)
			if !sleepContext(ctx, 2*time.Second) {
				return nil
			}
			continue
		}

		for _, stream := range streams {
			for _, message := range stream.Messages {
				if err := w.process(ctx, message); err != nil && ctx.Err() == nil {
					w.logger.Printf("process message %s: %v", message.ID, err)
				}
			}
		}
	}
}

func (w *Worker) recoverPending(ctx context.Context) error {
	result, _, err := w.client.XAutoClaim(
		ctx,
		&redis.XAutoClaimArgs{
			Stream:   w.cfg.Stream,
			Group:    w.cfg.Group,
			Consumer: w.cfg.Consumer,
			MinIdle:  w.cfg.PendingIdle,
			Start:    "0-0",
			Count:    int64(w.cfg.BatchSize),
		},
	).Result()

	if err != nil {
		return err
	}

	for _, message := range result {
		if ctx.Err() != nil {
			return ctx.Err()
		}

		executionID := stringValue(message.Values["execution_id"])
		if executionID == "" {
			w.logger.Printf("pending message %s has no execution_id; leaving it pending", message.ID)
			continue
		}

		state, err := w.client.HGetAll(
			ctx,
			executionKey(executionID),
		).Result()
		if err != nil {
			return fmt.Errorf("read retry state for %s: %w", executionID, err)
		}

		if retryAt := strings.TrimSpace(state["retry_at"]); retryAt != "" {
			parsed, err := time.Parse(time.RFC3339Nano, retryAt)
			if err != nil {
				w.logger.Printf("invalid retry_at for %s: %q", executionID, retryAt)
			} else if time.Now().Before(parsed) {
				continue
			}
		}

		if err := w.process(ctx, message); err != nil && ctx.Err() == nil {
			w.logger.Printf("recover message %s: %v", message.ID, err)
		}
	}

	return nil
}

func (w *Worker) process(ctx context.Context, message redis.XMessage) error {
	executionID := stringValue(message.Values["execution_id"])
	intent := stringValue(message.Values["intent"])

	if executionID == "" {
		// Keep the current Python worker's behavior for malformed
		// messages: log them and leave them pending for investigation.
		w.logger.Printf("message %s has no execution_id; leaving it pending", message.ID)
		return nil
	}

	key := executionKey(executionID)

	attemptValue, err := w.client.HGet(ctx, key, "attempt").Result()
	if err != nil && !errors.Is(err, redis.Nil) {
		return fmt.Errorf("read attempt: %w", err)
	}

	attempt, _ := strconv.Atoi(attemptValue)
	attempt++

	now := time.Now().UTC().Format(time.RFC3339Nano)

	if err := w.client.HSet(ctx, key, map[string]interface{}{
		"status":              "running",
		"attempt":             strconv.Itoa(attempt),
		"worker":              w.cfg.Consumer,
		"started_at":          now,
		"original_message_id": message.ID,
		"error":               "",
		"retry_at":            "",
		"failed_at":           "",
	}).Err(); err != nil {
		return fmt.Errorf("mark execution running: %w", err)
	}

	started := time.Now()
	answer, err := w.callAgent(ctx, intent)
	duration := time.Since(started).Milliseconds()

	if err == nil {
		fields := map[string]interface{}{
			"status":       "completed",
			"answer":       answer.Answer,
			"steps":        strconv.Itoa(answer.Steps),
			"attempt":      strconv.Itoa(attempt),
			"worker":       w.cfg.Consumer,
			"completed_at": time.Now().UTC().Format(time.RFC3339Nano),
			"duration_ms":  strconv.FormatInt(duration, 10),
			"retry_at":     "",
			"failed_at":    "",
		}

		encodedToolCalls, marshalErr := json.Marshal(answer.ToolCalls)
		if marshalErr == nil {
			fields["tool_calls"] = string(encodedToolCalls)
		}

		if err := w.client.HSet(ctx, key, fields).Err(); err != nil {
			return fmt.Errorf("save successful execution: %w", err)
		}

		if err := w.client.XAck(ctx, w.cfg.Stream, w.cfg.Group, message.ID).Err(); err != nil {
			return fmt.Errorf("acknowledge successful execution: %w", err)
		}

		w.logger.Printf(
			`{"event":"execution_completed","execution_id":%q,"attempt":%d}`,
			executionID,
			attempt,
		)
		return nil
	}

	if attempt >= w.cfg.MaxAttempts {
		return w.deadLetter(ctx, message, executionID, intent, attempt, err, duration)
	}

	delay := w.retryDelay(attempt)
	retryAt := time.Now().Add(delay).UTC().Format(time.RFC3339Nano)

	if updateErr := w.client.HSet(ctx, key, map[string]interface{}{
		"status":      "retrying",
		"error":       err.Error(),
		"attempt":     strconv.Itoa(attempt),
		"worker":      w.cfg.Consumer,
		"failed_at":   time.Now().UTC().Format(time.RFC3339Nano),
		"retry_at":    retryAt,
		"duration_ms": strconv.FormatInt(duration, 10),
	}).Err(); updateErr != nil {
		return fmt.Errorf("save retry state after agent error %v: %w", err, updateErr)
	}

	w.logger.Printf(
		`{"event":"execution_retrying","execution_id":%q,"attempt":%d,"delay_seconds":%d,"error":%q}`,
		executionID,
		attempt,
		int(delay.Seconds()),
		err.Error(),
	)

	// Do not ACK or re-enqueue. The pending message will be
	// reclaimed after its idle timeout and checked against retry_at.
	return nil
}

func (w *Worker) callAgent(ctx context.Context, intent string) (*agentResponse, error) {
	body, err := json.Marshal(map[string]string{"intent": intent})
	if err != nil {
		return nil, fmt.Errorf("encode Agent request: %w", err)
	}

	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		w.cfg.AgentURL+"/v1/agent/run",
		bytes.NewReader(body),
	)
	if err != nil {
		return nil, fmt.Errorf("create Agent request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")

	response, err := w.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("call Agent: %w", err)
	}
	defer response.Body.Close()

	responseBody, err := io.ReadAll(io.LimitReader(response.Body, 4<<20))
	if err != nil {
		return nil, fmt.Errorf("read Agent response: %w", err)
	}

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, fmt.Errorf(
			"Agent returned HTTP %d: %s",
			response.StatusCode,
			strings.TrimSpace(string(responseBody)),
		)
	}

	var result agentResponse
	if err := json.Unmarshal(responseBody, &result); err != nil {
		return nil, fmt.Errorf("decode Agent response: %w", err)
	}

	return &result, nil
}

func (w *Worker) deadLetter(
	ctx context.Context,
	message redis.XMessage,
	executionID string,
	intent string,
	attempt int,
	executionErr error,
	durationMillis int64,
) error {
	deadLetterID, err := w.client.XAdd(ctx, &redis.XAddArgs{
		Stream: "agenyx:tasks:dead-letter",
		Values: map[string]interface{}{
			"execution_id":        executionID,
			"intent":              intent,
			"attempt":             strconv.Itoa(attempt),
			"original_message_id": message.ID,
			"error":               executionErr.Error(),
			"consumer":            w.cfg.Consumer,
		},
	}).Result()
	if err != nil {
		return fmt.Errorf("publish dead-letter message: %w", err)
	}

	if err := w.client.HSet(ctx, executionKey(executionID), map[string]interface{}{
		"status":                 "failed",
		"error":                  executionErr.Error(),
		"attempt":                strconv.Itoa(attempt),
		"worker":                 w.cfg.Consumer,
		"failed_at":              time.Now().UTC().Format(time.RFC3339Nano),
		"duration_ms":            strconv.FormatInt(durationMillis, 10),
		"dead_letter_message_id": deadLetterID,
		"retry_at":               "",
	}).Err(); err != nil {
		return fmt.Errorf("save failed execution state: %w", err)
	}

	if err := w.client.XAck(ctx, w.cfg.Stream, w.cfg.Group, message.ID).Err(); err != nil {
		return fmt.Errorf("acknowledge dead-lettered task: %w", err)
	}

	w.logger.Printf(
		`{"event":"execution_dead_lettered","execution_id":%q,"attempt":%d}`,
		executionID,
		attempt,
	)
	return nil
}

func (w *Worker) retryDelay(attempt int) time.Duration {
	exponent := math.Pow(2, float64(attempt-1))
	delay := time.Duration(float64(w.cfg.RetryBase) * exponent)
	if delay > w.cfg.RetryMax {
		return w.cfg.RetryMax
	}
	return delay
}

func executionKey(executionID string) string {
	return "agenyx:execution:" + executionID
}

func stringValue(value interface{}) string {
	switch value := value.(type) {
	case string:
		return value
	case []byte:
		return string(value)
	default:
		return fmt.Sprint(value)
	}
}

func sleepContext(ctx context.Context, duration time.Duration) bool {
	timer := time.NewTimer(duration)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}

// Ensure Agent URLs are absolute HTTP(S) URLs.
func validateAgentURL(raw string) error {
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return fmt.Errorf("invalid Agent URL %q", raw)
	}
	return nil
}
