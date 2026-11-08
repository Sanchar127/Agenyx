package benchmark

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestLatencyMetrics tests the LatencyMetrics calculations.
func TestLatencyMetrics(t *testing.T) {
	m := &LatencyMetrics{}

	// Empty metrics
	assert.Equal(t, 0, m.Count())
	assert.Equal(t, 0.0, m.Min())
	assert.Equal(t, 0.0, m.Max())
	assert.Equal(t, 0.0, m.Avg())
	assert.Equal(t, 0.0, m.P50())
	assert.Equal(t, 0.0, m.P95())
	assert.Equal(t, 0.0, m.P99())

	// Add single value
	m.Add(100.0)
	assert.Equal(t, 1, m.Count())
	assert.Equal(t, 100.0, m.Min())
	assert.Equal(t, 100.0, m.Max())
	assert.Equal(t, 100.0, m.Avg())
	assert.Equal(t, 100.0, m.P50())
	assert.Equal(t, 100.0, m.P95())
	assert.Equal(t, 100.0, m.P99())

	// Add multiple values
	m.Add(200.0)
	m.Add(300.0)
	m.Add(400.0)
	m.Add(500.0)
	assert.Equal(t, 5, m.Count())
	assert.Equal(t, 100.0, m.Min())
	assert.Equal(t, 500.0, m.Max())
	assert.Equal(t, 300.0, m.Avg())

	// Percentiles with known values: [100, 200, 300, 400, 500]
	// P50: rank = 0.5 * 5 = 2.5, idx = 2, sorted[1] = 200
	assert.Equal(t, 200.0, m.P50())
	// P95: rank = 0.95 * 5 = 4.75, idx = 4, sorted[3] = 400
	assert.Equal(t, 400.0, m.P95())
	// P99: rank = 0.99 * 5 = 4.95, idx = 4, sorted[3] = 400 (capped at len)
	assert.Equal(t, 400.0, m.P99())
}

// TestThroughputMetrics tests throughput calculations.
func TestThroughputMetrics(t *testing.T) {
	m := &ThroughputMetrics{}

	// Empty metrics
	assert.Equal(t, 0, m.totalRequests)
	assert.Equal(t, 0.0, m.RPS(10.0))
	assert.Equal(t, 0.0, m.ErrorRate())
	assert.Equal(t, 0.0, m.SuccessRate())

	// Add successful requests
	m.Add(true, 100)
	m.Add(true, 200)
	m.Add(true, 300)
	assert.Equal(t, 3, m.totalRequests)
	assert.Equal(t, 3, m.successCount)
	assert.Equal(t, 0, m.errorCount)
	assert.Equal(t, 1.0, m.SuccessRate())
	assert.Equal(t, 0.0, m.ErrorRate())
	assert.Equal(t, int64(600), m.totalBytes)

	// Add errors
	m.Add(false, 0)
	m.Add(false, 0)
	assert.Equal(t, 5, m.totalRequests)
	assert.Equal(t, 3, m.successCount)
	assert.Equal(t, 2, m.errorCount)
	assert.Equal(t, 0.6, m.SuccessRate())
	assert.Equal(t, 0.4, m.ErrorRate())

	// RPS
	rps := m.RPS(10.0)
	assert.Equal(t, 0.5, rps)

	// Bytes per second
	bps := m.BytesPerSecond(10.0)
	assert.Equal(t, 60.0, bps)
}

// TestThroughputMetricsAggregate tests combining metrics.
func TestThroughputMetricsAggregate(t *testing.T) {
	m1 := &ThroughputMetrics{}
	m1.Add(true, 100)
	m1.Add(false, 0)

	m2 := &ThroughputMetrics{}
	m2.Add(true, 200)
	m2.Add(true, 300)

	m1.Aggregate(*m2)
	assert.Equal(t, 4, m1.totalRequests)
	assert.Equal(t, 3, m1.successCount)
	assert.Equal(t, 1, m1.errorCount)
	assert.Equal(t, int64(600), m1.totalBytes)
}

// TestHTTPRunner tests the HTTP benchmark runner with a mock server.
func TestHTTPRunner(t *testing.T) {
	store := NewMockStore()
	runner := NewHTTPRunner(store, 5)

	// Create a mock HTTP server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	}))
	defer server.Close()

	config := BenchmarkConfig{
		ID:               "bench-1",
		Name:             "test-benchmark",
		Type:             BenchmarkTypeThroughput,
		TargetService:    "test-service",
		TargetURL:        server.URL,
		Concurrency:      5,
		DurationSeconds:  1,
		RampUpSeconds:    0,
		Metrics:          []MetricName{MetricRPS, MetricP50Latency, MetricP95Latency, MetricP99Latency},
		TimeoutSeconds:   5,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	run, err := runner.Run(ctx, config)
	require.NoError(t, err)
	require.NotNil(t, run)
	assert.Equal(t, BenchmarkStatusCompleted, run.Status)
	assert.NotEmpty(t, run.ID)
	assert.Equal(t, config.ID, run.BenchmarkID)
	assert.NotNil(t, run.StartedAt)
	assert.NotNil(t, run.CompletedAt)

	// Verify results
	assert.Greater(t, len(run.Results), 0)
	for _, r := range run.Results {
		assert.Equal(t, run.ID, r.RunID)
		assert.GreaterOrEqual(t, r.ConcurrencyLevel, 0)
	}

	// Verify store persistence
	storedRun, err := store.GetRun(run.ID)
	require.NoError(t, err)
	assert.Equal(t, run.ID, storedRun.ID)
	assert.Equal(t, BenchmarkStatusCompleted, storedRun.Status)

	results, err := store.GetResults(run.ID)
	require.NoError(t, err)
	assert.Greater(t, len(results), 0)
}

// TestHTTPRunnerErrorHandling tests runner with errors.
func TestHTTPRunnerErrorHandling(t *testing.T) {
	store := NewMockStore()
	runner := NewHTTPRunner(store, 1)

	// Server that returns 500
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("error"))
	}))
	defer server.Close()

	config := BenchmarkConfig{
		ID:               "bench-error",
		Name:             "error-benchmark",
		Type:             BenchmarkTypeThroughput,
		TargetService:    "test-service",
		TargetURL:        server.URL,
		Concurrency:      3,
		DurationSeconds:  1,
		RampUpSeconds:    0,
		Metrics:          []MetricName{MetricRPS, MetricErrorRate},
		TimeoutSeconds:   5,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	run, err := runner.Run(ctx, config)
	require.NoError(t, err)
	assert.Equal(t, BenchmarkStatusCompleted, run.Status)

	// Should have error rate > 0
	var errorRate float64
	for _, r := range run.Results {
		if r.MetricName == MetricErrorRate {
			errorRate = r.MetricValue
			break
		}
	}
	assert.Greater(t, errorRate, 0.0)
}

// TestRegisteredTypes tests the registry.
func TestRegisteredTypes(t *testing.T) {
	// Initially empty
	assert.Equal(t, 0, len(RegisteredTypes()))

	// Register a type
	RegisterBenchmark(BenchmarkTypeThroughput, func() Runner {
		return NewHTTPRunner(NewMockStore(), 5)
	})

	types := RegisteredTypes()
	assert.Contains(t, types, BenchmarkTypeThroughput)

	// GetRunner should work
	runner, ok := GetRunner(BenchmarkTypeThroughput)
	require.True(t, ok)
	assert.NotNil(t, runner)

	// Unknown type
	_, ok = GetRunner(BenchmarkTypeReliability)
	assert.False(t, ok)
}
