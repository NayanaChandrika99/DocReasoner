// ABOUTME: Tests for metadata storage and indexing
// ABOUTME: Verifies flexible queries and multi-attribute filtering

package metadata

import (
	"os"
	"testing"
	"time"

	"github.com/nainya/treestore/pkg/storage"
)

func setupTestMetadataStore(t *testing.T) (*MetadataStore, *storage.KV, string) {
	path := "/tmp/test_metadatastore_" + t.Name() + ".db"
	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}

	ms := NewMetadataStore(kv)
	return ms, kv, path
}

func TestSetAndGetMetadata(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	entry := &MetadataEntry{
		EntityType: "document",
		EntityID:   "doc1",
		Key:        "author",
		Value:      "John Doe",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	// Set metadata
	if err := ms.SetMetadata(entry); err != nil {
		t.Fatalf("Failed to set metadata: %v", err)
	}

	// Get metadata
	retrieved, err := ms.GetMetadata("document", "doc1", "author")
	if err != nil {
		t.Fatalf("Failed to get metadata: %v", err)
	}

	if retrieved.Value != "John Doe" {
		t.Errorf("Expected 'John Doe', got '%s'", retrieved.Value)
	}

	if retrieved.ValueType != "string" {
		t.Errorf("Expected 'string', got '%s'", retrieved.ValueType)
	}
}

func TestGetAllMetadata(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Set multiple metadata entries
	entries := []*MetadataEntry{
		{
			EntityType: "document",
			EntityID:   "doc1",
			Key:        "author",
			Value:      "John Doe",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc1",
			Key:        "category",
			Value:      "policy",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc1",
			Key:        "version",
			Value:      "2.0",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
	}

	for _, e := range entries {
		if err := ms.SetMetadata(e); err != nil {
			t.Fatalf("Failed to set metadata: %v", err)
		}
	}

	// Get all metadata
	allMeta, err := ms.GetAllMetadata("document", "doc1")
	if err != nil {
		t.Fatalf("Failed to get all metadata: %v", err)
	}

	if len(allMeta) != 3 {
		t.Errorf("Expected 3 metadata entries, got %d", len(allMeta))
	}

	if allMeta["author"] != "John Doe" {
		t.Errorf("Expected author='John Doe', got '%s'", allMeta["author"])
	}

	if allMeta["category"] != "policy" {
		t.Errorf("Expected category='policy', got '%s'", allMeta["category"])
	}
}

func TestDeleteMetadata(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	entry := &MetadataEntry{
		EntityType: "document",
		EntityID:   "doc1",
		Key:        "author",
		Value:      "John Doe",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	ms.SetMetadata(entry)

	// Delete metadata
	if err := ms.DeleteMetadata("document", "doc1", "author"); err != nil {
		t.Fatalf("Failed to delete metadata: %v", err)
	}

	// Verify deletion
	_, err := ms.GetMetadata("document", "doc1", "author")
	if err == nil {
		t.Error("Expected error for deleted metadata")
	}
}

func TestQueryByKey(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Set metadata for multiple documents
	entries := []*MetadataEntry{
		{
			EntityType: "document",
			EntityID:   "doc1",
			Key:        "author",
			Value:      "John Doe",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc2",
			Key:        "author",
			Value:      "Jane Smith",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "node",
			EntityID:   "node1",
			Key:        "author",
			Value:      "Bob Wilson",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
	}

	for _, e := range entries {
		ms.SetMetadata(e)
	}

	// Query by key (all entity types)
	results, err := ms.QueryByKey("author", nil, 0)
	if err != nil {
		t.Fatalf("Failed to query by key: %v", err)
	}

	if len(results) != 3 {
		t.Errorf("Expected 3 results, got %d", len(results))
	}

	// Query by key with entity type filter
	docType := "document"
	results, err = ms.QueryByKey("author", &docType, 0)
	if err != nil {
		t.Fatalf("Failed to query by key with filter: %v", err)
	}

	if len(results) != 2 {
		t.Errorf("Expected 2 document results, got %d", len(results))
	}
}

func TestQueryByKeyValue(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Set metadata
	entries := []*MetadataEntry{
		{
			EntityType: "document",
			EntityID:   "doc1",
			Key:        "category",
			Value:      "policy",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc2",
			Key:        "category",
			Value:      "policy",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc3",
			Key:        "category",
			Value:      "guideline",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
	}

	for _, e := range entries {
		ms.SetMetadata(e)
	}

	// Query by key-value
	results, err := ms.QueryByKeyValue("category", "policy", nil, 0)
	if err != nil {
		t.Fatalf("Failed to query by key-value: %v", err)
	}

	if len(results) != 2 {
		t.Errorf("Expected 2 policy documents, got %d", len(results))
	}

	// Verify all results have correct value
	for _, r := range results {
		if r.Value != "policy" {
			t.Errorf("Expected value='policy', got '%s'", r.Value)
		}
	}
}

func TestQueryMultiple(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create documents with different metadata combinations
	docs := []struct {
		id       string
		category string
		status   string
		author   string
	}{
		{"doc1", "policy", "active", "John Doe"},
		{"doc2", "policy", "draft", "Jane Smith"},
		{"doc3", "guideline", "active", "John Doe"},
		{"doc4", "policy", "active", "Bob Wilson"},
	}

	for _, doc := range docs {
		ms.SetMetadata(&MetadataEntry{
			EntityType: "document",
			EntityID:   doc.id,
			Key:        "category",
			Value:      doc.category,
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		})
		ms.SetMetadata(&MetadataEntry{
			EntityType: "document",
			EntityID:   doc.id,
			Key:        "status",
			Value:      doc.status,
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		})
		ms.SetMetadata(&MetadataEntry{
			EntityType: "document",
			EntityID:   doc.id,
			Key:        "author",
			Value:      doc.author,
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		})
	}

	// Query: category=policy AND status=active
	docType := "document"
	results, err := ms.QueryMultiple(map[string]string{
		"category": "policy",
		"status":   "active",
	}, &docType, 0)
	if err != nil {
		t.Fatalf("Failed to query multiple: %v", err)
	}

	// Should match doc1 and doc4
	if len(results) != 2 {
		t.Errorf("Expected 2 results, got %d", len(results))
	}

	// Query: category=policy AND status=active AND author=John Doe
	results, err = ms.QueryMultiple(map[string]string{
		"category": "policy",
		"status":   "active",
		"author":   "John Doe",
	}, &docType, 0)
	if err != nil {
		t.Fatalf("Failed to query multiple: %v", err)
	}

	// Should match only doc1
	if len(results) != 1 {
		t.Errorf("Expected 1 result, got %d", len(results))
	}

	if len(results) > 0 && results[0] != "doc1" {
		t.Errorf("Expected doc1, got %s", results[0])
	}
}

func TestUpdateMetadata(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Initial metadata
	entry := &MetadataEntry{
		EntityType: "document",
		EntityID:   "doc1",
		Key:        "status",
		Value:      "draft",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	}
	ms.SetMetadata(entry)

	// Update metadata
	updated := &MetadataEntry{
		EntityType: "document",
		EntityID:   "doc1",
		Key:        "status",
		Value:      "published",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now.Add(1 * time.Hour),
	}
	ms.SetMetadata(updated)

	// Verify update
	retrieved, err := ms.GetMetadata("document", "doc1", "status")
	if err != nil {
		t.Fatalf("Failed to get metadata: %v", err)
	}

	if retrieved.Value != "published" {
		t.Errorf("Expected 'published', got '%s'", retrieved.Value)
	}
}

func TestMetadataNotFound(t *testing.T) {
	ms, kv, path := setupTestMetadataStore(t)
	defer os.Remove(path)
	defer kv.Close()

	// Try to get non-existent metadata
	_, err := ms.GetMetadata("document", "nonexistent", "author")
	if err == nil {
		t.Error("Expected error for non-existent metadata")
	}
}
