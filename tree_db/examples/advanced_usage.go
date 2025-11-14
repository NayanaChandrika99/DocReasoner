// ABOUTME: Advanced usage examples for TreeStore
// ABOUTME: Demonstrates complex queries and integrations

package main

import (
	"fmt"
	"log"
	"time"

	"github.com/nainya/treestore/pkg/document"
	"github.com/nainya/treestore/pkg/metadata"
	"github.com/nainya/treestore/pkg/prompt"
	"github.com/nainya/treestore/pkg/query"
	"github.com/nainya/treestore/pkg/storage"
	"github.com/nainya/treestore/pkg/version"
)

func main() {
	// Open database
	kv := &storage.KV{Path: "/tmp/advanced_example.db"}
	if err := kv.Open(); err != nil {
		log.Fatal(err)
	}
	defer kv.Close()

	// Example 1: Unified query engine
	fmt.Println("=== Example 1: Unified Query Engine ===")
	exampleQueryEngine(kv)

	// Example 2: Enriched results
	fmt.Println("\n=== Example 2: Enriched Results ===")
	exampleEnrichedResults(kv)

	// Example 3: Conversation tracking
	fmt.Println("\n=== Example 3: Conversation Tracking ===")
	exampleConversations(kv)

	// Example 4: Related entity discovery
	fmt.Println("\n=== Example 4: Related Entity Discovery ===")
	exampleRelatedEntities(kv)
}

func exampleQueryEngine(kv *storage.KV) {
	engine := query.NewEngine(kv)
	now := time.Now()

	// Setup: Create sample data
	doc := &document.Document{
		PolicyID:   "policy-advanced",
		VersionID:  "v1",
		RootNodeID: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*document.Node{
		{
			NodeID:    "root",
			PolicyID:  "policy-advanced",
			Title:     "Advanced Policy",
			PageStart: 1,
			PageEnd:   100,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	engine.docStore.StoreDocument(doc, nodes)

	// Use query builder for type-safe queries
	q := query.NewQueryBuilder(query.QueryDocument).
		Where("policyID", "policy-advanced").
		Where("nodeID", "root").
		Limit(10).
		Build()

	result, err := engine.Execute(q)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("✓ Query returned %d documents\n", len(result.Documents))
	if len(result.Documents) > 0 {
		fmt.Printf("  - Title: %s\n", result.Documents[0].Title)
	}

	// Batch retrieval for efficiency
	batchNodes, err := engine.BatchGetNodes("policy-advanced", []string{"root"})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Batch retrieved %d nodes\n", len(batchNodes))
}

func exampleEnrichedResults(kv *storage.KV) {
	engine := query.NewEngine(kv)
	now := time.Now()

	// Create document
	doc := &document.Document{
		PolicyID:   "policy-enriched",
		VersionID:  "v1.0.0",
		RootNodeID: "node-enriched",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*document.Node{
		{
			NodeID:    "node-enriched",
			PolicyID:  "policy-enriched",
			Title:     "Enriched Node",
			PageStart: 1,
			PageEnd:   10,
			Summary:   "This node has rich metadata",
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	engine.docStore.StoreDocument(doc, nodes)

	// Add metadata
	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "node",
		EntityID:   "node-enriched",
		Key:        "classification",
		Value:      "confidential",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	engine.metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "node",
		EntityID:   "node-enriched",
		Key:        "reviewer",
		Value:      "Alice",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	// Create version
	engine.verStore.CreateVersion(&version.Version{
		PolicyID:    "policy-enriched",
		VersionID:   "v1.0.0",
		DocumentID:  "doc-enriched",
		CreatedAt:   now,
		CreatedBy:   "admin",
		Description: "Initial version",
		Tags:        []string{"latest"},
	})

	// Get enriched document (combines node + metadata + version)
	versionID := "v1.0.0"
	enriched, err := engine.GetEnrichedDocument("policy-enriched", "node-enriched", &versionID)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("✓ Enriched document retrieved:\n")
	fmt.Printf("  - Node: %s\n", enriched.Node.Title)
	fmt.Printf("  - Metadata: %d attributes\n", len(enriched.Metadata))
	for key, value := range enriched.Metadata {
		fmt.Printf("    • %s: %s\n", key, value)
	}
	if enriched.Version != nil {
		fmt.Printf("  - Version: %s (%s)\n", enriched.Version.VersionID, enriched.Version.Description)
	}
}

func exampleConversations(kv *storage.KV) {
	promptStore := prompt.NewPromptStore(kv)
	metaStore := metadata.NewMetadataStore(kv)
	engine := query.NewEngine(kv)

	now := time.Now()

	// Create conversation
	conv := &prompt.Conversation{
		ConversationID: "conv-support-001",
		UserID:         "user-123",
		Title:          "Help with Privacy Policy",
		StartedAt:      now,
		LastMessageAt:  now,
		MessageCount:   0,
		Tags:           []string{"support", "privacy"},
	}

	if err := promptStore.CreateConversation(conv); err != nil {
		log.Fatal(err)
	}

	// Add messages
	messages := []*prompt.Message{
		{
			MessageID:      "msg-001",
			ConversationID: "conv-support-001",
			Role:           "user",
			Content:        "What is the data retention policy?",
			Timestamp:      now,
		},
		{
			MessageID:      "msg-002",
			ConversationID: "conv-support-001",
			Role:           "assistant",
			Content:        "According to our privacy policy, we retain user data for...",
			Timestamp:      now.Add(1 * time.Minute),
		},
		{
			MessageID:      "msg-003",
			ConversationID: "conv-support-001",
			Role:           "user",
			Content:        "Can I request data deletion?",
			Timestamp:      now.Add(2 * time.Minute),
		},
	}

	for _, msg := range messages {
		if err := promptStore.AddMessage(msg); err != nil {
			log.Fatal(err)
		}
	}

	// Add metadata to conversation
	metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "conversation",
		EntityID:   "conv-support-001",
		Key:        "sentiment",
		Value:      "neutral",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	metaStore.SetMetadata(&metadata.MetadataEntry{
		EntityType: "conversation",
		EntityID:   "conv-support-001",
		Key:        "priority",
		Value:      "high",
		ValueType:  "string",
		CreatedAt:  now,
		UpdatedAt:  now,
	})

	// Get enriched conversation
	enrichedConv, err := engine.GetEnrichedConversation("conv-support-001")
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("✓ Conversation: %s\n", enrichedConv.Conversation.Title)
	fmt.Printf("  - User: %s\n", enrichedConv.Conversation.UserID)
	fmt.Printf("  - Messages: %d\n", len(enrichedConv.Messages))
	fmt.Printf("  - Tags: %v\n", enrichedConv.Conversation.Tags)
	fmt.Printf("  - Metadata:\n")
	for key, value := range enrichedConv.Metadata {
		fmt.Printf("    • %s: %s\n", key, value)
	}

	// Query conversations by tag
	supportConvs, err := promptStore.ListConversationsByTag("support", 10)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Found %d conversations with 'support' tag\n", len(supportConvs))
}

func exampleRelatedEntities(kv *storage.KV) {
	engine := query.NewEngine(kv)
	now := time.Now()

	// Create multiple documents with same project tag
	projects := []struct {
		docID   string
		title   string
		project string
	}{
		{"doc-alpha-1", "Alpha Feature Spec", "project-alpha"},
		{"doc-alpha-2", "Alpha Test Plan", "project-alpha"},
		{"doc-alpha-3", "Alpha Architecture", "project-alpha"},
		{"doc-beta-1", "Beta Feature Spec", "project-beta"},
	}

	for _, p := range projects {
		// Add document metadata
		engine.metaStore.SetMetadata(&metadata.MetadataEntry{
			EntityType: "document",
			EntityID:   p.docID,
			Key:        "project",
			Value:      p.project,
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		})

		engine.metaStore.SetMetadata(&metadata.MetadataEntry{
			EntityType: "document",
			EntityID:   p.docID,
			Key:        "title",
			Value:      p.title,
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		})
	}

	// Find related documents by project
	related, err := engine.FindRelated("document", "doc-alpha-1", "project", 10)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("✓ Found %d documents related to doc-alpha-1:\n", len(related))
	for _, relatedID := range related {
		meta, _ := engine.metaStore.GetAllMetadata("document", relatedID)
		fmt.Printf("  - %s (%s)\n", relatedID, meta["title"])
	}

	// Multi-attribute filtering
	docType := "document"
	alphaProject, err := engine.metaStore.QueryMultiple(map[string]string{
		"project": "project-alpha",
	}, &docType, 0)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("✓ Total documents in project-alpha: %d\n", len(alphaProject))
}
