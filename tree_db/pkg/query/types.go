// ABOUTME: Unified query interface types
// ABOUTME: Cross-store query operations and result types

package query

import (
	"time"

	"github.com/nainya/treestore/pkg/document"
	"github.com/nainya/treestore/pkg/metadata"
	"github.com/nainya/treestore/pkg/prompt"
	"github.com/nainya/treestore/pkg/version"
)

// QueryType defines the type of query
type QueryType int

const (
	QueryDocument QueryType = iota
	QueryVersion
	QueryMetadata
	QueryPrompt
	QueryJoin // Cross-store query
)

// Query represents a unified query across stores
type Query struct {
	Type       QueryType
	Filters    map[string]interface{}
	Limit      int
	Offset     int
	OrderBy    string
	Descending bool
}

// JoinQuery represents a cross-store join operation
type JoinQuery struct {
	Primary   Query
	Secondary Query
	JoinKey   string // Field to join on
	JoinType  JoinType
}

// JoinType defines join operation type
type JoinType int

const (
	InnerJoin JoinType = iota
	LeftJoin
)

// Result represents a unified query result
type Result struct {
	Documents     []*document.Node
	Versions      []*version.Version
	Metadata      []*metadata.MetadataEntry
	Conversations []*prompt.Conversation
	Messages      []*prompt.Message
	Total         int
	HasMore       bool
}

// EnrichedDocument combines document with metadata and version info
type EnrichedDocument struct {
	Node     *document.Node
	Metadata map[string]string
	Version  *version.Version
}

// EnrichedConversation combines conversation with metadata
type EnrichedConversation struct {
	Conversation *prompt.Conversation
	Messages     []*prompt.Message
	Metadata     map[string]string
}

// QueryBuilder provides fluent interface for building queries
type QueryBuilder struct {
	query Query
}

// NewQueryBuilder creates a new query builder
func NewQueryBuilder(qtype QueryType) *QueryBuilder {
	return &QueryBuilder{
		query: Query{
			Type:    qtype,
			Filters: make(map[string]interface{}),
			Limit:   100,
		},
	}
}

// Where adds a filter condition
func (qb *QueryBuilder) Where(key string, value interface{}) *QueryBuilder {
	qb.query.Filters[key] = value
	return qb
}

// Limit sets the result limit
func (qb *QueryBuilder) Limit(limit int) *QueryBuilder {
	qb.query.Limit = limit
	return qb
}

// Offset sets the result offset
func (qb *QueryBuilder) Offset(offset int) *QueryBuilder {
	qb.query.Offset = offset
	return qb
}

// OrderBy sets ordering field
func (qb *QueryBuilder) OrderBy(field string, descending bool) *QueryBuilder {
	qb.query.OrderBy = field
	qb.query.Descending = descending
	return qb
}

// Build returns the constructed query
func (qb *QueryBuilder) Build() Query {
	return qb.query
}

// TimeRange represents a time-based filter
type TimeRange struct {
	Start *time.Time
	End   *time.Time
}

// SearchOptions for full-text search across stores
type SearchOptions struct {
	Query      string
	EntityType *string
	Limit      int
	MinScore   float64
}

// SearchResult represents a unified search result
type SearchResult struct {
	EntityType string
	EntityID   string
	Title      string
	Snippet    string
	Score      float64
	Metadata   map[string]string
}
