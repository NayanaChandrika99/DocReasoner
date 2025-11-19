package wal

import (
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"sync/atomic"
)

const (
	// MaxLogFileSize is the maximum size of a single WAL file (100MB)
	MaxLogFileSize = 100 << 20

	// MaxLogFiles is the maximum number of log files to keep
	MaxLogFiles = 3

	// WALFilePrefix is the prefix for WAL files
	WALFilePrefix = "wal"
)

// WAL represents a Write-Ahead Log
type WAL struct {
	// Path is the base path for WAL files (e.g., "/data/db.wal")
	Path string

	// fd is the current log file descriptor
	fd *os.File

	// mu protects concurrent access to WAL
	mu sync.Mutex

	// lsn is the current Log Sequence Number (atomic)
	lsn uint64

	// fileSize is the current log file size
	fileSize int64

	// fileIndex is the current log file index (0, 1, 2, ...)
	fileIndex int

	// closed indicates whether the WAL is closed
	closed bool
}

// Open opens or creates the WAL
func (w *WAL) Open() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	// Find existing WAL files
	files, err := w.findLogFiles()
	if err != nil && !os.IsNotExist(err) {
		return err
	}

	// Open the latest file or create new one
	if len(files) > 0 {
		// Open latest file in append mode
		latestFile := files[len(files)-1]
		fd, err := os.OpenFile(latestFile, os.O_RDWR|os.O_APPEND, 0644)
		if err != nil {
			return err
		}
		w.fd = fd

		// Get file size
		stat, err := fd.Stat()
		if err != nil {
			return err
		}
		w.fileSize = stat.Size()

		// Parse file index from name
		_, err = fmt.Sscanf(filepath.Base(latestFile), WALFilePrefix+".%d", &w.fileIndex)
		if err != nil {
			w.fileIndex = 0
		}

		// Scan for highest LSN
		maxLSN, err := w.scanForHighestLSN(files)
		if err != nil {
			return err
		}
		atomic.StoreUint64(&w.lsn, maxLSN)
	} else {
		// Create first log file
		logPath := w.logFilePath(0)
		if err := os.MkdirAll(filepath.Dir(logPath), 0755); err != nil {
			return err
		}
		fd, err := os.OpenFile(logPath, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0644)
		if err != nil {
			return err
		}
		w.fd = fd
		w.fileSize = 0
		w.fileIndex = 0
		atomic.StoreUint64(&w.lsn, 0)
	}

	w.closed = false
	return nil
}

// NextLSN returns the next Log Sequence Number
func (w *WAL) NextLSN() uint64 {
	return atomic.AddUint64(&w.lsn, 1)
}

// Write writes an entry to the WAL
func (w *WAL) Write(entry Entry) error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return ErrLogClosed
	}

	// Encode entry
	data := entry.Encode()

	// Check if rotation is needed
	if w.fileSize+int64(len(data)) > MaxLogFileSize {
		if err := w.rotateNoLock(); err != nil {
			return err
		}
	}

	// Write to log file
	n, err := w.fd.Write(data)
	if err != nil {
		return err
	}

	w.fileSize += int64(n)
	return nil
}

// Fsync ensures all written data is persisted to disk
func (w *WAL) Fsync() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return ErrLogClosed
	}

	return w.fd.Sync()
}

// Close closes the WAL
func (w *WAL) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return nil
	}

	err := w.fd.Close()
	w.closed = true
	return err
}

// rotateNoLock rotates to a new log file (caller must hold mu)
func (w *WAL) rotateNoLock() error {
	// Fsync current file before closing
	if err := w.fd.Sync(); err != nil {
		return err
	}

	// Close current file
	if err := w.fd.Close(); err != nil {
		return err
	}

	// Open next file
	w.fileIndex++
	logPath := w.logFilePath(w.fileIndex)
	fd, err := os.OpenFile(logPath, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0644)
	if err != nil {
		return err
	}

	w.fd = fd
	w.fileSize = 0

	// Clean old log files (keep last MaxLogFiles)
	return w.cleanOldLogsNoLock()
}

// cleanOldLogsNoLock removes old log files (caller must hold mu)
func (w *WAL) cleanOldLogsNoLock() error {
	files, err := w.findLogFiles()
	if err != nil {
		return err
	}

	// Keep last MaxLogFiles
	if len(files) > MaxLogFiles {
		toRemove := files[:len(files)-MaxLogFiles]
		for _, f := range toRemove {
			os.Remove(f) // Ignore errors
		}
	}

	return nil
}

// baseName returns the base filename for WAL files (e.g., "mydb.db.wal" from "/path/to/mydb.db.wal")
func (w *WAL) baseName() string {
	return filepath.Base(w.Path)
}

// logFilePath returns the path for a log file with the given index
func (w *WAL) logFilePath(index int) string {
	dir := filepath.Dir(w.Path)
	name := fmt.Sprintf("%s.%03d", w.baseName(), index)
	return filepath.Join(dir, name)
}

// findLogFiles returns all WAL files sorted by index
func (w *WAL) findLogFiles() ([]string, error) {
	dir := filepath.Dir(w.Path)

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}

	var files []string
	for _, entry := range entries {
		if !entry.IsDir() && w.isWALFile(entry.Name()) {
			files = append(files, filepath.Join(dir, entry.Name()))
		}
	}

	// Sort files by index
	sort.Slice(files, func(i, j int) bool {
		var idxI, idxJ int
		pattern := w.baseName() + ".%d"
		fmt.Sscanf(filepath.Base(files[i]), pattern, &idxI)
		fmt.Sscanf(filepath.Base(files[j]), pattern, &idxJ)
		return idxI < idxJ
	})

	return files, nil
}

// isWALFile returns true if the filename is a WAL file for this database
func (w *WAL) isWALFile(name string) bool {
	var index int
	pattern := w.baseName() + ".%d"
	_, err := fmt.Sscanf(name, pattern, &index)
	return err == nil
}

// scanForHighestLSN scans all WAL files and returns the highest LSN
func (w *WAL) scanForHighestLSN(files []string) (uint64, error) {
	var maxLSN uint64

	for _, file := range files {
		fd, err := os.Open(file)
		if err != nil {
			return 0, err
		}

		// Read entries and track max LSN
		for {
			entry, err := w.readEntry(fd)
			if err == io.EOF {
				break
			}
			if err != nil {
				// Skip corrupted entries by seeking forward
				// This prevents infinite loops when corruption occurs
				fd.Seek(1024, io.SeekCurrent)
				continue
			}

			if entry.LSN > maxLSN {
				maxLSN = entry.LSN
			}
		}

		fd.Close()
	}

	return maxLSN, nil
}

// readEntry reads a single entry from the reader
func (w *WAL) readEntry(r io.Reader) (*Entry, error) {
	// Read header first
	header := make([]byte, EntryHeaderSize)
	if _, err := io.ReadFull(r, header); err != nil {
		return nil, err
	}

	// Parse key and value lengths
	keyLen := binary.LittleEndian.Uint32(header[24:28])
	valLen := binary.LittleEndian.Uint32(header[28:32])

	// Read key, value, and CRC32
	dataLen := int(keyLen) + int(valLen) + 4
	data := make([]byte, EntryHeaderSize+dataLen)
	copy(data, header)
	if _, err := io.ReadFull(r, data[EntryHeaderSize:]); err != nil {
		return nil, err
	}

	// Decode entry
	return DecodeEntry(data)
}
