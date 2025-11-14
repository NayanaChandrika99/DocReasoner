// ABOUTME: Document data model for hierarchical policy documents
// ABOUTME: Defines Document and Node structures with metadata

package document

import "time"

// Document represents a policy document with metadata
type Document struct {
	PolicyID       string            // Unique policy identifier
	VersionID      string            // Version identifier
	PageIndexDocID string            // PageIndex document ID
	RootNodeID     string            // Root node of hierarchy
	Metadata       map[string]string // Additional metadata
	CreatedAt      time.Time         // Creation timestamp
	UpdatedAt      time.Time         // Last update timestamp
}

// Node represents a hierarchical section in a document
type Node struct {
	NodeID      string   // Unique node identifier
	PolicyID    string   // Parent policy ID
	ParentID    *string  // Parent node ID (nil for root)
	Title       string   // Section title
	PageStart   int      // Starting page number
	PageEnd     int      // Ending page number
	Summary     string   // Section summary
	Text        string   // Full section text
	SectionPath string   // Materialized path (e.g., "1.2.3")
	ChildIDs    []string // Child node IDs
	Depth       int      // Depth in hierarchy (0 for root)
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

// SearchResult represents a full-text search result
type SearchResult struct {
	NodeID   string
	PolicyID string
	Title    string
	Summary  string
	Score    float64 // BM25 score
	Snippet  string  // Text snippet with matches
}

// QueryOptions for hierarchical queries
type QueryOptions struct {
	MaxDepth   int  // Maximum depth to traverse
	IncludeText bool // Include full text in results
}
