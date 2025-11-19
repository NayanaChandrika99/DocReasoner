package wal

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestEntryEncodeDecode(t *testing.T) {
	// Test entry encoding and decoding
	entry := &Entry{
		LSN:       42,
		TxnID:     100,
		OpType:    OpInsert,
		Key:       []byte("test-key"),
		Value:     []byte("test-value"),
		Timestamp: time.Now(),
	}

	// Encode
	data := entry.Encode()

	// Decode
	decoded, err := DecodeEntry(data)
	if err != nil {
		t.Fatalf("decode failed: %v", err)
	}

	// Verify
	if decoded.LSN != entry.LSN {
		t.Errorf("LSN mismatch: got %d, want %d", decoded.LSN, entry.LSN)
	}
	if decoded.TxnID != entry.TxnID {
		t.Errorf("TxnID mismatch: got %d, want %d", decoded.TxnID, entry.TxnID)
	}
	if decoded.OpType != entry.OpType {
		t.Errorf("OpType mismatch: got %d, want %d", decoded.OpType, entry.OpType)
	}
	if string(decoded.Key) != string(entry.Key) {
		t.Errorf("Key mismatch: got %s, want %s", decoded.Key, entry.Key)
	}
	if string(decoded.Value) != string(entry.Value) {
		t.Errorf("Value mismatch: got %s, want %s", decoded.Value, entry.Value)
	}
}

func TestEntryEncodeDecodeEmptyValue(t *testing.T) {
	// Test with empty value (DELETE operation)
	entry := &Entry{
		LSN:       10,
		TxnID:     5,
		OpType:    OpDelete,
		Key:       []byte("key-to-delete"),
		Value:     nil,
		Timestamp: time.Now(),
	}

	data := entry.Encode()
	decoded, err := DecodeEntry(data)
	if err != nil {
		t.Fatalf("decode failed: %v", err)
	}

	if decoded.LSN != entry.LSN {
		t.Errorf("LSN mismatch")
	}
	if len(decoded.Value) != 0 {
		t.Errorf("Expected empty value, got %d bytes", len(decoded.Value))
	}
}

func TestWALWriteRead(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-test-*")
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

	// Write entries
	numEntries := 100
	for i := 0; i < numEntries; i++ {
		entry := Entry{
			LSN:       w.NextLSN(),
			TxnID:     uint64(i),
			OpType:    OpInsert,
			Key:       []byte(fmt.Sprintf("key-%d", i)),
			Value:     []byte(fmt.Sprintf("value-%d", i)),
			Timestamp: time.Now(),
		}
		if err := w.Write(entry); err != nil {
			t.Fatal(err)
		}
	}

	// Fsync
	if err := w.Fsync(); err != nil {
		t.Fatal(err)
	}

	w.Close()

	// Read back
	files, _ := w.findLogFiles()
	entries, err := ReadAll(files)
	if err != nil {
		t.Fatal(err)
	}

	if len(entries) != numEntries {
		t.Errorf("expected %d entries, got %d", numEntries, len(entries))
	}

	// Verify first and last entries
	if string(entries[0].Key) != "key-0" {
		t.Errorf("first entry key mismatch: got %s", entries[0].Key)
	}
	if string(entries[numEntries-1].Key) != fmt.Sprintf("key-%d", numEntries-1) {
		t.Errorf("last entry key mismatch: got %s", entries[numEntries-1].Key)
	}
}

func TestWALRotation(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-rotation-*")
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

	// Write enough data to trigger rotation (MaxLogFileSize = 100MB)
	// Write large entries to fill up quickly
	largeValue := make([]byte, 1<<20) // 1MB value
	entriesPerFile := MaxLogFileSize / (1 << 20)

	// Write enough to create 2 files
	for i := 0; i < int(entriesPerFile*2); i++ {
		entry := Entry{
			LSN:       w.NextLSN(),
			TxnID:     uint64(i),
			OpType:    OpInsert,
			Key:       []byte(fmt.Sprintf("key-%d", i)),
			Value:     largeValue,
			Timestamp: time.Now(),
		}
		if err := w.Write(entry); err != nil {
			t.Fatal(err)
		}
	}

	// Check that multiple log files were created
	files, err := w.findLogFiles()
	if err != nil {
		t.Fatal(err)
	}

	if len(files) < 2 {
		t.Errorf("expected at least 2 log files after rotation, got %d", len(files))
	}
}

func TestLSNGeneration(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-lsn-*")
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

	// Test LSN is monotonically increasing
	var prevLSN uint64 = 0
	for i := 0; i < 100; i++ {
		lsn := w.NextLSN()
		if lsn <= prevLSN {
			t.Errorf("LSN not monotonically increasing: prev=%d, current=%d", prevLSN, lsn)
		}
		prevLSN = lsn
	}
}

func TestWALReopen(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-reopen-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL and write some entries
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}

	for i := 0; i < 10; i++ {
		entry := Entry{
			LSN:       w.NextLSN(),
			TxnID:     uint64(i),
			OpType:    OpInsert,
			Key:       []byte(fmt.Sprintf("key-%d", i)),
			Value:     []byte(fmt.Sprintf("value-%d", i)),
			Timestamp: time.Now(),
		}
		w.Write(entry)
	}
	w.Fsync()
	lastLSN := w.lsn
	w.Close()

	// Reopen WAL
	w2 := &WAL{Path: walPath}
	if err := w2.Open(); err != nil {
		t.Fatal(err)
	}
	defer w2.Close()

	// LSN should continue from where it left off
	if w2.lsn != lastLSN {
		t.Errorf("LSN after reopen mismatch: got %d, want %d", w2.lsn, lastLSN)
	}

	// Write more entries
	nextLSN := w2.NextLSN()
	if nextLSN != lastLSN+1 {
		t.Errorf("next LSN after reopen should be %d, got %d", lastLSN+1, nextLSN)
	}
}

func TestWALCorruptedEntry(t *testing.T) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-corrupt-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL and write entries
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		t.Fatal(err)
	}

	// Write a few entries
	for i := 0; i < 5; i++ {
		entry := Entry{
			LSN:       w.NextLSN(),
			TxnID:     uint64(i),
			OpType:    OpInsert,
			Key:       []byte(fmt.Sprintf("key-%d", i)),
			Value:     []byte(fmt.Sprintf("value-%d", i)),
			Timestamp: time.Now(),
		}
		w.Write(entry)
	}
	w.Fsync()
	w.Close()

	// Corrupt the WAL file by writing garbage in the middle
	files, _ := w.findLogFiles()
	if len(files) > 0 {
		fd, err := os.OpenFile(files[0], os.O_RDWR, 0644)
		if err != nil {
			t.Fatal(err)
		}
		// Write garbage at offset 500
		garbage := []byte{0xFF, 0xFF, 0xFF, 0xFF}
		fd.WriteAt(garbage, 500)
		fd.Close()
	}

	// Try to read - should handle corruption gracefully
	reader := NewReader(files)
	reader.Open()
	defer reader.Close()

	count := 0
	for {
		_, err := reader.Next()
		if err != nil {
			break
		}
		count++
		// Prevent infinite loop
		if count > 100 {
			break
		}
	}

	// Should have read at least some valid entries before corruption
	if count < 1 {
		t.Errorf("expected to read some valid entries before corruption, got %d", count)
	}
}

func TestMultipleDatabasesSameDirectory(t *testing.T) {
	// Test that multiple databases in the same directory have isolated WAL files
	dir, err := os.MkdirTemp("", "wal-multi-db-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create two databases in the same directory
	wal1Path := filepath.Join(dir, "db1.db.wal")
	wal2Path := filepath.Join(dir, "db2.db.wal")

	wal1 := &WAL{Path: wal1Path}
	wal2 := &WAL{Path: wal2Path}

	if err := wal1.Open(); err != nil {
		t.Fatal(err)
	}
	if err := wal2.Open(); err != nil {
		t.Fatal(err)
	}

	// Write 5 entries to each database
	for i := 0; i < 5; i++ {
		entry1 := Entry{
			LSN:       wal1.NextLSN(),
			TxnID:     uint64(i),
			OpType:    OpInsert,
			Key:       []byte(fmt.Sprintf("db1-key-%d", i)),
			Value:     []byte(fmt.Sprintf("db1-value-%d", i)),
			Timestamp: time.Now(),
		}
		wal1.Write(entry1)

		entry2 := Entry{
			LSN:       wal2.NextLSN(),
			TxnID:     uint64(i),
			OpType:    OpInsert,
			Key:       []byte(fmt.Sprintf("db2-key-%d", i)),
			Value:     []byte(fmt.Sprintf("db2-value-%d", i)),
			Timestamp: time.Now(),
		}
		wal2.Write(entry2)
	}

	wal1.Fsync()
	wal2.Fsync()
	wal1.Close()
	wal2.Close()

	// Verify that each database only finds its own WAL files
	wal1Files, err := wal1.findLogFiles()
	if err != nil {
		t.Fatal(err)
	}
	wal2Files, err := wal2.findLogFiles()
	if err != nil {
		t.Fatal(err)
	}

	// Check that file names are different and database-specific
	if len(wal1Files) == 0 {
		t.Error("db1 should have WAL files")
	}
	if len(wal2Files) == 0 {
		t.Error("db2 should have WAL files")
	}

	// Verify file names contain database identifier
	for _, file := range wal1Files {
		if filepath.Base(file)[:6] != "db1.db" {
			t.Errorf("db1 WAL file should start with 'db1.db', got: %s", filepath.Base(file))
		}
	}
	for _, file := range wal2Files {
		if filepath.Base(file)[:6] != "db2.db" {
			t.Errorf("db2 WAL file should start with 'db2.db', got: %s", filepath.Base(file))
		}
	}

	// Verify entries are isolated - read back and check
	entries1, err := ReadAll(wal1Files)
	if err != nil {
		t.Fatal(err)
	}
	entries2, err := ReadAll(wal2Files)
	if err != nil {
		t.Fatal(err)
	}

	if len(entries1) != 5 {
		t.Errorf("db1 should have 5 entries, got %d", len(entries1))
	}
	if len(entries2) != 5 {
		t.Errorf("db2 should have 5 entries, got %d", len(entries2))
	}

	// Verify entries contain correct database-specific keys
	for _, entry := range entries1 {
		if len(entry.Key) >= 3 && string(entry.Key[:3]) != "db1" {
			t.Errorf("db1 WAL contains entry from wrong database: key=%s", entry.Key)
		}
	}
	for _, entry := range entries2 {
		if len(entry.Key) >= 3 && string(entry.Key[:3]) != "db2" {
			t.Errorf("db2 WAL contains entry from wrong database: key=%s", entry.Key)
		}
	}
}

func BenchmarkWALWrite(b *testing.B) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-bench-*")
	if err != nil {
		b.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		b.Fatal(err)
	}
	defer w.Close()

	entry := Entry{
		OpType:    OpInsert,
		Key:       []byte("benchmark-key"),
		Value:     []byte("benchmark-value"),
		Timestamp: time.Now(),
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		entry.LSN = w.NextLSN()
		entry.TxnID = uint64(i)
		w.Write(entry)
	}
	w.Fsync()
}

func BenchmarkWALWriteWithFsync(b *testing.B) {
	// Create temp directory
	dir, err := os.MkdirTemp("", "wal-bench-fsync-*")
	if err != nil {
		b.Fatal(err)
	}
	defer os.RemoveAll(dir)

	// Create WAL
	walPath := filepath.Join(dir, "test.wal")
	w := &WAL{Path: walPath}
	if err := w.Open(); err != nil {
		b.Fatal(err)
	}
	defer w.Close()

	entry := Entry{
		OpType:    OpInsert,
		Key:       []byte("benchmark-key"),
		Value:     []byte("benchmark-value"),
		Timestamp: time.Now(),
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		entry.LSN = w.NextLSN()
		entry.TxnID = uint64(i)
		w.Write(entry)
		w.Fsync() // Fsync on every write
	}
}
