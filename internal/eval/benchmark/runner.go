package benchmark

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"sync"
	"sync/atomic"
	"time"
)

// HTTPRunner executes HTTP-based benchmarks.
type HTTPRunner struct {
	client *http.Client
	store  Store
}

// NewHTTPRunner creates a new HTTP benchmark runner.
func NewHTTPRunner(store Store, timeoutSeconds int) *HTTPRunner {
	return &HTTPRunner{
		client: &http.Client{
			Timeout: time.Duration(timeoutSeconds) * time.Second,
		},
		store: store,
	}
}

// Run executes a benchmark and returns results.
func (r *HTTPRunner) Run(ctx context.Context, config BenchmarkConfig) (*BenchmarkRun, error) {
	run := &BenchmarkRun{
		ID:           generateID(),
		BenchmarkID:  config.ID,
		Status:       BenchmarkStatusRunning,
		Config:       config,
		StartedAt:    timePtr(time.Now()),
	}

	if err := r.store.CreateRun(run); err != nil {
		return nil, fmt.Errorf("create run: %w", err)
	}

	latencyMetrics := &LatencyMetrics{}
	throughputMetrics := &ThroughputMetrics{}

	var successCount int64
	var errorCount int64
	var totalRequests int64

	// Semaphore to limit concurrency
	sem := make(chan struct{}, config.Concurrency)

	done := make(chan struct{})
	go func() {
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				close(done)
				return
			case <-done:
				return
			case <-ticker.C:
				// Periodic checkpoint could go here
			}
		}
	}()

	start := time.Now()

	// Launch worker goroutines
	var wg sync.WaitGroup
	for i := 0; i < config.Concurrency; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case sem <- struct{}{}:
					// Check context again before making request
					select {
					case <-ctx.Done():
						<-sem
						return
					default:
					}

					reqStart := time.Now()
					err := r.doRequest(config)
					latencyMs := float64(time.Since(reqStart).Nanoseconds()) / 1e6
					<-sem

					if err != nil {
						atomic.AddInt64(&errorCount, 1)
						throughputMetrics.Add(false, 0)
					} else {
						atomic.AddInt64(&successCount, 1)
						throughputMetrics.Add(true, 0)
					}
					atomic.AddInt64(&totalRequests, 1)
					latencyMetrics.Add(latencyMs)

					// Check if duration elapsed
					if time.Since(start) >= time.Duration(config.DurationSeconds)*time.Second {
						return
					}
				}
			}
		}()
	}

	wg.Wait()
	close(done)

	duration := time.Since(start).Seconds()

	// Build results
	results := []BenchmarkResult{
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricRPS,
			MetricValue:       throughputMetrics.RPS(duration),
			MetricUnit:        "req/s",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricErrorRate,
			MetricValue:       throughputMetrics.ErrorRate() * 100,
			MetricUnit:        "percent",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricP50Latency,
			MetricValue:       latencyMetrics.P50(),
			MetricUnit:        "ms",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricP95Latency,
			MetricValue:       latencyMetrics.P95(),
			MetricUnit:        "ms",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricP99Latency,
			MetricValue:       latencyMetrics.P99(),
			MetricUnit:        "ms",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricAvgLatency,
			MetricValue:       latencyMetrics.Avg(),
			MetricUnit:        "ms",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricMinLatency,
			MetricValue:       latencyMetrics.Min(),
			MetricUnit:        "ms",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
		{
			ID:                generateID(),
			RunID:             run.ID,
			MetricName:        MetricMaxLatency,
			MetricValue:       latencyMetrics.Max(),
			MetricUnit:        "ms",
			ConcurrencyLevel:  config.Concurrency,
			RecordedAt:        time.Now(),
		},
	}

	run.Results = results
	run.CompletedAt = timePtr(time.Now())
	run.Status = BenchmarkStatusCompleted

	if err := r.store.UpdateRun(run); err != nil {
		return nil, fmt.Errorf("update run: %w", err)
	}
	for _, res := range results {
		if err := r.store.CreateResult(res); err != nil {
			return nil, fmt.Errorf("create result: %w", err)
		}
	}

	return run, nil
}

// doRequest performs a single HTTP request.
func (r *HTTPRunner) doRequest(config BenchmarkConfig) error {
	req, err := http.NewRequest("GET", config.TargetURL, nil)
	if err != nil {
		return err
	}

	for k, v := range config.Headers {
		req.Header.Set(k, v)
	}

	resp, err := r.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil
}

func timePtr(t time.Time) *time.Time {
	return &t
}

func generateID() string {
	return fmt.Sprintf("%d", time.Now().UnixNano())
}
