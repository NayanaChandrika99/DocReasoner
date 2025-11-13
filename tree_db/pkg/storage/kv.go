// ABOUTME: Disk-based KV store with B+Tree persistence
// ABOUTME: Implements copy-on-write with meta page and two-phase fsync updates

package storage

import (
	"encoding/binary"
	"fmt"
	"os"
	"path"
	"syscall"

	"github.com/nainya/treestore/pkg/btree"
)

const (
	DB_SIG          = "TreeStore01\x00\x00\x00\x00\x00" // Database signature (16 bytes)
	BTREE_PAGE_SIZE = 4096                               // Must match btree package
)

// KV represents a persistent key-value store
type KV struct {
	Path string

	// File descriptor
	fd int

	// B+Tree
	tree btree.BTree

	// Memory-mapped file
	mmap struct {
		total  int      // Total mmap size
		chunks [][]byte // Multiple mmap regions
	}

	// Page management
	page struct {
		flushed uint64   // Number of pages flushed to disk
		temp    [][]byte // Temporary pages pending flush
	}

	// Error recovery
	failed bool // Did last update fail?
}

// Open opens or creates a database file
func (db *KV) Open() error {
	// Create or open file with directory fsync
	fd, err := createFileSync(db.Path)
	if err != nil {
		return err
	}
	db.fd = fd

	// Get file size
	var stat syscall.Stat_t
	if err := syscall.Fstat(db.fd, &stat); err != nil {
		return fmt.Errorf("fstat: %w", err)
	}
	fileSize := stat.Size

	// Initialize mmap
	if fileSize == 0 {
		// Empty file - reserve meta page
		db.page.flushed = 1
	} else {
		// Existing file - read meta page
		mmapSize := 64 << 20 // Start with 64MB
		if int(fileSize) > mmapSize {
			mmapSize = int(fileSize)
		}

		chunk, err := syscall.Mmap(
			db.fd, 0, mmapSize,
			syscall.PROT_READ, syscall.MAP_SHARED,
		)
		if err != nil {
			return fmt.Errorf("mmap: %w", err)
		}

		db.mmap.total = mmapSize
		db.mmap.chunks = append(db.mmap.chunks, chunk)

		// Read meta page
		if err := db.readMeta(); err != nil {
			return err
		}
	}

	// Setup B+Tree callbacks - fields are unexported
	// We'll set them via the struct literal with field tags
	db.tree.SetCallbacks(
		func(ptr uint64) []byte {
			return db.pageRead(ptr)
		},
		func(node []byte) uint64 {
			return db.pageAppend(node)
		},
		func(uint64) {
			// Deletion handled by free list (Week 3)
		},
	)

	return nil
}

// Close closes the database
func (db *KV) Close() error {
	// Unmap all chunks
	for _, chunk := range db.mmap.chunks {
		if err := syscall.Munmap(chunk); err != nil {
			return err
		}
	}

	// Close file
	return syscall.Close(db.fd)
}

// Get retrieves a value by key
func (db *KV) Get(key []byte) ([]byte, bool) {
	return db.tree.Get(key)
}

// Set inserts or updates a key-value pair
func (db *KV) Set(key []byte, val []byte) error {
	// Save current meta state for potential rollback
	meta := db.saveMeta()

	// Perform B+Tree insert
	db.tree.Insert(key, val)

	// Two-phase update
	return db.updateOrRevert(meta)
}

// Del deletes a key
func (db *KV) Del(key []byte) (bool, error) {
	meta := db.saveMeta()

	deleted := db.tree.Delete(key)
	if !deleted {
		return false, nil
	}

	err := db.updateOrRevert(meta)
	return deleted, err
}

// pageRead reads a page by pointer
func (db *KV) pageRead(ptr uint64) []byte {
	start := uint64(0)
	for _, chunk := range db.mmap.chunks {
		end := start + uint64(len(chunk))/BTREE_PAGE_SIZE
		if ptr < end {
			offset := BTREE_PAGE_SIZE * (ptr - start)
			return chunk[offset : offset+BTREE_PAGE_SIZE]
		}
		start = end
	}
	panic("bad page pointer")
}

// pageAppend allocates a new page
func (db *KV) pageAppend(node []byte) uint64 {
	if len(node) != BTREE_PAGE_SIZE {
		panic("page size mismatch")
	}

	ptr := db.page.flushed + uint64(len(db.page.temp))
	db.page.temp = append(db.page.temp, node)
	return ptr
}

// saveMeta saves current meta state to byte slice
func (db *KV) saveMeta() []byte {
	var data [32]byte
	copy(data[:16], []byte(DB_SIG))
	binary.LittleEndian.PutUint64(data[16:], db.tree.GetRoot())
	binary.LittleEndian.PutUint64(data[24:], db.page.flushed)
	return data[:]
}

// loadMeta loads meta state from byte slice
func (db *KV) loadMeta(data []byte) {
	db.tree.SetRoot(binary.LittleEndian.Uint64(data[16:]))
	db.page.flushed = binary.LittleEndian.Uint64(data[24:])
}

// readMeta reads and validates meta page from disk
func (db *KV) readMeta() error {
	data := db.mmap.chunks[0][:32]

	// Verify signature
	sig := string(data[:16])
	if sig != DB_SIG {
		return fmt.Errorf("invalid database signature: %s", sig)
	}

	db.loadMeta(data)
	return nil
}

// updateOrRevert performs two-phase update with error recovery
func (db *KV) updateOrRevert(meta []byte) error {
	// Recover from previous failure
	if db.failed {
		if err := db.writeMeta(meta); err != nil {
			return err
		}
		if err := syscall.Fsync(db.fd); err != nil {
			return err
		}
		db.failed = false
	}

	// Two-phase update
	err := db.updateFile()

	if err != nil {
		// Revert in-memory state
		db.loadMeta(meta)
		db.page.temp = db.page.temp[:0]
		db.failed = true
	}

	return err
}

// updateFile performs the two-phase fsync update
func (db *KV) updateFile() error {
	// Phase 1: Write new pages
	if err := db.writePages(); err != nil {
		return err
	}

	// Phase 2: fsync to ensure pages are durable
	if err := syscall.Fsync(db.fd); err != nil {
		return err
	}

	// Phase 3: Update meta page atomically
	if err := db.writeMeta(db.saveMeta()); err != nil {
		return err
	}

	// Phase 4: fsync to make meta page durable
	return syscall.Fsync(db.fd)
}

// writePages writes temporary pages to disk
func (db *KV) writePages() error {
	if len(db.page.temp) == 0 {
		return nil
	}

	// Extend mmap if needed
	size := int(db.page.flushed+uint64(len(db.page.temp))) * BTREE_PAGE_SIZE
	if err := db.extendMmap(size); err != nil {
		return err
	}

	// Write pages
	offset := int64(db.page.flushed * BTREE_PAGE_SIZE)
	for _, page := range db.page.temp {
		if _, err := syscall.Pwrite(db.fd, page, offset); err != nil {
			return err
		}
		offset += BTREE_PAGE_SIZE
	}

	// Update state
	db.page.flushed += uint64(len(db.page.temp))
	db.page.temp = db.page.temp[:0]

	return nil
}

// writeMeta writes meta page at offset 0
func (db *KV) writeMeta(data []byte) error {
	_, err := syscall.Pwrite(db.fd, data, 0)
	if err != nil {
		return fmt.Errorf("write meta page: %w", err)
	}
	return nil
}

// extendMmap extends memory mapping if needed
func (db *KV) extendMmap(size int) error {
	if size <= db.mmap.total {
		return nil
	}

	// Double the allocation size
	alloc := max(db.mmap.total, 64<<20)
	for db.mmap.total+alloc < size {
		alloc *= 2
	}

	// Create new mapping
	chunk, err := syscall.Mmap(
		db.fd, int64(db.mmap.total), alloc,
		syscall.PROT_READ, syscall.MAP_SHARED,
	)
	if err != nil {
		return fmt.Errorf("mmap: %w", err)
	}

	db.mmap.total += alloc
	db.mmap.chunks = append(db.mmap.chunks, chunk)

	return nil
}

// createFileSync creates/opens file with directory fsync
func createFileSync(file string) (int, error) {
	// Open or create file
	flags := os.O_RDWR | os.O_CREATE
	fd, err := syscall.Open(file, flags, 0o644)
	if err != nil {
		return -1, fmt.Errorf("open file: %w", err)
	}

	// Open directory for fsync
	dirfd, err := syscall.Open(path.Dir(file), os.O_RDONLY, 0)
	if err != nil {
		_ = syscall.Close(fd)
		return -1, fmt.Errorf("open directory: %w", err)
	}
	defer syscall.Close(dirfd)

	// Fsync directory
	if err = syscall.Fsync(dirfd); err != nil {
		_ = syscall.Close(fd)
		return -1, fmt.Errorf("fsync directory: %w", err)
	}

	return fd, nil
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
