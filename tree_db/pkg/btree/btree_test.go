// ABOUTME: Integration tests for B+Tree operations
// ABOUTME: Tests Insert, Get, Delete with in-memory page simulation

package btree

import (
	"bytes"
	"fmt"
	"testing"
	"unsafe"
)

// TestContext simulates in-memory pages for testing
type TestContext struct {
	tree  BTree
	ref   map[string]string // reference data
	pages map[uint64]BNode  // in-memory pages
}

func newTestContext() *TestContext {
	pages := map[uint64]BNode{}
	c := &TestContext{
		tree: BTree{
			get: func(ptr uint64) []byte {
				node, ok := pages[ptr]
				if !ok {
					panic("page not found")
				}
				return node
			},
			new: func(node []byte) uint64 {
				if BNode(node).nbytes() > BTREE_PAGE_SIZE {
					panic("node too large")
				}
				ptr := uint64(uintptr(unsafe.Pointer(&node[0])))
				if pages[ptr] != nil {
					panic("page already allocated")
				}
				pages[ptr] = node
				return ptr
			},
			del: func(ptr uint64) {
				if pages[ptr] == nil {
					panic("page not allocated")
				}
				delete(pages, ptr)
			},
		},
		ref:   map[string]string{},
		pages: pages,
	}
	return c
}

func (c *TestContext) add(key string, val string) {
	c.tree.Insert([]byte(key), []byte(val))
	c.ref[key] = val
}

func (c *TestContext) del(key string) bool {
	delete(c.ref, key)
	return c.tree.Delete([]byte(key))
}

func TestBTreeBasicInsertGet(t *testing.T) {
	c := newTestContext()
	
	// Insert a few keys
	c.add("key1", "val1")
	c.add("key2", "val2")
	c.add("key3", "val3")
	
	// Test Get
	val, ok := c.tree.Get([]byte("key2"))
	if !ok {
		t.Fatal("key2 not found")
	}
	if string(val) != "val2" {
		t.Errorf("Expected val2, got %s", val)
	}
	
	// Test non-existent key
	_, ok = c.tree.Get([]byte("key4"))
	if ok {
		t.Error("Expected key4 to not exist")
	}
}

func TestBTreeUpdate(t *testing.T) {
	c := newTestContext()
	
	c.add("key1", "val1")
	c.add("key1", "val1_updated")
	
	val, ok := c.tree.Get([]byte("key1"))
	if !ok {
		t.Fatal("key1 not found")
	}
	if string(val) != "val1_updated" {
		t.Errorf("Expected val1_updated, got %s", val)
	}
}

func TestBTreeDelete(t *testing.T) {
	c := newTestContext()
	
	c.add("key1", "val1")
	c.add("key2", "val2")
	c.add("key3", "val3")
	
	// Delete key2
	ok := c.del("key2")
	if !ok {
		t.Error("Expected successful delete")
	}
	
	// Verify it's gone
	_, ok = c.tree.Get([]byte("key2"))
	if ok {
		t.Error("key2 should be deleted")
	}
	
	// Verify others still exist
	val, ok := c.tree.Get([]byte("key1"))
	if !ok || string(val) != "val1" {
		t.Error("key1 should still exist")
	}
}

func TestBTreeMultipleInsertions(t *testing.T) {
	c := newTestContext()
	
	// Insert 100 keys
	for i := 0; i < 100; i++ {
		key := fmt.Sprintf("key%03d", i)
		val := fmt.Sprintf("val%03d", i)
		c.add(key, val)
	}
	
	// Verify all keys
	for i := 0; i < 100; i++ {
		key := fmt.Sprintf("key%03d", i)
		expectedVal := fmt.Sprintf("val%03d", i)
		
		val, ok := c.tree.Get([]byte(key))
		if !ok {
			t.Errorf("Key %s not found", key)
		}
		if string(val) != expectedVal {
			t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
		}
	}
}

func TestBTree1000Insertions(t *testing.T) {
	c := newTestContext()
	
	// Insert 1000+ keys to test splitting
	for i := 0; i < 1500; i++ {
		key := fmt.Sprintf("key%05d", i)
		val := fmt.Sprintf("value%05d", i)
		c.add(key, val)
	}
	
	// Verify all keys exist and have correct values
	for i := 0; i < 1500; i++ {
		key := fmt.Sprintf("key%05d", i)
		expectedVal := fmt.Sprintf("value%05d", i)
		
		val, ok := c.tree.Get([]byte(key))
		if !ok {
			t.Errorf("Key %s not found", key)
			continue
		}
		if string(val) != expectedVal {
			t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
		}
	}
}

func TestBTreeInsertDeleteMixed(t *testing.T) {
	c := newTestContext()
	
	// Insert some keys
	for i := 0; i < 50; i++ {
		key := fmt.Sprintf("key%03d", i)
		val := fmt.Sprintf("val%03d", i)
		c.add(key, val)
	}
	
	// Delete every other key
	for i := 0; i < 50; i += 2 {
		key := fmt.Sprintf("key%03d", i)
		c.del(key)
	}
	
	// Verify deleted keys are gone
	for i := 0; i < 50; i += 2 {
		key := fmt.Sprintf("key%03d", i)
		_, ok := c.tree.Get([]byte(key))
		if ok {
			t.Errorf("Key %s should be deleted", key)
		}
	}
	
	// Verify remaining keys still exist
	for i := 1; i < 50; i += 2 {
		key := fmt.Sprintf("key%03d", i)
		expectedVal := fmt.Sprintf("val%03d", i)
		
		val, ok := c.tree.Get([]byte(key))
		if !ok {
			t.Errorf("Key %s should still exist", key)
		}
		if string(val) != expectedVal {
			t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
		}
	}
}

func TestBTreeNonExistentDelete(t *testing.T) {
	c := newTestContext()
	
	c.add("key1", "val1")
	
	// Try to delete non-existent key
	ok := c.tree.Delete([]byte("key2"))
	if ok {
		t.Error("Expected delete to fail for non-existent key")
	}
}

func TestBTreeEmptyTree(t *testing.T) {
	c := newTestContext()
	
	// Get from empty tree
	_, ok := c.tree.Get([]byte("key1"))
	if ok {
		t.Error("Expected Get to fail on empty tree")
	}
	
	// Delete from empty tree
	ok = c.tree.Delete([]byte("key1"))
	if ok {
		t.Error("Expected Delete to fail on empty tree")
	}
}

func TestBTreeLargeValues(t *testing.T) {
	c := newTestContext()
	
	// Test with larger values (but within limits)
	largeVal := bytes.Repeat([]byte("x"), 2000)
	c.tree.Insert([]byte("bigkey"), largeVal)
	
	val, ok := c.tree.Get([]byte("bigkey"))
	if !ok {
		t.Fatal("bigkey not found")
	}
	if !bytes.Equal(val, largeVal) {
		t.Error("Large value mismatch")
	}
}

func TestBTreeSentinelKey(t *testing.T) {
	c := newTestContext()
	
	// The tree should have a sentinel empty key
	c.add("a", "val_a")
	
	// Query for a key that's less than 'a' should still work
	_, ok := c.tree.Get([]byte("0"))
	if ok {
		t.Error("Expected key '0' to not exist")
	}
}
