// ABOUTME: Tests for transaction support
// ABOUTME: Verifies atomic multi-key operations with Begin/Commit/Abort

package storage

import (
	"fmt"
	"os"
	"testing"
)

func TestTransactionBasic(t *testing.T) {
	path := "/tmp/test_tx_basic.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Start transaction
	tx := db.Begin()

	// Insert keys within transaction
	tx.Set([]byte("key1"), []byte("value1"))
	tx.Set([]byte("key2"), []byte("value2"))

	// Verify within transaction
	val, ok := tx.Get([]byte("key1"))
	if !ok || string(val) != "value1" {
		t.Error("Failed to get key1 within transaction")
	}

	// Commit
	if err := tx.Commit(); err != nil {
		t.Fatalf("Failed to commit: %v", err)
	}

	// Verify after commit
	val, ok = db.Get([]byte("key1"))
	if !ok || string(val) != "value1" {
		t.Error("key1 not persisted after commit")
	}
}

func TestTransactionAbort(t *testing.T) {
	path := "/tmp/test_tx_abort.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Insert initial data
	if err := db.Set([]byte("existing"), []byte("value")); err != nil {
		t.Fatalf("Failed to set: %v", err)
	}

	// Start transaction
	tx := db.Begin()

	// Modify within transaction
	tx.Set([]byte("existing"), []byte("modified"))
	tx.Set([]byte("new_key"), []byte("new_value"))

	// Verify changes within transaction
	val, ok := tx.Get([]byte("existing"))
	if !ok || string(val) != "modified" {
		t.Error("Failed to see modification within transaction")
	}

	// Abort transaction
	tx.Abort()

	// Verify rollback
	val, ok = db.Get([]byte("existing"))
	if !ok || string(val) != "value" {
		t.Error("Abort failed to revert changes")
	}

	_, ok = db.Get([]byte("new_key"))
	if ok {
		t.Error("New key should not exist after abort")
	}
}

func TestTransactionMultipleOperations(t *testing.T) {
	path := "/tmp/test_tx_multi.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Transaction with insert, update, delete
	tx := db.Begin()

	// Insert
	tx.Set([]byte("key1"), []byte("value1"))
	tx.Set([]byte("key2"), []byte("value2"))
	tx.Set([]byte("key3"), []byte("value3"))

	// Update
	tx.Set([]byte("key2"), []byte("value2_updated"))

	// Delete
	tx.Del([]byte("key3"))

	// Commit
	if err := tx.Commit(); err != nil {
		t.Fatalf("Failed to commit: %v", err)
	}

	// Verify final state
	if val, ok := db.Get([]byte("key1")); !ok || string(val) != "value1" {
		t.Error("key1 incorrect")
	}

	if val, ok := db.Get([]byte("key2")); !ok || string(val) != "value2_updated" {
		t.Error("key2 not updated")
	}

	if _, ok := db.Get([]byte("key3")); ok {
		t.Error("key3 should be deleted")
	}
}

func TestTransactionScan(t *testing.T) {
	path := "/tmp/test_tx_scan.db"
	defer os.Remove(path)

	db := &KV{Path: path}
	if err := db.Open(); err != nil {
		t.Fatalf("Failed to open: %v", err)
	}
	defer db.Close()

	// Transaction with multiple inserts
	tx := db.Begin()

	for i := 0; i < 10; i++ {
		key := []byte(fmt.Sprintf("key%02d", i))
		val := []byte(fmt.Sprintf("val%02d", i))
		tx.Set(key, val)
	}

	// Scan within transaction
	count := 0
	tx.Scan([]byte("key00"), func(key, val []byte) bool {
		count++
		return true
	})

	if count != 10 {
		t.Errorf("Expected 10 keys in scan, got %d", count)
	}

	// Commit and scan again
	if err := tx.Commit(); err != nil {
		t.Fatalf("Failed to commit: %v", err)
	}

	count = 0
	db.Scan([]byte("key00"), func(key, val []byte) bool {
		count++
		return true
	})

	if count != 10 {
		t.Errorf("Expected 10 keys after commit, got %d", count)
	}
}

func TestTransactionPersistence(t *testing.T) {
	path := "/tmp/test_tx_persist.db"
	defer os.Remove(path)

	// First session
	{
		db := &KV{Path: path}
		if err := db.Open(); err != nil {
			t.Fatalf("Failed to open: %v", err)
		}

		tx := db.Begin()
		tx.Set([]byte("persistent"), []byte("data"))

		if err := tx.Commit(); err != nil {
			t.Fatalf("Failed to commit: %v", err)
		}

		if err := db.Close(); err != nil {
			t.Fatalf("Failed to close: %v", err)
		}
	}

	// Second session
	{
		db := &KV{Path: path}
		if err := db.Open(); err != nil {
			t.Fatalf("Failed to reopen: %v", err)
		}
		defer db.Close()

		val, ok := db.Get([]byte("persistent"))
		if !ok || string(val) != "data" {
			t.Error("Transaction data not persisted across sessions")
		}
	}
}
