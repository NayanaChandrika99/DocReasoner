.PHONY: all build test test-unit test-integration bench fmt lint clean run

all: build

build:
	@echo "Building TreeStore..."
	@mkdir -p build/bin
	go build -o build/bin/treestore cmd/treestore/main.go

test:
	@echo "Running all tests..."
	go test ./... -v -cover

test-unit:
	@echo "Running unit tests..."
	go test ./pkg/... -v -short

test-integration:
	@echo "Running integration tests..."
	go test ./test/integration/... -v

bench:
	@echo "Running benchmarks..."
	go test ./test/benchmark/... -bench=. -benchmem

fmt:
	@echo "Formatting code..."
	go fmt ./...

lint:
	@echo "Running linter..."
	golangci-lint run

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf data/

run:
	go run cmd/treestore/main.go
