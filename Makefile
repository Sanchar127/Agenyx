.PHONY: build test test-race lint fmt vet bench

build:
	go build ./...

test:
	go test ./...

test-race:
	go test -race ./...

lint:
	golangci-lint run ./...

fmt:
	gofmt -w .

vet:
	go vet ./...

bench:
	go test -bench=. -benchmem ./tests/benchmarks/...
