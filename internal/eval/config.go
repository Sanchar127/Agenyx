package eval

import (
	"time"
)

// Config is the typed configuration for the evaluation platform.
type Config struct {
	// API server settings
	APIAddr           string        `json:"api_addr" env:"EVAL_API_ADDR" env-default:":8006"`
	APIReadTimeout    time.Duration `json:"api_read_timeout" env:"EVAL_API_READ_TIMEOUT" env-default:"10s"`
	APIWriteTimeout   time.Duration `json:"api_write_timeout" env:"EVAL_API_WRITE_TIMEOUT" env-default:"30s"`
	APIIdleTimeout    time.Duration `json:"api_idle_timeout" env:"EVAL_API_IDLE_TIMEOUT" env-default:"120s"`

	// Scheduler settings
	SchedulerAddr     string        `json:"scheduler_addr" env:"EVAL_SCHEDULER_ADDR" env-default:":8007"`
	SchedulerInterval time.Duration `json:"scheduler_interval" env:"EVAL_SCHEDULER_INTERVAL" env-default:"5s"`
	JobLeaseSeconds   int           `json:"job_lease_seconds" env:"EVAL_JOB_LEASE_SECONDS" env-default:"300"`
	MaxJobAttempts    int           `json:"max_job_attempts" env:"EVAL_MAX_JOB_ATTEMPTS" env-default:"3"`

	// Database
	DatabaseURL       string        `json:"database_url" env:"EVAL_DATABASE_URL" env-default:"postgresql+asyncpg://agenyx:agenyx_dev_password@postgres:5432/agenyx"`
	MaxDBConns        int           `json:"max_db_conns" env:"EVAL_MAX_DB_CONNS" env-default:"20"`
	MinDBConns        int           `json:"min_db_conns" env:"EVAL_MIN_DB_CONNS" env-default:"5"`

	// Valkey (job queue)
	ValkeyURL         string        `json:"valkey_url" env:"EVAL_VALKEY_URL" env-default:"redis://valkey:6379/0"`
	ValkeyStream      string        `json:"valkey_stream" env:"EVAL_VALKEY_STREAM" env-default:"eval:jobs"`
	ValkeyConsumerGroup string       `json:"valkey_consumer_group" env:"EVAL_VALKEY_CONSUMER_GROUP" env-default:"eval-workers"`

	// Object storage (S3-compatible)
	S3Endpoint        string `json:"s3_endpoint" env:"EVAL_S3_ENDPOINT" env-default:"minio:9000"`
	S3Bucket          string `json:"s3_bucket" env:"EVAL_S3_BUCKET" env-default:"agenyx-eval"`
	S3AccessKey       string `json:"s3_access_key" env:"EVAL_S3_ACCESS_KEY" env-default:"minioadmin"`
	S3SecretKey       string `json:"s3_secret_key" env:"EVAL_S3_SECRET_KEY" env-default:"minioadmin"`
	S3UseSSL          bool   `json:"s3_use_ssl" env:"EVAL_S3_USE_SSL" env-default:"false"`

	// Authentication
	APIKey            string `json:"api_key" env:"EVAL_API_KEY" env-default:""`
	APIKeyRef         string `json:"api_key_ref" env:"EVAL_API_KEY_REF" env-default:""`

	// Inspect AI
	InspectAIEnabled  bool   `json:"inspect_ai_enabled" env:"EVAL_INSPECT_AI_ENABLED" env-default:"true"`
	InspectAIPath     string `json:"inspect_ai_path" env:"EVAL_INSPECT_AI_PATH" env-default:"/app/eval/inspect"`

	// Logging
	LogLevel          string `json:"log_level" env:"EVAL_LOG_LEVEL" env-default:"info"`
	LogJSON           bool   `json:"log_json" env:"EVAL_LOG_JSON" env-default:"true"`
}
