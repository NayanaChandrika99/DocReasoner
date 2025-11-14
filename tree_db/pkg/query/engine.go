// ABOUTME: Unified query engine implementation
// ABOUTME: Orchestrates queries across multiple stores

package query

import (
	"fmt"
	"strings"

	"github.com/nainya/treestore/pkg/document"
	"github.com/nainya/treestore/pkg/metadata"
	"github.com/nainya/treestore/pkg/prompt"
	"github.com/nainya/treestore/pkg/storage"
	"github.com/nainya/treestore/pkg/version"
)

// Engine provides unified query interface across all stores
type Engine struct {
	kv       *storage.KV
	docStore *document.SimpleStore
	verStore *version.VersionStore
	metaStore *metadata.MetadataStore
	promptStore *prompt.PromptStore
}

// NewEngine creates a new query engine
func NewEngine(kv *storage.KV) *Engine {
	return &Engine{
		kv:          kv,
		docStore:    document.NewSimpleStore(kv),
		verStore:    version.NewVersionStore(kv),
		metaStore:   metadata.NewMetadataStore(kv),
		promptStore: prompt.NewPromptStore(kv),
	}
}

// Execute runs a query and returns results
func (e *Engine) Execute(q Query) (*Result, error) {
	switch q.Type {
	case QueryDocument:
		return e.executeDocumentQuery(q)
	case QueryVersion:
		return e.executeVersionQuery(q)
	case QueryMetadata:
		return e.executeMetadataQuery(q)
	case QueryPrompt:
		return e.executePromptQuery(q)
	default:
		return nil, fmt.Errorf("unsupported query type: %d", q.Type)
	}
}

// GetEnrichedDocument retrieves a document with metadata and version info
func (e *Engine) GetEnrichedDocument(policyID, nodeID string, versionID *string) (*EnrichedDocument, error) {
	// Get base document
	node, err := e.docStore.GetNode(policyID, nodeID)
	if err != nil {
		return nil, err
	}

	enriched := &EnrichedDocument{
		Node: node,
	}

	// Get metadata
	meta, err := e.metaStore.GetAllMetadata("node", nodeID)
	if err == nil {
		enriched.Metadata = meta
	}

	// Get version if specified
	if versionID != nil {
		ver, err := e.verStore.GetVersion(policyID, *versionID)
		if err == nil {
			enriched.Version = ver
		}
	}

	return enriched, nil
}

// GetEnrichedConversation retrieves a conversation with messages and metadata
func (e *Engine) GetEnrichedConversation(conversationID string) (*EnrichedConversation, error) {
	// Get conversation with messages
	convWithMsgs, err := e.promptStore.GetConversationWithMessages(conversationID)
	if err != nil {
		return nil, err
	}

	enriched := &EnrichedConversation{
		Conversation: convWithMsgs.Conversation,
		Messages:     convWithMsgs.Messages,
	}

	// Get metadata
	meta, err := e.metaStore.GetAllMetadata("conversation", conversationID)
	if err == nil {
		enriched.Metadata = meta
	}

	return enriched, nil
}

// Search performs full-text search across document store
func (e *Engine) Search(opts SearchOptions) ([]*SearchResult, error) {
	if opts.Limit == 0 {
		opts.Limit = 100
	}

	// Currently only supports document search
	// Could be extended to search across other stores
	policyID, ok := getStringFilter("policyID", map[string]interface{}{})
	if !ok {
		return nil, fmt.Errorf("policyID required for search")
	}

	docResults, err := e.docStore.Search(policyID, opts.Query, opts.Limit)
	if err != nil {
		return nil, err
	}

	results := make([]*SearchResult, 0, len(docResults))
	for _, dr := range docResults {
		if dr.Score >= opts.MinScore {
			results = append(results, &SearchResult{
				EntityType: "document",
				EntityID:   dr.NodeID,
				Title:      dr.Title,
				Snippet:    dr.Summary,
				Score:      dr.Score,
			})
		}
	}

	return results, nil
}

// FindRelated finds entities related to a given entity via metadata
func (e *Engine) FindRelated(entityType, entityID, relationKey string, limit int) ([]string, error) {
	// Get the relation value from source entity
	entry, err := e.metaStore.GetMetadata(entityType, entityID, relationKey)
	if err != nil {
		return nil, err
	}

	// Find other entities with same relation value
	related, err := e.metaStore.QueryByKeyValue(relationKey, entry.Value, nil, limit)
	if err != nil {
		return nil, err
	}

	result := make([]string, 0, len(related))
	for _, r := range related {
		if r.EntityID != entityID { // Exclude self
			result = append(result, r.EntityID)
		}
	}

	return result, nil
}

// Internal query executors

func (e *Engine) executeDocumentQuery(q Query) (*Result, error) {
	result := &Result{Documents: []*document.Node{}}

	policyID, ok := getStringFilter("policyID", q.Filters)
	if !ok {
		return nil, fmt.Errorf("policyID required for document query")
	}

	nodeID, hasNodeID := getStringFilter("nodeID", q.Filters)

	if hasNodeID {
		// Single node query
		node, err := e.docStore.GetNode(policyID, nodeID)
		if err != nil {
			return nil, err
		}
		result.Documents = []*document.Node{node}
		result.Total = 1
	} else if parentID, hasParent := q.Filters["parentID"]; hasParent {
		// Children query
		var pid *string
		if parentID != nil {
			p := parentID.(string)
			pid = &p
		}
		children, err := e.docStore.GetChildren(policyID, pid)
		if err != nil {
			return nil, err
		}
		result.Documents = children
		result.Total = len(children)
	} else {
		return nil, fmt.Errorf("nodeID or parentID required")
	}

	// Apply limit/offset
	result.Documents = applyPagination(result.Documents, q.Limit, q.Offset)
	result.HasMore = result.Total > (q.Offset + len(result.Documents))

	return result, nil
}

func (e *Engine) executeVersionQuery(q Query) (*Result, error) {
	result := &Result{Versions: []*version.Version{}}

	policyID, ok := getStringFilter("policyID", q.Filters)
	if !ok {
		return nil, fmt.Errorf("policyID required for version query")
	}

	versionID, hasVersionID := getStringFilter("versionID", q.Filters)

	if hasVersionID {
		// Single version query
		ver, err := e.verStore.GetVersion(policyID, versionID)
		if err != nil {
			return nil, err
		}
		result.Versions = []*version.Version{ver}
		result.Total = 1
	} else if tag, hasTag := getStringFilter("tag", q.Filters); hasTag {
		// Tag query
		ver, err := e.verStore.GetVersionByTag(policyID, tag)
		if err != nil {
			return nil, err
		}
		result.Versions = []*version.Version{ver}
		result.Total = 1
	} else {
		// List versions
		versions, err := e.verStore.ListVersions(policyID, q.Limit)
		if err != nil {
			return nil, err
		}
		result.Versions = versions
		result.Total = len(versions)
	}

	result.HasMore = result.Total > (q.Offset + len(result.Versions))
	return result, nil
}

func (e *Engine) executeMetadataQuery(q Query) (*Result, error) {
	result := &Result{Metadata: []*metadata.MetadataEntry{}}

	key, hasKey := getStringFilter("key", q.Filters)
	value, hasValue := getStringFilter("value", q.Filters)

	var entityType *string
	if et, ok := getStringFilter("entityType", q.Filters); ok {
		entityType = &et
	}

	if hasKey && hasValue {
		// Key-value query
		entries, err := e.metaStore.QueryByKeyValue(key, value, entityType, q.Limit)
		if err != nil {
			return nil, err
		}
		result.Metadata = entries
	} else if hasKey {
		// Key-only query
		entries, err := e.metaStore.QueryByKey(key, entityType, q.Limit)
		if err != nil {
			return nil, err
		}
		result.Metadata = entries
	} else {
		return nil, fmt.Errorf("key required for metadata query")
	}

	result.Total = len(result.Metadata)
	result.HasMore = false
	return result, nil
}

func (e *Engine) executePromptQuery(q Query) (*Result, error) {
	result := &Result{Conversations: []*prompt.Conversation{}}

	if userID, ok := getStringFilter("userID", q.Filters); ok {
		// User conversations
		convs, err := e.promptStore.ListConversationsByUser(userID, q.Limit)
		if err != nil {
			return nil, err
		}
		result.Conversations = convs
	} else if tag, ok := getStringFilter("tag", q.Filters); ok {
		// Tag-based query
		convs, err := e.promptStore.ListConversationsByTag(tag, q.Limit)
		if err != nil {
			return nil, err
		}
		result.Conversations = convs
	} else {
		return nil, fmt.Errorf("userID or tag required for prompt query")
	}

	result.Total = len(result.Conversations)
	result.HasMore = false
	return result, nil
}

// Helper functions

func getStringFilter(key string, filters map[string]interface{}) (string, bool) {
	val, ok := filters[key]
	if !ok {
		return "", false
	}
	str, ok := val.(string)
	return str, ok
}

func applyPagination[T any](items []T, limit, offset int) []T {
	if offset >= len(items) {
		return []T{}
	}

	start := offset
	end := offset + limit
	if end > len(items) {
		end = len(items)
	}

	return items[start:end]
}

// BatchGet retrieves multiple entities efficiently
func (e *Engine) BatchGetNodes(policyID string, nodeIDs []string) ([]*document.Node, error) {
	nodes := make([]*document.Node, 0, len(nodeIDs))

	for _, nodeID := range nodeIDs {
		node, err := e.docStore.GetNode(policyID, nodeID)
		if err == nil {
			nodes = append(nodes, node)
		}
	}

	return nodes, nil
}

// GlobalSearch searches across all text fields in all stores
func (e *Engine) GlobalSearch(query string, limit int) ([]*SearchResult, error) {
	results := make([]*SearchResult, 0)
	query = strings.ToLower(query)

	// This is a simplified implementation
	// In production, you'd want proper full-text indexing

	// Search would need to be expanded across stores
	// For now, returning empty results as placeholder

	return results, nil
}
