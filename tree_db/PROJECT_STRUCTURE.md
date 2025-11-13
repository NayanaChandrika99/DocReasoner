# TreeStore Project Structure

This document defines the complete file and directory organization for the TreeStore project.

---

## Directory Layout

```
tree_db/
├── README.md                          # Project overview
├── IMPLEMENTATION_PLAN.md             # Week-by-week roadmap
├── ARCHITECTURE.md                    # System design
├── PROJECT_STRUCTURE.md               # This file
├── LICENSE                            # MIT License
├── Makefile                           # Build and test commands
├── go.mod                             # Go module definition
├── go.sum                             # Go dependency checksums
├── .gitignore                         # Git ignore rules
│
├── cmd/                               # Executable commands
│   └── treestore/                     # Main server binary
│       └── main.go                    # Entry point
│
├── pkg/                               # Public library packages
│   ├── btree/                         # B+Tree implementation
│   │   ├── btree.go                   # Main B+Tree interface
│   │   ├── node.go                    # Node structure and operations
│   │   ├── insert.go                  # Insertion logic
│   │   ├── delete.go                  # Deletion logic
│   │   ├── search.go                  # Search operations
│   │   ├── range.go                   # Range scan operations
│   │   ├── iterator.go                # Iterator interface
│   │   ├── split.go                   # Node splitting logic
│   │   ├── merge.go                   # Node merging logic
│   │   └── serialize.go               # Serialization/deserialization
│   │
│   ├── storage/                       # Storage layer
│   │   ├── page.go                    # Page abstraction
│   │   ├── page_manager.go            # Page allocation/deallocation
│   │   ├── buffer_pool.go             # In-memory page cache (LRU)
│   │   ├── file.go                    # File I/O operations
│   │   └── freelist.go                # Free space management
│   │
│   ├── wal/                           # Write-Ahead Log
│   │   ├── wal.go                     # WAL interface
│   │   ├── writer.go                  # Log writing
│   │   ├── reader.go                  # Log reading
│   │   ├── recovery.go                # Crash recovery
│   │   ├── checkpoint.go              # Checkpointing logic
│   │   └── entry.go                   # Log entry format
│   │
│   ├── index/                         # Index management
│   │   ├── manager.go                 # Index manager
│   │   ├── primary.go                 # Primary index
│   │   ├── secondary.go               # Secondary indexes
│   │   └── composite_key.go           # Composite key encoding
│   │
│   ├── txn/                           # Transaction management
│   │   ├── transaction.go             # Transaction interface
│   │   ├── manager.go                 # Transaction manager
│   │   ├── mvcc.go                    # MVCC implementation
│   │   ├── version.go                 # Version chain management
│   │   └── isolation.go               # Isolation levels
│   │
│   ├── document/                      # Document service layer (DocumentStore)
│   │   ├── document.go                # Document operations
│   │   ├── node.go                    # Node structure
│   │   ├── hierarchy.go               # Hierarchical queries
│   │   ├── store.go                   # StoreDocument implementation
│   │   ├── retrieve.go                # GetNode, GetSubtree
│   │   ├── search.go                  # Search operations
│   │   └── flatten.go                 # Tree flattening logic
│   │
│   ├── version/                       # Version service layer (NEW - Week 7)
│   │   ├── store.go                   # VersionStore implementation
│   │   ├── version.go                 # PolicyVersion structure
│   │   ├── temporal.go                # Temporal queries (GetVersionAsOf)
│   │   ├── diff.go                    # Version diff tracking
│   │   └── supersede.go               # Version supersession logic
│   │
│   ├── metadata/                      # Metadata service layer (NEW - Week 8)
│   │   ├── store.go                   # MetadataStore implementation
│   │   ├── tool_result.go             # Tool result storage
│   │   ├── trajectory.go              # Search trajectory storage
│   │   ├── cross_ref.go               # Cross-reference storage
│   │   ├── contradiction.go           # Contradiction storage
│   │   └── analytics.go               # Trajectory analytics
│   │
│   ├── prompt/                        # Prompt service layer (NEW - Week 9)
│   │   ├── store.go                   # PromptStore implementation
│   │   ├── prompt.go                  # Prompt structure
│   │   ├── version.go                 # Prompt versioning
│   │   ├── usage.go                   # Usage tracking
│   │   └── schema.go                  # Tool schema storage
│   │
│   ├── fts/                           # Full-text search
│   │   ├── inverted_index.go          # Inverted index
│   │   ├── tokenizer.go               # Text tokenization
│   │   ├── bm25.go                    # BM25 ranking
│   │   └── query.go                   # Query parsing
│   │
│   ├── api/                           # gRPC API
│   │   ├── server.go                  # gRPC server
│   │   ├── service.go                 # Service implementation
│   │   ├── handlers.go                # Request handlers
│   │   ├── validation.go              # Request validation
│   │   ├── document_handlers.go       # DocumentStore handlers
│   │   ├── version_handlers.go        # VersionStore handlers (NEW)
│   │   ├── metadata_handlers.go       # MetadataStore handlers (NEW)
│   │   └── prompt_handlers.go         # PromptStore handlers (NEW)
│   │
│   └── kv/                            # Key-value store interface
│       ├── store.go                   # KV store interface
│       └── impl.go                    # Implementation
│
├── internal/                          # Private packages
│   ├── config/                        # Configuration
│   │   ├── config.go                  # Config structure
│   │   └── defaults.go                # Default values
│   │
│   ├── metrics/                       # Observability
│   │   ├── prometheus.go              # Prometheus metrics
│   │   ├── logging.go                 # Structured logging
│   │   └── tracing.go                 # Distributed tracing (future)
│   │
│   └── util/                          # Utilities
│       ├── bytes.go                   # Byte operations
│       ├── crc.go                     # CRC checksums
│       └── encoding.go                # Encoding helpers
│
├── proto/                             # Protocol Buffer definitions
│   ├── treestore.proto                # gRPC service definition
│   └── types.proto                    # Common message types
│
├── client/                            # Client libraries
│   ├── go/                            # Go client (generated from proto)
│   │   └── ...
│   └── python/                        # Python client
│       ├── setup.py                   # Python package setup
│       ├── treestore/                 # Python package
│       │   ├── __init__.py
│       │   ├── client.py              # Main client class
│       │   ├── types.py               # Type definitions
│       │   └── exceptions.py          # Custom exceptions
│       └── examples/                  # Usage examples
│           ├── basic_usage.py
│           └── integrate_pageindex.py
│
├── test/                              # Tests
│   ├── unit/                          # Unit tests
│   │   ├── btree_test.go
│   │   ├── wal_test.go
│   │   ├── txn_test.go
│   │   └── document_test.go
│   │
│   ├── integration/                   # Integration tests
│   │   ├── e2e_test.go                # End-to-end tests
│   │   ├── crash_recovery_test.go     # Recovery tests
│   │   └── concurrent_test.go         # Concurrency tests
│   │
│   ├── benchmark/                     # Performance benchmarks
│   │   ├── btree_bench.go
│   │   ├── document_bench.go
│   │   └── compare_postgres_bench.go  # vs PostgreSQL
│   │
│   └── testdata/                      # Test fixtures
│       ├── sample_trees/              # Sample PageIndex outputs
│       │   ├── policy_123.json
│       │   └── policy_456.json
│       └── expected/                  # Expected results
│
├── scripts/                           # Utility scripts
│   ├── setup.sh                       # Initial setup
│   ├── migrate_from_postgres.py       # Data migration
│   ├── benchmark.sh                   # Run benchmarks
│   ├── backup.sh                      # Backup database
│   ├── restore.sh                     # Restore from backup
│   └── generate_proto.sh              # Generate gRPC code
│
├── docs/                              # Additional documentation
│   ├── api/                           # API documentation
│   │   ├── grpc_reference.md          # gRPC API reference
│   │   └── examples.md                # Usage examples
│   │
│   ├── deployment/                    # Deployment guides
│   │   ├── docker.md                  # Docker deployment
│   │   ├── kubernetes.md              # K8s deployment
│   │   └── systemd.md                 # Systemd service
│   │
│   ├── development/                   # Developer docs
│   │   ├── contributing.md            # Contribution guidelines
│   │   ├── testing.md                 # Testing strategy
│   │   └── debugging.md               # Debugging tips
│   │
│   └── diagrams/                      # Architecture diagrams
│       ├── system_overview.png
│       ├── btree_structure.png
│       └── data_flow.png
│
├── build/                             # Build artifacts (gitignored)
│   ├── bin/                           # Compiled binaries
│   │   └── treestore
│   └── docker/                        # Docker images
│
├── data/                              # Runtime data (gitignored)
│   ├── db/                            # Database files
│   │   ├── data.db                    # B+Tree data
│   │   └── indexes/                   # Index files
│   ├── wal/                           # WAL files
│   │   ├── 000001.log
│   │   ├── 000002.log
│   │   └── 000003.log
│   └── backups/                       # Backup files
│
├── deploy/                            # Deployment configurations
│   ├── docker/                        # Docker configs
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   │
│   ├── k8s/                           # Kubernetes manifests
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml
│   │
│   └── systemd/                       # Systemd service files
│       └── treestore.service
│
└── examples/                          # Example code
    ├── basic_operations.go            # Basic CRUD
    ├── hierarchical_queries.go        # Tree traversal
    ├── transactions.go                # Transaction usage
    └── python_integration.py          # Python client example
```

---

## File Descriptions

### Core Database Components

#### `pkg/btree/`
The heart of TreeStore - implements the B+Tree data structure.

**Key files:**
- `btree.go` - Main interface and tree structure
- `node.go` - Node struct (internal vs leaf), key/value storage
- `insert.go` - Insertion with splitting
- `delete.go` - Deletion with merging
- `search.go` - Point and range lookups
- `iterator.go` - Iterator for range scans

#### `pkg/wal/`
Write-Ahead Logging for durability and crash recovery.

**Key files:**
- `wal.go` - WAL interface
- `writer.go` - Sequential log appending
- `recovery.go` - Replay logic on startup
- `checkpoint.go` - Periodic checkpoints

#### `pkg/txn/`
Transaction management with MVCC.

**Key files:**
- `transaction.go` - Transaction lifecycle (begin/commit/rollback)
- `mvcc.go` - Multi-version concurrency control
- `isolation.go` - Snapshot isolation implementation

#### `pkg/document/` - DocumentStore
High-level document operations built on top of KV store.

**Key files:**
- `store.go` - StoreDocument from PageIndex JSON
- `retrieve.go` - GetNode, GetSubtree, GetChildren
- `hierarchy.go` - Tree traversal algorithms
- `flatten.go` - Convert tree JSON to flat nodes

#### `pkg/version/` - VersionStore (NEW - Week 7)
Temporal queries and policy version management.

**Key files:**
- `store.go` - VersionStore implementation
- `temporal.go` - GetVersionAsOf, ListVersions
- `diff.go` - Track changes between versions
- `supersede.go` - Handle version supersession

**Supports tool:** `temporal_lookup`

#### `pkg/metadata/` - MetadataStore (NEW - Week 8)
Tool results, trajectories, cross-references, and contradictions.

**Key files:**
- `store.go` - MetadataStore implementation
- `tool_result.go` - Store outputs from ReAct tools
- `trajectory.go` - Store pi_search trajectories
- `cross_ref.go` - Store node relationships for policy_xref
- `contradiction.go` - Store detected contradictions
- `analytics.go` - Trajectory and tool result analytics

**Supports tools:** `pi_search`, `policy_xref`, `contradiction_detector`, `confidence_score`

#### `pkg/prompt/` - PromptStore (NEW - Week 9)
Prompt versioning and usage tracking.

**Key files:**
- `store.go` - PromptStore implementation
- `prompt.go` - Prompt structure and versioning
- `usage.go` - Track which prompts were used
- `schema.go` - Store tool schemas with prompts

**Supports tool:** `finish` (tracks prompt used for decision)

---

### API Layer

#### `proto/`
Protocol Buffer definitions for gRPC API.

```protobuf
// treestore.proto
service TreeStoreService {
    rpc StoreDocument(StoreDocumentRequest) returns (StoreDocumentResponse);
    rpc GetNode(GetNodeRequest) returns (GetNodeResponse);
    rpc GetSubtree(GetSubtreeRequest) returns (GetSubtreeResponse);
    // ... more RPCs
}
```

#### `pkg/api/`
gRPC server implementation.

**Key files:**
- `server.go` - gRPC server setup
- `service.go` - Service interface implementation
- `handlers.go` - Request handling logic

---

### Client Libraries

#### `client/python/`
Python client for integration with reasoning-service.

```python
# treestore/client.py
class TreeStoreClient:
    def __init__(self, host='localhost', port=50051)
    def store_document(self, policy_id, tree_json)
    def get_node(self, policy_id, node_id)
    def get_subtree(self, policy_id, node_id, max_depth=None)
```

---

### Testing

#### `test/unit/`
Unit tests for individual components.
- `*_test.go` - One test file per package
- Tests should be fast (<1s each)
- High coverage (>80%)

#### `test/integration/`
End-to-end integration tests.
- Test full workflows
- Include crash recovery tests
- Test concurrent access

#### `test/benchmark/`
Performance benchmarks.
- Compare with PostgreSQL
- Measure latency percentiles
- Track over time

---

### Configuration

#### `internal/config/config.go`
```go
type Config struct {
    // Server
    GRPCPort int
    
    // Storage
    DataDir   string
    PageSize  int
    CacheSize int
    
    // WAL
    WALDir        string
    MaxWALSize    int64
    CheckpointInt time.Duration
    
    // Performance
    MaxConcurrentTxns int
    ReadBufferSize    int
    
    // Observability
    MetricsPort   int
    LogLevel      string
}
```

---

### Deployment

#### `deploy/docker/Dockerfile`
```dockerfile
FROM golang:1.21 AS builder
WORKDIR /build
COPY . .
RUN make build

FROM alpine:latest
RUN apk add --no-cache ca-certificates
COPY --from=builder /build/bin/treestore /usr/local/bin/
EXPOSE 50051 9090
CMD ["treestore"]
```

#### `deploy/k8s/deployment.yaml`
Kubernetes deployment for production.

---

## Development Workflow

### 1. Setup Development Environment
```bash
cd tree_db
./scripts/setup.sh

# Create extended package structure
mkdir -p pkg/{version,metadata,prompt}
```

### 2. Run Tests
```bash
make test           # All tests
make test-unit      # Unit tests only
make test-integration  # Integration tests
make test-stores    # Test all stores (document, version, metadata, prompt)
make bench          # Benchmarks
```

### 3. Build
```bash
make build          # Build binary
make build-all      # Build all packages
make docker         # Build Docker image
```

### 4. Run Locally
```bash
./build/bin/treestore --config config.yaml

# Or with specific features enabled
./build/bin/treestore \
  --enable-version-store \
  --enable-metadata-store \
  --enable-prompt-store
```

### 5. Generate gRPC Code
```bash
./scripts/generate_proto.sh

# Regenerate with extended API
./scripts/generate_proto.sh --include-extensions
```

### 6. Test Tool Integration
```bash
# Test specific tool support
make test-tool-pi-search
make test-tool-temporal-lookup
make test-tool-policy-xref
```

---

## Makefile Targets

```makefile
.PHONY: all build test clean

# Build binary
build:
	go build -o build/bin/treestore cmd/treestore/main.go

# Build all packages
build-all:
	go build ./pkg/...

# Run all tests
test:
	go test ./... -v -cover

# Unit tests only
test-unit:
	go test ./pkg/... -v -short

# Test individual stores
test-stores:
	go test ./pkg/document/... -v
	go test ./pkg/version/... -v
	go test ./pkg/metadata/... -v
	go test ./pkg/prompt/... -v

# Test tool integration
test-tool-pi-search:
	go test ./test/integration/... -v -run TestPiSearchTool

test-tool-temporal-lookup:
	go test ./test/integration/... -v -run TestTemporalLookupTool

test-tool-policy-xref:
	go test ./test/integration/... -v -run TestPolicyXrefTool

# Integration tests
test-integration:
	go test ./test/integration/... -v

# Benchmarks
bench:
	go test ./test/benchmark/... -bench=. -benchmem

# Generate protobuf code (with extensions)
proto:
	./scripts/generate_proto.sh --include-extensions

# Format code
fmt:
	go fmt ./...

# Lint
lint:
	golangci-lint run

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf data/

# Run server
run:
	go run cmd/treestore/main.go

# Run with all stores enabled
run-full:
	go run cmd/treestore/main.go \
		--enable-version-store \
		--enable-metadata-store \
		--enable-prompt-store

# Docker build
docker:
	docker build -t treestore:latest -f deploy/docker/Dockerfile .
```

---

## Dependencies

### Go Dependencies (go.mod)
```go
module github.com/yourusername/treestore

go 1.21

require (
	github.com/prometheus/client_golang v1.17.0
	go.uber.org/zap v1.26.0
	google.golang.org/grpc v1.59.0
	google.golang.org/protobuf v1.31.0
)
```

### Python Dependencies (client/python/requirements.txt)
```
grpcio>=1.59.0
grpcio-tools>=1.59.0
protobuf>=4.25.0
```

---

## Git Ignore

```gitignore
# Binaries
build/
*.exe
*.dll
*.so
*.dylib

# Test artifacts
*.test
*.prof
*.out

# Data files
data/
*.db
*.log

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Generated code
*.pb.go
*_pb2.py
```

---

## Code Organization Principles

### 1. Package Structure
- `pkg/` - Public, importable packages
- `internal/` - Private, project-specific code
- `cmd/` - Executable binaries

### 2. Naming Conventions
- Files: `lowercase_with_underscores.go`
- Packages: Short, lowercase, no underscores
- Types: PascalCase
- Functions: camelCase (exported: PascalCase)

### 3. Test Files
- Co-located with source: `foo.go` → `foo_test.go`
- Integration tests: Separate `test/` directory
- Benchmarks: Separate `test/benchmark/` directory

### 4. Import Grouping
```go
import (
    // Standard library
    "context"
    "fmt"
    
    // Third-party
    "github.com/prometheus/client_golang/prometheus"
    "google.golang.org/grpc"
    
    // Local
    "github.com/yourusername/treestore/pkg/btree"
    "github.com/yourusername/treestore/pkg/wal"
)
```

---

## Next Steps

1. Create this directory structure:
   ```bash
   cd tree_db
   mkdir -p {pkg,internal,cmd,test,proto,client,scripts,docs,deploy}
   # ... (see structure above)
   ```

2. Initialize Go module:
   ```bash
   go mod init github.com/yourusername/treestore
   ```

3. Start with Week 1 implementation (pkg/btree/)

4. Follow IMPLEMENTATION_PLAN.md week by week

---

## Questions?

Refer to:
- IMPLEMENTATION_PLAN.md for timeline
- ARCHITECTURE.md for design decisions
- docs/ for specific guides

Happy coding! 🚀

