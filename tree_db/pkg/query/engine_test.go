// ABOUTME: Tests for unified query engine
// ABOUTME: Verifies cross-store queries and enriched results

package query

import (
	"os"
	"testing"
	"time"

	"github.com/nainya/treestore/pkg/document"
	"github.com/nainya/treestore/pkg/metadata"
	"github.com/nainya/treestore/pkg/prompt"
	"github.com/nainya/treestore/pkg/storage"
	"github.com/nainya/treestore/pkg/version"
)

func setupTestEngine(t *testing.T) (*Engine, *storage.KV, string) {
	path := "/tmp/test_queryengine_" + t.Name() + ".db"
	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}

	engine := NewEngine(kv)
	return engine, kv, path
}

func TestQueryBuilder(t *testing.T) {
	qb := NewQueryBuilder(QueryDocument)
	q := qb.
		Where("policyID", "policy1").
		Where("nodeID", "node1").
		Limit(10).
		Offset(0).
		OrderBy("createdAt", true).
		Build()

	if q.Type != QueryDocument {
		t.Errorf("Expected QueryDocument, got %d", q.Type)
	}

	if q.Filters["policyID"] != "policy1" {
		t.Error("policyID filter not set correctly")
	}

	if q.Limit != 10 {
		t.Errorf("Expected limit 10, got %d", q.Limit)
	}
}

func TestExecuteDocumentQuery(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create test document
	doc := &document.Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "node1",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*document.Node{
		{
			NodeID:    "node1",
			PolicyID:  "policy1",
			Title:     "Test Node",
			PageStart: 1,
			PageEnd:   5,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	engine.docStore.StoreDocument(doc, nodes)

	// Query for the document
	q := NewQueryBuilder(QueryDocument).
		Where("policyID", "policy1").
		Where("nodeID", "node1").
		Build()

	result, err := engine.Execute(q)
	if err != nil {
		t.Fatalf("Failed to execute query: %v", err)
	}

	if len(result.Documents) != 1 {
		t.Errorf("Expected 1 document, got %d", len(result.Documents))
	}

	if result.Documents[0].NodeID != "node1" {
		t.Errorf("Expected node1, got %s", result.Documents[0].NodeID)
	}
}

func TestGetEnrichedDocument(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create document
	doc := &document.Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "node1",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*document.Node{
		{
			NodeID:    "node1",
			PolicyID:  "policy1",
			Title:     "Test Node",
			PageStart: 1,
			PageEnd:   5,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	engine.docStore.StoreDocument(doc, nodes)

	// Add metadata
	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "node",
		EntityID:   "node1",
		Key:        "author",
		Value:      "John Doe",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	// Create version
	engine.verStore.CreateVersion(&version.Version{
		PolicyID:   "policy1",
		VersionID:  "v1",
		DocumentID: "doc1",
		CreatedAt:  now,
		CreatedBy:  "user1",
	})

	// Get enriched document
	versionID := "v1"
	enriched, err := engine.GetEnrichedDocument("policy1", "node1", &versionID)
	if err != nil {
		t.Fatalf("Failed to get enriched document: %v", err)
	}

	if enriched.Node.NodeID != "node1" {
		t.Errorf("Expected node1, got %s", enriched.Node.NodeID)
	}

	if enriched.Metadata["author"] != "John Doe" {
		t.Errorf("Expected author=John Doe, got %s", enriched.Metadata["author"])
	}

	if enriched.Version == nil {
		t.Error("Expected version to be populated")
	}

	if enriched.Version != nil && enriched.Version.VersionID != "v1" {
		t.Errorf("Expected v1, got %s", enriched.Version.VersionID)
	}
}

func TestGetEnrichedConversation(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversation
	conv := &prompt.Conversation{
		ConversationID: "conv1",
		UserID:         "user1",
		Title:          "Test Conversation",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
	}

	engine.promptStore.CreateConversation(conv)

	// Add messages
	engine.promptStore.AddMessage(&prompt.Message{
		MessageID:      "msg1",
		ConversationID: "conv1",
		Role:           "user",
		Content:        "Hello",
		Timestamp:      now,
	})

	// Add metadata
	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "conversation",
		EntityID:   "conv1",
		Key:        "category",
		Value:      "support",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	// Get enriched conversation
	enriched, err := engine.GetEnrichedConversation("conv1")
	if err != nil {
		t.Fatalf("Failed to get enriched conversation: %v", err)
	}

	if enriched.Conversation.ConversationID != "conv1" {
		t.Errorf("Expected conv1, got %s", enriched.Conversation.ConversationID)
	}

	if len(enriched.Messages) != 1 {
		t.Errorf("Expected 1 message, got %d", len(enriched.Messages))
	}

	if enriched.Metadata["category"] != "support" {
		t.Errorf("Expected category=support, got %s", enriched.Metadata["category"])
	}
}

func TestExecuteVersionQuery(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create versions
	engine.verStore.CreateVersion(&version.Version{
		PolicyID:   "policy1",
		VersionID:  "v1.0.0",
		DocumentID: "doc1",
		CreatedAt:  now,
		CreatedBy:  "user1",
		Tags:       []string{"latest"},
	})

	// Query by tag
	q := NewQueryBuilder(QueryVersion).
		Where("policyID", "policy1").
		Where("tag", "latest").
		Build()

	result, err := engine.Execute(q)
	if err != nil {
		t.Fatalf("Failed to execute version query: %v", err)
	}

	if len(result.Versions) != 1 {
		t.Errorf("Expected 1 version, got %d", len(result.Versions))
	}

	if result.Versions[0].VersionID != "v1.0.0" {
		t.Errorf("Expected v1.0.0, got %s", result.Versions[0].VersionID)
	}
}

func TestExecuteMetadataQuery(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Add metadata entries
	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "document",
		EntityID:   "doc1",
		Key:        "category",
		Value:      "policy",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "document",
		EntityID:   "doc2",
		Key:        "category",
		Value:      "policy",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	// Query by key-value
	q := NewQueryBuilder(QueryMetadata).
		Where("key", "category").
		Where("value", "policy").
		Build()

	result, err := engine.Execute(q)
	if err != nil {
		t.Fatalf("Failed to execute metadata query: %v", err)
	}

	if len(result.Metadata) != 2 {
		t.Errorf("Expected 2 metadata entries, got %d", len(result.Metadata))
	}
}

func TestExecutePromptQuery(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create conversations
	engine.promptStore.CreateConversation(&prompt.Conversation{
		ConversationID: "conv1",
		UserID:         "user1",
		Title:          "Conv 1",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
	})

	engine.promptStore.CreateConversation(&prompt.Conversation{
		ConversationID: "conv2",
		UserID:         "user1",
		Title:          "Conv 2",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
	})

	// Query by user
	q := NewQueryBuilder(QueryPrompt).
		Where("userID", "user1").
		Build()

	result, err := engine.Execute(q)
	if err != nil {
		t.Fatalf("Failed to execute prompt query: %v", err)
	}

	if len(result.Conversations) != 2 {
		t.Errorf("Expected 2 conversations, got %d", len(result.Conversations))
	}
}

func TestFindRelated(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create entities with same project tag
	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "document",
		EntityID:   "doc1",
		Key:        "project",
		Value:      "alpha",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "document",
		EntityID:   "doc2",
		Key:        "project",
		Value:      "alpha",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "document",
		EntityID:   "doc3",
		Key:        "project",
		Value:      "alpha",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	// Find related documents
	related, err := engine.FindRelated("document", "doc1", "project", 10)
	if err != nil {
		t.Fatalf("Failed to find related: %v", err)
	}

	if len(related) != 2 { // Should exclude doc1 itself
		t.Errorf("Expected 2 related documents, got %d", len(related))
	}
}

func TestBatchGetNodes(t *testing.T) {
	engine, kv, path := setupTestEngine(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create multiple nodes
	doc := &document.Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "node1",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*document.Node{
		{
			NodeID:    "node1",
			PolicyID:  "policy1",
			Title:     "Node 1",
			PageStart: 1,
			PageEnd:   5,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeID:    "node2",
			PolicyID:  "policy1",
			Title:     "Node 2",
			PageStart: 6,
			PageEnd:   10,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeID:    "node3",
			PolicyID:  "policy1",
			Title:     "Node 3",
			PageStart: 11,
			PageEnd:   15,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	engine.docStore.StoreDocument(doc, nodes)

	// Batch get
	retrieved, err := engine.BatchGetNodes("policy1", []string{"node1", "node2", "node3"})
	if err != nil {
		t.Fatalf("Failed to batch get: %v", err)
	}

	if len(retrieved) != 3 {
		t.Errorf("Expected 3 nodes, got %d", len(retrieved))
	}
}
