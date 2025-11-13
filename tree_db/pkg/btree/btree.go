// ABOUTME: B+Tree core structure and high-level operations
// ABOUTME: Implements Insert, Get, Delete with copy-on-write for crash safety

package btree

import (
	"bytes"
)

// BTree represents the B+Tree data structure
type BTree struct {
	root uint64                      // pointer to root node (page number)
	get  func(uint64) []byte         // dereference a pointer
	new  func([]byte) uint64         // allocate a new page
	del  func(uint64)                // deallocate a page
}

// Get retrieves a value by key
func (tree *BTree) Get(key []byte) ([]byte, bool) {
	if tree.root == 0 {
		return nil, false
	}

	node := BNode(tree.get(tree.root))
	return treeGet(tree, node, key)
}

// treeGet recursively searches for a key
func treeGet(tree *BTree, node BNode, key []byte) ([]byte, bool) {
	idx := nodeLookupLE(node, key)

	switch node.btype() {
	case BNODE_LEAF:
		if bytes.Equal(key, node.getKey(idx)) {
			return node.getVal(idx), true
		}
		return nil, false
	case BNODE_NODE:
		// Internal node - recurse to child
		childPtr := node.getPtr(idx)
		childNode := BNode(tree.get(childPtr))
		return treeGet(tree, childNode, key)
	default:
		panic("bad node type")
	}
}

// Insert inserts or updates a key-value pair
func (tree *BTree) Insert(key []byte, val []byte) {
	if tree.root == 0 {
		// Create the first node
		root := make([]byte, BTREE_PAGE_SIZE)
		node := BNode(root)
		node.setHeader(BNODE_LEAF, 2)
		// Sentinel key (empty) - covers whole key space
		nodeAppendKV(node, 0, 0, nil, nil)
		nodeAppendKV(node, 1, 0, key, val)
		tree.root = tree.new(root)
		return
	}
	
	node := treeInsert(tree, BNode(tree.get(tree.root)), key, val)
	nsplit, split := nodeSplit3(node)
	tree.del(tree.root)
	
	if nsplit > 1 {
		// Root was split, add new level
		root := make([]byte, BTREE_PAGE_SIZE)
		rootNode := BNode(root)
		rootNode.setHeader(BNODE_NODE, nsplit)
		
		for i, knode := range split[:nsplit] {
			ptr, key := tree.new(knode), knode.getKey(0)
			nodeAppendKV(rootNode, uint16(i), ptr, key, nil)
		}
		tree.root = tree.new(root)
	} else {
		tree.root = tree.new(split[0])
	}
}

// treeInsert inserts a KV into a node, result might be split
func treeInsert(tree *BTree, node BNode, key []byte, val []byte) BNode {
	// Result node - allowed to be bigger than 1 page
	new := make([]byte, 2*BTREE_PAGE_SIZE)
	newNode := BNode(new)
	
	// Where to insert the key?
	idx := nodeLookupLE(node, key)
	
	switch node.btype() {
	case BNODE_LEAF:
		if bytes.Equal(key, node.getKey(idx)) {
			// Update existing key
			leafUpdate(newNode, node, idx, key, val)
		} else {
			// Insert after position
			leafInsert(newNode, node, idx+1, key, val)
		}
	case BNODE_NODE:
		// Internal node - insert to kid node
		nodeInsert(tree, newNode, node, idx, key, val)
	default:
		panic("bad node type")
	}
	
	return newNode
}

// leafInsert adds a new key to a leaf node
func leafInsert(new BNode, old BNode, idx uint16, key []byte, val []byte) {
	new.setHeader(BNODE_LEAF, old.nkeys()+1)
	nodeAppendRange(new, old, 0, 0, idx)
	nodeAppendKV(new, idx, 0, key, val)
	nodeAppendRange(new, old, idx+1, idx, old.nkeys()-idx)
}

// leafUpdate updates an existing key in a leaf node
func leafUpdate(new BNode, old BNode, idx uint16, key []byte, val []byte) {
	new.setHeader(BNODE_LEAF, old.nkeys())
	nodeAppendRange(new, old, 0, 0, idx)
	nodeAppendKV(new, idx, 0, key, val)
	nodeAppendRange(new, old, idx+1, idx+1, old.nkeys()-(idx+1))
}

// nodeInsert handles insertion to an internal node
func nodeInsert(tree *BTree, new BNode, node BNode, idx uint16, key []byte, val []byte) {
	kptr := node.getPtr(idx)
	// Recursive insertion to kid node
	knode := treeInsert(tree, BNode(tree.get(kptr)), key, val)
	// Split the result
	nsplit, split := nodeSplit3(knode)
	// Deallocate the kid node
	tree.del(kptr)
	// Update the kid links
	nodeReplaceKidN(tree, new, node, idx, split[:nsplit]...)
}

// nodeReplaceKidN replaces a link with one or multiple links
func nodeReplaceKidN(tree *BTree, new BNode, old BNode, idx uint16, kids ...BNode) {
	inc := uint16(len(kids))
	new.setHeader(BNODE_NODE, old.nkeys()+inc-1)
	nodeAppendRange(new, old, 0, 0, idx)
	
	for i, node := range kids {
		nodeAppendKV(new, idx+uint16(i), tree.new(node), node.getKey(0), nil)
	}
	
	nodeAppendRange(new, old, idx+inc, idx+1, old.nkeys()-(idx+1))
}

// nodeSplit3 splits a node if it's too big
func nodeSplit3(old BNode) (uint16, [3]BNode) {
	if old.nbytes() <= BTREE_PAGE_SIZE {
		old = old[:BTREE_PAGE_SIZE]
		return 1, [3]BNode{old}
	}
	
	left := make([]byte, 2*BTREE_PAGE_SIZE)
	right := make([]byte, BTREE_PAGE_SIZE)
	nodeSplit2(BNode(left), BNode(right), old)
	
	if BNode(left).nbytes() <= BTREE_PAGE_SIZE {
		left = left[:BTREE_PAGE_SIZE]
		return 2, [3]BNode{BNode(left), BNode(right)}
	}
	
	// Need to split left again
	leftleft := make([]byte, BTREE_PAGE_SIZE)
	middle := make([]byte, BTREE_PAGE_SIZE)
	nodeSplit2(BNode(leftleft), BNode(middle), BNode(left))
	
	return 3, [3]BNode{BNode(leftleft), BNode(middle), BNode(right)}
}

// nodeSplit2 splits an oversized node into 2
func nodeSplit2(left BNode, right BNode, old BNode) {
	// Distribute keys between left and right
	// Target: fill left to ~75% of page size
	nkeys := old.nkeys()
	nleft := uint16(0)
	
	// Find split point
	for i := uint16(0); i < nkeys; i++ {
		nleft = i + 1
		if old.kvPos(nleft) >= BTREE_PAGE_SIZE*3/4 {
			break
		}
	}
	
	// Copy to left and right
	left.setHeader(old.btype(), nleft)
	nodeAppendRange(left, old, 0, 0, nleft)
	
	right.setHeader(old.btype(), nkeys-nleft)
	nodeAppendRange(right, old, 0, nleft, nkeys-nleft)
}

// Delete deletes a key from the tree
func (tree *BTree) Delete(key []byte) bool {
	if tree.root == 0 {
		return false
	}
	
	updated := treeDelete(tree, BNode(tree.get(tree.root)), key)
	if len(updated) == 0 {
		return false // not found
	}
	
	tree.del(tree.root)
	
	if updated.btype() == BNODE_NODE && updated.nkeys() == 1 {
		// Remove a level if root has only 1 child
		tree.root = updated.getPtr(0)
	} else {
		tree.root = tree.new(updated)
	}
	
	return true
}

// treeDelete deletes a key from the tree
func treeDelete(tree *BTree, node BNode, key []byte) BNode {
	idx := nodeLookupLE(node, key)
	
	switch node.btype() {
	case BNODE_LEAF:
		if !bytes.Equal(key, node.getKey(idx)) {
			return nil // not found
		}
		// Delete from leaf
		new := make([]byte, BTREE_PAGE_SIZE)
		leafDelete(BNode(new), node, idx)
		return BNode(new)
	case BNODE_NODE:
		return nodeDelete(tree, node, idx, key)
	default:
		panic("bad node type")
	}
}

// leafDelete removes a key from a leaf node
func leafDelete(new BNode, old BNode, idx uint16) {
	new.setHeader(BNODE_LEAF, old.nkeys()-1)
	nodeAppendRange(new, old, 0, 0, idx)
	nodeAppendRange(new, old, idx, idx+1, old.nkeys()-(idx+1))
}

// nodeDelete deletes a key from an internal node
func nodeDelete(tree *BTree, node BNode, idx uint16, key []byte) BNode {
	kptr := node.getPtr(idx)
	updated := treeDelete(tree, BNode(tree.get(kptr)), key)
	
	if len(updated) == 0 {
		return nil // not found
	}
	
	tree.del(kptr)
	new := make([]byte, BTREE_PAGE_SIZE)
	
	// Check for merging
	mergeDir, sibling := shouldMerge(tree, node, idx, updated)
	
	switch {
	case mergeDir < 0: // merge with left
		merged := make([]byte, BTREE_PAGE_SIZE)
		nodeMerge(BNode(merged), sibling, updated)
		tree.del(node.getPtr(idx - 1))
		nodeReplace2Kid(BNode(new), node, idx-1, tree.new(merged), BNode(merged).getKey(0))
	case mergeDir > 0: // merge with right
		merged := make([]byte, BTREE_PAGE_SIZE)
		nodeMerge(BNode(merged), updated, sibling)
		tree.del(node.getPtr(idx + 1))
		nodeReplace2Kid(BNode(new), node, idx, tree.new(merged), BNode(merged).getKey(0))
	case mergeDir == 0 && updated.nkeys() == 0:
		// Empty child with no sibling
		BNode(new).setHeader(BNODE_NODE, 0)
	case mergeDir == 0 && updated.nkeys() > 0:
		// No merge needed
		nodeReplaceKidN(tree, BNode(new), node, idx, updated)
	}
	
	return BNode(new)
}

// shouldMerge checks if node should be merged with sibling
func shouldMerge(tree *BTree, node BNode, idx uint16, updated BNode) (int, BNode) {
	if updated.nbytes() > BTREE_PAGE_SIZE/4 {
		return 0, nil
	}
	
	// Try left sibling
	if idx > 0 {
		sibling := BNode(tree.get(node.getPtr(idx - 1)))
		merged := sibling.nbytes() + updated.nbytes() - HEADER
		if merged <= BTREE_PAGE_SIZE {
			return -1, sibling
		}
	}
	
	// Try right sibling
	if idx+1 < node.nkeys() {
		sibling := BNode(tree.get(node.getPtr(idx + 1)))
		merged := sibling.nbytes() + updated.nbytes() - HEADER
		if merged <= BTREE_PAGE_SIZE {
			return +1, sibling
		}
	}
	
	return 0, nil
}

// nodeMerge merges two nodes into one
func nodeMerge(new BNode, left BNode, right BNode) {
	new.setHeader(left.btype(), left.nkeys()+right.nkeys())
	nodeAppendRange(new, left, 0, 0, left.nkeys())
	nodeAppendRange(new, right, left.nkeys(), 0, right.nkeys())
}

// nodeReplace2Kid replaces 2 adjacent links with 1
func nodeReplace2Kid(new BNode, old BNode, idx uint16, ptr uint64, key []byte) {
	new.setHeader(BNODE_NODE, old.nkeys()-1)
	nodeAppendRange(new, old, 0, 0, idx)
	nodeAppendKV(new, idx, ptr, key, nil)
	nodeAppendRange(new, old, idx+1, idx+2, old.nkeys()-(idx+2))
}

// GetRoot returns the root pointer
func (tree *BTree) GetRoot() uint64 {
	return tree.root
}

// SetRoot sets the root pointer
func (tree *BTree) SetRoot(root uint64) {
	tree.root = root
}


// SetCallbacks sets the page management callbacks
func (tree *BTree) SetCallbacks(
	getFunc func(uint64) []byte,
	newFunc func([]byte) uint64,
	delFunc func(uint64),
) {
	tree.get = getFunc
	tree.new = newFunc
	tree.del = delFunc
}
