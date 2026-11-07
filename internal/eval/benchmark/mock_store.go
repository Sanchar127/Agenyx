package benchmark

import (
	"fmt"
	"sync"
)

// MockStore is an in-memory implementation of Store for testing.
type MockStore struct {
	mu      sync.RWMutex
	runs    map[string]*BenchmarkRun
	results map[string][]BenchmarkResult
}

// NewMockStore creates a new in-memory store.
func NewMockStore() *MockStore {
	return &MockStore{
		runs:    make(map[string]*BenchmarkRun),
		results: make(map[string][]BenchmarkResult),
	}
}

// CreateRun stores a benchmark run.
func (s *MockStore) CreateRun(run *BenchmarkRun) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runs[run.ID] = run
	return nil
}

// CreateBenchmark stores a benchmark config.
func (s *MockStore) CreateBenchmark(config BenchmarkConfig) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	id := generateID()
	s.runs[id] = &BenchmarkRun{
		ID:           id,
		BenchmarkID:  config.ID,
		Status:       BenchmarkStatusQueued,
		Config:       config,
	}
	return id, nil
}

// UpdateRun updates a benchmark run.
func (s *MockStore) UpdateRun(run *BenchmarkRun) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.runs[run.ID]; !exists {
		return fmt.Errorf("run %s not found", run.ID)
	}
	s.runs[run.ID] = run
	return nil
}

// CreateResult stores a benchmark result.
func (s *MockStore) CreateResult(result BenchmarkResult) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.results[result.RunID] = append(s.results[result.RunID], result)
	return nil
}

// GetRun retrieves a run by ID.
func (s *MockStore) GetRun(id string) (*BenchmarkRun, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	run, ok := s.runs[id]
	if !ok {
		return nil, fmt.Errorf("run %s not found", id)
	}
	return run, nil
}

// ListRuns returns all runs for a benchmark.
func (s *MockStore) ListRuns(benchmarkID string) ([]*BenchmarkRun, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []*BenchmarkRun
	for _, run := range s.runs {
		if run.BenchmarkID == benchmarkID {
			result = append(result, run)
		}
	}
	return result, nil
}

// GetResults returns all results for a run.
func (s *MockStore) GetResults(runID string) ([]BenchmarkResult, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.results[runID], nil
}
