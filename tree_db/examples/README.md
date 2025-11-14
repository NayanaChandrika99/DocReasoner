# TreeStore Examples

This directory contains example code demonstrating how to use TreeStore.

## Running the Examples

### Basic Usage
```bash
cd examples
go run basic_usage.go
```

This example demonstrates:
- Document storage and retrieval
- Hierarchical queries (GetChildren, GetSubtree)
- Full-text search
- Version management
- Temporal queries (GetVersionAsOf)
- Metadata queries and filtering

### Advanced Usage
```bash
cd examples
go run advanced_usage.go
```

This example demonstrates:
- Unified query engine with QueryBuilder
- Enriched results (document + metadata + version)
- Conversation tracking and management
- Related entity discovery via metadata
- Multi-attribute queries
- Batch operations

## Example Scenarios

### Scenario 1: Policy Document Management

Store hierarchical policy documents with versioning:

```go
kv := &storage.KV{Path: "policies.db"}
kv.Open()

docStore := document.NewSimpleStore(kv)
verStore := version.NewVersionStore(kv)

// Store document with nodes
doc := &document.Document{
    PolicyID: "company-handbook",
    VersionID: "v2.0.0",
    RootNodeID: "root",
}

nodes := []*document.Node{
    {NodeID: "root", Title: "Company Handbook", ...},
    {NodeID: "conduct", ParentID: &rootID, Title: "Code of Conduct", ...},
    {NodeID: "privacy", ParentID: &rootID, Title: "Privacy Policy", ...},
}

docStore.StoreDocument(doc, nodes)

// Create version
verStore.CreateVersion(&version.Version{
    PolicyID: "company-handbook",
    VersionID: "v2.0.0",
    CreatedAt: time.Now(),
    Tags: []string{"latest", "published"},
})
```

### Scenario 2: Conversation Tracking

Track user conversations with metadata:

```go
promptStore := prompt.NewPromptStore(kv)
metaStore := metadata.NewMetadataStore(kv)

// Create conversation
conv := &prompt.Conversation{
    ConversationID: "conv-123",
    UserID: "user-456",
    Title: "Support Request",
    Tags: []string{"support", "billing"},
}
promptStore.CreateConversation(conv)

// Add messages
promptStore.AddMessage(&prompt.Message{
    MessageID: "msg-1",
    ConversationID: "conv-123",
    Role: "user",
    Content: "I have a question about my bill",
})

// Tag with metadata
metaStore.SetMetadata(&metadata.MetadataEntry{
    EntityType: "conversation",
    EntityID: "conv-123",
    Key: "priority",
    Value: "high",
})
```

### Scenario 3: Document Search with Metadata Filtering

Search documents with metadata constraints:

```go
engine := query.NewEngine(kv)

// Search for content
results := docStore.Search("policy-id", "privacy data protection", 10)

// Filter by metadata
legalDocs := metaStore.QueryByKeyValue("department", "Legal", nil, 0)

// Multi-attribute query
publishedDocs := metaStore.QueryMultiple(map[string]string{
    "status": "published",
    "department": "Legal",
    "year": "2024",
}, &docType, 100)
```

### Scenario 4: Temporal Queries

Access historical versions:

```go
verStore := version.NewVersionStore(kv)

// Get current version
latest := verStore.GetLatestVersion("policy-id")

// Time travel: Get version from 30 days ago
pastTime := time.Now().Add(-30 * 24 * time.Hour)
oldVersion := verStore.GetVersionAsOf("policy-id", pastTime)

// Get version by tag
stable := verStore.GetVersionByTag("policy-id", "stable")
```

### Scenario 5: Enriched Results

Combine data from multiple stores:

```go
engine := query.NewEngine(kv)

// Get document with all associated data
enriched := engine.GetEnrichedDocument("policy-id", "node-id", &versionID)

// Access combined data
fmt.Println(enriched.Node.Title)
fmt.Println(enriched.Metadata["author"])
fmt.Println(enriched.Version.Description)

// Get conversation with messages and metadata
convEnriched := engine.GetEnrichedConversation("conv-id")
```

## Best Practices

1. **Use Transactions for Batch Operations**
   ```go
   tx := kv.Begin()
   for _, item := range items {
       // Add to transaction
   }
   tx.Commit() // Single commit
   ```

2. **Leverage Indexes**
   - All stores have optimized indexes
   - Query by indexed fields for best performance
   - Document: (policyID, nodeID), (policyID, parentID)
   - Version: (policyID, createdAt), (policyID, tag)
   - Metadata: (key, value), (entityType, entityID)

3. **Use the Query Engine**
   - Unified interface across all stores
   - Type-safe query builder
   - Automatic result enrichment

4. **Cache Frequently Accessed Data**
   - Implement application-level caching for hot data
   - Use batch retrieval for multiple entities

5. **Set Appropriate Limits**
   - Always specify limits for queries
   - Use pagination for large result sets

## Common Patterns

### Pattern 1: Document with Metadata
```go
// Store document
docStore.StoreDocument(doc, nodes)

// Add metadata
metaStore.SetMetadata(&metadata.MetadataEntry{
    EntityType: "document",
    EntityID: doc.PolicyID,
    Key: "status",
    Value: "published",
})
```

### Pattern 2: Versioned Documents
```go
// Store document
docStore.StoreDocument(doc, nodes)

// Create version
verStore.CreateVersion(&version.Version{
    PolicyID: doc.PolicyID,
    VersionID: "v1.0.0",
    DocumentID: doc.PolicyID,
    Tags: []string{"latest"},
})
```

### Pattern 3: Related Entity Discovery
```go
// Find all documents in same project
related := engine.FindRelated("document", docID, "project", 10)

// Find similar conversations
similarConvs := engine.FindRelated("conversation", convID, "topic", 10)
```

## Troubleshooting

**Issue**: Slow queries
- **Solution**: Check if you're querying by indexed fields
- **Solution**: Add appropriate limits to queries
- **Solution**: Use batch operations instead of loops

**Issue**: High memory usage
- **Solution**: Use pagination for large result sets
- **Solution**: Close database connections properly
- **Solution**: Implement result streaming for large queries

**Issue**: Version not found
- **Solution**: Verify version was created with correct PolicyID
- **Solution**: Check version tags are set correctly
- **Solution**: Use ListVersions to see all available versions

## More Information

- See `../PERFORMANCE.md` for performance guidelines
- See `../README.md` for architecture overview
- See test files (`*_test.go`) for additional examples
