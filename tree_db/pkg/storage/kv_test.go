// ABOUTME: Integration tests for disk-based KV store
// ABOUTME: Tests persistence, crash recovery, and two-phase updates

package storage

import (
	"fmt"
	"os"
	"testing"
)

func TestKVBasicOperations(t *testing.T) {
	// Create temp file
	path := "/tmp/test_kv_basic.db"
	defer os.Remove(path)

	// Open database
	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Insert key-value pairs
	if err := db.Set([]byte("key1"), []byte("value1")); err != nil {
		t.Fatalf("Failed to set key1: %v", err)
	}

	if err := db.Set([]byte("key2"), []byte("value2")); err != nil {
		t.Fatalf("Failed to set key2: %v", err)
	}

	// Retrieve values
	val, ok := db.Get([]byte("key1"))
	if !ok {
		t.Fatal("key1 not found")
	}
	if string(val) != "value1" {
		t.Errorf("Expected value1, got %s", val)
	}

	val, ok = db.Get([]byte("key2"))
	if !ok {
		t.Fatal("key2 not found")
	}
	if string(val) != "value2" {
		t.Errorf("Expected value2, got %s", val)
	}
}

func TestKVPersistence(t *testing.T) {
	path := "/tmp/test_kv_persist.db"
	defer os.Remove(path)

	// First session: write data
	{
		db := &KV{Path: path}
		if err := db.Open(); err != nil {
			t.Fatalf("Failed to open database: %v", err)
		}

		for i := 0; i < 100; i++ {
			key := []byte(fmt.Sprintf("key%03d", i))
			val := []byte(fmt.Sprintf("value%03d", i))
			if err := db.Set(key, val); err != nil {
				t.Fatalf("Failed to set %s: %v", key, err)
			}
		}

		if err := db.Close(); err != nil {
			t.Fatalf("Failed to close database: %v", err)
		}
	}

	// Second session: verify data persisted
	{
		db := &KV{Path: path}
		if err := db.Open(); err != nil {
			t.Fatalf("Failed to reopen database: %v", err)
		}
		defer db.Close()

		for i := 0; i < 100; i++ {
			key := []byte(fmt.Sprintf("key%03d", i))
			expectedVal := []byte(fmt.Sprintf("value%03d", i))

			val, ok := db.Get(key)
			if !ok {
				t.Errorf("Key %s not found after reopen", key)
				continue
			}
			if string(val) != string(expectedVal) {
				t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
			}
		}
	}
}

func TestKVUpdate(t *testing.T) {
	path := "/tmp/test_kv_update.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Insert
	if err := db.Set([]byte("key1"), []byte("value1")); err != nil {
		t.Fatalf("Failed to set: %v", err)
	}

	// Update
	if err := db.Set([]byte("key1"), []byte("value1_updated")); err != nil {
		t.Fatalf("Failed to update: %v", err)
	}

	// Verify
	val, ok := db.Get([]byte("key1"))
	if !ok {
		t.Fatal("key1 not found")
	}
	if string(val) != "value1_updated" {
		t.Errorf("Expected value1_updated, got %s", val)
	}
}

func TestKVDelete(t *testing.T) {
	path := "/tmp/test_kv_delete.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Insert
	if err := db.Set([]byte("key1"), []byte("value1")); err != nil {
		t.Fatalf("Failed to set: %v", err)
	}
	if err := db.Set([]byte("key2"), []byte("value2")); err != nil {
		t.Fatalf("Failed to set: %v", err)
	}

	// Delete
	deleted, err := db.Del([]byte("key1"))
	if err != nil {
		t.Fatalf("Failed to delete: %v", err)
	}
	if !deleted {
		t.Error("Expected successful delete")
	}

	// Verify deleted
	_, ok := db.Get([]byte("key1"))
	if ok {
		t.Error("key1 should be deleted")
	}

	// Verify other key still exists
	val, ok := db.Get([]byte("key2"))
	if !ok || string(val) != "value2" {
		t.Error("key2 should still exist")
	}
}

func TestKVEmptyDatabase(t *testing.T) {
	path := "/tmp/test_kv_empty.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Get from empty database
	_, ok := db.Get([]byte("nonexistent"))
	if ok {
		t.Error("Expected key not found in empty database")
	}
}

func TestKVLargeDataset(t *testing.T) {
	path := "/tmp/test_kv_large.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	// Insert 500 keys to test page allocation and mmap extension
	for i := 0; i < 500; i++ {
		key := []byte(fmt.Sprintf("key%05d", i))
		val := []byte(fmt.Sprintf("value%05d_with_some_extra_data", i))
		if err := db.Set(key, val); err != nil {
			t.Fatalf("Failed to set %s: %v", key, err)
		}
	}

	// Verify all keys
	for i := 0; i < 500; i++ {
		key := []byte(fmt.Sprintf("key%05d", i))
		expectedVal := []byte(fmt.Sprintf("value%05d_with_some_extra_data", i))

		val, ok := db.Get(key)
		if !ok {
			t.Errorf("Key %s not found", key)
			continue
		}
		if string(val) != string(expectedVal) {
			t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
		}
	}
}

func TestKVReopenAfterWrites(t *testing.T) {
	path := "/tmp/test_kv_reopen.db"
	defer os.Remove(path)

	// Write some data
	db1 := &KV{Path: path}
	if err := db1.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}

	for i := 0; i < 50; i++ {
		key := []byte(fmt.Sprintf("k%02d", i))
		val := []byte(fmt.Sprintf("v%02d", i))
		if err := db1.Set(key, val); err != nil {
			t.Fatalf("Failed to set: %v", err)
		}
	}

	if err := db1.Close(); err != nil {
		t.Fatalf("Failed to close: %v", err)
	}

	// Reopen and add more data
	db2 := &KV{Path: path}
	if err := db2.Open(); err != nil {
		t.Fatalf("Failed to reopen: %v", err)
	}
	defer db2.Close()

	// Add more keys
	for i := 50; i < 100; i++ {
		key := []byte(fmt.Sprintf("k%02d", i))
		val := []byte(fmt.Sprintf("v%02d", i))
		if err := db2.Set(key, val); err != nil {
			t.Fatalf("Failed to set: %v", err)
		}
	}

	// Verify all 100 keys
	for i := 0; i < 100; i++ {
		key := []byte(fmt.Sprintf("k%02d", i))
		expectedVal := []byte(fmt.Sprintf("v%02d", i))

		val, ok := db2.Get(key)
		if !ok {
			t.Errorf("Key %s not found", key)
		} else if string(val) != string(expectedVal) {
			t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
		}
	}
}
