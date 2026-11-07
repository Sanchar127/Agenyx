package benchmark

import (
	"sort"
)

// LatencyMetrics collects latency measurements and computes percentiles.
type LatencyMetrics struct {
	latencies []float64 // in milliseconds
}

// Add records a latency measurement.
func (m *LatencyMetrics) Add(latencyMs float64) {
	m.latencies = append(m.latencies, latencyMs)
}

// Count returns the number of measurements.
func (m *LatencyMetrics) Count() int {
	return len(m.latencies)
}

// Min returns the minimum latency.
func (m *LatencyMetrics) Min() float64 {
	if len(m.latencies) == 0 {
		return 0
	}
	min := m.latencies[0]
	for _, v := range m.latencies[1:] {
		if v < min {
			min = v
		}
	}
	return min
}

// Max returns the maximum latency.
func (m *LatencyMetrics) Max() float64 {
	if len(m.latencies) == 0 {
		return 0
	}
	max := m.latencies[0]
	for _, v := range m.latencies[1:] {
		if v > max {
			max = v
		}
	}
	return max
}

// Avg returns the average latency.
func (m *LatencyMetrics) Avg() float64 {
	if len(m.latencies) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range m.latencies {
		sum += v
	}
	return sum / float64(len(m.latencies))
}

// Percentile returns the value at the given percentile (0-100).
// Uses the nearest-rank method.
func (m *LatencyMetrics) Percentile(p float64) float64 {
	if len(m.latencies) == 0 {
		return 0
	}
	if p <= 0 {
		return m.Min()
	}
	if p >= 100 {
		return m.Max()
	}

	sorted := make([]float64, len(m.latencies))
	copy(sorted, m.latencies)
	sort.Float64s(sorted)

	rank := (p / 100.0) * float64(len(sorted))
	idx := int(rank)
	if idx < 1 {
		idx = 1
	}
	if idx > len(sorted) {
		idx = len(sorted)
	}
	return sorted[idx-1]
}

// P50 returns the 50th percentile latency.
func (m *LatencyMetrics) P50() float64 {
	return m.Percentile(50)
}

// P95 returns the 95th percentile latency.
func (m *LatencyMetrics) P95() float64 {
	return m.Percentile(95)
}

// P99 returns the 99th percentile latency.
func (m *LatencyMetrics) P99() float64 {
	return m.Percentile(99)
}

// ThroughputMetrics tracks requests per second.
type ThroughputMetrics struct {
	totalRequests int
	successCount  int
	errorCount    int
	totalBytes    int64
}

// Add records a completed request.
func (m *ThroughputMetrics) Add(success bool, bytes int64) {
	m.totalRequests++
	if success {
		m.successCount++
	} else {
		m.errorCount++
	}
	m.totalBytes += bytes
}

// RPS returns requests per second given the duration in seconds.
func (m *ThroughputMetrics) RPS(durationSeconds float64) float64 {
	if durationSeconds <= 0 {
		return 0
	}
	return float64(m.totalRequests) / durationSeconds
}

// ErrorRate returns the error rate (0-1).
func (m *ThroughputMetrics) ErrorRate() float64 {
	if m.totalRequests == 0 {
		return 0
	}
	return float64(m.errorCount) / float64(m.totalRequests)
}

// SuccessRate returns the success rate (0-1).
func (m *ThroughputMetrics) SuccessRate() float64 {
	if m.totalRequests == 0 {
		return 0
	}
	return float64(m.successCount) / float64(m.totalRequests)
}

// BytesPerSecond returns throughput in bytes per second.
func (m *ThroughputMetrics) BytesPerSecond(durationSeconds float64) float64 {
	if durationSeconds <= 0 {
		return 0
	}
	return float64(m.totalBytes) / durationSeconds
}

// Aggregate combines multiple ThroughputMetrics.
func (m *ThroughputMetrics) Aggregate(other ThroughputMetrics) {
	m.totalRequests += other.totalRequests
	m.successCount += other.successCount
	m.errorCount += other.errorCount
	m.totalBytes += other.totalBytes
}
