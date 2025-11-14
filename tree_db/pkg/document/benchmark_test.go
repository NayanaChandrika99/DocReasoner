// ABOUTME: Performance benchmarks for document layer
// ABOUTME: Measures hierarchical query performance

package document

import (
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/nainya/treestore/pkg/storage"
)

func BenchmarkStoreDocument(b *testing.B) {
	path := "/tmp/bench_doc_store.db"
	defer os.Remove(path)

	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	ds := NewSimpleStore(kv)
	now := time.Now()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		doc := &Document{
			PolicyID:   fmt.Sprintf("policy%d", i),
			VersionID:  "v1",
			RootNodeID: fmt.Sprintf("node%d", i),
			CreatedAt:  now,
			UpdatedAt:  now,
		}

		nodes := []*Node{
			{
				NodeID:    fmt.Sprintf("node%d", i),
				PolicyID:  fmt.Sprintf("policy%d", i),
				Title:     fmt.Sprintf("Node %d", i),
				PageStart: 1,
				PageEnd:   10,
				CreatedAt: now,
				UpdatedAt: now,
			},
		}

		if err := ds.StoreDocument(doc, nodes); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkGetNode(b *testing.B) {
	path := "/tmp/bench_doc_get.db"
	defer os.Remove(path)

	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	ds := NewSimpleStore(kv)
	now := time.Now()

	// Pre-populate
	numNodes := 1000
	for i := 0; i < numNodes; i++ {
		doc := &Document{
			PolicyID:   "policy1",
			VersionID:  "v1",
			RootNodeID: fmt.Sprintf("node%d", i),
			CreatedAt:  now,
			UpdatedAt:  now,
		}

		nodes := []*Node{
			{
				NodeID:    fmt.Sprintf("node%d", i),
				PolicyID:  "policy1",
				Title:     fmt.Sprintf("Node %d", i),
				PageStart: 1,
				PageEnd:   10,
				CreatedAt: now,
				UpdatedAt: now,
			},
		}

		ds.StoreDocument(doc, nodes)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		nodeID := fmt.Sprintf("node%d", i%numNodes)
		_, err := ds.GetNode("policy1", nodeID)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkGetChildren(b *testing.B) {
	path := "/tmp/bench_doc_children.db"
	defer os.Remove(path)

	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	ds := NewSimpleStore(kv)
	now := time.Now()

	// Create hierarchy: root with 10 children
	rootID := "root"
	nodes := []*Node{
		{
			NodeID:    rootID,
			PolicyID:  "policy1",
			Title:     "Root",
			PageStart: 1,
			PageEnd:   100,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	for i := 0; i < 10; i++ {
		nodes = append(nodes, &Node{
			NodeID:    fmt.Sprintf("child%d", i),
			PolicyID:  "policy1",
			ParentID:  &rootID,
			Title:     fmt.Sprintf("Child %d", i),
			PageStart: i * 10,
			PageEnd:   (i + 1) * 10,
			CreatedAt: now,
			UpdatedAt: now,
		})
	}

	doc := &Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: rootID,
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	ds.StoreDocument(doc, nodes)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := ds.GetChildren("policy1", &rootID)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkGetSubtree(b *testing.B) {
	path := "/tmp/bench_doc_subtree.db"
	defer os.Remove(path)

	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	ds := NewSimpleStore(kv)
	now := time.Now()

	// Create 3-level hierarchy
	rootID := "root"
	nodes := []*Node{
		{
			NodeID:    rootID,
			PolicyID:  "policy1",
			Title:     "Root",
			Depth:     0,
			PageStart: 1,
			PageEnd:   100,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	// Level 1: 5 children
	for i := 0; i < 5; i++ {
		childID := fmt.Sprintf("L1_%d", i)
		nodes = append(nodes, &Node{
			NodeID:    childID,
			PolicyID:  "policy1",
			ParentID:  &rootID,
			Title:     fmt.Sprintf("L1 Node %d", i),
			Depth:     1,
			PageStart: i * 20,
			PageEnd:   (i + 1) * 20,
			CreatedAt: now,
			UpdatedAt: now,
		})

		// Level 2: 3 children each
		for j := 0; j < 3; j++ {
			nodes = append(nodes, &Node{
				NodeID:    fmt.Sprintf("L2_%d_%d", i, j),
				PolicyID:  "policy1",
				ParentID:  &childID,
				Title:     fmt.Sprintf("L2 Node %d-%d", i, j),
				Depth:     2,
				PageStart: i*20 + j*5,
				PageEnd:   i*20 + (j+1)*5,
				CreatedAt: now,
				UpdatedAt: now,
			})
		}
	}

	doc := &Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: rootID,
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	ds.StoreDocument(doc, nodes)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := ds.GetSubtree("policy1", rootID, QueryOptions{MaxDepth: 0})
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkSearch(b *testing.B) {
	path := "/tmp/bench_doc_search.db"
	defer os.Remove(path)

	kv := &storage.KV{Path: path}
	if err := kv.Open(); err != nil {
		b.Fatal(err)
	}
	defer kv.Close()

	ds := NewSimpleStore(kv)
	now := time.Now()

	// Create 100 nodes with searchable content
	nodes := make([]*Node, 100)
	for i := 0; i < 100; i++ {
		nodes[i] = &Node{
			NodeID:    fmt.Sprintf("node%d", i),
			PolicyID:  "policy1",
			Title:     fmt.Sprintf("Privacy Policy Section %d", i),
			Summary:   fmt.Sprintf("This section covers privacy requirements for users %d", i),
			Text:      fmt.Sprintf("Full text about privacy and data protection in section %d", i),
			PageStart: i,
			PageEnd:   i + 1,
			CreatedAt: now,
			UpdatedAt: now,
		}
	}

	doc := &Document{
		PolicyID:   "policy1",
		VersionID:  "v1",
		RootNodeID: "node0",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	ds.StoreDocument(doc, nodes)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := ds.Search("policy1", "privacy requirements", 10)
		if err != nil {
			b.Fatal(err)
		}
	}
}
