// ABOUTME: Basic usage examples for TreeStore
// ABOUTME: Demonstrates fundamental operations

package main

import (
	"fmt"
	"log"
	"time"

	"github.com/nainya/treestore/pkg/document"
	"github.com/nainya/treestore/pkg/metadata"
	"github.com/nainya/treestore/pkg/storage"
	"github.com/nainya/treestore/pkg/version"
)

func main() {
	// Open database
	kv := &storage.KV{Path: "/tmp/example.db"}
	if err := kv.Open(); err != nil {
		log.Fatal(err)
	}
	defer kv.Close()

	// Example 1: Store and retrieve a document
	fmt.Println("=== Example 1: Document Storage ===")
	exampleDocumentStorage(kv)

	// Example 2: Version management
	fmt.Println("\n=== Example 2: Version Management ===")
	exampleVersionManagement(kv)

	// Example 3: Metadata queries
	fmt.Println("\n=== Example 3: Metadata Queries ===")
	exampleMetadataQueries(kv)
}

func exampleDocumentStorage(kv *storage.KV) {
	docStore := document.NewSimpleStore(kv)

	now := time.Now()

	// Create a hierarchical document
	doc := &document.Document{
		PolicyID:   "company-policy-2024",
		VersionID:  "v1.0.0",
		RootNodeID: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	rootID := "root"
	nodes := []*document.Node{
		{
			NodeID:      "root",
			PolicyID:    "company-policy-2024",
			Title:       "Company Policy Document",
			PageStart:   1,
			PageEnd:     100,
			Summary:     "Overview of company policies",
			Text:        "This document contains all company policies...",
			SectionPath: "1",
			Depth:       0,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "section-1",
			PolicyID:    "company-policy-2024",
			ParentID:    &rootID,
			Title:       "Code of Conduct",
			PageStart:   1,
			PageEnd:     25,
			Summary:     "Employee code of conduct",
			Text:        "All employees must adhere to...",
			SectionPath: "1.1",
			Depth:       1,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeID:      "section-2",
			PolicyID:    "company-policy-2024",
			ParentID:    &rootID,
			Title:       "Privacy Policy",
			PageStart:   26,
			PageEnd:     50,
			Summary:     "Data privacy guidelines",
			Text:        "We are committed to protecting user privacy...",
			SectionPath: "1.2",
			Depth:       1,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
	}

	// Store the document
	if err := docStore.StoreDocument(doc, nodes); err != nil {
		log.Fatal(err)
	}
	fmt.Println("✓ Document stored successfully")

	// Retrieve a node
	node, err := docStore.GetNode("company-policy-2024", "section-1")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Retrieved node: %s - %s\n", node.NodeID, node.Title)

	// Get children of root
	children, err := docStore.GetChildren("company-policy-2024", &rootID)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Root has %d children\n", len(children))

	// Search for content
	results, err := docStore.Search("company-policy-2024", "privacy", 10)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Found %d search results for 'privacy'\n", len(results))
	if len(results) > 0 {
		fmt.Printf("  - Top result: %s (score: %.1f)\n", results[0].Title, results[0].Score)
	}
}

func exampleVersionManagement(kv *storage.KV) {
	verStore := version.NewVersionStore(kv)

	now := time.Now()

	// Create multiple versions
	versions := []*version.Version{
		{
			PolicyID:    "company-policy-2024",
			VersionID:   "v1.0.0",
			DocumentID:  "doc-001",
			CreatedAt:   now.Add(-30 * 24 * time.Hour), // 30 days ago
			CreatedBy:   "admin",
			Description: "Initial release",
			Tags:        []string{"stable"},
		},
		{
			PolicyID:    "company-policy-2024",
			VersionID:   "v1.1.0",
			DocumentID:  "doc-002",
			CreatedAt:   now.Add(-15 * 24 * time.Hour), // 15 days ago
			CreatedBy:   "admin",
			Description: "Updated privacy section",
			Tags:        []string{"stable"},
		},
		{
			PolicyID:    "company-policy-2024",
			VersionID:   "v2.0.0",
			DocumentID:  "doc-003",
			CreatedAt:   now,
			CreatedBy:   "admin",
			Description: "Major update with new sections",
			Tags:        []string{"latest", "stable"},
		},
	}

	for _, v := range versions {
		if err := verStore.CreateVersion(v); err != nil {
			log.Fatal(err)
		}
	}
	fmt.Println("✓ Created 3 versions")

	// Get latest version
	latest, err := verStore.GetLatestVersion("company-policy-2024")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Latest version: %s (%s)\n", latest.VersionID, latest.Description)

	// Temporal query: Get version as of 20 days ago
	asOfTime := now.Add(-20 * 24 * time.Hour)
	oldVersion, err := verStore.GetVersionAsOf("company-policy-2024", asOfTime)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Version 20 days ago: %s\n", oldVersion.VersionID)

	// Get by tag
	stableVersion, err := verStore.GetVersionByTag("company-policy-2024", "stable")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Version with 'stable' tag: %s\n", stableVersion.VersionID)

	// List all versions
	allVersions, err := verStore.ListVersions("company-policy-2024", 0)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Total versions: %d\n", len(allVersions))
}

func exampleMetadataQueries(kv *storage.KV) {
	metaStore := metadata.NewMetadataStore(kv)

	now := time.Now()

	// Add metadata to entities
	metadataEntries := []*metadata.MetadataEntry{
		{
			EntityType: "document",
			EntityID:   "doc-001",
			Key:        "author",
			Value:      "John Doe",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc-001",
			Key:        "department",
			Value:      "Legal",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc-001",
			Key:        "status",
			Value:      "published",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc-002",
			Key:        "author",
			Value:      "Jane Smith",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc-002",
			Key:        "department",
			Value:      "Legal",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		{
			EntityType: "document",
			EntityID:   "doc-002",
			Key:        "status",
			Value:      "draft",
			ValueType:  "string",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
	}

	for _, entry := range metadataEntries {
		if err := metaStore.SetMetadata(entry); err != nil {
			log.Fatal(err)
		}
	}
	fmt.Println("✓ Added metadata to 2 documents")

	// Query by key
	authorEntries, err := metaStore.QueryByKey("author", nil, 0)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Documents with 'author' metadata: %d\n", len(authorEntries))

	// Query by key-value
	legalDocs, err := metaStore.QueryByKeyValue("department", "Legal", nil, 0)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Documents in Legal department: %d\n", len(legalDocs))

	// Multi-attribute query
	docType := "document"
	publishedLegalDocs, err := metaStore.QueryMultiple(map[string]string{
		"department": "Legal",
		"status":     "published",
	}, &docType, 0)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ Published Legal documents: %d\n", len(publishedLegalDocs))

	// Get all metadata for an entity
	allMeta, err := metaStore.GetAllMetadata("document", "doc-001")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("✓ doc-001 has %d metadata attributes:\n", len(allMeta))
	for key, value := range allMeta {
		fmt.Printf("  - %s: %s\n", key, value)
	}
}
