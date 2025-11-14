// ABOUTME: Simplified document storage without IndexManager
// ABOUTME: Direct KV operations for document and node management

package document

import (
	"fmt"
	"strings"

	"github.com/nainya/treestore/pkg/storage"
)

// Prefixes for different index types
const (
	PREFIX_DOCUMENT = uint32(1000)
	PREFIX_NODE     = uint32(2000)
	PREFIX_CHILDREN = uint32(3000)
	PREFIX_PATH     = uint32(4000)
	PREFIX_PAGE     = uint32(5000)
)

// SimpleStore manages documents with direct KV access
type SimpleStore struct {
	kv *storage.KV
}

// NewSimpleStore creates a simplified document store
func NewSimpleStore(kv *storage.KV) *SimpleStore {
	return &SimpleStore{kv: kv}
}

// StoreDocument stores a document and nodes atomically
func (ss *SimpleStore) StoreDocument(doc *Document, nodes []*Node) error {
	tx := ss.kv.Begin()

	// Store each node with composite key (policyID, nodeID)
	for _, node := range nodes {
		key := storage.EncodeKey(PREFIX_NODE, []storage.Value{
			storage.NewBytesValue([]byte(node.PolicyID)),
			storage.NewBytesValue([]byte(node.NodeID)),
		})

		parentID := ""
		if node.ParentID != nil {
			parentID = *node.ParentID
		}

		val := storage.EncodeValues([]storage.Value{
			storage.NewBytesValue([]byte(node.PolicyID)),
			storage.NewBytesValue([]byte(node.NodeID)),
			storage.NewBytesValue([]byte(parentID)),
			storage.NewBytesValue([]byte(node.Title)),
			storage.NewInt64Value(int64(node.PageStart)),
			storage.NewInt64Value(int64(node.PageEnd)),
			storage.NewBytesValue([]byte(node.Summary)),
			storage.NewBytesValue([]byte(node.Text)),
			storage.NewBytesValue([]byte(node.SectionPath)),
			storage.NewInt64Value(int64(node.Depth)),
			storage.NewTimeValue(node.CreatedAt),
			storage.NewTimeValue(node.UpdatedAt),
		})

		tx.Set(key, val)

		// Create secondary index for children lookup
		childKey := storage.EncodeKey(PREFIX_CHILDREN, []storage.Value{
			storage.NewBytesValue([]byte(node.PolicyID)),
			storage.NewBytesValue([]byte(parentID)),
			storage.NewBytesValue([]byte(node.NodeID)),
		})
		tx.Set(childKey, []byte{})
	}

	return tx.Commit()
}

// GetNode retrieves a node by ID
func (ss *SimpleStore) GetNode(policyID, nodeID string) (*Node, error) {
	key := storage.EncodeKey(PREFIX_NODE, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
		storage.NewBytesValue([]byte(nodeID)),
	})

	val, ok := ss.kv.Get(key)
	if !ok {
		return nil, fmt.Errorf("node not found: %s/%s", policyID, nodeID)
	}

	vals, err := storage.DecodeValues(val)
	if err != nil {
		return nil, err
	}

	return parseNodeVals(vals)
}

// GetChildren returns children of a parent node
func (ss *SimpleStore) GetChildren(policyID string, parentID *string) ([]*Node, error) {
	pid := ""
	if parentID != nil {
		pid = *parentID
	}

	// Scan children index
	startKey := storage.EncodeKey(PREFIX_CHILDREN, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
		storage.NewBytesValue([]byte(pid)),
	})

	var children []*Node
	ss.kv.Scan(startKey, func(key, val []byte) bool {
		// Extract nodeID from key
		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 3 {
			return true
		}

		// Check if still in same policy/parent
		if string(vals[0].Str) != policyID || string(vals[1].Str) != pid {
			return false
		}

		// Get full node
		nodeID := string(vals[2].Str)
		node, err := ss.GetNode(policyID, nodeID)
		if err == nil {
			children = append(children, node)
		}

		return true
	})

	return children, nil
}

// GetSubtree retrieves a subtree
func (ss *SimpleStore) GetSubtree(policyID, nodeID string, opts QueryOptions) ([]*Node, error) {
	root, err := ss.GetNode(policyID, nodeID)
	if err != nil {
		return nil, err
	}

	nodes := []*Node{root}
	currentDepth := 0
	toVisit := []*Node{root}

	for len(toVisit) > 0 && (opts.MaxDepth == 0 || currentDepth < opts.MaxDepth) {
		nextLevel := []*Node{}

		for _, parent := range toVisit {
			children, err := ss.GetChildren(policyID, &parent.NodeID)
			if err != nil {
				continue
			}

			nodes = append(nodes, children...)
			nextLevel = append(nextLevel, children...)
		}

		toVisit = nextLevel
		currentDepth++
	}

	return nodes, nil
}

// GetAncestorPath returns path from root to node
func (ss *SimpleStore) GetAncestorPath(policyID, nodeID string) ([]*Node, error) {
	var path []*Node

	currentID := nodeID
	for currentID != "" {
		node, err := ss.GetNode(policyID, currentID)
		if err != nil {
			return nil, err
		}

		path = append([]*Node{node}, path...)

		if node.ParentID == nil {
			break
		}
		currentID = *node.ParentID
	}

	return path, nil
}

// Search performs simple text search
func (ss *SimpleStore) Search(policyID, query string, limit int) ([]*SearchResult, error) {
	terms := strings.Fields(strings.ToLower(query))

	startKey := storage.EncodeKey(PREFIX_NODE, []storage.Value{
		storage.NewBytesValue([]byte(policyID)),
	})

	var results []*SearchResult
	count := 0

	ss.kv.Scan(startKey, func(key, val []byte) bool {
		if count >= limit {
			return false
		}

		vals, err := storage.ExtractValues(key)
		if err != nil || len(vals) < 2 {
			return true
		}

		if string(vals[0].Str) != policyID {
			return false
		}

		nodeVals, err := storage.DecodeValues(val)
		if err != nil {
			return true
		}

		node, err := parseNodeVals(nodeVals)
		if err != nil {
			return true
		}

		score := scoreNode(node, terms)
		if score > 0 {
			results = append(results, &SearchResult{
				NodeID:   node.NodeID,
				PolicyID: node.PolicyID,
				Title:    node.Title,
				Summary:  node.Summary,
				Score:    score,
			})
			count++
		}

		return true
	})

	return results, nil
}

func parseNodeVals(vals []storage.Value) (*Node, error) {
	if len(vals) < 12 {
		return nil, fmt.Errorf("incomplete node data")
	}

	node := &Node{
		PolicyID:    string(vals[0].Str),
		NodeID:      string(vals[1].Str),
		Title:       string(vals[3].Str),
		PageStart:   int(vals[4].I64),
		PageEnd:     int(vals[5].I64),
		Summary:     string(vals[6].Str),
		Text:        string(vals[7].Str),
		SectionPath: string(vals[8].Str),
		Depth:       int(vals[9].I64),
		CreatedAt:   vals[10].Time,
		UpdatedAt:   vals[11].Time,
	}

	if len(vals[2].Str) > 0 {
		pid := string(vals[2].Str)
		node.ParentID = &pid
	}

	return node, nil
}

func scoreNode(node *Node, terms []string) float64 {
	score := 0.0
	titleLower := strings.ToLower(node.Title)
	summaryLower := strings.ToLower(node.Summary)
	textLower := strings.ToLower(node.Text)

	for _, term := range terms {
		if strings.Contains(titleLower, term) {
			score += 3.0
		}
		if strings.Contains(summaryLower, term) {
			score += 2.0
		}
		if strings.Contains(textLower, term) {
			score += 1.0
		}
	}

	return score
}
