# TreeStore Production Readiness Plan

**Created:** 2025-11-14  
**Status:** Phase 6 - Weeks 14-16 (3 weeks remaining)  
**Current Completion:** 56% (Core engine complete, production features in progress)

---

## Executive Summary

TreeStore has a **fully functional core database engine** with 87 passing tests, but lacks **4 critical production features** needed to integrate with the Python reasoning-service:

1. ❌ **Write-Ahead Log (WAL)** - No crash recovery
2. ❌ **gRPC API** - No way for Python to call TreeStore
3. ❌ **Python Client** - No client library for reasoning-service
4. ❌ **Observability** - No monitoring, metrics, or structured logging

**Timeline:** 3 weeks (19 days) to complete all 4 features  
**Critical Path:** gRPC API → Python Client → Integration with reasoning-service

---

## What's Already Complete ✅

### Core Database Engine (Weeks 1-9)
- ✅ B+Tree storage engine (`pkg/btree/`)
  - Insert, Get, Delete, RangeScan operations
  - Node splitting/merging, tree rebalancing
  - 23 passing tests
  
- ✅ Storage layer (`pkg/storage/`)
  - Disk-based KV store with copy-on-write
  - Freelist for space reclamation
  - Composite key encoding
  - Transaction support (Begin/Commit/Abort)
  - Secondary indexes (parent, page, path)
  - 25 passing tests

- ✅ Specialized stores
  - **DocumentStore** (`pkg/document/`) - Hierarchical policy documents (5 tests)
  - **VersionStore** (`pkg/version/`) - Temporal queries for `temporal_lookup` tool (7 tests)
  - **MetadataStore** (`pkg/metadata/`) - Tool results, trajectories, cross-references (8 tests)
  - **PromptStore** (`pkg/prompt/`) - Prompt versioning and usage tracking (8 tests)

- ✅ Query engine (`pkg/query/`)
  - Unified cross-store queries
  - Enriched results combining document + metadata + version
  - 9 passing tests

**Total:** 87 tests passing, >80% code coverage

---

## What's Missing ❌

### 1. Write-Ahead Log (WAL) & Crash Recovery

**Problem:**
- `pkg/wal/` directory exists but is completely empty
- Current copy-on-write provides atomicity but NO crash recovery
- If process crashes before flush, data is lost
- **NOT production-ready**

**Impact:**
- Cannot deploy to production without risk of data loss
- Acceptable for development/testing only

**Solution:** Week 14 (5 days)

---

### 2. gRPC API Server

**Problem:**
- No `.proto` files anywhere in project
- `cmd/treestore/` directory exists but is empty (no `main.go`)
- TreeStore currently only usable as a Go library
- **Cannot be called from Python**

**Impact:**
- reasoning-service (Python) cannot access TreeStore
- All 10 ReAct tools blocked
- Cannot migrate from PostgreSQL

**Solution:** Week 15, Days 1-4 (4 days)

---

### 3. Python Client Library

**Problem:**
- `client/python/treestore/` directory exists but is empty
- No Python bindings or client library
- No way for reasoning-service to call TreeStore

**Impact:**
- Even with gRPC server, reasoning-service needs a clean Python API
- Tool handlers (`pi_search`, `temporal_lookup`, `policy_xref`) cannot use TreeStore
- Integration blocked

**Solution:** Week 15, Days 5-7 (3 days)

---

### 4. Observability (Monitoring & Logging)

**Problem:**
- No Prometheus metrics
- No structured logging (only ~51 `fmt.Printf` statements)
- No health checks
- No profiling endpoints
- **Cannot monitor or debug in production**

**Impact:**
- Can't tell if TreeStore is healthy
- Can't measure query latency or cache hit rate
- Can't debug issues in production
- Can't prove performance claims

**Solution:** Week 16 (7 days)

---

## Detailed Implementation Plan

### Week 14: WAL & Crash Recovery (5 days)

**Goal:** Add durability guarantees and crash recovery

#### Day 1-2: WAL Core Infrastructure
**Files to create:**
- `pkg/wal/entry.go` - Log entry format
- `pkg/wal/writer.go` - Sequential log writing
- `pkg/wal/reader.go` - Log reading

**Tasks:**
- [ ] Design WAL entry format with LSN, TxnID, OpType, CRC32
- [ ] Implement sequential log writing to disk
- [ ] Add fsync after each write for durability
- [ ] Implement log file rotation (new file every 100MB)
- [ ] Add buffer management for performance
- [ ] Implement log reader with CRC32 validation
- [ ] Handle corrupted entries gracefully

**Deliverables:**
- Working WAL writer and reader
- Basic tests for log writing/reading

---

#### Day 3-4: Recovery & Checkpointing
**Files to create:**
- `pkg/wal/recovery.go` - Crash recovery logic
- `pkg/wal/checkpoint.go` - Checkpointing mechanism

**Tasks:**
- [ ] Implement recovery: replay log entries on startup
- [ ] Rebuild B+Tree state from log
- [ ] Handle partial transactions
- [ ] Skip already-applied entries
- [ ] Implement background checkpointing (every 10 minutes)
- [ ] Flush in-memory state to disk during checkpoint
- [ ] Truncate old log files after checkpoint
- [ ] Keep last 3 log files for safety

**Deliverables:**
- Working crash recovery
- Checkpointing mechanism
- Recovery tests

---

#### Day 5: Integration & Testing
**Files to update:**
- `pkg/storage/kv.go` - Add WAL integration

**Tasks:**
- [ ] Integrate WAL with KV store
- [ ] Ensure write order: WAL → fsync → B+Tree
- [ ] Add recovery call in `Open()`
- [ ] Write comprehensive tests:
  - [ ] `wal_test.go` - Basic WAL operations
  - [ ] `recovery_test.go` - Crash recovery scenarios
  - [ ] `checkpoint_test.go` - Checkpointing logic
- [ ] Simulate crashes mid-transaction
- [ ] Verify data integrity after recovery
- [ ] Update ARCHITECTURE.md with WAL details

**Deliverables:**
- ✅ Durable storage with crash recovery
- ✅ 15+ new tests for WAL/recovery
- ✅ Updated documentation

**References:**
- Build Your Own Database, Chapters 4, 7
- BadgerDB WAL implementation
- PostgreSQL WAL documentation

---

### Week 15: gRPC API & Python Client (7 days)

**Goal:** Expose TreeStore via gRPC and create Python client library

#### Day 1-2: Protocol Buffers Definition
**Files to create:**
- `proto/treestore.proto` - Complete API definition

**Tasks:**
- [ ] Define Protocol Buffers schema with 24 RPC methods:
  - Document operations (Store, Get, Delete)
  - Node operations (GetNode, GetChildren, GetSubtree, GetAncestorPath)
  - Search operations (SearchByKeyword, GetNodesByPage)
  - Version operations (GetVersionAsOf, ListVersions)
  - Metadata operations (StoreToolResult, GetToolResults, StoreTrajectory, etc.)
  - Prompt operations (StorePrompt, GetPrompt, RecordPromptUsage)
  - Health & status (Health, Stats)
- [ ] Define all request/response message types
- [ ] Define Document, Node, PolicyVersion, etc. message types
- [ ] Generate Go stubs: `protoc --go_out=. --go-grpc_out=. proto/treestore.proto`

**Deliverables:**
- Complete `.proto` file
- Generated Go gRPC stubs

---

#### Day 3-4: gRPC Server Implementation
**Files to create:**
- `cmd/treestore/main.go` - Server entry point
- `internal/server/server.go` - RPC handler implementation
- `internal/config/config.go` - Server configuration

**Tasks:**
- [ ] Create `main.go`:
  - [ ] Initialize all stores (Document, Version, Metadata, Prompt, Query)
  - [ ] Start gRPC server on `:50051`
  - [ ] Graceful shutdown handling
  - [ ] Configuration via environment variables
- [ ] Implement `server.go`:
  - [ ] Implement all 24 RPC methods
  - [ ] Map proto messages to internal types
  - [ ] Error handling with proper gRPC status codes
  - [ ] Request validation
  - [ ] Logging for all requests
- [ ] Add server configuration:
  - [ ] Port, TLS settings, timeouts
  - [ ] Max message size (default 100MB for large documents)
  - [ ] Connection pooling
  - [ ] Rate limiting (optional)

**Deliverables:**
- Working gRPC server
- All RPC methods implemented
- Basic error handling

---

#### Day 5: Python Client Library
**Files to create:**
- `client/python/treestore/client.py` - Main client class
- `client/python/treestore/__init__.py` - Package init
- `client/python/setup.py` - Packaging
- `client/python/requirements.txt` - Dependencies
- `client/python/README.md` - Usage documentation

**Tasks:**
- [ ] Generate Python stubs:
  ```bash
  python -m grpc_tools.protoc \
      -I./proto \
      --python_out=./client/python/treestore \
      --grpc_python_out=./client/python/treestore \
      proto/treestore.proto
  ```
- [ ] Create `TreeStoreClient` class:
  - [ ] `__init__(host, port, timeout)` - Setup gRPC channel
  - [ ] `store_document(policy_id, tree_json)` - Store PageIndex output
  - [ ] `get_node(policy_id, node_id)` - Retrieve single node
  - [ ] `get_subtree(policy_id, node_id, max_depth)` - Get hierarchical tree
  - [ ] `search_nodes(policy_id, query)` - Keyword search
  - [ ] `get_version_as_of(policy_id, as_of_date)` - Temporal lookup
  - [ ] `store_tool_result(case_id, tool_name, result)` - Store tool result
  - [ ] `get_cross_references(node_id)` - Get cross-references
  - [ ] `close()` - Close gRPC channel
- [ ] Add error handling and retries
- [ ] Add connection pooling
- [ ] Create `setup.py` for packaging
- [ ] Add `requirements.txt`: grpcio, grpcio-tools, protobuf

**Deliverables:**
- Working Python client library
- Clean API for reasoning-service
- Packaging for pip install

---

#### Day 6-7: Integration & Testing
**Files to create:**
- `test/integration/grpc_test.go` - Go integration tests
- `client/python/tests/test_client.py` - Python client tests
- `examples/python/ingest_pageindex.py` - PageIndex ingestion example
- `examples/python/query_policy.py` - Query example
- `examples/python/temporal_lookup.py` - Temporal query example

**Tasks:**
- [ ] Write Go integration tests:
  - [ ] Test all RPC methods
  - [ ] Test error handling
  - [ ] Test large documents
- [ ] Write Python client tests:
  - [ ] Test all client methods
  - [ ] Test connection handling
  - [ ] Test error handling
- [ ] Create example scripts:
  - [ ] Ingest PageIndex output into TreeStore
  - [ ] Query policy nodes
  - [ ] Temporal lookups
- [ ] End-to-end test: Store document → Retrieve → Verify

**Deliverables:**
- ✅ Complete gRPC API with all operations
- ✅ Working gRPC server
- ✅ Python client library ready for reasoning-service
- ✅ Integration tests passing
- ✅ Example scripts demonstrating usage
- ✅ API documentation

**References:**
- gRPC Go tutorial: https://grpc.io/docs/languages/go/
- gRPC Python tutorial: https://grpc.io/docs/languages/python/

---

### Week 16: Observability & Production Deployment (7 days)

**Goal:** Add monitoring, logging, and deploy to production

#### Day 1-2: Observability Infrastructure
**Files to create:**
- `internal/metrics/metrics.go` - Prometheus metrics
- `internal/logging/logger.go` - Structured logging

**Tasks:**
- [ ] Add Prometheus metrics:
  - [ ] `treestore_query_duration_seconds` - Query latency histogram
  - [ ] `treestore_cache_hit_rate` - Cache hit rate gauge
  - [ ] `treestore_transaction_duration_seconds` - Transaction duration
  - [ ] `treestore_wal_size_bytes` - WAL size gauge
  - [ ] `treestore_errors_total` - Error counter by type
  - [ ] `treestore_active_transactions` - Active transactions gauge
  - [ ] `treestore_documents_total` - Total documents counter
- [ ] Implement structured logging:
  - [ ] Use `zap` or `zerolog`
  - [ ] Log levels: DEBUG, INFO, WARN, ERROR
  - [ ] Include request ID, operation, latency, error details
  - [ ] Replace all 51 `fmt.Printf` statements
- [ ] Add profiling endpoints:
  - [ ] `/debug/pprof/` for CPU, memory, goroutine profiling
  - [ ] Enable with `import _ "net/http/pprof"`

**Deliverables:**
- Prometheus metrics instrumentation
- Structured logging throughout codebase
- Profiling endpoints

---

#### Day 3: Health Checks & Monitoring Endpoints
**Files to update:**
- `internal/server/server.go` - Add Health() and Stats() methods

**Tasks:**
- [ ] Implement Health() RPC method:
  - [ ] Check if DB is accessible
  - [ ] Check WAL status
  - [ ] Check disk space
  - [ ] Return uptime and status
- [ ] Implement Stats() RPC method:
  - [ ] Total documents
  - [ ] Total nodes
  - [ ] Index sizes
  - [ ] WAL size
  - [ ] Cache hit rate
- [ ] Expose Prometheus metrics endpoint:
  - [ ] HTTP server on `:9090/metrics`
  - [ ] Register all metrics

**Deliverables:**
- Health check endpoint
- Stats endpoint
- Prometheus metrics endpoint

---

#### Day 4-5: Deployment Artifacts
**Files to create:**
- `Dockerfile` - Multi-stage Docker build
- `deploy/k8s/deployment.yaml` - Kubernetes deployment
- `deploy/k8s/service.yaml` - Kubernetes service
- `deploy/k8s/configmap.yaml` - Configuration
- `deploy/k8s/pvc.yaml` - Persistent volume claim
- `docker-compose.yml` - Local development stack
- `deploy/prometheus.yml` - Prometheus config
- `deploy/grafana-dashboards/treestore.json` - Grafana dashboard

**Tasks:**
- [ ] Create Dockerfile:
  - [ ] Multi-stage build (builder + runtime)
  - [ ] Expose ports 50051 (gRPC) and 9090 (metrics)
  - [ ] Optimize image size
- [ ] Create Kubernetes manifests:
  - [ ] Deployment with resource limits
  - [ ] Service (ClusterIP)
  - [ ] ConfigMap for configuration
  - [ ] PVC for persistent data
- [ ] Create docker-compose.yml:
  - [ ] TreeStore service
  - [ ] Prometheus service
  - [ ] Grafana service
  - [ ] Volume mounts
- [ ] Create Prometheus config:
  - [ ] Scrape TreeStore metrics
- [ ] Create Grafana dashboard:
  - [ ] Query latency panels
  - [ ] Cache hit rate
  - [ ] Transaction throughput
  - [ ] WAL size
  - [ ] Error rates

**Deliverables:**
- Docker image
- Kubernetes manifests
- docker-compose.yml for local dev
- Monitoring stack configuration

---

#### Day 6-7: Integration with Reasoning Service
**Files to update:**
- `../src/reasoning_service/services/tool_handlers.py` - Update tool handlers
- `../pyproject.toml` - Add treestore-client dependency

**Files to create:**
- `../scripts/migrate_postgres_to_treestore.py` - Migration script

**Tasks:**
- [ ] Update reasoning-service dependencies:
  - [ ] Add `treestore-client` to `pyproject.toml`
  - [ ] Install: `pip install -e ../tree_db/client/python`
- [ ] Update tool handlers to use TreeStore:
  - [ ] `pi_search` → `treestore_client.get_subtree()`
  - [ ] `temporal_lookup` → `treestore_client.get_version_as_of()`
  - [ ] `policy_xref` → `treestore_client.get_cross_references()`
  - [ ] Store all tool results → `treestore_client.store_tool_result()`
  - [ ] Store trajectories → `treestore_client.store_trajectory()`
- [ ] Create migration script:
  - [ ] Read existing policy data from PostgreSQL
  - [ ] Convert to TreeStore format
  - [ ] Validate migration
  - [ ] Compare results
- [ ] Run end-to-end tests:
  - [ ] Start TreeStore server
  - [ ] Run reasoning-service integration tests
  - [ ] Verify all 10 tools work correctly
  - [ ] Measure performance vs PostgreSQL

**Deliverables:**
- ✅ Complete observability stack (Prometheus + Grafana)
- ✅ Structured logging throughout codebase
- ✅ Health checks and monitoring endpoints
- ✅ Docker image and Kubernetes manifests
- ✅ Integration with reasoning-service complete
- ✅ Migration from PostgreSQL validated
- ✅ Production deployment ready

**References:**
- Prometheus Go client: https://github.com/prometheus/client_golang
- Zap logging: https://github.com/uber-go/zap
- Kubernetes best practices

---

## Success Criteria

### Week 14 (WAL) ✅
- [ ] All WAL tests passing (15+ new tests)
- [ ] Crash recovery works correctly
- [ ] No data loss in crash scenarios
- [ ] Checkpointing runs successfully
- [ ] Documentation updated

### Week 15 (gRPC + Python) ✅
- [ ] gRPC server running on `:50051`
- [ ] All 24 RPC methods implemented
- [ ] Python client library installable via pip
- [ ] Integration tests passing (Go + Python)
- [ ] Example scripts working
- [ ] API documentation complete

### Week 16 (Observability + Deployment) ✅
- [ ] Prometheus metrics exposed on `:9090/metrics`
- [ ] Structured logging throughout codebase
- [ ] Health checks working
- [ ] Docker image builds successfully
- [ ] Kubernetes deployment successful
- [ ] Grafana dashboard displaying metrics
- [ ] reasoning-service integration complete
- [ ] PostgreSQL migration validated
- [ ] End-to-end tests passing

---

## Risk Management

### Potential Challenges

**1. WAL Complexity**
- *Risk:* Bugs in recovery logic causing data corruption
- *Mitigation:* Extensive testing, fuzzy testing, reference implementations
- *Fallback:* Use copy-on-write only for MVP, add WAL later

**2. gRPC Performance**
- *Risk:* gRPC overhead slower than expected
- *Mitigation:* Benchmark early, optimize serialization, use connection pooling
- *Fallback:* Profile and optimize critical path

**3. Python Integration Issues**
- *Risk:* gRPC Python client has issues or performance problems
- *Mitigation:* Test early with real data, add retries and error handling
- *Fallback:* Use HTTP/REST API instead of gRPC

**4. Timeline Slippage**
- *Risk:* 3 weeks is aggressive for 4 major features
- *Mitigation:* Prioritize gRPC first (unblocks integration), defer WAL if needed
- *Fallback:* Ship "Portfolio MVP" with gRPC only, add WAL/observability later

---

## Alternative Approach: Portfolio MVP (1 week)

If timeline is tight, consider **Portfolio MVP** approach:

**Week 1: gRPC + Python Client Only**
- Skip WAL (use copy-on-write, accept risk)
- Skip full observability (add basic logging only)
- Focus on getting reasoning-service integration working

**Result:**
- Working end-to-end demo in 1 week
- Can showcase in portfolio/interviews
- Document "production hardening" as future work
- Still impressive (shows distributed systems skills)

**Then add later:**
- Week 2: WAL + crash recovery
- Week 3: Full observability + deployment

---

## Recommendation

**Start with Week 15 (gRPC) first**, not Week 14 (WAL):

**Reasons:**
1. **Unblocks integration immediately** - Can start testing with reasoning-service
2. **Faster feedback loop** - Can verify API design with real tools
3. **WAL can be added later** - Doesn't change API, can be done independently
4. **Better for portfolio** - Working demo is more impressive than invisible WAL

**Revised Order:**
1. Week 15: gRPC + Python Client (7 days) - **START HERE**
2. Week 14: WAL + Recovery (5 days)
3. Week 16: Observability + Deployment (7 days)

**Total:** Still 3 weeks, but unblocks integration faster.

---

## Next Steps

**Immediate:**
1. Review this plan with Nainy
2. Confirm priority order (gRPC first vs WAL first)
3. Start Week 15, Day 1: Create `proto/treestore.proto`

**After Week 15:**
4. Test integration with reasoning-service
5. Measure performance vs PostgreSQL
6. Start Week 14 (WAL) or Week 16 (Observability) based on priority

**After Week 16:**
7. Production deployment
8. Create portfolio materials (blog post, demo video)
9. Performance benchmarks and graphs

---

**Last Updated:** 2025-11-14  
**Next Review:** After Week 15 completion

