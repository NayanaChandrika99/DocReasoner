// ABOUTME: Metadata storage data model
// ABOUTME: Supports custom attributes and flexible indexing

package metadata

import "time"

// MetadataEntry represents a single metadata attribute
type MetadataEntry struct {
	EntityType string    // Type of entity (document, node, version)
	EntityID   string    // Entity identifier
	Key        string    // Metadata key
	Value      string    // Metadata value
	ValueType  string    // Type hint (string, number, boolean, date)
	CreatedAt  time.Time // When metadata was added
	UpdatedAt  time.Time // Last update time
}

// MetadataQuery options for querying metadata
type MetadataQuery struct {
	EntityType *string            // Filter by entity type
	EntityID   *string            // Filter by entity ID
	Key        *string            // Filter by key
	Value      *string            // Filter by value
	Filters    map[string]string  // Multiple key-value filters
	Limit      int                // Maximum results
}

// MetadataIndex represents indexed metadata for an entity
type MetadataIndex struct {
	EntityType string
	EntityID   string
	Attributes map[string]string // All metadata key-value pairs
	UpdatedAt  time.Time
}
