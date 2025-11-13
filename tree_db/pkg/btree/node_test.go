// ABOUTME: Unit tests for B+Tree node operations
// ABOUTME: Tests node creation, KV access, and manipulation functions

package btree

import (
	"bytes"
	"testing"
)

func TestNodeHeader(t *testing.T) {
	node := make(BNode, BTREE_PAGE_SIZE)
	
	// Test setting and getting header
	node.setHeader(BNODE_LEAF, 3)
	
	if node.btype() != BNODE_LEAF {
		t.Errorf("Expected node type %d, got %d", BNODE_LEAF, node.btype())
	}
	
	if node.nkeys() != 3 {
		t.Errorf("Expected 3 keys, got %d", node.nkeys())
	}
}

func TestNodePointers(t *testing.T) {
	node := make(BNode, BTREE_PAGE_SIZE)
	node.setHeader(BNODE_NODE, 3)
	
	// Set pointers
	node.setPtr(0, 100)
	node.setPtr(1, 200)
	node.setPtr(2, 300)
	
	// Verify pointers
	if node.getPtr(0) != 100 {
		t.Errorf("Expected pointer 100, got %d", node.getPtr(0))
	}
	if node.getPtr(1) != 200 {
		t.Errorf("Expected pointer 200, got %d", node.getPtr(1))
	}
	if node.getPtr(2) != 300 {
		t.Errorf("Expected pointer 300, got %d", node.getPtr(2))
	}
}

func TestNodeKVOperations(t *testing.T) {
	node := make(BNode, BTREE_PAGE_SIZE)
	node.setHeader(BNODE_LEAF, 0)
	
	// Add a KV pair
	key1 := []byte("key1")
	val1 := []byte("value1")
	
	node.setHeader(BNODE_LEAF, 1)
	nodeAppendKV(node, 0, 0, key1, val1)
	
	// Verify key and value
	gotKey := node.getKey(0)
	if !bytes.Equal(gotKey, key1) {
		t.Errorf("Expected key %s, got %s", key1, gotKey)
	}
	
	gotVal := node.getVal(0)
	if !bytes.Equal(gotVal, val1) {
		t.Errorf("Expected value %s, got %s", val1, gotVal)
	}
}

func TestNodeAppendMultipleKVs(t *testing.T) {
	node := make(BNode, BTREE_PAGE_SIZE)
	node.setHeader(BNODE_LEAF, 3)
	
	// Add multiple KV pairs
	keys := [][]byte{
		[]byte("a"),
		[]byte("b"),
		[]byte("c"),
	}
	vals := [][]byte{
		[]byte("val_a"),
		[]byte("val_b"),
		[]byte("val_c"),
	}
	
	for i := 0; i < 3; i++ {
		nodeAppendKV(node, uint16(i), 0, keys[i], vals[i])
	}
	
	// Verify all KVs
	for i := 0; i < 3; i++ {
		gotKey := node.getKey(uint16(i))
		if !bytes.Equal(gotKey, keys[i]) {
			t.Errorf("Key %d: expected %s, got %s", i, keys[i], gotKey)
		}
		
		gotVal := node.getVal(uint16(i))
		if !bytes.Equal(gotVal, vals[i]) {
			t.Errorf("Value %d: expected %s, got %s", i, vals[i], gotVal)
		}
	}
}

func TestNodeLookupLE(t *testing.T) {
	node := make(BNode, BTREE_PAGE_SIZE)
	node.setHeader(BNODE_LEAF, 4)
	
	// Create sorted keys
	keys := [][]byte{
		[]byte("a"),
		[]byte("c"),
		[]byte("e"),
		[]byte("g"),
	}
	
	for i, key := range keys {
		nodeAppendKV(node, uint16(i), 0, key, []byte("val"))
	}
	
	tests := []struct {
		searchKey []byte
		expected  uint16
	}{
		{[]byte("a"), 0},
		{[]byte("b"), 0}, // between a and c
		{[]byte("c"), 1},
		{[]byte("d"), 1}, // between c and e
		{[]byte("e"), 2},
		{[]byte("f"), 2}, // between e and g
		{[]byte("g"), 3},
		{[]byte("h"), 3}, // after g
	}
	
	for _, tt := range tests {
		got := nodeLookupLE(node, tt.searchKey)
		if got != tt.expected {
			t.Errorf("nodeLookupLE(%s) = %d, want %d", tt.searchKey, got, tt.expected)
		}
	}
}

func TestNodeAppendRange(t *testing.T) {
	oldNode := make(BNode, BTREE_PAGE_SIZE)
	oldNode.setHeader(BNODE_LEAF, 3)
	
	// Populate old node
	keys := [][]byte{[]byte("a"), []byte("b"), []byte("c")}
	vals := [][]byte{[]byte("val1"), []byte("val2"), []byte("val3")}
	
	for i := 0; i < 3; i++ {
		nodeAppendKV(oldNode, uint16(i), 0, keys[i], vals[i])
	}
	
	// Create new node and copy range
	newNode := make(BNode, BTREE_PAGE_SIZE)
	newNode.setHeader(BNODE_LEAF, 2)
	
	// Copy 2 entries from oldNode[1:3] to newNode[0:2]
	nodeAppendRange(newNode, oldNode, 0, 1, 2)
	
	// Verify copied data
	expectedKeys := [][]byte{[]byte("b"), []byte("c")}
	expectedVals := [][]byte{[]byte("val2"), []byte("val3")}
	
	for i := 0; i < 2; i++ {
		gotKey := newNode.getKey(uint16(i))
		if !bytes.Equal(gotKey, expectedKeys[i]) {
			t.Errorf("Key %d: expected %s, got %s", i, expectedKeys[i], gotKey)
		}
		
		gotVal := newNode.getVal(uint16(i))
		if !bytes.Equal(gotVal, expectedVals[i]) {
			t.Errorf("Value %d: expected %s, got %s", i, expectedVals[i], gotVal)
		}
	}
}

func TestNodeSize(t *testing.T) {
	node := make(BNode, BTREE_PAGE_SIZE)
	node.setHeader(BNODE_LEAF, 2)
	
	nodeAppendKV(node, 0, 0, []byte("key1"), []byte("value1"))
	nodeAppendKV(node, 1, 0, []byte("key2"), []byte("value2"))
	
	size := node.nbytes()
	
	// Size should be header + pointers + offsets + actual KV data
	// This is a basic sanity check
	if size == 0 || size > BTREE_PAGE_SIZE {
		t.Errorf("Invalid node size: %d", size)
	}
}
