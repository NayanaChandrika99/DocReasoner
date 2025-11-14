// ABOUTME: Transaction support for atomic multi-key operations
// ABOUTME: Implements Begin/Commit/Abort with copy-on-write atomicity

package storage

import (
	"github.com/nainya/treestore/pkg/btree"
)

// KVTX represents a key-value transaction
type KVTX struct {
	db   *KV
	meta []byte // Saved meta for rollback
}

// Begin starts a new transaction
func (db *KV) Begin() *KVTX {
	tx := &KVTX{
		db:   db,
		meta: db.saveMeta(),
	}
	return tx
}

// Commit commits the transaction atomically
func (tx *KVTX) Commit() error {
	return tx.db.updateOrRevert(tx.meta)
}

// Abort rolls back the transaction
func (tx *KVTX) Abort() {
	// Revert in-memory state
	tx.db.loadMeta(tx.meta)

	// Discard temporary pages
	tx.db.page.temp = tx.db.page.temp[:0]
	tx.db.page.updates = make(map[uint64][]byte)
}

// Get retrieves a value within the transaction
func (tx *KVTX) Get(key []byte) ([]byte, bool) {
	return tx.db.tree.Get(key)
}

// Set inserts or updates a key-value pair within the transaction
func (tx *KVTX) Set(key []byte, val []byte) {
	tx.db.tree.Insert(key, val)
}

// Del deletes a key within the transaction
func (tx *KVTX) Del(key []byte) bool {
	return tx.db.tree.Delete(key)
}

// Scan performs a range scan within the transaction
func (tx *KVTX) Scan(start []byte, callback func(key, val []byte) bool) {
	tx.db.tree.Scan(start, callback)
}

// NewIterator creates an iterator within the transaction
func (tx *KVTX) NewIterator() *btree.BIter {
	return tx.db.tree.NewIterator()
}
