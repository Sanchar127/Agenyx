package benchmark

import (
	"context"
	"time"
)

// BenchmarkType defines the category of benchmark.
type BenchmarkType string

const (
	BenchmarkTypeRuntime      BenchmarkType = "runtime"
	BenchmarkTypeThroughput   BenchmarkType = "throughput"
	BenchmarkTypeLatency      BenchmarkType = "latency"
	BenchmarkTypeConcurrency  BenchmarkType = "concurrency"
	BenchmarkTypeReliability  BenchmarkType = "reliability"
	BenchmarkTypeResource     BenchmarkType = "resource"
)

// BenchmarkStatus defines the lifecycle state of a benchmark run.
type BenchmarkStatus string

const (
	BenchmarkStatusQueued    BenchmarkStatus = "queued"
	BenchmarkStatusRunning   BenchmarkStatus = "running"
	BenchmarkStatusCompleted BenchmarkStatus = "completed"
	BenchmarkStatusFailed    BenchmarkStatus = "failed"
	BenchmarkStatusCancelled BenchmarkStatus = "cancelled"
)

// MetricName defines the type of metric being measured.
type MetricName string

const (
	MetricRPS               MetricName = "rps"                // requests per second
	MetricP50Latency        MetricName = "p50_latency_ms"     // p50 latency in ms
	MetricP95Latency        MetricName = "p95_latency_ms"     // p95 latency in ms
	MetricP99Latency        MetricName = "p99_latency_ms"     // p99 latency in ms
	MetricMaxLatency        MetricName = "max_latency_ms"     // max latency in ms
	MetricMinLatency        MetricName = "min_latency_ms"     // min latency in ms
	MetricAvgLatency        MetricName = "avg_latency_ms"     // average latency in ms
	MetricErrorRate         MetricName = "error_rate"          // error rate (0-1)
	MetricCPUUtilization    MetricName = "cpu_utilization"     // CPU utilization percent
	MetricMemoryUtilization MetricName = "memory_utilization"  // memory utilization percent
	MetricGPUTilization     MetricName = "gpu_utilization"     // GPU utilization percent
	MetricNetworkIO         MetricName = "network_io_bytes"    // network I/O bytes
	MetricDiskIO            MetricName = "disk_io_bytes"       // disk I/O bytes
)

// BenchmarkConfig is the configuration for a benchmark run.
type BenchmarkConfig struct {
	ID               string                 `json:"id"`
	Name             string                 `json:"name"`
	Type             BenchmarkType          `json:"type"`
	TargetService    string                 `json:"target_service"`
	TargetURL        string                 `json:"target_url"`
	Concurrency      int                    `json:"concurrency"`           // concurrent requests
	DurationSeconds  int                    `json:"duration_seconds"`      // test duration
	RampUpSeconds    int                    `json:"ramp_up_seconds"`       // ramp-up duration
	Metrics          []MetricName           `json:"metrics"`               // metrics to collect
	Payload          string                 `json:"payload,omitempty"`     // request body
	ContentType      string                 `json:"content_type,omitempty"`// content type
	Headers          map[string]string      `json:"headers,omitempty"`     // custom headers
	TimeoutSeconds   int                    `json:"timeout_seconds"`       // per-request timeout
	Metadata         map[string]string      `json:"metadata,omitempty"`    // additional metadata
}

// BenchmarkResult is a single measurement from a benchmark run.
type BenchmarkResult struct {
	ID                string      `json:"id"`
	RunID             string      `json:"run_id"`
	MetricName        MetricName  `json:"metric_name"`
	MetricValue       float64     `json:"metric_value"`
	MetricUnit        string      `json:"metric_unit"`
	ConcurrencyLevel  int         `json:"concurrency_level"`
	RecordedAt        time.Time   `json:"recorded_at"`
}

// BenchmarkRun is a single benchmark execution.
type BenchmarkRun struct {
	ID               string                 `json:"id"`
	BenchmarkID      string                 `json:"benchmark_id"`
	Status           BenchmarkStatus        `json:"status"`
	Config           BenchmarkConfig        `json:"config"`
	Results          []BenchmarkResult      `json:"results,omitempty"`
	StartedAt        *time.Time             `json:"started_at,omitempty"`
	CompletedAt      *time.Time             `json:"completed_at,omitempty"`
	ErrorMessage     string                 `json:"error_message,omitempty"`
}

// Reporter formats benchmark results.
type Reporter interface {
	Format(run *BenchmarkRun) ([]byte, error)
}

// Runner executes benchmarks.
type Runner interface {
	Run(ctx context.Context, config BenchmarkConfig) (*BenchmarkRun, error)
}

// Store persists benchmark data.
type Store interface {
	CreateBenchmark(config BenchmarkConfig) (string, error)
	CreateRun(run *BenchmarkRun) error
	UpdateRun(run *BenchmarkRun) error
	CreateResult(result BenchmarkResult) error
	GetRun(id string) (*BenchmarkRun, error)
	ListRuns(benchmarkID string) ([]*BenchmarkRun, error)
}
