// Integration tests for TreeStore gRPC server
package server

import (
	"context"
	"net"
	"os"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/nainya/treestore/proto"
)

const bufSize = 1024 * 1024

func setupTestServer(t *testing.T) (*Server, pb.TreeStoreServiceClient, func()) {
	// Create temp database
	dbPath := "/tmp/test_treestore_" + time.Now().Format("20060102150405") + ".db"

	// Create server
	server, err := NewServer(dbPath)
	if err != nil {
		t.Fatalf("Failed to create server: %v", err)
	}

	// Create a new listener for this test
	lis := bufconn.Listen(bufSize)

	// Create gRPC server
	grpcServer := grpc.NewServer()
	pb.RegisterTreeStoreServiceServer(grpcServer, server)

	go func() {
		if err := grpcServer.Serve(lis); err != nil {
			// Server closed is expected during cleanup
		}
	}()

	// Create client with custom dialer
	bufDialer := func(context.Context, string) (net.Conn, error) {
		return lis.Dial()
	}

	ctx := context.Background()
	conn, err := grpc.DialContext(ctx, "bufnet",
		grpc.WithContextDialer(bufDialer),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("Failed to dial bufnet: %v", err)
	}

	client := pb.NewTreeStoreServiceClient(conn)

	cleanup := func() {
		conn.Close()
		grpcServer.Stop()
		lis.Close()
		server.Close()
		os.Remove(dbPath)
	}

	return server, client, cleanup
}

func TestStoreAndGetDocument(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	now := timestamppb.Now()

	// Store document
	doc := &pb.Document{
		PolicyId:       "TEST-001",
		VersionId:      "v1.0",
		RootNodeId:     "root",
		PageindexDocId: "pageindex-123",
		Metadata:       map[string]string{"author": "test"},
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	nodes := []*pb.Node{
		{
			NodeId:      "root",
			PolicyId:    "TEST-001",
			Title:       "Test Document",
			PageStart:   1,
			PageEnd:     100,
			Summary:     "Test summary",
			Text:        "Test content",
			SectionPath: "1",
			Depth:       0,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			NodeId:      "section-1",
			PolicyId:    "TEST-001",
			ParentId:    "root",
			Title:       "Section 1",
			PageStart:   1,
			PageEnd:     25,
			Summary:     "Section summary",
			Text:        "Section content",
			SectionPath: "1.1",
			Depth:       1,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
	}

	storeReq := &pb.StoreDocumentRequest{
		Document: doc,
		Nodes:    nodes,
	}

	storeResp, err := client.StoreDocument(ctx, storeReq)
	if err != nil {
		t.Fatalf("StoreDocument failed: %v", err)
	}

	if !storeResp.Success {
		t.Errorf("StoreDocument returned success=false: %s", storeResp.Message)
	}

	// Get document
	getReq := &pb.GetDocumentRequest{PolicyId: "TEST-001"}
	getResp, err := client.GetDocument(ctx, getReq)
	if err != nil {
		t.Fatalf("GetDocument failed: %v", err)
	}

	if getResp.Document.PolicyId != "TEST-001" {
		t.Errorf("Expected policy_id TEST-001, got %s", getResp.Document.PolicyId)
	}

	if len(getResp.Nodes) != 2 {
		t.Errorf("Expected 2 nodes, got %d", len(getResp.Nodes))
	}
}

func TestGetNode(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	now := timestamppb.Now()

	// Store a document first
	doc := &pb.Document{
		PolicyId:   "TEST-002",
		VersionId:  "v1.0",
		RootNodeId: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*pb.Node{
		{
			NodeId:    "root",
			PolicyId:  "TEST-002",
			Title:     "Root Node",
			PageStart: 1,
			PageEnd:   50,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	_, err := client.StoreDocument(ctx, &pb.StoreDocumentRequest{
		Document: doc,
		Nodes:    nodes,
	})
	if err != nil {
		t.Fatalf("StoreDocument failed: %v", err)
	}

	// Get node
	getReq := &pb.GetNodeRequest{
		PolicyId: "TEST-002",
		NodeId:   "root",
	}

	getResp, err := client.GetNode(ctx, getReq)
	if err != nil {
		t.Fatalf("GetNode failed: %v", err)
	}

	if getResp.Node.NodeId != "root" {
		t.Errorf("Expected node_id root, got %s", getResp.Node.NodeId)
	}

	if getResp.Node.Title != "Root Node" {
		t.Errorf("Expected title 'Root Node', got %s", getResp.Node.Title)
	}
}

func TestGetChildren(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	now := timestamppb.Now()

	// Store document with parent-child relationship
	doc := &pb.Document{
		PolicyId:   "TEST-003",
		VersionId:  "v1.0",
		RootNodeId: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*pb.Node{
		{
			NodeId:    "root",
			PolicyId:  "TEST-003",
			Title:     "Root",
			PageStart: 1,
			PageEnd:   100,
			Depth:     0,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeId:    "child-1",
			PolicyId:  "TEST-003",
			ParentId:  "root",
			Title:     "Child 1",
			PageStart: 1,
			PageEnd:   50,
			Depth:     1,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeId:    "child-2",
			PolicyId:  "TEST-003",
			ParentId:  "root",
			Title:     "Child 2",
			PageStart: 51,
			PageEnd:   100,
			Depth:     1,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	_, err := client.StoreDocument(ctx, &pb.StoreDocumentRequest{
		Document: doc,
		Nodes:    nodes,
	})
	if err != nil {
		t.Fatalf("StoreDocument failed: %v", err)
	}

	// Get children of root
	getReq := &pb.GetChildrenRequest{
		PolicyId: "TEST-003",
		ParentId: "root",
	}

	getResp, err := client.GetChildren(ctx, getReq)
	if err != nil {
		t.Fatalf("GetChildren failed: %v", err)
	}

	if len(getResp.Children) != 2 {
		t.Errorf("Expected 2 children, got %d", len(getResp.Children))
	}

	// Verify children IDs
	childIDs := make(map[string]bool)
	for _, child := range getResp.Children {
		childIDs[child.NodeId] = true
	}

	if !childIDs["child-1"] || !childIDs["child-2"] {
		t.Errorf("Expected children child-1 and child-2, got: %v", childIDs)
	}
}

func TestSearch(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	now := timestamppb.Now()

	// Store document with searchable content
	doc := &pb.Document{
		PolicyId:   "TEST-004",
		VersionId:  "v1.0",
		RootNodeId: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*pb.Node{
		{
			NodeId:    "root",
			PolicyId:  "TEST-004",
			Title:     "Medical Policy",
			Summary:   "Coverage criteria for diabetes treatment",
			Text:      "This policy covers diabetes medications and monitoring",
			PageStart: 1,
			PageEnd:   10,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeId:    "section-1",
			PolicyId:  "TEST-004",
			ParentId:  "root",
			Title:     "Eligibility Requirements",
			Summary:   "Patient eligibility for diabetes coverage",
			Text:      "Patients must have diagnosed diabetes mellitus",
			PageStart: 1,
			PageEnd:   5,
			Depth:     1,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	_, err := client.StoreDocument(ctx, &pb.StoreDocumentRequest{
		Document: doc,
		Nodes:    nodes,
	})
	if err != nil {
		t.Fatalf("StoreDocument failed: %v", err)
	}

	// Search for "diabetes"
	searchReq := &pb.SearchRequest{
		PolicyId: "TEST-004",
		Query:    "diabetes",
		Limit:    10,
	}

	searchResp, err := client.SearchByKeyword(ctx, searchReq)
	if err != nil {
		t.Fatalf("SearchByKeyword failed: %v", err)
	}

	if len(searchResp.Results) == 0 {
		t.Error("Expected search results, got none")
	}

	// Verify results contain "diabetes"
	foundDiabetes := false
	for _, result := range searchResp.Results {
		if result.Node.Title == "Medical Policy" || result.Node.Title == "Eligibility Requirements" {
			foundDiabetes = true
			if result.Score <= 0 {
				t.Errorf("Expected positive score, got %f", result.Score)
			}
		}
	}

	if !foundDiabetes {
		t.Error("Expected to find diabetes-related results")
	}
}

func TestGetSubtree(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	now := timestamppb.Now()

	// Store multi-level hierarchy
	doc := &pb.Document{
		PolicyId:   "TEST-005",
		VersionId:  "v1.0",
		RootNodeId: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*pb.Node{
		{
			NodeId:    "root",
			PolicyId:  "TEST-005",
			Title:     "Root",
			Depth:     0,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeId:    "level1",
			PolicyId:  "TEST-005",
			ParentId:  "root",
			Title:     "Level 1",
			Depth:     1,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeId:    "level2",
			PolicyId:  "TEST-005",
			ParentId:  "level1",
			Title:     "Level 2",
			Depth:     2,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	_, err := client.StoreDocument(ctx, &pb.StoreDocumentRequest{
		Document: doc,
		Nodes:    nodes,
	})
	if err != nil {
		t.Fatalf("StoreDocument failed: %v", err)
	}

	// Get subtree from root
	subtreeReq := &pb.GetSubtreeRequest{
		PolicyId: "TEST-005",
		NodeId:   "root",
		MaxDepth: 0, // Unlimited
	}

	subtreeResp, err := client.GetSubtree(ctx, subtreeReq)
	if err != nil {
		t.Fatalf("GetSubtree failed: %v", err)
	}

	if len(subtreeResp.Nodes) != 3 {
		t.Errorf("Expected 3 nodes in subtree, got %d", len(subtreeResp.Nodes))
	}

	// Get subtree with max_depth=1
	subtreeReq.MaxDepth = 1
	subtreeResp, err = client.GetSubtree(ctx, subtreeReq)
	if err != nil {
		t.Fatalf("GetSubtree with max_depth failed: %v", err)
	}

	if len(subtreeResp.Nodes) != 2 {
		t.Errorf("Expected 2 nodes with max_depth=1, got %d", len(subtreeResp.Nodes))
	}
}

func TestGetAncestorPath(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	now := timestamppb.Now()

	// Store multi-level hierarchy
	doc := &pb.Document{
		PolicyId:   "TEST-006",
		VersionId:  "v1.0",
		RootNodeId: "root",
		CreatedAt:  now,
		UpdatedAt:  now,
	}

	nodes := []*pb.Node{
		{
			NodeId:    "root",
			PolicyId:  "TEST-006",
			Title:     "Root",
			Depth:     0,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeId:    "parent",
			PolicyId:  "TEST-006",
			ParentId:  "root",
			Title:     "Parent",
			Depth:     1,
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			NodeId:    "child",
			PolicyId:  "TEST-006",
			ParentId:  "parent",
			Title:     "Child",
			Depth:     2,
			CreatedAt: now,
			UpdatedAt: now,
		},
	}

	_, err := client.StoreDocument(ctx, &pb.StoreDocumentRequest{
		Document: doc,
		Nodes:    nodes,
	})
	if err != nil {
		t.Fatalf("StoreDocument failed: %v", err)
	}

	// Get ancestor path for deepest child
	pathReq := &pb.GetAncestorPathRequest{
		PolicyId: "TEST-006",
		NodeId:   "child",
	}

	pathResp, err := client.GetAncestorPath(ctx, pathReq)
	if err != nil {
		t.Fatalf("GetAncestorPath failed: %v", err)
	}

	if len(pathResp.Ancestors) != 3 {
		t.Errorf("Expected 3 ancestors (root, parent, child), got %d", len(pathResp.Ancestors))
	}

	// Verify order: root -> parent -> child
	expectedOrder := []string{"root", "parent", "child"}
	for i, expected := range expectedOrder {
		if pathResp.Ancestors[i].NodeId != expected {
			t.Errorf("Expected ancestor[%d]=%s, got %s", i, expected, pathResp.Ancestors[i].NodeId)
		}
	}
}

func TestHealth(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()

	req := &pb.HealthRequest{}
	resp, err := client.Health(ctx, req)
	if err != nil {
		t.Fatalf("Health check failed: %v", err)
	}

	if !resp.Healthy {
		t.Error("Expected healthy=true")
	}

	if resp.Version == "" {
		t.Error("Expected non-empty version")
	}

	if resp.UptimeSeconds < 0 {
		t.Errorf("Expected non-negative uptime, got %d", resp.UptimeSeconds)
	}
}

func TestStats(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()

	// First store some data
	now := timestamppb.Now()
	_, err := client.StoreDocument(ctx, &pb.StoreDocumentRequest{
		Document: &pb.Document{
			PolicyId:   "TEST-007",
			RootNodeId: "root",
			CreatedAt:  now,
			UpdatedAt:  now,
		},
		Nodes: []*pb.Node{
			{
				NodeId:    "root",
				PolicyId:  "TEST-007",
				Title:     "Test",
				CreatedAt: now,
				UpdatedAt: now,
			},
		},
	})
	if err != nil {
		t.Fatalf("StoreDocument failed: %v", err)
	}

	// Get stats
	req := &pb.StatsRequest{}
	resp, err := client.Stats(ctx, req)
	if err != nil {
		t.Fatalf("Stats failed: %v", err)
	}

	// Check operation counts
	if resp.OperationCounts["StoreDocument"] == 0 {
		t.Error("Expected StoreDocument operation count > 0")
	}
}

func TestVersionOperations(t *testing.T) {
	_, client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()

	// Note: Version operations require VersionStore which needs manual setup
	// This test verifies the API works, actual version management tested elsewhere

	// Try to get a non-existent version (should fail gracefully)
	asOfReq := &pb.GetVersionAsOfRequest{
		PolicyId:  "NONEXISTENT",
		AsOfTime:  timestamppb.Now(),
	}

	_, err := client.GetVersionAsOf(ctx, asOfReq)
	if err == nil {
		t.Error("Expected error for non-existent policy")
	}
}
