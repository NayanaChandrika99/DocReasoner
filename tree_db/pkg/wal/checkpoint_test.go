package wal

import (
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"
)

func TestCheckpointCreation(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-checkpoint-create-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Track flush calls
	var flushCalled int32

	// Create checkpointer
	checkpointer := NewCheckpointer(w, func() error {
		atomic.StoreInt32(&flushCalled, 1)
		return nil
	})

	// Manually trigger checkpoint
	err = checkpointer.Checkpoint()
	if err != nil {
		t.Fatal(err)
	}

	// Verify flush was called
	if atomic.LoadInt32(&flushCalled) != 1 {
		t.Error("flush function should have been called")
	}

	// Verify checkpoint marker in WAL
	files, _ := w.findLogFiles()
	entries, err := ReadAll(files)
	if err != nil {
		t.Fatal(err)
	}

	// Should have at least one checkpoint entry
	hasCheckpoint := false
	for _, entry := range entries {
		if entry.OpType == OpCheckpoint {
			hasCheckpoint = true
			break
		}
	}

	if !hasCheckpoint {
		t.Error("checkpoint marker not found in WAL")
	}
}

func TestCheckpointTruncation(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-checkpoint-truncate-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Write enough data to create multiple log files
	largeValue := make([]byte, 1<<20) // 1MB
	entriesPerFile := MaxLogFileSize / (1 << 20)

	// Create 5 log files
	for i := 0; i < int(entriesPerFile*5); i++ {
		entry := Entry{
			LSN:    w.NextLSN(),
			TxnID:  uint64(i),
			OpType: OpInsert,
			Key:    []byte("key"),
			Value:  largeValue,
		}
		w.Write(entry)
	}
	w.Fsync()

	// Check initial number of files
	files, _ := w.findLogFiles()
	initialFileCount := len(files)

	if initialFileCount < 5 {
		t.Skipf("need at least 5 log files for this test, got %d", initialFileCount)
	}

	// Create checkpointer and trigger checkpoint
	checkpointer := NewCheckpointer(w, func() error {
		return nil
	})

	err = checkpointer.Checkpoint()
	if err != nil {
		t.Fatal(err)
	}

	// Check file count after checkpoint - should keep last 3
	files, _ = w.findLogFiles()
	finalFileCount := len(files)

	if finalFileCount > 3 {
		t.Errorf("expected at most 3 log files after checkpoint, got %d", finalFileCount)
	}
}

func TestCheckpointInterval(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-checkpoint-interval-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Track checkpoint calls
	var checkpointCount int32

	// Create checkpointer with short interval
	checkpointer := NewCheckpointer(w, func() error {
		atomic.AddInt32(&checkpointCount, 1)
		return nil
	})
	checkpointer.SetInterval(100 * time.Millisecond)
	checkpointer.Start()
	defer checkpointer.Stop()

	// Wait for multiple checkpoint intervals
	time.Sleep(350 * time.Millisecond)

	// Should have triggered at least 2 checkpoints
	count := atomic.LoadInt32(&checkpointCount)
	if count < 2 {
		t.Errorf("expected at least 2 automatic checkpoints, got %d", count)
	}
}

func TestCheckpointGracefulShutdown(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-checkpoint-shutdown-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Create checkpointer
	checkpointer := NewCheckpointer(w, func() error {
		return nil
	})
	checkpointer.Start()

	// Stop should complete without hanging
	done := make(chan bool)
	go func() {
		checkpointer.Stop()
		done <- true
	}()

	select {
	case <-done:
		// Success
	case <-time.After(2 * time.Second):
		t.Error("checkpointer.Stop() did not complete within timeout")
	}
}

func TestCheckpointFlushError(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-checkpoint-error-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Create checkpointer with flush function that returns error
	checkpointer := NewCheckpointer(w, func() error {
		return os.ErrPermission
	})

	// Checkpoint should return error
	err = checkpointer.Checkpoint()
	if err == nil {
		t.Error("expected checkpoint to fail when flush returns error")
	}
}

func TestCheckpointMultipleFiles(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-checkpoint-multi-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}
	defer w.Close()

	// Write data to create multiple files
	largeValue := make([]byte, 1<<20)
	for i := 0; i < 250; i++ { // Enough to create 2-3 files
		w.Write(Entry{
			LSN:    w.NextLSN(),
			TxnID:  uint64(i),
			OpType: OpInsert,
			Key:    []byte("key"),
			Value:  largeValue,
		})
	}
	w.Fsync()

	// Verify multiple files exist
	files, _ := w.findLogFiles()
	if len(files) < 2 {
		t.Skipf("need at least 2 files for this test, got %d", len(files))
	}

	// Checkpoint
	checkpointer := NewCheckpointer(w, func() error { return nil })
	err = checkpointer.Checkpoint()
	if err != nil {
		t.Fatal(err)
	}

	// Verify checkpoint marker exists
	files, _ = w.findLogFiles()
	entries, err := ReadAll(files)
	if err != nil {
		t.Fatal(err)
	}

	hasCheckpoint := false
	for _, entry := range entries {
		if entry.OpType == OpCheckpoint {
			hasCheckpoint = true
			break
		}
	}

	if !hasCheckpoint {
		t.Error("checkpoint marker not found after checkpoint")
	}
}
