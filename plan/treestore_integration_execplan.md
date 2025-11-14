# TreeStore Integration ExecPlan

**Status:** Ready for Integration  
**Timeline:** 2-3 weeks  
**Goal:** Replace PostgreSQL with TreeStore for PageIndex document storage and extend for ReAct controller tool support

---

## Current State

### ✅ TreeStore Implementation Complete
- **Core Storage Engine**: Disk-backed B+Tree with copy-on-write, free-list, transactions (`pkg/storage/`)
- **Specialized Stores**: Document, Version, Metadata, Prompt stores (`pkg/document/`, `pkg/version/`, etc.)
- **Query Engine**: Unified query interface across stores (`pkg/query/`)
- **All Core Tests Passing**: `go test ./pkg/...` green

### ❌ Missing for Integration
1. **gRPC Server**: No `cmd/treestore/main.go` or `proto/treestore.proto`
2. **Python Client**: Empty `client/python/treestore/`
3. **WAL/Recovery**: `pkg/wal/` empty (crash recovery not implemented)
4. **Observability**: No Prometheus metrics, structured logging

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Python Reasoning Service                               │
│  ├─ FastAPI (/reason/auth-review)                       │
│  ├─ ReActController (LLM-driven)                        │
│  │  └─ Tools: pi_search, facts_get, policy_xref,       │
│  │            temporal_lookup, etc.                     │
│  └─ TreeStoreClient (Python gRPC client)                │
└────────────────────┬────────────────────────────────────┘
                     │ gRPC (localhost:50051)
                     ▼
┌─────────────────────────────────────────────────────────┐
│  TreeStore Service (Go)                                 │
│  ├─ gRPC Server (:50051)                                │
│  ├─ Query Engine (unified interface)                   │
│  ├─ DocumentStore (PageIndex trees)                    │
│  ├─ VersionStore (temporal_lookup support)             │
│  ├─ MetadataStore (policy_xref, trajectories)          │
│  └─ PromptStore (GEPA optimization history)            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
              [Disk: /var/lib/treestore/]
```

---

## Milestone A: gRPC API Layer (Week 1)

**Goal:** Expose TreeStore via gRPC for Python integration

### Tasks

#### A.1: Define Protocol Buffers Schema
**File:** `tree_db/proto/treestore.proto`

```protobuf
syntax = "proto3";
package treestore;

service TreeStoreService {
  // Document Operations (PageIndex storage)
  rpc StoreDocument(StoreDocumentRequest) returns (StoreDocumentResponse);
  rpc GetNode(GetNodeRequest) returns (GetNodeResponse);
  rpc GetChildren(GetChildrenRequest) returns (GetChildrenResponse);
  rpc GetSubtree(GetSubtreeRequest) returns (GetSubtreeResponse);
  rpc SearchNodes(SearchNodesRequest) returns (SearchNodesResponse);
  
  // Version Operations (temporal_lookup tool)
  rpc GetVersion(GetVersionRequest) returns (GetVersionResponse);
  rpc GetVersionAsOf(GetVersionAsOfRequest) returns (GetVersionResponse);
  rpc ListVersions(ListVersionsRequest) returns (ListVersionsResponse);
  
  // Metadata Operations (policy_xref tool)
  rpc GetMetadata(GetMetadataRequest) returns (GetMetadataResponse);
  rpc SetMetadata(SetMetadataRequest) returns (SetMetadataResponse);
  rpc GetCrossReferences(GetCrossReferencesRequest) returns (GetCrossReferencesResponse);
  
  // Tool Result Storage (ReAct controller)
  rpc StoreToolResult(StoreToolResultRequest) returns (StoreToolResultResponse);
  rpc GetToolResults(GetToolResultsRequest) returns (GetToolResultsResponse);
  
  // Trajectory Storage (pi_search paths)
  rpc StoreTrajectory(StoreTrajectoryRequest) returns (StoreTrajectoryResponse);
  rpc GetTrajectories(GetTrajectoriesRequest) returns (GetTrajectoriesResponse);
  
  // Health & Stats
  rpc Health(HealthRequest) returns (HealthResponse);
  rpc Stats(StatsRequest) returns (StatsResponse);
}

message Node {
  string node_id = 1;
  string parent_id = 2;
  string title = 3;
  int32 page_start = 4;
  int32 page_end = 5;
  string summary = 6;
  string text = 7;
  string section_path = 8;
  repeated string child_ids = 9;
}

message StoreDocumentRequest {
  string policy_id = 1;
  string version_id = 2;
  string pageindex_doc_id = 3;
  repeated Node nodes = 4;
  map<string, string> metadata = 5;
}

message GetVersionAsOfRequest {
  string policy_id = 1;
  string as_of_date = 2; // ISO 8601 format
}

message GetCrossReferencesRequest {
  string policy_id = 1;
  string node_id = 2;
  int32 max_depth = 3;
}

// ... (complete message definitions)
```

**Deliverable:**
- [ ] Complete `.proto` file with all message types
- [ ] Generate Go stubs: `protoc --go_out=. --go-grpc_out=. proto/treestore.proto`

---

#### A.2: Implement gRPC Server
**File:** `tree_db/cmd/treestore/main.go`

```go
package main

import (
    "flag"
    "fmt"
    "log"
    "net"
    
    "google.golang.org/grpc"
    "github.com/nainya/treestore/pkg/storage"
    "github.com/nainya/treestore/pkg/query"
    pb "github.com/nainya/treestore/proto"
)

type server struct {
    pb.UnimplementedTreeStoreServiceServer
    engine *query.Engine
}

func (s *server) StoreDocument(ctx context.Context, req *pb.StoreDocumentRequest) (*pb.StoreDocumentResponse, error) {
    // Convert proto nodes to internal format
    // Call engine.docStore.StoreDocument()
    // Return response
}

func (s *server) GetVersionAsOf(ctx context.Context, req *pb.GetVersionAsOfRequest) (*pb.GetVersionResponse, error) {
    // Parse as_of_date
    // Call engine.verStore.GetVersionAsOf()
    // Return version
}

// ... implement all service methods

func main() {
    port := flag.Int("port", 50051, "gRPC server port")
    dbPath := flag.String("db", "/var/lib/treestore/data.db", "Database path")
    flag.Parse()
    
    // Initialize KV store
    kv := &storage.KV{Path: *dbPath}
    if err := kv.Open(); err != nil {
        log.Fatalf("Failed to open database: %v", err)
    }
    defer kv.Close()
    
    // Create query engine
    engine := query.NewEngine(kv)
    
    // Start gRPC server
    lis, err := net.Listen("tcp", fmt.Sprintf(":%d", *port))
    if err != nil {
        log.Fatalf("Failed to listen: %v", err)
    }
    
    grpcServer := grpc.NewServer()
    pb.RegisterTreeStoreServiceServer(grpcServer, &server{engine: engine})
    
    log.Printf("TreeStore gRPC server listening on :%d", *port)
    if err := grpcServer.Serve(lis); err != nil {
        log.Fatalf("Failed to serve: %v", err)
    }
}
```

**Deliverable:**
- [ ] Complete gRPC server implementation
- [ ] All service methods mapped to query engine
- [ ] Error handling and logging
- [ ] Build: `go build -o bin/treestore cmd/treestore/main.go`

---

#### A.3: Add Observability
**File:** `tree_db/pkg/observability/metrics.go`

```go
package observability

import "github.com/prometheus/client_golang/prometheus"

var (
    RequestDuration = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "treestore_request_duration_seconds",
            Help: "Request duration in seconds",
        },
        []string{"method"},
    )
    
    RequestTotal = prometheus.NewCounterVec(
        prometheus.CounterOpts{
            Name: "treestore_requests_total",
            Help: "Total requests",
        },
        []string{"method", "status"},
    )
    
    CacheHitRate = prometheus.NewGauge(
        prometheus.GaugeOpts{
            Name: "treestore_cache_hit_rate",
            Help: "Cache hit rate",
        },
    )
)

func init() {
    prometheus.MustRegister(RequestDuration, RequestTotal, CacheHitRate)
}
```

**Deliverable:**
- [ ] Prometheus metrics for all operations
- [ ] Structured logging (JSON format)
- [ ] Metrics endpoint: `/metrics`

---

## Milestone B: Python Client Library (Week 1)

**Goal:** Create Python gRPC client for reasoning-service integration

### Tasks

#### B.1: Generate Python Stubs
```bash
cd tree_db
python -m grpc_tools.protoc \
    -I proto \
    --python_out=client/python/treestore \
    --grpc_python_out=client/python/treestore \
    proto/treestore.proto
```

**Deliverable:**
- [ ] `treestore_pb2.py` (message classes)
- [ ] `treestore_pb2_grpc.py` (service stubs)

---

#### B.2: Build Python Client Wrapper
**File:** `tree_db/client/python/treestore/client.py`

```python
"""TreeStore Python client for reasoning-service integration."""

import grpc
from typing import Optional, List, Dict, Any
from datetime import datetime

from . import treestore_pb2 as pb
from . import treestore_pb2_grpc as pb_grpc


class TreeStoreClient:
    """Python client for TreeStore gRPC service."""
    
    def __init__(self, host: str = "localhost", port: int = 50051):
        """Initialize TreeStore client.
        
        Args:
            host: TreeStore server host
            port: TreeStore server port
        """
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = pb_grpc.TreeStoreServiceStub(self.channel)
    
    def store_document(
        self,
        policy_id: str,
        version_id: str,
        pageindex_doc_id: str,
        nodes: List[Dict[str, Any]],
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Store PageIndex document tree.
        
        Args:
            policy_id: Policy identifier (e.g., "LCD-L34220")
            version_id: Version identifier (e.g., "2024-Q1")
            pageindex_doc_id: PageIndex document ID
            nodes: List of node dictionaries from PageIndex
            metadata: Optional metadata
            
        Returns:
            Document ID
        """
        proto_nodes = [
            pb.Node(
                node_id=n["node_id"],
                parent_id=n.get("parent_id", ""),
                title=n.get("title", ""),
                page_start=n.get("page_start", 0),
                page_end=n.get("page_end", 0),
                summary=n.get("summary", ""),
                text=n.get("text", ""),
                section_path=n.get("section_path", ""),
                child_ids=n.get("child_ids", []),
            )
            for n in nodes
        ]
        
        request = pb.StoreDocumentRequest(
            policy_id=policy_id,
            version_id=version_id,
            pageindex_doc_id=pageindex_doc_id,
            nodes=proto_nodes,
            metadata=metadata or {},
        )
        
        response = self.stub.StoreDocument(request)
        return response.document_id
    
    def get_node(self, policy_id: str, node_id: str) -> Dict[str, Any]:
        """Retrieve single node."""
        request = pb.GetNodeRequest(policy_id=policy_id, node_id=node_id)
        response = self.stub.GetNode(request)
        return self._node_to_dict(response.node)
    
    def get_version_as_of(
        self, policy_id: str, as_of_date: datetime
    ) -> Dict[str, Any]:
        """Get policy version as of specific date (temporal_lookup tool)."""
        request = pb.GetVersionAsOfRequest(
            policy_id=policy_id,
            as_of_date=as_of_date.isoformat(),
        )
        response = self.stub.GetVersionAsOf(request)
        return {
            "version_id": response.version_id,
            "effective_date": response.effective_date,
            "pageindex_doc_id": response.pageindex_doc_id,
        }
    
    def get_cross_references(
        self, policy_id: str, node_id: str, max_depth: int = 2
    ) -> List[Dict[str, Any]]:
        """Get cross-referenced nodes (policy_xref tool)."""
        request = pb.GetCrossReferencesRequest(
            policy_id=policy_id,
            node_id=node_id,
            max_depth=max_depth,
        )
        response = self.stub.GetCrossReferences(request)
        return [
            {
                "node_id": ref.node_id,
                "title": ref.title,
                "relation_type": ref.relation_type,
                "section_path": ref.section_path,
            }
            for ref in response.references
        ]
    
    def store_tool_result(
        self,
        case_id: str,
        tool_name: str,
        result: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Store ReAct controller tool execution result."""
        request = pb.StoreToolResultRequest(
            case_id=case_id,
            tool_name=tool_name,
            result_json=json.dumps(result),
            timestamp=timestamp.isoformat() if timestamp else datetime.utcnow().isoformat(),
        )
        self.stub.StoreToolResult(request)
    
    def close(self):
        """Close gRPC channel."""
        self.channel.close()
    
    @staticmethod
    def _node_to_dict(node: pb.Node) -> Dict[str, Any]:
        """Convert proto Node to dict."""
        return {
            "node_id": node.node_id,
            "parent_id": node.parent_id,
            "title": node.title,
            "page_start": node.page_start,
            "page_end": node.page_end,
            "summary": node.summary,
            "text": node.text,
            "section_path": node.section_path,
            "child_ids": list(node.child_ids),
        }
```

**Deliverable:**
- [ ] Complete Python client with all methods
- [ ] Type hints and docstrings
- [ ] Connection pooling and retry logic
- [ ] Unit tests: `tree_db/client/python/tests/test_client.py`

---

## Milestone C: Reasoning-Service Integration (Week 2)

**Goal:** Replace PostgreSQL with TreeStore in reasoning-service

### Tasks

#### C.1: Add TreeStore Client to Reasoning-Service
**File:** `src/reasoning_service/services/treestore_client.py`

```python
"""TreeStore client wrapper for reasoning-service."""

from typing import Optional, List, Dict, Any
from datetime import datetime

from treestore import TreeStoreClient as _TreeStoreClient
from reasoning_service.config import settings


class TreeStoreClient:
    """Singleton TreeStore client for reasoning-service."""
    
    _instance: Optional[_TreeStoreClient] = None
    
    @classmethod
    def get_client(cls) -> _TreeStoreClient:
        """Get or create TreeStore client singleton."""
        if cls._instance is None:
            cls._instance = _TreeStoreClient(
                host=settings.TREESTORE_HOST,
                port=settings.TREESTORE_PORT,
            )
        return cls._instance
    
    @classmethod
    def close(cls):
        """Close TreeStore client."""
        if cls._instance:
            cls._instance.close()
            cls._instance = None


# Convenience functions for tool handlers
def get_node(policy_id: str, node_id: str) -> Dict[str, Any]:
    """Get node from TreeStore."""
    return TreeStoreClient.get_client().get_node(policy_id, node_id)


def get_version_as_of(policy_id: str, as_of_date: datetime) -> Dict[str, Any]:
    """Get policy version as of date (temporal_lookup tool)."""
    return TreeStoreClient.get_client().get_version_as_of(policy_id, as_of_date)


def get_cross_references(policy_id: str, node_id: str) -> List[Dict[str, Any]]:
    """Get cross-references (policy_xref tool)."""
    return TreeStoreClient.get_client().get_cross_references(policy_id, node_id)
```

**Deliverable:**
- [ ] TreeStore client wrapper in reasoning-service
- [ ] Config: `TREESTORE_HOST`, `TREESTORE_PORT`
- [ ] Singleton pattern for connection pooling

---

#### C.2: Update Tool Handlers to Use TreeStore
**File:** `src/reasoning_service/services/tool_handlers.py`

```python
# Add TreeStore imports
from reasoning_service.services.treestore_client import (
    get_node,
    get_version_as_of,
    get_cross_references,
)

class ToolExecutor:
    # ... existing code ...
    
    async def _temporal_lookup(
        self, policy_id: str, as_of_date: str
    ) -> Dict[str, Any]:
        """Get policy version as of specific date via TreeStore."""
        try:
            date_obj = datetime.fromisoformat(as_of_date)
            version = get_version_as_of(policy_id, date_obj)
            
            return {
                "success": True,
                "version_id": version["version_id"],
                "effective_date": version["effective_date"],
                "pageindex_doc_id": version["pageindex_doc_id"],
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def _policy_xref(
        self, criterion_id: str
    ) -> Dict[str, Any]:
        """Get cross-referenced policy sections via TreeStore."""
        try:
            # Parse criterion_id to extract policy_id and node_id
            policy_id, node_id = self._parse_criterion_id(criterion_id)
            
            refs = get_cross_references(policy_id, node_id)
            
            return {
                "success": True,
                "related_nodes": [
                    {
                        "node_id": ref["node_id"],
                        "title": ref["title"],
                        "relation": ref["relation_type"],
                        "path": ref["section_path"],
                    }
                    for ref in refs
                ],
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
```

**Deliverable:**
- [ ] Update `temporal_lookup` handler to use TreeStore
- [ ] Update `policy_xref` handler to use TreeStore
- [ ] Update `pi_search` to optionally use TreeStore backend
- [ ] Add fallback to PageIndex if TreeStore unavailable

---

#### C.3: Migration Script
**File:** `scripts/migrate_postgres_to_treestore.py`

```python
"""Migrate policy documents from PostgreSQL to TreeStore."""

import asyncio
from sqlalchemy import select
from reasoning_service.models.policy import PolicyVersion, PolicyNode
from reasoning_service.services.treestore_client import TreeStoreClient
from reasoning_service.database import get_session


async def migrate_policy(policy_id: str, version_id: str):
    """Migrate single policy version to TreeStore."""
    async with get_session() as session:
        # Get policy version
        version = await session.execute(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy_id,
                PolicyVersion.version_id == version_id,
            )
        )
        version = version.scalar_one()
        
        # Get all nodes
        nodes = await session.execute(
            select(PolicyNode).where(
                PolicyNode.policy_id == policy_id,
                PolicyNode.version_id == version_id,
            )
        )
        nodes = nodes.scalars().all()
        
        # Convert to TreeStore format
        node_dicts = [
            {
                "node_id": n.node_id,
                "parent_id": n.parent_id,
                "title": n.title,
                "page_start": n.page_start,
                "page_end": n.page_end,
                "summary": n.summary,
                "text": n.text,
                "section_path": n.section_path,
            }
            for n in nodes
        ]
        
        # Store in TreeStore
        client = TreeStoreClient.get_client()
        doc_id = client.store_document(
            policy_id=policy_id,
            version_id=version_id,
            pageindex_doc_id=version.pageindex_doc_id,
            nodes=node_dicts,
        )
        
        print(f"Migrated {policy_id} v{version_id}: {len(nodes)} nodes → {doc_id}")


async def main():
    """Migrate all policies."""
    async with get_session() as session:
        versions = await session.execute(select(PolicyVersion))
        versions = versions.scalars().all()
        
        for version in versions:
            await migrate_policy(version.policy_id, version.version_id)
    
    print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(main())
```

**Deliverable:**
- [ ] Migration script tested on dev data
- [ ] Validation: compare PostgreSQL vs TreeStore results
- [ ] Rollback plan documented

---

## Milestone D: Deployment & Testing (Week 2-3)

### Tasks

#### D.1: Docker Deployment
**File:** `tree_db/deploy/docker/Dockerfile`

```dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o treestore cmd/treestore/main.go

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /app
COPY --from=builder /build/treestore .
EXPOSE 50051 9090
VOLUME ["/var/lib/treestore"]
CMD ["./treestore", "--port", "50051", "--db", "/var/lib/treestore/data.db"]
```

**File:** `docker-compose.yml` (add TreeStore service)

```yaml
services:
  treestore:
    build: ./tree_db
    ports:
      - "50051:50051"  # gRPC
      - "9090:9090"    # Metrics
    volumes:
      - treestore-data:/var/lib/treestore
    healthcheck:
      test: ["CMD", "grpc_health_probe", "-addr=:50051"]
      interval: 10s
      timeout: 5s
      retries: 3
  
  reasoning-service:
    # ... existing config ...
    environment:
      - TREESTORE_HOST=treestore
      - TREESTORE_PORT=50051
    depends_on:
      - treestore

volumes:
  treestore-data:
```

**Deliverable:**
- [ ] Dockerfile for TreeStore
- [ ] docker-compose integration
- [ ] Health checks configured

---

#### D.2: Integration Tests
**File:** `tests/integration/test_treestore_integration.py`

```python
"""Integration tests for TreeStore."""

import pytest
from reasoning_service.services.treestore_client import TreeStoreClient


@pytest.fixture
def treestore_client():
    """TreeStore client fixture."""
    client = TreeStoreClient.get_client()
    yield client
    # Cleanup test data


def test_store_and_retrieve_document(treestore_client):
    """Test storing and retrieving PageIndex document."""
    # Store test document
    doc_id = treestore_client.store_document(
        policy_id="TEST-001",
        version_id="2024-01",
        pageindex_doc_id="test_doc_123",
        nodes=[
            {
                "node_id": "root",
                "title": "Test Policy",
                "summary": "Test summary",
            }
        ],
    )
    
    # Retrieve node
    node = treestore_client.get_node("TEST-001", "root")
    assert node["title"] == "Test Policy"


def test_temporal_lookup(treestore_client):
    """Test temporal_lookup tool via TreeStore."""
    # Store multiple versions
    # Query as_of specific date
    # Verify correct version returned


def test_policy_xref(treestore_client):
    """Test policy_xref tool via TreeStore."""
    # Store nodes with cross-references
    # Query cross-references
    # Verify related nodes returned
```

**Deliverable:**
- [ ] Integration tests for all TreeStore operations
- [ ] End-to-end test: PageIndex → TreeStore → ReActController
- [ ] Performance benchmarks: TreeStore vs PostgreSQL

---

#### D.3: Documentation Updates
**Files to Update:**
- `README.md`: Add TreeStore setup instructions
- `docs/architecture.md`: Update data flow diagrams
- `docs/deployment.md`: Add TreeStore deployment guide
- `tree_db/README.md`: Add integration examples

**Deliverable:**
- [ ] Complete deployment documentation
- [ ] API reference for TreeStore client
- [ ] Troubleshooting guide

---

## Configuration

### Environment Variables (reasoning-service)
```bash
# TreeStore connection
TREESTORE_HOST=localhost
TREESTORE_PORT=50051
TREESTORE_TIMEOUT=30  # seconds

# Backend selection
RETRIEVAL_BACKEND=treestore  # or "pageindex" for fallback
ENABLE_TREESTORE_CACHE=true

# Migration
DUAL_WRITE_MODE=false  # Write to both PostgreSQL and TreeStore during migration
```

### TreeStore Server Config
```bash
# Server
TREESTORE_PORT=50051
TREESTORE_DB_PATH=/var/lib/treestore/data.db
TREESTORE_LOG_LEVEL=info

# Performance
TREESTORE_CACHE_SIZE_MB=512
TREESTORE_MAX_CONNECTIONS=100

# Observability
TREESTORE_METRICS_PORT=9090
TREESTORE_ENABLE_TRACING=true
```

---

## Success Criteria

### Performance
- [ ] Sub-10ms latency for single node retrieval
- [ ] Sub-50ms latency for subtree queries (depth=3)
- [ ] 3x faster than PostgreSQL for tree traversal
- [ ] Handle 50K+ nodes per policy document

### Reliability
- [ ] Zero data loss in crash scenarios (once WAL implemented)
- [ ] Graceful degradation if TreeStore unavailable
- [ ] All integration tests passing

### Integration
- [ ] All 10 ReAct controller tools working with TreeStore
- [ ] PageIndex ingestion pipeline functional
- [ ] Migration from PostgreSQL complete
- [ ] Monitoring dashboards operational

---

## Rollout Plan

### Phase 1: Development (Week 1)
- Implement gRPC server
- Build Python client
- Unit tests passing

### Phase 2: Integration (Week 2)
- Wire reasoning-service to TreeStore
- Run integration tests
- Performance benchmarks

### Phase 3: Migration (Week 2-3)
- Dual-write mode (PostgreSQL + TreeStore)
- Migrate historical data
- Validate data integrity
- Switch to TreeStore-only

### Phase 4: Production (Week 3)
- Deploy to staging
- Monitor metrics
- Deploy to production
- Deprecate PostgreSQL policy tables

---

## Risk Mitigation

### Risk: TreeStore Performance Issues
- **Mitigation**: Benchmark early; implement caching layer if needed
- **Fallback**: Keep PageIndex direct integration as backup

### Risk: Data Migration Bugs
- **Mitigation**: Dual-write mode; extensive validation scripts
- **Fallback**: Rollback to PostgreSQL

### Risk: gRPC Connection Failures
- **Mitigation**: Retry logic; circuit breaker pattern
- **Fallback**: Graceful degradation to cached data

---

## Next Steps

1. **Start with Milestone A**: Implement gRPC server and proto definitions
2. **Parallel work**: Build Python client while server is being developed
3. **Test early**: Integration tests from day 1
4. **Incremental rollout**: Use feature flags for gradual migration

**First task**: Create `tree_db/proto/treestore.proto` with complete service definition.

---

**Status:** Ready to begin  
**Estimated Completion:** 2-3 weeks  
**Dependencies:** TreeStore core implementation (✅ Complete)

