package wal

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRecoveryCommittedTransactions(t *testing.T) {
	// Setup: Create WAL with committed transactions
	dir, err := os.MkdirTemp("", "wal-recovery-committed-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}

	// Write 3 committed transactions
	for txn := 0; txn < 3; txn++ {
		// Write INSERT
		entry := Entry{
			LSN:       w.NextLSN(),
			TxnID:     uint64(txn),
			OpType:    OpInsert,
			Key:       []byte(fmt.Sprintf("key-%d", txn)),
			Value:     []byte(fmt.Sprintf("value-%d", txn)),
			Timestamp: time.Now(),
		}
		w.Write(entry)

		// Write COMMIT
		commit := Entry{
			LSN:       w.NextLSN(),
			TxnID:     uint64(txn),
			OpType:    OpCommit,
			Timestamp: time.Now(),
		}
		w.Write(commit)
	}
	w.Fsync()
	w.Close()

	// Recovery: Replay WAL
	w2 := &WAL{Path: walPath}
	w2.Open()
	defer w2.Close()

	recovery := NewRecovery(w2)
	replayedOps := make(map[string]string)

	err = recovery.Recover(func(op OpType, key, value []byte) error {
		if op == OpInsert {
			replayedOps[string(key)] = string(value)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	// Verify: All 3 operations applied
	if len(replayedOps) != 3 {
		t.Errorf("expected 3 replayed operations, got %d", len(replayedOps))
	}

	for i := 0; i < 3; i++ {
		key := fmt.Sprintf("key-%d", i)
		expectedValue := fmt.Sprintf("value-%d", i)
		if replayedOps[key] != expectedValue {
			t.Errorf("key %s: expected %s, got %s", key, expectedValue, replayedOps[key])
		}
	}
}

func TestRecoveryUncommittedTransactions(t *testing.T) {
	// Setup: Create WAL with uncommitted transactions
	dir, err := os.MkdirTemp("", "wal-recovery-uncommitted-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}

	// Write 2 transactions: 1 committed, 1 uncommitted
	// Transaction 0: committed
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  0,
		OpType: OpInsert,
		Key:    []byte("committed-key"),
		Value:  []byte("committed-value"),
	})
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  0,
		OpType: OpCommit,
	})

	// Transaction 1: uncommitted
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  1,
		OpType: OpInsert,
		Key:    []byte("uncommitted-key"),
		Value:  []byte("uncommitted-value"),
	})
	// No COMMIT marker

	w.Fsync()
	w.Close()

	// Recovery: Replay WAL
	w2 := &WAL{Path: walPath}
	w2.Open()
	defer w2.Close()

	recovery := NewRecovery(w2)
	replayedOps := make(map[string]string)

	err = recovery.Recover(func(op OpType, key, value []byte) error {
		if op == OpInsert {
			replayedOps[string(key)] = string(value)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	// Verify: Only committed operation applied
	if len(replayedOps) != 1 {
		t.Errorf("expected 1 replayed operation, got %d", len(replayedOps))
	}

	if replayedOps["committed-key"] != "committed-value" {
		t.Errorf("committed transaction not replayed correctly")
	}

	if _, exists := replayedOps["uncommitted-key"]; exists {
		t.Errorf("uncommitted transaction should not be replayed")
	}
}

func TestRecoveryAfterCheckpoint(t *testing.T) {
	// Setup: Create WAL with checkpoint in middle
	dir, err := os.MkdirTemp("", "wal-recovery-checkpoint-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}

	// Write transaction 0 (before checkpoint)
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  0,
		OpType: OpInsert,
		Key:    []byte("before-checkpoint"),
		Value:  []byte("value-0"),
	})
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  0,
		OpType: OpCommit,
	})

	// Write checkpoint marker
	checkpointLSN := w.NextLSN()
	w.Write(Entry{
		LSN:    checkpointLSN,
		TxnID:  0,
		OpType: OpCheckpoint,
	})

	// Write transaction 1 (after checkpoint)
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  1,
		OpType: OpInsert,
		Key:    []byte("after-checkpoint"),
		Value:  []byte("value-1"),
	})
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  1,
		OpType: OpCommit,
	})

	w.Fsync()
	w.Close()

	// Recovery: Replay WAL
	w2 := &WAL{Path: walPath}
	w2.Open()
	defer w2.Close()

	recovery := NewRecovery(w2)
	replayedOps := make(map[string]string)

	err = recovery.Recover(func(op OpType, key, value []byte) error {
		if op == OpInsert {
			replayedOps[string(key)] = string(value)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	// Verify: Only entries after checkpoint replayed
	if _, exists := replayedOps["before-checkpoint"]; exists {
		t.Errorf("entries before checkpoint should not be replayed")
	}

	if replayedOps["after-checkpoint"] != "value-1" {
		t.Errorf("entries after checkpoint should be replayed")
	}
}

func TestRecoveryWithStats(t *testing.T) {
	// Setup: Create WAL with mixed transactions
	dir, err := os.MkdirTemp("", "wal-recovery-stats-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}

	// Write 2 committed + 1 uncommitted
	for txn := 0; txn < 3; txn++ {
		w.Write(Entry{
			LSN:    w.NextLSN(),
			TxnID:  uint64(txn),
			OpType: OpInsert,
			Key:    []byte(fmt.Sprintf("key-%d", txn)),
			Value:  []byte(fmt.Sprintf("value-%d", txn)),
		})

		// Only commit first 2
		if txn < 2 {
			w.Write(Entry{
				LSN:    w.NextLSN(),
				TxnID:  uint64(txn),
				OpType: OpCommit,
			})
		}
	}
	w.Fsync()
	w.Close()

	// Recovery with stats
	w2 := &WAL{Path: walPath}
	w2.Open()
	defer w2.Close()

	recovery := NewRecovery(w2)
	stats, err := recovery.RecoverWithStats(func(op OpType, key, value []byte) error {
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	// Verify stats
	if stats.CommittedTxns != 2 {
		t.Errorf("expected 2 committed txns, got %d", stats.CommittedTxns)
	}
	if stats.UncommittedTxns != 1 {
		t.Errorf("expected 1 uncommitted txn, got %d", stats.UncommittedTxns)
	}
	if stats.ReplayedOperations != 2 {
		t.Errorf("expected 2 replayed operations, got %d", stats.ReplayedOperations)
	}
}

func TestRecoveryDeleteOperations(t *testing.T) {
	// Setup: Create WAL with DELETE operations
	dir, err := os.MkdirTemp("", "wal-recovery-delete-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}

	// Write INSERT
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  0,
		OpType: OpInsert,
		Key:    []byte("test-key"),
		Value:  []byte("test-value"),
	})
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  0,
		OpType: OpCommit,
	})

	// Write DELETE
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  1,
		OpType: OpDelete,
		Key:    []byte("test-key"),
	})
	w.Write(Entry{
		LSN:    w.NextLSN(),
		TxnID:  1,
		OpType: OpCommit,
	})

	w.Fsync()
	w.Close()

	// Recovery: Track operations
	w2 := &WAL{Path: walPath}
	w2.Open()
	defer w2.Close()

	recovery := NewRecovery(w2)
	operations := []string{}

	err = recovery.Recover(func(op OpType, key, value []byte) error {
		if op == OpInsert {
			operations = append(operations, fmt.Sprintf("INSERT:%s", key))
		} else if op == OpDelete {
			operations = append(operations, fmt.Sprintf("DELETE:%s", key))
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	// Verify: Both INSERT and DELETE replayed
	if len(operations) != 2 {
		t.Errorf("expected 2 operations, got %d", len(operations))
	}
	if operations[0] != "INSERT:test-key" {
		t.Errorf("expected INSERT operation first, got %s", operations[0])
	}
	if operations[1] != "DELETE:test-key" {
		t.Errorf("expected DELETE operation second, got %s", operations[1])
	}
}

func TestRecoveryEmptyWAL(t *testing.T) {
	// Test recovery when WAL is empty/doesn't exist
	dir, err := os.MkdirTemp("", "wal-recovery-empty-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create an empty WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}
	w.Close()

	// Reopen for recovery
	w2 := &WAL{Path: walPath}
	if err := w2.Open(); err != nil {
		t.Fatal(err)
	}
	defer w2.Close()

	recovery := NewRecovery(w2)
	err = recovery.Recover(func(op OpType, key, value []byte) error {
		t.Error("should not replay any operations for empty WAL")
		return nil
	})

	// Should succeed without error
	if err != nil {
		t.Errorf("recovery of empty WAL should succeed, got error: %v", err)
	}
}
