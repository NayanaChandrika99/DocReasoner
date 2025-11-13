// ABOUTME: B+Tree node structure and manipulation functions
// ABOUTME: Implements copy-on-write node operations for crash safety

package btree

import (
	"bytes"
	"encoding/binary"
)

const (
	BNODE_NODE = 1 // internal nodes without values
	BNODE_LEAF = 2 // leaf nodes with values
)

const (
	HEADER            = 4
	BTREE_PAGE_SIZE   = 4096
	BTREE_MAX_KEY_SIZE = 1000
	BTREE_MAX_VAL_SIZE = 3000
)

// BNode represents a B+Tree node as a byte slice
type BNode []byte

// btype returns the node type (internal or leaf)
func (node BNode) btype() uint16 {
	return binary.LittleEndian.Uint16(node[0:2])
}

// nkeys returns the number of keys in the node
func (node BNode) nkeys() uint16 {
	return binary.LittleEndian.Uint16(node[2:4])
}

// setHeader sets the node type and number of keys
func (node BNode) setHeader(btype uint16, nkeys uint16) {
	binary.LittleEndian.PutUint16(node[0:2], btype)
	binary.LittleEndian.PutUint16(node[2:4], nkeys)
}

// getPtr returns the pointer at the given index
func (node BNode) getPtr(idx uint16) uint64 {
	if idx >= node.nkeys() {
		panic("index out of range")
	}
	pos := HEADER + 8*idx
	return binary.LittleEndian.Uint64(node[pos:])
}

// setPtr sets the pointer at the given index
func (node BNode) setPtr(idx uint16, val uint64) {
	if idx >= node.nkeys() {
		panic("index out of range")
	}
	pos := HEADER + 8*idx
	binary.LittleEndian.PutUint64(node[pos:], val)
}

// offsetPos returns the position of the offset for the given index
func offsetPos(node BNode, idx uint16) uint16 {
	if idx < 1 || idx > node.nkeys() {
		panic("index out of range")
	}
	return HEADER + 8*node.nkeys() + 2*(idx-1)
}

// getOffset returns the offset for the given index
func (node BNode) getOffset(idx uint16) uint16 {
	if idx == 0 {
		return 0
	}
	return binary.LittleEndian.Uint16(node[offsetPos(node, idx):])
}

// setOffset sets the offset for the given index
func (node BNode) setOffset(idx uint16, offset uint16) {
	binary.LittleEndian.PutUint16(node[offsetPos(node, idx):], offset)
}

// kvPos returns the position of the nth KV pair
func (node BNode) kvPos(idx uint16) uint16 {
	if idx > node.nkeys() {
		panic("index out of range")
	}
	return HEADER + 8*node.nkeys() + 2*node.nkeys() + node.getOffset(idx)
}

// getKey returns the key at the given index
func (node BNode) getKey(idx uint16) []byte {
	if idx >= node.nkeys() {
		panic("index out of range")
	}
	pos := node.kvPos(idx)
	klen := binary.LittleEndian.Uint16(node[pos:])
	return node[pos+4:][:klen]
}

// getVal returns the value at the given index
func (node BNode) getVal(idx uint16) []byte {
	if idx >= node.nkeys() {
		panic("index out of range")
	}
	pos := node.kvPos(idx)
	klen := binary.LittleEndian.Uint16(node[pos+0:])
	vlen := binary.LittleEndian.Uint16(node[pos+2:])
	return node[pos+4+klen:][:vlen]
}

// nbytes returns the node size in bytes
func (node BNode) nbytes() uint16 {
	return node.kvPos(node.nkeys())
}

// nodeLookupLE returns the first kid node whose range intersects the key
// Returns the index where key should be inserted or found
func nodeLookupLE(node BNode, key []byte) uint16 {
	nkeys := node.nkeys()
	found := uint16(0)
	
	// The first key is a copy from the parent node,
	// thus it's always less than or equal to the key
	for i := uint16(1); i < nkeys; i++ {
		cmp := bytes.Compare(node.getKey(i), key)
		if cmp <= 0 {
			found = i
		}
		if cmp >= 0 {
			break
		}
	}
	return found
}

// nodeAppendRange copies a range of KVs from old node to new node
func nodeAppendRange(
	new BNode, old BNode,
	dstNew uint16, srcOld uint16, n uint16,
) {
	if srcOld+n > old.nkeys() {
		panic("source range out of bounds")
	}
	if dstNew+n > new.nkeys() {
		panic("destination range out of bounds")
	}
	
	if n == 0 {
		return
	}
	
	// Copy pointers for internal nodes
	if old.btype() == BNODE_NODE {
		for i := uint16(0); i < n; i++ {
			new.setPtr(dstNew+i, old.getPtr(srcOld+i))
		}
	}
	
	// Copy offsets
	dstBegin := new.getOffset(dstNew)
	srcBegin := old.getOffset(srcOld)

	for i := uint16(1); i <= n; i++ {
		offset := dstBegin + old.getOffset(srcOld+i) - srcBegin
		new.setOffset(dstNew+i, offset)
	}

	// Copy actual KV data
	begin := old.kvPos(srcOld)
	end := old.kvPos(srcOld + n)
	copy(new[new.kvPos(dstNew):], old[begin:end])
}

// nodeAppendKV appends a single KV to the node
func nodeAppendKV(new BNode, idx uint16, ptr uint64, key []byte, val []byte) {
	// Set pointer for internal nodes
	new.setPtr(idx, ptr)
	
	// KV
	pos := new.kvPos(idx)
	binary.LittleEndian.PutUint16(new[pos+0:], uint16(len(key)))
	binary.LittleEndian.PutUint16(new[pos+2:], uint16(len(val)))
	copy(new[pos+4:], key)
	copy(new[pos+4+uint16(len(key)):], val)
	
	// Offset of the next key
	new.setOffset(idx+1, new.getOffset(idx)+4+uint16(len(key)+len(val)))
}

func init() {
	node1max := HEADER + 8 + 2 + 4 + BTREE_MAX_KEY_SIZE + BTREE_MAX_VAL_SIZE
	if node1max > BTREE_PAGE_SIZE {
		panic("node size exceeds page size")
	}
}
