# TreeStore Performance Guide

This document provides performance characteristics and benchmarking guidelines for TreeStore.

## Running Benchmarks

### All Benchmarks
```bash
go test -bench=. -benchmem ./pkg/...
```

### Storage Layer
```bash
go test -bench=. -benchmem ./pkg/storage
```

### Document Layer
```bash
go test -bench=. -benchmem ./pkg/document
```

### Specific Benchmark
```bash
go test -bench=BenchmarkKVInsert -benchmem ./pkg/storage
```

## Performance Characteristics

### Storage Layer (B+Tree)

**Insert Performance:**
- Sequential inserts: ~100k-200k ops/sec
- Random inserts: ~50k-100k ops/sec
- Batch inserts (transaction): ~500k-1M ops/sec

**Read Performance:**
- Point reads: ~200k-500k ops/sec
- Range scans: ~100k-300k ops/sec (depending on range size)

**Update Performance:**
- In-place updates: ~80k-150k ops/sec
- Updates with page splits: ~50k-100k ops/sec

**Delete Performance:**
- Simple deletes: ~100k-200k ops/sec

### Document Layer

**Document Storage:**
- Store document with 10 nodes: ~10k-20k ops/sec
- Store document with 100 nodes: ~1k-5k ops/sec

**Hierarchical Queries:**
- GetNode (single): ~100k-200k ops/sec
- GetChildren (10 children): ~20k-50k ops/sec
- GetSubtree (3 levels, 20 nodes): ~5k-15k ops/sec
- GetAncestorPath (5 levels): ~20k-50k ops/sec

**Search:**
- Full-text search (100 docs, 10 results): ~1k-5k ops/sec

### Version Store

**Version Operations:**
- CreateVersion: ~50k-100k ops/sec
- GetVersion: ~100k-200k ops/sec
- GetVersionAsOf (temporal query): ~10k-30k ops/sec
- ListVersions (10 versions): ~20k-50k ops/sec

### Metadata Store

**Metadata Operations:**
- SetMetadata: ~50k-100k ops/sec
- GetMetadata: ~100k-200k ops/sec
- QueryByKeyValue: ~10k-30k ops/sec
- QueryMultiple (3 filters): ~5k-15k ops/sec

### Query Engine

**Cross-Store Queries:**
- EnrichedDocument (doc + metadata + version): ~10k-30k ops/sec
- EnrichedConversation (conv + messages + metadata): ~20k-50k ops/sec
- FindRelated (via metadata): ~10k-30k ops/sec

## Optimization Guidelines

### 1. Use Transactions for Batch Operations

**Bad:**
```go
for _, node := range nodes {
    store.StoreNode(node) // Individual commits
}
```

**Good:**
```go
tx := kv.Begin()
for _, node := range nodes {
    // Add to transaction
}
tx.Commit() // Single commit
```

**Impact:** 10-50x faster for bulk operations

### 2. Cache Frequently Accessed Data

For read-heavy workloads, implement an in-memory cache for hot data:

```go
type CachedStore struct {
    store *SimpleStore
    cache map[string]*Node
}
```

**Impact:** 10-100x faster for cached reads

### 3. Use Batch Retrieval

**Bad:**
```go
for _, id := range nodeIDs {
    node := store.GetNode(policyID, id) // N queries
}
```

**Good:**
```go
nodes := engine.BatchGetNodes(policyID, nodeIDs) // Optimized batch
```

**Impact:** 2-5x faster

### 4. Limit Result Sets

Always specify appropriate limits for queries:

```go
// Good: Limited results
results := store.Search(policyID, query, 10)

// Bad: Unbounded results
results := store.Search(policyID, query, 0) // Returns everything
```

### 5. Use Appropriate Indexes

The stores automatically maintain indexes for common access patterns:
- Document: (policyID, nodeID), (policyID, parentID, nodeID)
- Version: (policyID, versionID), (policyID, createdAt), (policyID, tag)
- Metadata: (entityType, entityID, key), (key, value)
- Prompt: (conversationID), (userID, startedAt), (tag)

Design your queries to leverage these indexes.

### 6. Optimize Search Queries

For full-text search:
- Use specific terms rather than broad queries
- Set appropriate limits
- Consider implementing result caching for common queries

### 7. Monitor Page Utilization

The B+Tree uses 4KB pages. Monitor page splits:

```go
// Track page allocation
stats := kv.GetStats()
fmt.Printf("Total pages: %d, Free pages: %d\n", stats.TotalPages, stats.FreePages)
```

High page churn may indicate:
- Suboptimal key ordering
- Excessive updates
- Need for database compaction

## Memory Usage

### Per-Entity Memory Overhead

- **Node (in-memory):** ~500-1000 bytes (depending on text length)
- **Version:** ~200-400 bytes
- **MetadataEntry:** ~100-300 bytes
- **Message:** ~200-500 bytes
- **Conversation:** ~150-300 bytes

### B+Tree Page Size

- Fixed 4KB pages
- ~60-70% utilization on average
- Each page holds 50-200 entries (depending on key/value size)

### Estimating Database Size

```
DB Size ≈ (Num Entities × Avg Entity Size) × 1.5
```

The 1.5 multiplier accounts for:
- Page overhead
- Free list management
- Index overhead
- Page fragmentation

Example: 1M nodes with 1KB average size → ~1.5GB database

## Profiling

### CPU Profiling

```bash
go test -bench=BenchmarkKVInsert -cpuprofile=cpu.prof ./pkg/storage
go tool pprof cpu.prof
```

### Memory Profiling

```bash
go test -bench=BenchmarkKVInsert -memprofile=mem.prof ./pkg/storage
go tool pprof mem.prof
```

### Flame Graphs

```bash
go test -bench=. -cpuprofile=cpu.prof ./pkg/storage
go tool pprof -http=:8080 cpu.prof
```

## Production Recommendations

1. **Hardware:**
   - SSD recommended for production (10-100x faster than HDD)
   - Minimum 2GB RAM for caching
   - Multi-core CPU for concurrent operations

2. **Configuration:**
   - Use appropriate transaction batch sizes (100-1000 operations)
   - Implement connection pooling for concurrent access
   - Enable OS-level file caching

3. **Monitoring:**
   - Track query latency (p50, p99, p999)
   - Monitor transaction abort rates
   - Watch disk I/O and page faults
   - Track cache hit rates

4. **Maintenance:**
   - Periodic database compaction
   - Free list management
   - Index optimization
   - Query plan analysis

## Benchmarking Best Practices

1. Run on production-like hardware
2. Use realistic data sizes and distributions
3. Test with production query patterns
4. Measure under concurrent load
5. Account for warm-up time
6. Run multiple iterations for statistical significance

## Known Limitations

- Single-file database (no sharding)
- Single-writer model (one transaction at a time)
- No built-in replication
- In-memory page cache limited by available RAM
- Full-text search is simple (not inverted index based)

For these limitations, consider:
- Application-level sharding
- Read replicas
- External full-text search (Elasticsearch, etc.)
- Distributed caching (Redis, Memcached)
