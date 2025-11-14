// ABOUTME: B+Tree iterator for range scans
// ABOUTME: Implements SeekLE and Next for forward iteration

package btree

import "bytes"

// BIter represents an iterator over the B+Tree
type BIter struct {
	tree *BTree
	path []BNode  // Stack of nodes from root to current leaf
	pos  []uint16 // Stack of positions at each level
}

// NewIterator creates a new iterator for the tree
func (tree *BTree) NewIterator() *BIter {
	return &BIter{
		tree: tree,
		path: make([]BNode, 0, 8),   // Pre-allocate for typical tree height
		pos:  make([]uint16, 0, 8),
	}
}

// SeekLE positions the iterator at the first key <= the given key
// Returns false if the tree is empty
func (iter *BIter) SeekLE(key []byte) bool {
	iter.path = iter.path[:0]
	iter.pos = iter.pos[:0]

	if iter.tree.root == 0 {
		return false
	}

	// Navigate from root to leaf
	node := BNode(iter.tree.get(iter.tree.root))
	for {
		iter.path = append(iter.path, node)
		idx := nodeLookupLE(node, key)
		iter.pos = append(iter.pos, idx)

		if node.btype() == BNODE_LEAF {
			break
		}

		// Internal node - descend to child
		ptr := node.getPtr(idx)
		node = BNode(iter.tree.get(ptr))
	}

	return true
}

// Valid returns true if the iterator is positioned at a valid key
func (iter *BIter) Valid() bool {
	if len(iter.path) == 0 {
		return false
	}

	leaf := iter.path[len(iter.path)-1]
	pos := iter.pos[len(iter.pos)-1]

	// Check if we're past the last key
	return pos < leaf.nkeys()
}

// Key returns the current key
func (iter *BIter) Key() []byte {
	if !iter.Valid() {
		return nil
	}

	leaf := iter.path[len(iter.path)-1]
	pos := iter.pos[len(iter.pos)-1]
	return leaf.getKey(pos)
}

// Val returns the current value
func (iter *BIter) Val() []byte {
	if !iter.Valid() {
		return nil
	}

	leaf := iter.path[len(iter.path)-1]
	pos := iter.pos[len(iter.pos)-1]
	return leaf.getVal(pos)
}

// Next advances the iterator to the next key
// Returns false if there are no more keys
func (iter *BIter) Next() bool {
	if len(iter.path) == 0 {
		return false
	}

	// Try to advance within current leaf
	leafIdx := len(iter.pos) - 1
	iter.pos[leafIdx]++

	leaf := iter.path[leafIdx]
	if iter.pos[leafIdx] < leaf.nkeys() {
		return true // Still within current leaf
	}

	// Need to move to next leaf - backtrack up the tree
	// Pop the leaf level
	iter.path = iter.path[:leafIdx]
	iter.pos = iter.pos[:leafIdx]

	// Backtrack to find a parent with more children
	for len(iter.pos) > 0 {
		parentIdx := len(iter.pos) - 1
		iter.pos[parentIdx]++

		parent := iter.path[parentIdx]
		if iter.pos[parentIdx] < parent.nkeys() {
			// Found a parent with more children - descend to leftmost leaf
			return iter.descendToLeftmost()
		}

		// This parent is exhausted too, pop it
		iter.path = iter.path[:parentIdx]
		iter.pos = iter.pos[:parentIdx]
	}

	// Reached end of tree
	return false
}

// descendToLeftmost descends from the current position to the leftmost leaf
func (iter *BIter) descendToLeftmost() bool {
	for {
		parentIdx := len(iter.path) - 1
		parent := iter.path[parentIdx]
		pos := iter.pos[parentIdx]

		// Get child pointer
		ptr := parent.getPtr(pos)
		child := BNode(iter.tree.get(ptr))

		// Add child to path
		iter.path = append(iter.path, child)

		if child.btype() == BNODE_LEAF {
			// Reached leaf - start at first key
			iter.pos = append(iter.pos, 0)
			return true
		}

		// Internal node - continue descending
		iter.pos = append(iter.pos, 0)
	}
}

// Scan executes a range scan from the given start key
// Calls the callback for each key-value pair until callback returns false
func (tree *BTree) Scan(start []byte, callback func(key, val []byte) bool) {
	iter := tree.NewIterator()
	if !iter.SeekLE(start) {
		return
	}

	// If seeked key is less than start, advance to next
	if bytes.Compare(iter.Key(), start) < 0 {
		if !iter.Next() {
			return
		}
	}

	// Iterate until callback returns false
	for iter.Valid() {
		if !callback(iter.Key(), iter.Val()) {
			return
		}
		if !iter.Next() {
			return
		}
	}
}
