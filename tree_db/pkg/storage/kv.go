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
	META_PAGE_SIZE  = 80                                 // Meta page size (expanded for free list)
)

// KV represents a persistent key-value store
type KV struct {
	Path string

	// File descriptor
	fd int

	// B+Tree
	tree btree.BTree

	// Free list for page recycling
	free FreeList

	// Memory-mapped file
	mmap struct {
		total  int      // Total mmap size
		chunks [][]byte // Multiple mmap regions
	}

	// Page management
	page struct {
		flushed uint64              // Number of pages flushed to disk
		temp    [][]byte            // Temporary pages pending flush
		updates map[uint64][]byte   // In-place updates
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

	// Initialize page updates map
	db.page.updates = make(map[uint64][]byte)

	// Setup free list callbacks
	db.free.get = func(ptr uint64) []byte {
		return db.pageRead(ptr)
	}
	db.free.new = func(node []byte) uint64 {
		return db.pageAppend(node)
	}
	db.free.set = func(ptr uint64, node []byte) {
		db.pageWrite(ptr, node)
	}

	// After loading from disk, all freed pages are available for reuse
	// maxSeq will be set at the start of each transaction
	if db.free.tailSeq > 0 {
		db.free.maxSeq = db.free.tailSeq
	}

	// Setup B+Tree callbacks
	db.tree.SetCallbacks(
		func(ptr uint64) []byte {
			return db.pageRead(ptr)
		},
		func(node []byte) uint64 {
			return db.pageAlloc(node)
		},
		func(ptr uint64) {
			db.pageFree(ptr)
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

// Scan performs a range scan starting from the given key
func (db *KV) Scan(start []byte, callback func(key, val []byte) bool) {
	db.tree.Scan(start, callback)
}

// pageRead reads a page by pointer
func (db *KV) pageRead(ptr uint64) []byte {
	// Check pending updates first
	if page, ok := db.page.updates[ptr]; ok {
		return page
	}

	// Check temp pages
	if ptr >= db.page.flushed {
		idx := ptr - db.page.flushed
		if idx < uint64(len(db.page.temp)) {
			return db.page.temp[idx]
		}
	}

	// Read from mmap
	start := uint64(0)
	for _, chunk := range db.mmap.chunks {
		end := start + uint64(len(chunk))/BTREE_PAGE_SIZE
		if ptr < end {
			offset := BTREE_PAGE_SIZE * (ptr - start)
			return chunk[offset : offset+BTREE_PAGE_SIZE]
		}
		start = end
	}
	panic(fmt.Sprintf("bad page pointer: %d (flushed: %d, temp: %d)", ptr, db.page.flushed, len(db.page.temp)))
}

// pageAlloc allocates a new page (tries free list first)
func (db *KV) pageAlloc(node []byte) uint64 {
	if len(node) != BTREE_PAGE_SIZE {
		panic("page size mismatch")
	}

	// Try to get a page from free list
	ptr := db.free.PopHead()
	if ptr != 0 {
		// Reuse freed page
		db.page.updates[ptr] = node
		return ptr
	}

	// Append new page
	return db.pageAppend(node)
}

// pageAppend allocates a new page at the end
func (db *KV) pageAppend(node []byte) uint64 {
	if len(node) != BTREE_PAGE_SIZE {
		panic("page size mismatch")
	}

	ptr := db.page.flushed + uint64(len(db.page.temp))
	db.page.temp = append(db.page.temp, node)
	return ptr
}

// pageWrite updates a page in-place
func (db *KV) pageWrite(ptr uint64, node []byte) {
	if len(node) != BTREE_PAGE_SIZE {
		panic("page size mismatch")
	}
	db.page.updates[ptr] = node
}

// pageFree adds a page to the free list
func (db *KV) pageFree(ptr uint64) {
	// Only free pages that were already flushed to disk
	// Temp pages can't be reused until they're committed
	if ptr < db.page.flushed {
		db.free.PushTail(ptr)
	}
}

// saveMeta saves current meta state to byte slice
func (db *KV) saveMeta() []byte {
	var data [META_PAGE_SIZE]byte
	copy(data[:16], []byte(DB_SIG))
	binary.LittleEndian.PutUint64(data[16:], db.tree.GetRoot())
	binary.LittleEndian.PutUint64(data[24:], db.page.flushed)

	// Save free list metadata
	freeData := db.free.Serialize()
	copy(data[32:], freeData)

	return data[:]
}

// loadMeta loads meta state from byte slice
func (db *KV) loadMeta(data []byte) {
	db.tree.SetRoot(binary.LittleEndian.Uint64(data[16:]))
	db.page.flushed = binary.LittleEndian.Uint64(data[24:])

	// Load free list metadata
	db.free.Deserialize(data[32:72])
}

// readMeta reads and validates meta page from disk
func (db *KV) readMeta() error {
	data := db.mmap.chunks[0][:META_PAGE_SIZE]

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

	// Save current tailSeq and freeze free list for this transaction
	savedMaxSeq := db.free.maxSeq
	db.free.SetMaxSeq()

	// Two-phase update
	err := db.updateFile()

	if err != nil {
		// Revert in-memory state
		db.loadMeta(meta)
		db.page.temp = db.page.temp[:0]
		db.page.updates = make(map[uint64][]byte)
		db.free.maxSeq = savedMaxSeq
		db.failed = true
	} else {
		// Success - all freed pages including newly freed ones are now available
		db.free.maxSeq = db.free.tailSeq
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
	// Write in-place updates first
	for ptr, page := range db.page.updates {
		offset := int64(ptr * BTREE_PAGE_SIZE)
		if _, err := syscall.Pwrite(db.fd, page, offset); err != nil {
			return err
		}
	}

	// Clear updates after writing
	db.page.updates = make(map[uint64][]byte)

	// Write new pages
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
