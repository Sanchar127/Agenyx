.PHONY: fmt lint test vet build run check clean

fmt:
	gofmt -w .

lint:
	golangci-lint run

test:
	go test ./...

vet:
	go vet ./...

build:
	go build -o bin/agenyx ./cmd/agenyx

run:
	go run ./cmd/agenyx

check: fmt lint vet test

clean:
	rm -rf bin/
