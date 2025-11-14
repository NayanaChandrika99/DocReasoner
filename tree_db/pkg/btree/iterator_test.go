// ABOUTME: Tests for B+Tree iterator and range scans
// ABOUTME: Verifies SeekLE, Next, and Scan operations

package btree

import (
	"fmt"
	"testing"
)

func TestIteratorEmpty(t *testing.T) {
	c := newTestContext()
	iter := c.tree.NewIterator()

	if iter.SeekLE([]byte("key1")) {
		t.Error("Expected SeekLE to fail on empty tree")
	}

	if iter.Valid() {
		t.Error("Iterator should not be valid on empty tree")
	}
}

func TestIteratorSeekLE(t *testing.T) {
	c := newTestContext()

	// Insert keys: key1, key3, key5
	c.add("key1", "val1")
	c.add("key3", "val3")
	c.add("key5", "val5")

	iter := c.tree.NewIterator()

	// Seek to exact key
	if !iter.SeekLE([]byte("key3")) {
		t.Fatal("SeekLE failed")
	}
	if !iter.Valid() {
		t.Fatal("Iterator should be valid")
	}
	if string(iter.Key()) != "key3" {
		t.Errorf("Expected key3, got %s", iter.Key())
	}
	if string(iter.Val()) != "val3" {
		t.Errorf("Expected val3, got %s", iter.Val())
	}

	// Seek to key that doesn't exist (should find previous)
	if !iter.SeekLE([]byte("key4")) {
		t.Fatal("SeekLE failed")
	}
	if string(iter.Key()) != "key3" {
		t.Errorf("Expected key3, got %s", iter.Key())
	}

	// Seek to key before all keys
	if !iter.SeekLE([]byte("key0")) {
		t.Fatal("SeekLE failed")
	}
	// Should be at sentinel or first key
}

func TestIteratorNext(t *testing.T) {
	c := newTestContext()

	// Insert keys
	for i := 0; i < 10; i++ {
		key := fmt.Sprintf("key%02d", i)
		val := fmt.Sprintf("val%02d", i)
		c.add(key, val)
	}

	iter := c.tree.NewIterator()
	if !iter.SeekLE([]byte("key00")) {
		t.Fatal("SeekLE failed")
	}

	// Iterate through all keys
	count := 0
	for iter.Valid() {
		expectedKey := fmt.Sprintf("key%02d", count)
		expectedVal := fmt.Sprintf("val%02d", count)

		if string(iter.Key()) != expectedKey {
			t.Errorf("Expected %s, got %s", expectedKey, iter.Key())
		}
		if string(iter.Val()) != expectedVal {
			t.Errorf("Expected %s, got %s", expectedVal, iter.Val())
		}

		count++
		if count < 10 {
			if !iter.Next() {
				t.Fatalf("Next failed at index %d", count)
			}
		} else {
			if iter.Next() {
				t.Error("Next should fail at end")
			}
		}
	}

	if count != 10 {
		t.Errorf("Expected to iterate over 10 keys, got %d", count)
	}
}

func TestIteratorScan(t *testing.T) {
	c := newTestContext()

	// Insert 20 keys
	for i := 0; i < 20; i++ {
		key := fmt.Sprintf("key%02d", i)
		val := fmt.Sprintf("val%02d", i)
		c.add(key, val)
	}

	// Scan from key05 to key15
	results := make(map[string]string)
	c.tree.Scan([]byte("key05"), func(key, val []byte) bool {
		k := string(key)
		if k > "key15" {
			return false
		}
		results[k] = string(val)
		return true
	})

	// Should have keys from key05 to key15
	expectedCount := 11
	if len(results) != expectedCount {
		t.Errorf("Expected %d results, got %d", expectedCount, len(results))
	}

	for i := 5; i <= 15; i++ {
		key := fmt.Sprintf("key%02d", i)
		if val, ok := results[key]; !ok {
			t.Errorf("Missing key %s", key)
		} else {
			expectedVal := fmt.Sprintf("val%02d", i)
			if val != expectedVal {
				t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
			}
		}
	}
}

func TestIteratorLargeRange(t *testing.T) {
	c := newTestContext()

	// Insert 100 keys
	for i := 0; i < 100; i++ {
		key := fmt.Sprintf("key%03d", i)
		val := fmt.Sprintf("val%03d", i)
		c.add(key, val)
	}

	// Scan all keys
	count := 0
	c.tree.Scan([]byte("key000"), func(key, val []byte) bool {
		count++
		return true
	})

	if count != 100 {
		t.Errorf("Expected to scan 100 keys, got %d", count)
	}
}

func TestIteratorPartialScan(t *testing.T) {
	c := newTestContext()

	// Insert keys
	for i := 0; i < 50; i++ {
		key := fmt.Sprintf("key%03d", i)
		val := fmt.Sprintf("val%03d", i)
		c.add(key, val)
	}

	// Scan and stop after 10 items
	count := 0
	c.tree.Scan([]byte("key010"), func(key, val []byte) bool {
		count++
		return count < 10
	})

	if count != 10 {
		t.Errorf("Expected to scan 10 keys, got %d", count)
	}
}
