// ABOUTME: Free list for page recycling in TreeStore
// ABOUTME: Implements unrolled linked list with self-managing nodes

package storage

import (
	"encoding/binary"
)

const (
	FREE_LIST_HEADER = 8
	FREE_LIST_CAP    = (BTREE_PAGE_SIZE - FREE_LIST_HEADER) / 8
)

// LNode represents a free list node (linked list node)
type LNode []byte

// getNext returns the pointer to the next node
func (node LNode) getNext() uint64 {
	return binary.LittleEndian.Uint64(node[0:8])
}

// setNext sets the pointer to the next node
func (node LNode) setNext(next uint64) {
	binary.LittleEndian.PutUint64(node[0:8], next)
}

// getPtr returns the pointer at the given index
func (node LNode) getPtr(idx int) uint64 {
	offset := FREE_LIST_HEADER + idx*8
	return binary.LittleEndian.Uint64(node[offset:])
}

// setPtr sets the pointer at the given index
func (node LNode) setPtr(idx int, ptr uint64) {
	offset := FREE_LIST_HEADER + idx*8
	binary.LittleEndian.PutUint64(node[offset:], ptr)
}

// FreeList manages a pool of freed pages for reuse
type FreeList struct {
	// Callbacks for page management
	get func(uint64) []byte         // read a page
	new func([]byte) uint64         // allocate a new page
	set func(uint64, []byte)        // update a page in-place

	// Head of the list (pop from here)
	headPage uint64
	headSeq  uint64

	// Tail of the list (push to here)
	tailPage uint64
	tailSeq  uint64

	// Maximum sequence to prevent consuming newly added items
	maxSeq uint64
}

// Total returns the number of items in the free list
func (fl *FreeList) Total() int {
	if fl.headSeq >= fl.tailSeq {
		return 0
	}
	return int(fl.tailSeq - fl.headSeq)
}

// PopHead removes and returns a page from the head of the list
func (fl *FreeList) PopHead() uint64 {
	if fl.headSeq >= fl.tailSeq {
		return 0 // empty
	}

	// maxSeq controls which items can be popped:
	// - During a transaction: maxSeq is frozen, preventing newly freed pages from being reused
	// - After commit: maxSeq = tailSeq, allowing all pages to be reused
	// Only block if maxSeq < tailSeq (there are new items) AND we've reached maxSeq
	if fl.maxSeq > 0 && fl.maxSeq < fl.tailSeq && fl.headSeq >= fl.maxSeq {
		return 0 // would consume newly added items not yet committed
	}

	if fl.headPage == 0 {
		return 0 // invalid state
	}

	node := LNode(fl.get(fl.headPage))
	idx := int(fl.headSeq % FREE_LIST_CAP)
	ptr := node.getPtr(idx)

	fl.headSeq++

	// Move to next node if current is exhausted
	if fl.headSeq%FREE_LIST_CAP == 0 {
		nextPage := node.getNext()
		if nextPage != 0 {
			// Free the current head node by reusing it
			fl.PushTail(fl.headPage)
			fl.headPage = nextPage
		}
	}

	return ptr
}

// PushTail adds a page to the tail of the list
func (fl *FreeList) PushTail(ptr uint64) {
	// Get or create tail node
	if fl.tailPage == 0 {
		// First node - allocate it
		page := make([]byte, BTREE_PAGE_SIZE)
		node := LNode(page)
		node.setNext(0)
		fl.tailPage = fl.new(page)
	}

	idx := int(fl.tailSeq % FREE_LIST_CAP)

	// If current node is full, allocate a new one
	if idx == 0 && fl.tailSeq > 0 {
		// Allocate new tail node
		newPage := make([]byte, BTREE_PAGE_SIZE)
		newNode := LNode(newPage)
		newNode.setNext(0)
		newTail := fl.new(newPage)

		// Link current tail to new tail
		oldPage := make([]byte, BTREE_PAGE_SIZE)
		copy(oldPage, fl.get(fl.tailPage))
		oldNode := LNode(oldPage)
		oldNode.setNext(newTail)
		fl.set(fl.tailPage, oldPage)

		// Move to new tail
		fl.tailPage = newTail
		idx = 0
	}

	// Store the pointer in a new copy of the page
	page := make([]byte, BTREE_PAGE_SIZE)
	copy(page, fl.get(fl.tailPage))
	node := LNode(page)
	node.setPtr(idx, ptr)
	fl.set(fl.tailPage, page)
	fl.tailSeq++
}

// SetMaxSeq sets the maximum sequence to prevent consuming newly added items
func (fl *FreeList) SetMaxSeq() {
	fl.maxSeq = fl.tailSeq
}

// Serialize serializes the free list metadata to bytes
func (fl *FreeList) Serialize() []byte {
	data := make([]byte, 40)
	binary.LittleEndian.PutUint64(data[0:], fl.headPage)
	binary.LittleEndian.PutUint64(data[8:], fl.headSeq)
	binary.LittleEndian.PutUint64(data[16:], fl.tailPage)
	binary.LittleEndian.PutUint64(data[24:], fl.tailSeq)
	binary.LittleEndian.PutUint64(data[32:], fl.maxSeq)
	return data
}

// Deserialize loads free list metadata from bytes
func (fl *FreeList) Deserialize(data []byte) {
	fl.headPage = binary.LittleEndian.Uint64(data[0:])
	fl.headSeq = binary.LittleEndian.Uint64(data[8:])
	fl.tailPage = binary.LittleEndian.Uint64(data[16:])
	fl.tailSeq = binary.LittleEndian.Uint64(data[24:])
	fl.maxSeq = binary.LittleEndian.Uint64(data[32:])
}
