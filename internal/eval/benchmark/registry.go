package benchmark

// registry maps benchmark types to runner factories.
var registry = make(map[BenchmarkType]func() Runner)

// RegisterBenchmark registers a benchmark runner factory for a type.
func RegisterBenchmark(bt BenchmarkType, factory func() Runner) {
	registry[bt] = factory
}

// GetRunner returns a runner for the given benchmark type.
func GetRunner(bt BenchmarkType) (Runner, bool) {
	factory, ok := registry[bt]
	if !ok {
		return nil, false
	}
	return factory(), true
}

// RegisteredTypes returns all registered benchmark types.
func RegisteredTypes() []BenchmarkType {
	types := make([]BenchmarkType, 0, len(registry))
	for bt := range registry {
		types = append(types, bt)
	}
	return types
}
