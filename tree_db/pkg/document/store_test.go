// ABOUTME: Tests for document storage and hierarchical queries
// ABOUTME: Verifies document operations, children, subtree, and search

package document

import (
	"os"
	"testing"
	"time"

	"github.com/nainya/treestore/pkg/storage"
)

func setupTestStore(t *testing.T) (*SimpleStore, *storage.KV, string) {
	path := "/tmp/test_docstore_" + t.Name() + ".db"
	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}

	ds := NewSimpleStore(kv)
	return ds, kv, path
}

func TestStoreAndRetrieveDocument(t *testing.T) {
	ds, kv, path := setupTestStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create test document
	doc := &Document{
		PolicyID:       "policy1",
		VersionID:      "v1",
		PageIndexDocID: "page_idx_1",
		RootNodeID:     "node1",
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	rootID := "node1"
	nodes := []*Node{
		{
			NodeID:      "node1",
			PolicyID:    "policy1",
			ParentID:    nil,
			Title:       "Root Section",
			PageStart:   1,
			PageEnd:     10,
			Summary:     "This is the root section",
			Text:        "Full text of root section",
			SectionPath: "1",
			Depth:       0,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "node2",
			PolicyID:    "policy1",
			ParentID:    &rootID,
			Title:       "Child Section 1",
			PageStart:   1,
			PageEnd:     5,
			Summary:     "First child section",
			Text:        "Full text of child 1",
			SectionPath: "1.1",
			Depth:       1,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
	}

	// Store document
	if err := ds.StoreDocument(doc, nodes); err != nil {
		t.Fatalf("Failed to store document: %v", err)
	}

	// Retrieve node
	node, err := ds.GetNode("policy1", "node1")
	if err != nil {
		t.Fatalf("Failed to get node: %v", err)
	}

	if node.Title != "Root Section" {
		t.Errorf("Expected 'Root Section', got '%s'", node.Title)
	}

	if node.PageStart != 1 || node.PageEnd != 10 {
		t.Errorf("Page range incorrect: %d-%d", node.PageStart, node.PageEnd)
	}
}

func TestGetChildren(t *testing.T) {
	ds, kv, path := setupTestStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create hierarchy: root -> child1, child2
	doc := &Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	rootID := "root"
	nodes := []*Node{
		{
			NodeID:      "root",
			PolicyID:    "policy1",
			ParentID:    nil,
			Title:       "Root",
			PageStart:   1,
			PageEnd:     10,
			SectionPath: "1",
			Depth:       0,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "child1",
			PolicyID:    "policy1",
			ParentID:    &rootID,
			Title:       "Child 1",
			PageStart:   1,
			PageEnd:     5,
			SectionPath: "1.1",
			Depth:       1,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "child2",
			PolicyID:    "policy1",
			ParentID:    &rootID,
			Title:       "Child 2",
			PageStart:   6,
			PageEnd:     10,
			SectionPath: "1.2",
			Depth:       1,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
	}

	if err := ds.StoreDocument(doc, nodes); err != nil {
		t.Fatalf("Failed to store: %v", err)
	}

	// Get children of root
	children, err := ds.GetChildren("policy1", &rootID)
	if err != nil {
		t.Fatalf("Failed to get children: %v", err)
	}

	if len(children) != 2 {
		t.Errorf("Expected 2 children, got %d", len(children))
	}
}

func TestGetSubtree(t *testing.T) {
	ds, kv, path := setupTestStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	// Create 3-level hierarchy
	doc := &Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	rootID := "root"
	child1ID := "child1"

	nodes := []*Node{
		{
			NodeID:      "root",
			PolicyID:    "policy1",
			Title:       "Root",
			SectionPath: "1",
			Depth:       0,
			PageStart:   1,
			PageEnd:     20,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "child1",
			PolicyID:    "policy1",
			ParentID:    &rootID,
			Title:       "Child 1",
			SectionPath: "1.1",
			Depth:       1,
			PageStart:   1,
			PageEnd:     10,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "child2",
			PolicyID:    "policy1",
			ParentID:    &rootID,
			Title:       "Child 2",
			SectionPath: "1.2",
			Depth:       1,
			PageStart:   11,
			PageEnd:     20,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "grandchild1",
			PolicyID:    "policy1",
			ParentID:    &child1ID,
			Title:       "Grandchild 1",
			SectionPath: "1.1.1",
			Depth:       2,
			PageStart:   1,
			PageEnd:     5,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
	}

	if err := ds.StoreDocument(doc, nodes); err != nil {
		t.Fatalf("Failed to store: %v", err)
	}

	// Get full subtree
	subtree, err := ds.GetSubtree("policy1", "root", QueryOptions{MaxDepth: 0})
	if err != nil {
		t.Fatalf("Failed to get subtree: %v", err)
	}

	if len(subtree) != 4 {
		t.Errorf("Expected 4 nodes in subtree, got %d", len(subtree))
	}

	// Get subtree with depth limit
	subtree, err = ds.GetSubtree("policy1", "root", QueryOptions{MaxDepth: 1})
	if err != nil {
		t.Fatalf("Failed to get subtree: %v", err)
	}

	if len(subtree) != 3 {
		t.Errorf("Expected 3 nodes with depth=1, got %d", len(subtree))
	}
}

func TestGetAncestorPath(t *testing.T) {
	ds, kv, path := setupTestStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	rootID := "root"
	child1ID := "child1"

	doc := &Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*Node{
		{
			NodeID:    "root",
			PolicyID:  "policy1",
			Title:     "Root",
			Depth:     0,
			PageStart: 1,
			PageEnd:   10,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeID:    "child1",
			PolicyID:  "policy1",
			ParentID:  &rootID,
			Title:     "Child 1",
			Depth:     1,
			PageStart: 1,
			PageEnd:   5,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeID:    "grandchild1",
			PolicyID:  "policy1",
			ParentID:  &child1ID,
			Title:     "Grandchild 1",
			Depth:     2,
			PageStart: 1,
			PageEnd:   2,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	if err := ds.StoreDocument(doc, nodes); err != nil {
		t.Fatalf("Failed to store: %v", err)
	}

	// Get ancestor path from root to grandchild
	ancestorPath, err := ds.GetAncestorPath("policy1", "grandchild1")
	if err != nil {
		t.Fatalf("Failed to get path: %v", err)
	}

	if len(ancestorPath) != 3 {
		t.Errorf("Expected path length 3, got %d", len(ancestorPath))
	}

	if ancestorPath[0].NodeID != "root" {
		t.Errorf("Expected root first, got %s", ancestorPath[0].NodeID)
	}

	if ancestorPath[2].NodeID != "grandchild1" {
		t.Errorf("Expected grandchild last, got %s", ancestorPath[2].NodeID)
	}
}

func TestSearch(t *testing.T) {
	ds, kv, path := setupTestStore(t)
	defer os.Remove(path)
	defer kv.Close()

	now := time.Now()

	doc := &Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*Node{
		{
			NodeID:    "node1",
			PolicyID:  "policy1",
			Title:     "Privacy Policy Section",
			Summary:   "This section covers privacy requirements",
			Text:      "Full text about privacy and data protection",
			PageStart: 1,
			PageEnd:   5,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeID:    "node2",
			PolicyID:  "policy1",
			Title:     "Security Guidelines",
			Summary:   "Security and compliance requirements",
			Text:      "Full text about security measures",
			PageStart: 6,
			PageEnd:   10,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	if err := ds.StoreDocument(doc, nodes); err != nil {
		t.Fatalf("Failed to store: %v", err)
	}

	// Search for "privacy"
	results, err := ds.Search("policy1", "privacy", 10)
	if err != nil {
		t.Fatalf("Search failed: %v", err)
	}

	if len(results) == 0 {
		t.Error("Expected search results")
	}

	if results[0].NodeID != "node1" {
		t.Errorf("Expected node1 first, got %s", results[0].NodeID)
	}

	if results[0].Score <= 0 {
		t.Error("Expected positive score")
	}
}
