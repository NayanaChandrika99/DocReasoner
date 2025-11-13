# TreeStore Implementation Plan

## Project Timeline: 12-13 Weeks (Extended)

This document outlines the complete implementation roadmap for TreeStore, a hierarchical document database built from scratch in Go.

**Update:** Timeline extended to include VersionStore, MetadataStore, and PromptStore for full ReAct controller tool support.

---

## Phase 1: Core Database Engine (Weeks 1-3)

### Week 1: Foundation & B+Tree Basics

**Goal:** Set up project structure and implement basic B+Tree operations

#### Tasks:
- [ ] Initialize Go project structure
  ```bash
  go mod init github.com/yourusername/treestore
  mkdir -p pkg/{btree,storage,wal,index}
  mkdir -p cmd/treestore
  mkdir -p internal/{config,metrics}
  mkdir -p test/{unit,integration,benchmark}
  ```

- [ ] Implement B+Tree node structure
  - [ ] Define `Node` struct (internal vs leaf nodes)
  - [ ] Implement node serialization/deserialization
  - [ ] Write unit tests for node operations

- [ ] Implement B+Tree insertion
  - [ ] `Insert(key, value)` operation
  - [ ] Node splitting logic
  - [ ] Tree rebalancing
  - [ ] Test with 1000+ insertions

- [ ] Implement B+Tree search
  - [ ] `Get(key)` operation
  - [ ] Key comparison and traversal
  - [ ] Test lookup performance

**Deliverables:**
- Working B+Tree with insert and search
- Comprehensive unit tests (>80% coverage)
- Basic benchmarks

**References:**
- Build Your Own Database, Chapters 3-5
- go-memdb radix tree implementation (for patterns)

---

### Week 2: Persistence & WAL

**Goal:** Add durability through Write-Ahead Logging and disk persistence

#### Tasks:
- [ ] Implement Write-Ahead Log (WAL)
  - [ ] Log entry format design
  - [ ] Sequential log writing
  - [ ] Log rotation strategy
  - [ ] Fsync for durability

- [ ] Implement crash recovery
  - [ ] Replay WAL entries on startup
  - [ ] Checkpointing mechanism
  - [ ] Handle corrupted log entries

- [ ] Add page management
  - [ ] Fixed-size page abstraction
  - [ ] Page allocation/deallocation
  - [ ] Page cache (buffer pool)

- [ ] Implement B+Tree deletion
  - [ ] `Delete(key)` operation
  - [ ] Node merging and redistribution
  - [ ] Update WAL for deletions

**Deliverables:**
- Durable B+Tree with crash recovery
- WAL replay tests
- Recovery integration tests

**References:**
- Build Your Own Database, Chapters 4, 7
- BadgerDB WAL implementation

---

### Week 3: Range Queries & Free List

**Goal:** Add range scan support and space reclamation

#### Tasks:
- [ ] Implement range queries
  - [ ] `RangeScan(start, end)` operation
  - [ ] Efficient leaf node traversal
  - [ ] Iterator pattern for large result sets
  - [ ] Test with various key ranges

- [ ] Implement free list management
  - [ ] Track deleted pages
  - [ ] Reuse freed space
  - [ ] Defragmentation strategy

- [ ] Add basic key-value store interface
  ```go
  type KVStore interface {
      Get(key []byte) ([]byte, error)
      Put(key, value []byte) error
      Delete(key []byte) error
      RangeScan(start, end []byte) (Iterator, error)
  }
  ```

**Deliverables:**
- Working range scans
- Space reclamation system
- Clean KV interface
- Performance benchmarks for range queries

**References:**
- Build Your Own Database, Chapters 6, 8

---

## Phase 2: Advanced Features (Weeks 4-6)

### Week 4: Secondary Indexes

**Goal:** Support multiple access patterns for document nodes

#### Tasks:
- [ ] Design secondary index architecture
  ```go
  type IndexManager struct {
      primary   *BTree  // (policy_id, node_id) -> node data
      byParent  *BTree  // (policy_id, parent_id) -> [node_ids]
      byPage    *BTree  // (policy_id, page_num) -> [node_ids]
      byPath    *BTree  // (policy_id, path_hash) -> node_id
  }
  ```

- [ ] Implement index maintenance
  - [ ] Automatic index updates on insert/delete
  - [ ] Consistency guarantees across indexes
  - [ ] Batch index updates

- [ ] Add composite key support
  - [ ] Multi-field key encoding
  - [ ] Lexicographic ordering
  - [ ] Test with complex keys

**Deliverables:**
- Multiple B+Trees for different access patterns
- Index consistency tests
- Query performance comparisons

**References:**
- Build Your Own Database, Chapter 11 (Secondary Indexes)

---

### Week 5: Transactions

**Goal:** ACID transaction support for multi-operation consistency

#### Tasks:
- [ ] Design transaction interface
  ```go
  type Transaction interface {
      Get(key []byte) ([]byte, error)
      Put(key, value []byte) error
      Delete(key []byte) error
      Commit() error
      Rollback() error
  }
  ```

- [ ] Implement MVCC (Multi-Version Concurrency Control)
  - [ ] Version tracking for rows
  - [ ] Snapshot isolation
  - [ ] Garbage collection of old versions

- [ ] Add transaction manager
  - [ ] Transaction ID generation
  - [ ] Conflict detection
  - [ ] Deadlock prevention

- [ ] Implement batch operations
  - [ ] `BatchInsert([]KV)` - atomic multi-insert
  - [ ] Transaction rollback on failure

**Deliverables:**
- Working transaction system
- Isolation level tests
- Concurrent transaction tests

**References:**
- Build Your Own Database, Chapters 12, 13
- go-memdb transaction patterns

---

### Week 6: Document Abstraction Layer

**Goal:** Build document-specific operations on top of KV store

#### Tasks:
- [ ] Define document data model
  ```go
  type Document struct {
      PolicyID      string
      VersionID     string
      PageIndexDocID string
      RootNodeID    string
      Metadata      map[string]string
      CreatedAt     time.Time
  }
  
  type Node struct {
      NodeID      string
      ParentID    *string
      Title       string
      PageStart   int
      PageEnd     int
      Summary     string
      Text        string
      SectionPath string
      ChildIDs    []string
  }
  ```

- [ ] Implement document operations
  - [ ] `StoreDocument(doc, nodes)` - atomic storage
  - [ ] `GetNode(policyID, nodeID)` - direct lookup
  - [ ] `GetChildren(policyID, parentID)` - hierarchical query
  - [ ] `GetSubtree(policyID, nodeID, depth)` - recursive retrieval
  - [ ] `GetAncestorPath(policyID, nodeID)` - path to root

- [ ] Add hierarchical index
  - [ ] Materialized path for fast ancestor queries
  - [ ] Nested set model for subtree queries
  - [ ] Choose optimal strategy

- [ ] Implement full-text search
  - [ ] Inverted index for titles/summaries
  - [ ] BM25-style ranking
  - [ ] Keyword query parser

**Deliverables:**
- High-level document API
- Hierarchical query optimizations
- Full-text search capability

---

## Phase 3: Extended Stores (Weeks 7-9)

### Week 7: VersionStore - Temporal Queries

**Goal:** Support `temporal_lookup` tool with version management

#### Tasks:
- [ ] Design VersionStore architecture
  ```go
  type VersionStore struct {
      btree *BTree  // Reuse B+Tree
      // Key: (policy_id, effective_date, version_id)
  }
  ```

- [ ] Implement version storage
  - [ ] Store policy versions with effective dates
  - [ ] Version diff tracking
  - [ ] Range queries on dates

- [ ] Implement temporal queries
  - [ ] `GetVersionAsOf(policyID, date)` - Get version effective on date
  - [ ] `ListVersions(policyID)` - List all versions
  - [ ] Handle version supersession logic

- [ ] Test temporal queries
  - [ ] Query before first version
  - [ ] Query between versions
  - [ ] Query after last version
  - [ ] Edge cases (same-day updates)

**Deliverables:**
- Working VersionStore
- Temporal query tests
- Integration with DocumentStore

**References:**
- Temporal database patterns
- Version control systems

---

### Week 8: MetadataStore - Tool Results & Trajectories

**Goal:** Store results from ReAct tools and search trajectories

#### Tasks:
- [ ] Design MetadataStore architecture
  ```go
  type MetadataStore struct {
      toolResults   *BTree  // (case_id, tool_name, timestamp)
      trajectories  *BTree  // (case_id, timestamp)
      crossRefs     *BTree  // (from_node_id, to_node_id)
      contradictions *BTree  // (case_id, criterion_id)
  }
  ```

- [ ] Implement tool result storage
  - [ ] Store tool inputs/outputs
  - [ ] Track latency and success rate
  - [ ] Query by case_id or tool_name

- [ ] Implement trajectory storage
  - [ ] Store pi_search trajectories
  - [ ] Track nodes visited, thinking, confidence
  - [ ] Enable trajectory analytics

- [ ] Implement cross-reference storage
  - [ ] Store node relationships (for policy_xref)
  - [ ] Bidirectional references
  - [ ] Query related nodes

- [ ] Implement contradiction storage
  - [ ] Store detected contradictions
  - [ ] Track evidence pieces
  - [ ] Resolution tracking

**Deliverables:**
- Working MetadataStore
- Tool result storage tests
- Trajectory analytics examples

---

### Week 9: PromptStore - Prompt Versioning

**Goal:** Track which prompts were used for decisions

#### Tasks:
- [ ] Design PromptStore architecture
  ```go
  type PromptStore struct {
      prompts *BTree  // (prompt_id, version)
      usage   *BTree  // (case_id, timestamp)
  }
  ```

- [ ] Implement prompt storage
  - [ ] Store prompt content and tool schemas
  - [ ] Version tracking
  - [ ] Deployment date tracking

- [ ] Implement usage tracking
  - [ ] Record which prompt was used for each case
  - [ ] Link to tool results
  - [ ] Query prompts by version or date

- [ ] Test prompt versioning
  - [ ] Multiple prompt versions
  - [ ] Usage analytics
  - [ ] Prompt effectiveness metrics

**Deliverables:**
- Working PromptStore
- Prompt versioning tests
- Usage tracking integration

---

## Phase 4: API & Integration (Weeks 10-11)

### Week 10: gRPC API

**Goal:** Expose TreeStore functionality via gRPC for Python integration

#### Tasks:
- [ ] Define Protocol Buffers schema
  ```protobuf
  service TreeStoreService {
      // Document operations
      rpc StoreDocument(StoreDocumentRequest) returns (StoreDocumentResponse);
      rpc GetDocument(GetDocumentRequest) returns (GetDocumentResponse);
      rpc DeleteDocument(DeleteDocumentRequest) returns (DeleteDocumentResponse);
      
      // Node operations
      rpc GetNode(GetNodeRequest) returns (GetNodeResponse);
      rpc GetChildren(GetChildrenRequest) returns (GetChildrenResponse);
      rpc GetSubtree(GetSubtreeRequest) returns (GetSubtreeResponse);
      rpc GetAncestorPath(GetAncestorPathRequest) returns (GetAncestorPathResponse);
      
      // Search operations
      rpc SearchByKeyword(SearchRequest) returns (SearchResponse);
      rpc GetNodesByPage(GetNodesByPageRequest) returns (GetNodesByPageResponse);
      
      // Version operations (NEW - Week 7)
      rpc GetVersionAsOf(GetVersionAsOfRequest) returns (PolicyVersion);
      rpc ListVersions(ListVersionsRequest) returns (ListVersionsResponse);
      
      // Metadata operations (NEW - Week 8)
      rpc StoreToolResult(StoreToolResultRequest) returns (StoreToolResultResponse);
      rpc GetToolResults(GetToolResultsRequest) returns (GetToolResultsResponse);
      rpc StoreTrajectory(StoreTrajectoryRequest) returns (StoreTrajectoryResponse);
      rpc GetTrajectories(GetTrajectoriesRequest) returns (GetTrajectoriesResponse);
      rpc StoreCrossReference(StoreCrossReferenceRequest) returns (StoreCrossReferenceResponse);
      rpc GetCrossReferences(GetCrossReferencesRequest) returns (GetCrossReferencesResponse);
      rpc StoreContradiction(StoreContradictionRequest) returns (StoreContradictionResponse);
      
      // Prompt operations (NEW - Week 9)
      rpc StorePrompt(StorePromptRequest) returns (StorePromptResponse);
      rpc GetPrompt(GetPromptRequest) returns (GetPromptResponse);
      rpc RecordPromptUsage(RecordPromptUsageRequest) returns (RecordPromptUsageResponse);
      
      // Batch operations
      rpc BatchInsertNodes(BatchInsertNodesRequest) returns (BatchInsertNodesResponse);
      
      // Health & status
      rpc Health(HealthRequest) returns (HealthResponse);
      rpc Stats(StatsRequest) returns (StatsResponse);
  }
  ```

- [ ] Implement gRPC server
  - [ ] Service implementation
  - [ ] Error handling and status codes
  - [ ] Request validation
  - [ ] Connection pooling

- [ ] Add server configuration
  - [ ] Port, TLS, timeouts
  - [ ] Max message size
  - [ ] Rate limiting

- [ ] Implement health checks
  - [ ] Liveness probe
  - [ ] Readiness probe
  - [ ] Database stats endpoint

**Deliverables:**
- Working gRPC server
- Complete API implementation
- API documentation

---

### Week 11: Python Client & Integration

**Goal:** Create Python client library and integrate with reasoning-service

#### Tasks:
- [ ] Generate Python gRPC stubs
  ```bash
  python -m grpc_tools.protoc \
      --python_out=. \
      --grpc_python_out=. \
      treestore.proto
  ```

- [ ] Build Python client library
  ```python
  class TreeStoreClient:
      def __init__(self, host='localhost', port=50051):
          # Setup gRPC channel
      
      def store_document(self, policy_id, tree_json):
          # Store PageIndex output
      
      def get_node(self, policy_id, node_id):
          # Retrieve single node
      
      def get_subtree(self, policy_id, node_id, max_depth=None):
          # Get hierarchical tree
      
      def search_nodes(self, policy_id, query):
          # Keyword search
  ```

- [ ] Create integration script
  - [ ] Ingest PageIndex output into TreeStore
  - [ ] Migrate existing PostgreSQL data
  - [ ] Validate data integrity

- [ ] Update reasoning-service
  - [ ] Replace PostgreSQL calls with TreeStore
  - [ ] Update retrieval service
  - [ ] Maintain backward compatibility

**Deliverables:**
- Python client library
- Integration with reasoning-service
- Migration scripts
- End-to-end tests

---

## Phase 5: Production Polish (Weeks 12-13)

### Week 12: Observability & Performance

**Goal:** Production-ready monitoring and optimization

#### Tasks:
- [ ] Add Prometheus metrics
  - [ ] Query latency histograms
  - [ ] Cache hit rates
  - [ ] Transaction durations
  - [ ] Index sizes
  - [ ] WAL size and rotation

- [ ] Implement structured logging
  - [ ] Request/response logging
  - [ ] Error tracking
  - [ ] Slow query logging

- [ ] Add profiling support
  - [ ] CPU profiling endpoint
  - [ ] Memory profiling
  - [ ] Goroutine profiling

- [ ] Performance benchmarking
  - [ ] Compare vs PostgreSQL
  - [ ] Measure key operations
  - [ ] Load testing
  - [ ] Generate performance report

- [ ] Query optimization
  - [ ] Index selection
  - [ ] Cache tuning
  - [ ] Query plan analysis

**Deliverables:**
- Complete observability stack
- Performance benchmarks
- Optimization report

---

### Week 13: Documentation & Deployment

**Goal:** Complete documentation and production deployment

#### Tasks:
- [ ] Write comprehensive documentation
  - [ ] Architecture diagrams
  - [ ] API reference
  - [ ] Client usage examples
  - [ ] Deployment guide
  - [ ] Troubleshooting guide

- [ ] Create deployment artifacts
  - [ ] Docker image
  - [ ] Kubernetes manifests
  - [ ] Helm chart (optional)
  - [ ] Systemd service file

- [ ] Add operational tools
  - [ ] Backup/restore scripts
  - [ ] Data migration tools
  - [ ] Health check scripts
  - [ ] Debug utilities

- [ ] Production deployment
  - [ ] Deploy alongside reasoning-service
  - [ ] Configure monitoring
  - [ ] Set up alerting
  - [ ] Validate in production

- [ ] Create portfolio materials
  - [ ] Blog post writeup
  - [ ] Demo video
  - [ ] GitHub README polish
  - [ ] Performance comparison graphs

**Deliverables:**
- Complete documentation
- Production deployment
- Portfolio presentation materials

---

## Success Metrics

### Technical Milestones
- [ ] All unit tests passing (>80% coverage)
- [ ] All integration tests passing
- [ ] Sub-10ms query latency for node lookups
- [ ] 3x+ performance improvement vs PostgreSQL for tree queries
- [ ] Zero data loss in crash recovery tests
- [ ] Support 50K+ document nodes

### Learning Objectives
- [ ] Deep understanding of B+Tree internals
- [ ] Experience with WAL and crash recovery
- [ ] Transaction and concurrency control knowledge
- [ ] gRPC and cross-language integration
- [ ] Production database deployment

### Portfolio Impact
- [ ] Complete GitHub repository with documentation
- [ ] Blog post explaining technical decisions
- [ ] Performance benchmarks with graphs
- [ ] Demo video showing functionality
- [ ] Production deployment proof

---

## Risk Management

### Potential Challenges

1. **B+Tree Complexity**
   - *Risk:* Implementation bugs causing data corruption
   - *Mitigation:* Extensive unit tests, fuzzy testing, reference implementations

2. **Performance Bottlenecks**
   - *Risk:* Slower than PostgreSQL
   - *Mitigation:* Profiling early, benchmark-driven optimization

3. **Concurrent Access**
   - *Risk:* Deadlocks or race conditions
   - *Mitigation:* Race detector, stress tests, simple locking strategy initially

4. **Data Migration**
   - *Risk:* Bugs during PostgreSQL → TreeStore migration
   - *Mitigation:* Dual-write period, data validation scripts

### Contingency Plans

- **If behind schedule:** Skip optional features (hybrid vector search, advanced query optimization)
- **If stuck on B+Tree:** Use bbolt as temporary backend, focus on document layer
- **If performance issues:** Profile and optimize critical path, defer advanced features

---

## Next Steps

1. Review this plan with any mentors/advisors
2. Set up development environment
3. Begin Week 1 tasks
4. Track progress in daily commits
5. Update this document as you learn

---

## Resources

### Books
- [Build Your Own Database From Scratch in Go](https://build-your-own.org/database/)
- Database Internals by Alex Petrov
- Designing Data-Intensive Applications by Martin Kleppmann

### Reference Implementations
- [go-memdb](https://github.com/hashicorp/go-memdb) - Transaction patterns, API design
- [BadgerDB](https://github.com/dgraph-io/badger) - LSM/WAL patterns, benchmarks
- [CloverDB](https://github.com/ostafen/clover) - Document abstraction

### Tools
- Go profiler (pprof)
- Prometheus + Grafana
- k6 for load testing
- Docker for deployment

Good luck building! 🚀

