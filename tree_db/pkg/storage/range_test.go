// ABOUTME: Tests for range query operations
// ABOUTME: Verifies Scan functionality at storage level

package storage

import (
	"fmt"
	"os"
	"testing"
)

func TestKVScanBasic(t *testing.T) {
	path := "/tmp/test_scan_basic.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Insert 10 keys
	for i := 0; i < 10; i++ {
		key := []byte(fmt.Sprintf("key%02d", i))
		val := []byte(fmt.Sprintf("val%02d", i))
		if err := db.Set(key, val); err != nil {
			t.Fatalf("Failed to set: %v", err)
		}
	}

	// Scan all keys
	results := make(map[string]string)
	db.Scan([]byte("key00"), func(key, val []byte) bool {
		results[string(key)] = string(val)
		return true
	})

	if len(results) != 10 {
		t.Errorf("Expected 10 results, got %d", len(results))
	}

	for i := 0; i < 10; i++ {
		key := fmt.Sprintf("key%02d", i)
		expectedVal := fmt.Sprintf("val%02d", i)
		if val, ok := results[key]; !ok {
			t.Errorf("Missing key %s", key)
		} else if val != expectedVal {
			t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
		}
	}
}

func TestKVScanRange(t *testing.T) {
	path := "/tmp/test_scan_range.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Insert 30 keys
	for i := 0; i < 30; i++ {
		key := []byte(fmt.Sprintf("key%02d", i))
		val := []byte(fmt.Sprintf("val%02d", i))
		if err := db.Set(key, val); err != nil {
			t.Fatalf("Failed to set: %v", err)
		}
	}

	// Scan from key10 to key20
	results := make(map[string]string)
	db.Scan([]byte("key10"), func(key, val []byte) bool {
		k := string(key)
		if k > "key20" {
			return false
		}
		results[k] = string(val)
		return true
	})

	// Should have keys from key10 to key20 (11 keys)
	expectedCount := 11
	if len(results) != expectedCount {
		t.Errorf("Expected %d results, got %d", expectedCount, len(results))
	}

	for i := 10; i <= 20; i++ {
		key := fmt.Sprintf("key%02d", i)
		expectedVal := fmt.Sprintf("val%02d", i)
		if val, ok := results[key]; !ok {
			t.Errorf("Missing key %s", key)
		} else if val != expectedVal {
			t.Errorf("Key %s: expected %s, got %s", key, expectedVal, val)
		}
	}
}

func TestKVScanEmpty(t *testing.T) {
	path := "/tmp/test_scan_empty.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Scan empty database
	count := 0
	db.Scan([]byte("key00"), func(key, val []byte) bool {
		count++
		return true
	})

	if count != 0 {
		t.Errorf("Expected 0 results, got %d", count)
	}
}

func TestKVScanLargeDataset(t *testing.T) {
	path := "/tmp/test_scan_large.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Insert 200 keys
	for i := 0; i < 200; i++ {
		key := []byte(fmt.Sprintf("key%04d", i))
		val := []byte(fmt.Sprintf("val%04d", i))
		if err := db.Set(key, val); err != nil {
			t.Fatalf("Failed to set: %v", err)
		}
	}

	// Scan subset
	count := 0
	db.Scan([]byte("key0050"), func(key, val []byte) bool {
		k := string(key)
		if k > "key0149" {
			return false
		}
		count++
		return true
	})

	expectedCount := 100
	if count != expectedCount {
		t.Errorf("Expected %d results, got %d", expectedCount, count)
	}
}

func TestKVScanAfterDeletes(t *testing.T) {
	path := "/tmp/test_scan_deletes.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Insert 20 keys
	for i := 0; i < 20; i++ {
		key := []byte(fmt.Sprintf("key%02d", i))
		val := []byte(fmt.Sprintf("val%02d", i))
		if err := db.Set(key, val); err != nil {
			t.Fatalf("Failed to set: %v", err)
		}
	}

	// Delete every other key
	for i := 0; i < 20; i += 2 {
		key := []byte(fmt.Sprintf("key%02d", i))
		if _, err := db.Del(key); err != nil {
			t.Fatalf("Failed to delete: %v", err)
		}
	}

	// Scan all - should only see odd-numbered keys
	results := make(map[string]string)
	db.Scan([]byte("key00"), func(key, val []byte) bool {
		results[string(key)] = string(val)
		return true
	})

	expectedCount := 10
	if len(results) != expectedCount {
		t.Errorf("Expected %d results, got %d", expectedCount, len(results))
	}

	// Verify only odd keys exist
	for i := 1; i < 20; i += 2 {
		key := fmt.Sprintf("key%02d", i)
		if _, ok := results[key]; !ok {
			t.Errorf("Expected key %s to exist", key)
		}
	}

	// Verify even keys don't exist
	for i := 0; i < 20; i += 2 {
		key := fmt.Sprintf("key%02d", i)
		if _, ok := results[key]; ok {
			t.Errorf("Key %s should have been deleted", key)
		}
	}
}
