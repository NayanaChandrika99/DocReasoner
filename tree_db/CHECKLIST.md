# TreeStore Production Readiness Checklist

Quick reference for tracking implementation progress.

---

## Week 14: WAL & Crash Recovery (5 days)

### Day 1-2: WAL Core
- [ ] `pkg/wal/entry.go` - Log entry format with LSN, TxnID, OpType, CRC32
- [ ] `pkg/wal/writer.go` - Sequential log writing with fsync
- [ ] `pkg/wal/reader.go` - Log reading with CRC32 validation
- [ ] `pkg/wal/wal_test.go` - Basic WAL tests
- [ ] Log file rotation (100MB per file)

### Day 3-4: Recovery & Checkpointing
- [ ] `pkg/wal/recovery.go` - Replay log entries on startup
- [ ] `pkg/wal/checkpoint.go` - Background checkpointing
- [ ] `pkg/wal/recovery_test.go` - Crash recovery tests
- [ ] `pkg/wal/checkpoint_test.go` - Checkpointing tests
- [ ] Keep last 3 log files

### Day 5: Integration
- [ ] Update `pkg/storage/kv.go` to use WAL
- [ ] Add recovery call in `Open()`
- [ ] Simulate crash scenarios
- [ ] Verify data integrity after recovery
- [ ] Update ARCHITECTURE.md

**Deliverables:**
- [ ] 15+ WAL/recovery tests passing
- [ ] Zero data loss in crash tests
- [ ] Documentation updated

---

## Week 15: gRPC API & Python Client (7 days)

### Day 1-2: Protocol Buffers
- [ ] Create `proto/treestore.proto`
- [ ] Define all 24 RPC methods
- [ ] Define all message types (Document, Node, etc.)
- [ ] Generate Go stubs: `protoc --go_out=. --go-grpc_out=.`

### Day 3-4: gRPC Server
- [ ] `cmd/treestore/main.go` - Server entry point
- [ ] `internal/server/server.go` - Implement all 24 RPC methods
- [ ] `internal/config/config.go` - Server configuration
- [ ] Error handling with gRPC status codes
- [ ] Request validation
- [ ] Logging for all requests

### Day 5: Python Client
- [ ] Generate Python stubs
- [ ] `client/python/treestore/client.py` - TreeStoreClient class
- [ ] `client/python/treestore/__init__.py` - Package init
- [ ] `client/python/setup.py` - Packaging
- [ ] `client/python/requirements.txt` - Dependencies
- [ ] `client/python/README.md` - Usage docs

### Day 6-7: Integration & Testing
- [ ] `test/integration/grpc_test.go` - Go integration tests
- [ ] `client/python/tests/test_client.py` - Python client tests
- [ ] `examples/python/ingest_pageindex.py` - Ingestion example
- [ ] `examples/python/query_policy.py` - Query example
- [ ] `examples/python/temporal_lookup.py` - Temporal query example
- [ ] End-to-end test: Store → Retrieve → Verify

**Deliverables:**
- [ ] gRPC server running on `:50051`
- [ ] Python client installable via pip
- [ ] All integration tests passing
- [ ] Example scripts working

---

## Week 16: Observability & Deployment (7 days)

### Day 1-2: Observability
- [ ] `internal/metrics/metrics.go` - Prometheus metrics
  - [ ] Query latency histogram
  - [ ] Cache hit rate gauge
  - [ ] Transaction duration
  - [ ] WAL size gauge
  - [ ] Error counter
  - [ ] Active transactions gauge
- [ ] `internal/logging/logger.go` - Structured logging (zap/zerolog)
- [ ] Replace all 51 `fmt.Printf` statements
- [ ] Add profiling endpoints (`/debug/pprof/`)

### Day 3: Health & Monitoring
- [ ] Implement `Health()` RPC method
- [ ] Implement `Stats()` RPC method
- [ ] Expose Prometheus metrics on `:9090/metrics`
- [ ] HTTP server for metrics endpoint

### Day 4-5: Deployment Artifacts
- [ ] `Dockerfile` - Multi-stage build
- [ ] `deploy/k8s/deployment.yaml` - K8s deployment
- [ ] `deploy/k8s/service.yaml` - K8s service
- [ ] `deploy/k8s/configmap.yaml` - Configuration
- [ ] `deploy/k8s/pvc.yaml` - Persistent volume
- [ ] `docker-compose.yml` - Local dev stack
- [ ] `deploy/prometheus.yml` - Prometheus config
- [ ] `deploy/grafana-dashboards/treestore.json` - Grafana dashboard

### Day 6-7: Integration with Reasoning Service
- [ ] Update `../pyproject.toml` - Add treestore-client
- [ ] Update `tool_handlers.py`:
  - [ ] `pi_search` → `treestore_client.get_subtree()`
  - [ ] `temporal_lookup` → `treestore_client.get_version_as_of()`
  - [ ] `policy_xref` → `treestore_client.get_cross_references()`
  - [ ] Store tool results → `treestore_client.store_tool_result()`
- [ ] `../scripts/migrate_postgres_to_treestore.py` - Migration script
- [ ] Run end-to-end tests
- [ ] Measure performance vs PostgreSQL

**Deliverables:**
- [ ] Prometheus + Grafana monitoring working
- [ ] Docker image builds successfully
- [ ] Kubernetes deployment successful
- [ ] reasoning-service integration complete
- [ ] PostgreSQL migration validated

---

## Success Metrics

### Technical
- [ ] All unit tests passing (87 + 15 WAL = 102 tests)
- [ ] All integration tests passing (gRPC + Python)
- [ ] Sub-10ms query latency for node lookups
- [ ] Zero data loss in crash recovery tests
- [ ] 3x+ performance vs PostgreSQL for tree queries

### Integration
- [ ] TreeStore running on `:50051` (gRPC)
- [ ] Metrics exposed on `:9090/metrics`
- [ ] reasoning-service successfully using TreeStore
- [ ] All 10 ReAct tools working with TreeStore
- [ ] PostgreSQL migration complete

### Deployment
- [ ] Docker image < 50MB
- [ ] Kubernetes deployment successful
- [ ] Grafana dashboard displaying metrics
- [ ] Health checks passing
- [ ] Production-ready

---

## Quick Commands

### Development
```bash
# Run all tests
cd tree_db && go test ./pkg/...

# Run specific package tests
go test ./pkg/wal/... -v

# Build gRPC server
go build -o treestore ./cmd/treestore

# Run server
./treestore

# Generate proto stubs (Go)
protoc --go_out=. --go-grpc_out=. proto/treestore.proto

# Generate proto stubs (Python)
python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./client/python/treestore \
    --grpc_python_out=./client/python/treestore \
    proto/treestore.proto

# Install Python client
pip install -e ./client/python
```

### Docker
```bash
# Build Docker image
docker build -t treestore:latest .

# Run with docker-compose
docker-compose up -d

# Check logs
docker-compose logs -f treestore

# Stop
docker-compose down
```

### Kubernetes
```bash
# Apply manifests
kubectl apply -f deploy/k8s/

# Check status
kubectl get pods
kubectl get svc

# Port forward
kubectl port-forward svc/treestore 50051:50051

# Check logs
kubectl logs -f deployment/treestore
```

---

**Last Updated:** 2025-11-14

