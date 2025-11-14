// ABOUTME: Secondary index management for multi-access patterns
// ABOUTME: Maintains multiple B+Trees with automatic consistency

package storage

import (
	"fmt"

	"github.com/nainya/treestore/pkg/btree"
)

// IndexDef defines a secondary index
type IndexDef struct {
	Name    string   // Index name
	Columns []string // Columns to index (in order)
	Prefix  uint32   // Unique prefix for this index
}

// IndexManager manages multiple secondary indexes
type IndexManager struct {
	db      *KV
	primary *btree.BTree // Primary index
	indexes map[string]*IndexInfo
}

// IndexInfo holds index metadata
type IndexInfo struct {
	Def  IndexDef
	Tree *btree.BTree
}

// NewIndexManager creates a new index manager
func NewIndexManager(db *KV) *IndexManager {
	return &IndexManager{
		db:      db,
		primary: &db.tree,
		indexes: make(map[string]*IndexInfo),
	}
}

// AddIndex registers a new secondary index
func (im *IndexManager) AddIndex(def IndexDef) error {
	if _, exists := im.indexes[def.Name]; exists {
		return fmt.Errorf("index %s already exists", def.Name)
	}

	// Create a new B+Tree for this index
	// It shares the same page storage as the primary tree
	tree := &btree.BTree{}
	tree.SetCallbacks(
		func(ptr uint64) []byte {
			return im.db.pageRead(ptr)
		},
		func(node []byte) uint64 {
			return im.db.pageAlloc(node)
		},
		func(ptr uint64) {
			im.db.pageFree(ptr)
		},
	)

	im.indexes[def.Name] = &IndexInfo{
		Def:  def,
		Tree: tree,
	}

	return nil
}

// IndexedTx represents a transaction with automatic index maintenance
type IndexedTx struct {
	im      *IndexManager
	tx      *KVTX
	updates map[string]IndexUpdate // Track updates for index maintenance
}

// IndexUpdate tracks changes for index maintenance
type IndexUpdate struct {
	OldKey []byte
	OldVal []byte
	NewKey []byte
	NewVal []byte
	IsNew  bool
}

// Begin starts a new indexed transaction
func (im *IndexManager) Begin() *IndexedTx {
	return &IndexedTx{
		im:      im,
		tx:      im.db.Begin(),
		updates: make(map[string]IndexUpdate),
	}
}

// Set inserts/updates a record and maintains all indexes
func (itx *IndexedTx) Set(primaryKey []Value, record map[string]Value) error {
	// Encode primary key
	pkBytes := EncodeValues(primaryKey)

	// Check if this is an update or insert
	oldVal, exists := itx.tx.Get(pkBytes)

	// Store the primary record
	recBytes := encodeRecord(record)
	itx.tx.Set(pkBytes, recBytes)

	// Update all secondary indexes
	for name, info := range itx.im.indexes {
		// Extract index key from record
		indexKey := extractIndexKey(record, info.Def.Columns, primaryKey)

		if exists {
			// Delete old index entry
			oldRecord, err := decodeRecord(oldVal)
			if err != nil {
				return err
			}
			oldIndexKey := extractIndexKey(oldRecord, info.Def.Columns, primaryKey)
			info.Tree.Delete(EncodeKey(info.Def.Prefix, oldIndexKey))
		}

		// Insert new index entry (value is empty for secondary indexes)
		info.Tree.Insert(EncodeKey(info.Def.Prefix, indexKey), []byte{})

		// Track update
		itx.updates[name] = IndexUpdate{
			OldKey: pkBytes,
			OldVal: oldVal,
			NewKey: pkBytes,
			NewVal: recBytes,
			IsNew:  !exists,
		}
	}

	return nil
}

// Get retrieves a record by primary key
func (itx *IndexedTx) Get(primaryKey []Value) (map[string]Value, bool, error) {
	pkBytes := EncodeValues(primaryKey)
	val, ok := itx.tx.Get(pkBytes)
	if !ok {
		return nil, false, nil
	}

	record, err := decodeRecord(val)
	if err != nil {
		return nil, false, err
	}

	return record, true, nil
}

// Del deletes a record and maintains all indexes
func (itx *IndexedTx) Del(primaryKey []Value) (bool, error) {
	pkBytes := EncodeValues(primaryKey)

	// Get old value for index cleanup
	oldVal, exists := itx.tx.Get(pkBytes)
	if !exists {
		return false, nil
	}

	// Delete from primary
	itx.tx.Del(pkBytes)

	// Delete from all secondary indexes
	oldRecord, err := decodeRecord(oldVal)
	if err != nil {
		return false, err
	}

	for _, info := range itx.im.indexes {
		indexKey := extractIndexKey(oldRecord, info.Def.Columns, primaryKey)
		info.Tree.Delete(EncodeKey(info.Def.Prefix, indexKey))
	}

	return true, nil
}

// ScanIndex performs a range scan on a secondary index
func (itx *IndexedTx) ScanIndex(indexName string, start []Value, callback func(primaryKey []Value, record map[string]Value) bool) error {
	info, ok := itx.im.indexes[indexName]
	if !ok {
		return fmt.Errorf("index %s not found", indexName)
	}

	startKey := EncodeKey(info.Def.Prefix, start)

	// Scan the secondary index
	info.Tree.Scan(startKey, func(indexKey, _ []byte) bool {
		// Extract primary key from index key
		vals, err := ExtractValues(indexKey)
		if err != nil {
			return false
		}

		// The last values in the index key are the primary key
		// (secondary indexes include primary key to ensure uniqueness)
		numIndexCols := len(info.Def.Columns)
		if len(vals) < numIndexCols {
			return false
		}

		primaryKey := vals[numIndexCols:]

		// Fetch full record
		pkBytes := EncodeValues(primaryKey)
		recVal, ok := itx.tx.Get(pkBytes)
		if !ok {
			return true // Skip missing records
		}

		record, err := decodeRecord(recVal)
		if err != nil {
			return false
		}

		return callback(primaryKey, record)
	})

	return nil
}

// Commit commits the transaction
func (itx *IndexedTx) Commit() error {
	return itx.tx.Commit()
}

// Abort aborts the transaction
func (itx *IndexedTx) Abort() {
	itx.tx.Abort()
}

// Helper functions

func extractIndexKey(record map[string]Value, columns []string, primaryKey []Value) []Value {
	// Extract index columns from record
	indexVals := make([]Value, 0, len(columns)+len(primaryKey))

	for _, col := range columns {
		if val, ok := record[col]; ok {
			indexVals = append(indexVals, val)
		}
	}

	// Append primary key to ensure uniqueness
	indexVals = append(indexVals, primaryKey...)

	return indexVals
}

func encodeRecord(record map[string]Value) []byte {
	// Simple encoding: count + (name_len + name + value)*
	out := make([]byte, 0, 256)

	// Write number of fields
	out = append(out, byte(len(record)))

	for name, val := range record {
		// Write field name length
		out = append(out, byte(len(name)))
		// Write field name
		out = append(out, []byte(name)...)
		// Write field value (encoded)
		valBytes := EncodeValues([]Value{val})
		out = append(out, valBytes...)
	}

	return out
}

func decodeRecord(data []byte) (map[string]Value, error) {
	if len(data) == 0 {
		return make(map[string]Value), nil
	}

	record := make(map[string]Value)
	pos := 0

	// Read number of fields
	numFields := int(data[pos])
	pos++

	for i := 0; i < numFields; i++ {
		if pos >= len(data) {
			return nil, fmt.Errorf("incomplete record at field %d", i)
		}

		// Read field name length
		nameLen := int(data[pos])
		pos++

		if pos+nameLen > len(data) {
			return nil, fmt.Errorf("incomplete field name at pos %d", pos)
		}

		// Read field name
		name := string(data[pos : pos+nameLen])
		pos += nameLen

		// Read field value
		vals, err := DecodeValues(data[pos:])
		if err != nil {
			return nil, err
		}

		if len(vals) == 0 {
			return nil, fmt.Errorf("no value for field %s", name)
		}

		record[name] = vals[0]

		// Advance position (need to re-encode to get exact length)
		valBytes := EncodeValues([]Value{vals[0]})
		pos += len(valBytes)
	}

	return record, nil
}
