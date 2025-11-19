// Package server implements the gRPC TreeStore service
package server

import (
	"context"
	"fmt"
	"os"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	"github.com/nainya/treestore/pkg/document"
	"github.com/nainya/treestore/pkg/metadata"
	"github.com/nainya/treestore/pkg/prompt"
	"github.com/nainya/treestore/pkg/storage"
	"github.com/nainya/treestore/pkg/version"
	pb "github.com/nainya/treestore/proto"
)

// Server implements the TreeStoreServiceServer interface
type Server struct {
	pb.UnimplementedTreeStoreServiceServer

	kv          *storage.KV
	docStore    *document.SimpleStore
	verStore    *version.VersionStore
	metaStore   *metadata.MetadataStore
	promptStore *prompt.PromptStore

	startTime   time.Time
	opCounts    map[string]int64
}

// NewServer creates a new gRPC server instance
func NewServer(dbPath string) (*Server, error) {
	kv := &storage.KV{Path: dbPath}
	if err := kv.Open(); err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	return &Server{
		kv:          kv,
		docStore:    document.NewSimpleStore(kv),
		verStore:    version.NewVersionStore(kv),
		metaStore:   metadata.NewMetadataStore(kv),
		promptStore: prompt.NewPromptStore(kv),
		startTime:   time.Now(),
		opCounts:    make(map[string]int64),
	}, nil
}

// Close closes the database connection
func (s *Server) Close() error {
	return s.kv.Close()
}

// ========== Document Operations ==========

func (s *Server) StoreDocument(ctx context.Context, req *pb.StoreDocumentRequest) (*pb.StoreDocumentResponse, error) {
	s.opCounts["StoreDocument"]++

	if req.Document == nil {
		return nil, status.Error(codes.InvalidArgument, "document is required")
	}

	// Convert protobuf Document to internal type
	doc := &document.Document{
		PolicyID:       req.Document.PolicyId,
		VersionID:      req.Document.VersionId,
		PageIndexDocID: req.Document.PageindexDocId,
		RootNodeID:     req.Document.RootNodeId,
		Metadata:       req.Document.Metadata,
		CreatedAt:      req.Document.CreatedAt.AsTime(),
		UpdatedAt:      req.Document.UpdatedAt.AsTime(),
	}

	// Convert protobuf Nodes to internal type
	nodes := make([]*document.Node, len(req.Nodes))
	for i, pbNode := range req.Nodes {
		var parentID *string
		if pbNode.ParentId != "" {
			parentID = &pbNode.ParentId
		}

		nodes[i] = &document.Node{
			NodeID:      pbNode.NodeId,
			PolicyID:    pbNode.PolicyId,
			ParentID:    parentID,
			Title:       pbNode.Title,
			PageStart:   int(pbNode.PageStart),
			PageEnd:     int(pbNode.PageEnd),
			Summary:     pbNode.Summary,
			Text:        pbNode.Text,
			SectionPath: pbNode.SectionPath,
			ChildIDs:    pbNode.ChildIds,
			Depth:       int(pbNode.Depth),
			CreatedAt:   pbNode.CreatedAt.AsTime(),
			UpdatedAt:   pbNode.UpdatedAt.AsTime(),
		}
	}

	if err := s.docStore.StoreDocument(doc, nodes); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to store document: %v", err)
	}

	return &pb.StoreDocumentResponse{
		Success: true,
		Message: fmt.Sprintf("Stored document %s with %d nodes", doc.PolicyID, len(nodes)),
	}, nil
}

func (s *Server) GetDocument(ctx context.Context, req *pb.GetDocumentRequest) (*pb.GetDocumentResponse, error) {
	s.opCounts["GetDocument"]++

	if req.PolicyId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id is required")
	}

	// Get root node first to find document structure
	// Note: SimpleStore doesn't have GetDocument, so we need to scan for the root
	var rootNode *document.Node
	var err error

	// Try to find root by getting children with nil parent
	children, err := s.docStore.GetChildren(req.PolicyId, nil)
	if err != nil || len(children) == 0 {
		return nil, status.Errorf(codes.NotFound, "document not found: %v", err)
	}
	rootNode = children[0]

	// Get all nodes for this document
	nodes, err := s.docStore.GetSubtree(req.PolicyId, rootNode.NodeID, document.QueryOptions{})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get nodes: %v", err)
	}

	// Build document from root node
	pbDoc := &pb.Document{
		PolicyId:        req.PolicyId,
		VersionId:       "",  // Would need to be stored separately
		PageindexDocId:  "",
		RootNodeId:      rootNode.NodeID,
		Metadata:        make(map[string]string),
		CreatedAt:       timestamppb.New(rootNode.CreatedAt),
		UpdatedAt:       timestamppb.New(rootNode.UpdatedAt),
	}

	pbNodes := make([]*pb.Node, len(nodes))
	for i, node := range nodes {
		parentID := ""
		if node.ParentID != nil {
			parentID = *node.ParentID
		}

		pbNodes[i] = &pb.Node{
			NodeId:      node.NodeID,
			PolicyId:    node.PolicyID,
			ParentId:    parentID,
			Title:       node.Title,
			PageStart:   int32(node.PageStart),
			PageEnd:     int32(node.PageEnd),
			Summary:     node.Summary,
			Text:        node.Text,
			SectionPath: node.SectionPath,
			ChildIds:    node.ChildIDs,
			Depth:       int32(node.Depth),
			CreatedAt:   timestamppb.New(node.CreatedAt),
			UpdatedAt:   timestamppb.New(node.UpdatedAt),
		}
	}

	return &pb.GetDocumentResponse{
		Document: pbDoc,
		Nodes:    pbNodes,
	}, nil
}

func (s *Server) DeleteDocument(ctx context.Context, req *pb.DeleteDocumentRequest) (*pb.DeleteDocumentResponse, error) {
	s.opCounts["DeleteDocument"]++

	if req.PolicyId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id is required")
	}

	// SimpleStore doesn't have DeleteDocument, so we'll return a not implemented error for now
	// In production, would need to implement by scanning and deleting all nodes for the policy
	return nil, status.Error(codes.Unimplemented, "DeleteDocument not yet implemented in SimpleStore")
}

// ========== Node Operations ==========

func (s *Server) GetNode(ctx context.Context, req *pb.GetNodeRequest) (*pb.GetNodeResponse, error) {
	s.opCounts["GetNode"]++

	if req.PolicyId == "" || req.NodeId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id and node_id are required")
	}

	node, err := s.docStore.GetNode(req.PolicyId, req.NodeId)
	if err != nil {
		return nil, status.Errorf(codes.NotFound, "node not found: %v", err)
	}

	parentID := ""
	if node.ParentID != nil {
		parentID = *node.ParentID
	}

	pbNode := &pb.Node{
		NodeId:      node.NodeID,
		PolicyId:    node.PolicyID,
		ParentId:    parentID,
		Title:       node.Title,
		PageStart:   int32(node.PageStart),
		PageEnd:     int32(node.PageEnd),
		Summary:     node.Summary,
		Text:        node.Text,
		SectionPath: node.SectionPath,
		ChildIds:    node.ChildIDs,
		Depth:       int32(node.Depth),
		CreatedAt:   timestamppb.New(node.CreatedAt),
		UpdatedAt:   timestamppb.New(node.UpdatedAt),
	}

	return &pb.GetNodeResponse{Node: pbNode}, nil
}

func (s *Server) GetChildren(ctx context.Context, req *pb.GetChildrenRequest) (*pb.GetChildrenResponse, error) {
	s.opCounts["GetChildren"]++

	if req.PolicyId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id is required")
	}

	var parentID *string
	if req.ParentId != "" {
		parentID = &req.ParentId
	}

	children, err := s.docStore.GetChildren(req.PolicyId, parentID)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get children: %v", err)
	}

	pbChildren := make([]*pb.Node, len(children))
	for i, node := range children {
		parentIDStr := ""
		if node.ParentID != nil {
			parentIDStr = *node.ParentID
		}

		pbChildren[i] = &pb.Node{
			NodeId:      node.NodeID,
			PolicyId:    node.PolicyID,
			ParentId:    parentIDStr,
			Title:       node.Title,
			PageStart:   int32(node.PageStart),
			PageEnd:     int32(node.PageEnd),
			Summary:     node.Summary,
			Text:        node.Text,
			SectionPath: node.SectionPath,
			ChildIds:    node.ChildIDs,
			Depth:       int32(node.Depth),
			CreatedAt:   timestamppb.New(node.CreatedAt),
			UpdatedAt:   timestamppb.New(node.UpdatedAt),
		}
	}

	return &pb.GetChildrenResponse{Children: pbChildren}, nil
}

func (s *Server) GetSubtree(ctx context.Context, req *pb.GetSubtreeRequest) (*pb.GetSubtreeResponse, error) {
	s.opCounts["GetSubtree"]++

	if req.PolicyId == "" || req.NodeId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id and node_id are required")
	}

	opts := document.QueryOptions{
		MaxDepth: int(req.MaxDepth),
	}

	nodes, err := s.docStore.GetSubtree(req.PolicyId, req.NodeId, opts)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get subtree: %v", err)
	}

	pbNodes := make([]*pb.Node, len(nodes))
	for i, node := range nodes {
		parentID := ""
		if node.ParentID != nil {
			parentID = *node.ParentID
		}

		pbNodes[i] = &pb.Node{
			NodeId:      node.NodeID,
			PolicyId:    node.PolicyID,
			ParentId:    parentID,
			Title:       node.Title,
			PageStart:   int32(node.PageStart),
			PageEnd:     int32(node.PageEnd),
			Summary:     node.Summary,
			Text:        node.Text,
			SectionPath: node.SectionPath,
			ChildIds:    node.ChildIDs,
			Depth:       int32(node.Depth),
			CreatedAt:   timestamppb.New(node.CreatedAt),
			UpdatedAt:   timestamppb.New(node.UpdatedAt),
		}
	}

	return &pb.GetSubtreeResponse{Nodes: pbNodes}, nil
}

func (s *Server) GetAncestorPath(ctx context.Context, req *pb.GetAncestorPathRequest) (*pb.GetAncestorPathResponse, error) {
	s.opCounts["GetAncestorPath"]++

	if req.PolicyId == "" || req.NodeId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id and node_id are required")
	}

	path, err := s.docStore.GetAncestorPath(req.PolicyId, req.NodeId)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get ancestor path: %v", err)
	}

	pbPath := make([]*pb.Node, len(path))
	for i, node := range path {
		parentID := ""
		if node.ParentID != nil {
			parentID = *node.ParentID
		}

		pbPath[i] = &pb.Node{
			NodeId:      node.NodeID,
			PolicyId:    node.PolicyID,
			ParentId:    parentID,
			Title:       node.Title,
			PageStart:   int32(node.PageStart),
			PageEnd:     int32(node.PageEnd),
			Summary:     node.Summary,
			Text:        node.Text,
			SectionPath: node.SectionPath,
			ChildIds:    node.ChildIDs,
			Depth:       int32(node.Depth),
			CreatedAt:   timestamppb.New(node.CreatedAt),
			UpdatedAt:   timestamppb.New(node.UpdatedAt),
		}
	}

	return &pb.GetAncestorPathResponse{Ancestors: pbPath}, nil
}

// ========== Search Operations ==========

func (s *Server) SearchByKeyword(ctx context.Context, req *pb.SearchRequest) (*pb.SearchResponse, error) {
	s.opCounts["SearchByKeyword"]++

	if req.PolicyId == "" || req.Query == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id and query are required")
	}

	limit := int(req.Limit)
	if limit == 0 {
		limit = 10
	}

	results, err := s.docStore.Search(req.PolicyId, req.Query, limit)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "search failed: %v", err)
	}

	pbResults := make([]*pb.SearchResult, len(results))
	for i, result := range results {
		// Get full node details for the search result
		node, err := s.docStore.GetNode(result.PolicyID, result.NodeID)
		if err != nil {
			// If we can't get the node, just use what we have from search
			pbResults[i] = &pb.SearchResult{
				Node: &pb.Node{
					NodeId:   result.NodeID,
					PolicyId: result.PolicyID,
					Title:    result.Title,
					Summary:  result.Summary,
				},
				Score: float32(result.Score),
			}
			continue
		}

		parentID := ""
		if node.ParentID != nil {
			parentID = *node.ParentID
		}

		pbResults[i] = &pb.SearchResult{
			Node: &pb.Node{
				NodeId:      node.NodeID,
				PolicyId:    node.PolicyID,
				ParentId:    parentID,
				Title:       node.Title,
				PageStart:   int32(node.PageStart),
				PageEnd:     int32(node.PageEnd),
				Summary:     node.Summary,
				Text:        node.Text,
				SectionPath: node.SectionPath,
				ChildIds:    node.ChildIDs,
				Depth:       int32(node.Depth),
				CreatedAt:   timestamppb.New(node.CreatedAt),
				UpdatedAt:   timestamppb.New(node.UpdatedAt),
			},
			Score: float32(result.Score),
		}
	}

	return &pb.SearchResponse{Results: pbResults}, nil
}

func (s *Server) GetNodesByPage(ctx context.Context, req *pb.GetNodesByPageRequest) (*pb.GetNodesByPageResponse, error) {
	s.opCounts["GetNodesByPage"]++

	if req.PolicyId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id is required")
	}

	// GetNodesByPage not implemented in SimpleStore yet
	// For now, return unimplemented error
	// In production, would need to add method to SimpleStore that queries by page range
	return nil, status.Error(codes.Unimplemented, "GetNodesByPage not yet implemented in SimpleStore")
}

// ========== Version Operations ==========

func (s *Server) GetVersionAsOf(ctx context.Context, req *pb.GetVersionAsOfRequest) (*pb.PolicyVersion, error) {
	s.opCounts["GetVersionAsOf"]++

	if req.PolicyId == "" || req.AsOfTime == nil {
		return nil, status.Error(codes.InvalidArgument, "policy_id and as_of_time are required")
	}

	ver, err := s.verStore.GetVersionAsOf(req.PolicyId, req.AsOfTime.AsTime())
	if err != nil {
		return nil, status.Errorf(codes.NotFound, "version not found: %v", err)
	}

	return &pb.PolicyVersion{
		PolicyId:    ver.PolicyID,
		VersionId:   ver.VersionID,
		DocumentId:  ver.DocumentID,
		CreatedAt:   timestamppb.New(ver.CreatedAt),
		CreatedBy:   ver.CreatedBy,
		Description: ver.Description,
		Tags:        ver.Tags,
	}, nil
}

func (s *Server) ListVersions(ctx context.Context, req *pb.ListVersionsRequest) (*pb.ListVersionsResponse, error) {
	s.opCounts["ListVersions"]++

	if req.PolicyId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id is required")
	}

	limit := int(req.Limit)
	if limit == 0 {
		limit = 100
	}

	versions, err := s.verStore.ListVersions(req.PolicyId, limit)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list versions: %v", err)
	}

	pbVersions := make([]*pb.PolicyVersion, len(versions))
	for i, ver := range versions {
		pbVersions[i] = &pb.PolicyVersion{
			PolicyId:    ver.PolicyID,
			VersionId:   ver.VersionID,
			DocumentId:  ver.DocumentID,
			CreatedAt:   timestamppb.New(ver.CreatedAt),
			CreatedBy:   ver.CreatedBy,
			Description: ver.Description,
			Tags:        ver.Tags,
		}
	}

	return &pb.ListVersionsResponse{Versions: pbVersions}, nil
}

// ========== Metadata Operations ==========

func (s *Server) StoreToolResult(ctx context.Context, req *pb.StoreToolResultRequest) (*pb.StoreToolResultResponse, error) {
	s.opCounts["StoreToolResult"]++

	if req.Result == nil {
		return nil, status.Error(codes.InvalidArgument, "result is required")
	}

	// Store as metadata entry
	entry := &metadata.MetadataEntry{
		EntityType: "tool_result",
		EntityID:   req.Result.ExecutionId,
		Key:        "tool_result",
		Value:      fmt.Sprintf("%s|%s|%s|%s", req.Result.ToolName, req.Result.PolicyId, req.Result.NodeId, req.Result.ResultData),
		ValueType:  "json",
		CreatedAt:  req.Result.ExecutedAt.AsTime(),
		UpdatedAt:  req.Result.ExecutedAt.AsTime(),
	}

	if err := s.metaStore.SetMetadata(entry); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to store tool result: %v", err)
	}

	return &pb.StoreToolResultResponse{
		Success: true,
		Message: "Tool result stored successfully",
	}, nil
}

func (s *Server) GetToolResults(ctx context.Context, req *pb.GetToolResultsRequest) (*pb.GetToolResultsResponse, error) {
	s.opCounts["GetToolResults"]++

	if req.PolicyId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id is required")
	}

	// Query metadata by entity type
	var entityType = "tool_result"
	entries, err := s.metaStore.QueryByKey("tool_result", &entityType, int(req.Limit))
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get tool results: %v", err)
	}

	// Convert to tool results (simplified - in production would parse the stored data)
	results := make([]*pb.ToolResult, 0)
	for _, entry := range entries {
		results = append(results, &pb.ToolResult{
			ExecutionId: entry.EntityID,
			ExecutedAt:  timestamppb.New(entry.CreatedAt),
		})
	}

	return &pb.GetToolResultsResponse{Results: results}, nil
}

func (s *Server) StoreTrajectory(ctx context.Context, req *pb.StoreTrajectoryRequest) (*pb.StoreTrajectoryResponse, error) {
	s.opCounts["StoreTrajectory"]++

	if req.Trajectory == nil {
		return nil, status.Error(codes.InvalidArgument, "trajectory is required")
	}

	// Store as metadata
	entry := &metadata.MetadataEntry{
		EntityType: "trajectory",
		EntityID:   req.Trajectory.TrajectoryId,
		Key:        "case_id",
		Value:      req.Trajectory.CaseId,
		ValueType:  "string",
		CreatedAt:  req.Trajectory.StartedAt.AsTime(),
		UpdatedAt:  req.Trajectory.CompletedAt.AsTime(),
	}

	if err := s.metaStore.SetMetadata(entry); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to store trajectory: %v", err)
	}

	return &pb.StoreTrajectoryResponse{
		Success: true,
		Message: "Trajectory stored successfully",
	}, nil
}

func (s *Server) GetTrajectories(ctx context.Context, req *pb.GetTrajectoriesRequest) (*pb.GetTrajectoriesResponse, error) {
	s.opCounts["GetTrajectories"]++

	if req.CaseId == "" {
		return nil, status.Error(codes.InvalidArgument, "case_id is required")
	}

	var entityType = "trajectory"
	entries, err := s.metaStore.QueryByKeyValue("case_id", req.CaseId, &entityType, int(req.Limit))
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get trajectories: %v", err)
	}

	trajectories := make([]*pb.Trajectory, len(entries))
	for i, entry := range entries {
		trajectories[i] = &pb.Trajectory{
			TrajectoryId: entry.EntityID,
			CaseId:       entry.Value,
			StartedAt:    timestamppb.New(entry.CreatedAt),
			CompletedAt:  timestamppb.New(entry.UpdatedAt),
		}
	}

	return &pb.GetTrajectoriesResponse{Trajectories: trajectories}, nil
}

func (s *Server) StoreCrossReference(ctx context.Context, req *pb.StoreCrossReferenceRequest) (*pb.StoreCrossReferenceResponse, error) {
	s.opCounts["StoreCrossReference"]++

	if req.CrossReference == nil {
		return nil, status.Error(codes.InvalidArgument, "cross_reference is required")
	}

	refID := fmt.Sprintf("%s:%s->%s:%s",
		req.CrossReference.SourcePolicyId, req.CrossReference.SourceNodeId,
		req.CrossReference.TargetPolicyId, req.CrossReference.TargetNodeId)

	entry := &metadata.MetadataEntry{
		EntityType: "cross_reference",
		EntityID:   refID,
		Key:        "reference_type",
		Value:      req.CrossReference.ReferenceType,
		ValueType:  "string",
		CreatedAt:  req.CrossReference.CreatedAt.AsTime(),
		UpdatedAt:  req.CrossReference.CreatedAt.AsTime(),
	}

	if err := s.metaStore.SetMetadata(entry); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to store cross reference: %v", err)
	}

	return &pb.StoreCrossReferenceResponse{
		Success: true,
		Message: "Cross reference stored successfully",
	}, nil
}

func (s *Server) GetCrossReferences(ctx context.Context, req *pb.GetCrossReferencesRequest) (*pb.GetCrossReferencesResponse, error) {
	s.opCounts["GetCrossReferences"]++

	if req.PolicyId == "" || req.NodeId == "" {
		return nil, status.Error(codes.InvalidArgument, "policy_id and node_id are required")
	}

	var entityType = "cross_reference"
	entries, err := s.metaStore.QueryByKey("reference_type", &entityType, 0)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get cross references: %v", err)
	}

	references := make([]*pb.CrossReference, 0)
	for _, entry := range entries {
		references = append(references, &pb.CrossReference{
			ReferenceType: entry.Value,
			CreatedAt:     timestamppb.New(entry.CreatedAt),
		})
	}

	return &pb.GetCrossReferencesResponse{References: references}, nil
}

func (s *Server) StoreContradiction(ctx context.Context, req *pb.StoreContradictionRequest) (*pb.StoreContradictionResponse, error) {
	s.opCounts["StoreContradiction"]++

	if req.Contradiction == nil {
		return nil, status.Error(codes.InvalidArgument, "contradiction is required")
	}

	entry := &metadata.MetadataEntry{
		EntityType: "contradiction",
		EntityID:   req.Contradiction.ContradictionId,
		Key:        "severity",
		Value:      req.Contradiction.Severity,
		ValueType:  "string",
		CreatedAt:  req.Contradiction.DetectedAt.AsTime(),
		UpdatedAt:  req.Contradiction.DetectedAt.AsTime(),
	}

	if err := s.metaStore.SetMetadata(entry); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to store contradiction: %v", err)
	}

	return &pb.StoreContradictionResponse{
		Success: true,
		Message: "Contradiction stored successfully",
	}, nil
}

// ========== Prompt Operations ==========

func (s *Server) StorePrompt(ctx context.Context, req *pb.StorePromptRequest) (*pb.StorePromptResponse, error) {
	s.opCounts["StorePrompt"]++

	if req.Prompt == nil {
		return nil, status.Error(codes.InvalidArgument, "prompt is required")
	}

	// Store as prompt template (simplified - would use actual prompt store in production)
	entry := &metadata.MetadataEntry{
		EntityType: "prompt",
		EntityID:   req.Prompt.PromptId,
		Key:        "name",
		Value:      req.Prompt.Name,
		ValueType:  "string",
		CreatedAt:  req.Prompt.CreatedAt.AsTime(),
		UpdatedAt:  req.Prompt.CreatedAt.AsTime(),
	}

	if err := s.metaStore.SetMetadata(entry); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to store prompt: %v", err)
	}

	return &pb.StorePromptResponse{
		Success: true,
		Message: "Prompt stored successfully",
	}, nil
}

func (s *Server) GetPrompt(ctx context.Context, req *pb.GetPromptRequest) (*pb.GetPromptResponse, error) {
	s.opCounts["GetPrompt"]++

	if req.PromptId == "" {
		return nil, status.Error(codes.InvalidArgument, "prompt_id is required")
	}

	entry, err := s.metaStore.GetMetadata("prompt", req.PromptId, "name")
	if err != nil {
		return nil, status.Errorf(codes.NotFound, "prompt not found: %v", err)
	}

	return &pb.GetPromptResponse{
		Prompt: &pb.PromptTemplate{
			PromptId:  entry.EntityID,
			Name:      entry.Value,
			CreatedAt: timestamppb.New(entry.CreatedAt),
		},
	}, nil
}

func (s *Server) RecordPromptUsage(ctx context.Context, req *pb.RecordPromptUsageRequest) (*pb.RecordPromptUsageResponse, error) {
	s.opCounts["RecordPromptUsage"]++

	if req.Usage == nil {
		return nil, status.Error(codes.InvalidArgument, "usage is required")
	}

	entry := &metadata.MetadataEntry{
		EntityType: "prompt_usage",
		EntityID:   req.Usage.UsageId,
		Key:        "prompt_id",
		Value:      req.Usage.PromptId,
		ValueType:  "string",
		CreatedAt:  req.Usage.UsedAt.AsTime(),
		UpdatedAt:  req.Usage.UsedAt.AsTime(),
	}

	if err := s.metaStore.SetMetadata(entry); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to record prompt usage: %v", err)
	}

	return &pb.RecordPromptUsageResponse{
		Success: true,
		Message: "Prompt usage recorded successfully",
	}, nil
}

// ========== Health & Status ==========

func (s *Server) Health(ctx context.Context, req *pb.HealthRequest) (*pb.HealthResponse, error) {
	return &pb.HealthResponse{
		Healthy:       true,
		Version:       "1.0.0",
		UptimeSeconds: int64(time.Since(s.startTime).Seconds()),
	}, nil
}

func (s *Server) Stats(ctx context.Context, req *pb.StatsRequest) (*pb.StatsResponse, error) {
	// Count nodes by scanning with PREFIX_NODE (2000)
	nodeCount := int64(0)
	nodePrefix := []byte{0x00, 0x00, 0x07, 0xD0} // PREFIX_NODE = 2000 encoded
	s.kv.Scan(nodePrefix, func(key, val []byte) bool {
		if len(key) >= 4 {
			// Check if key starts with PREFIX_NODE
			prefix := uint32(key[0])<<24 | uint32(key[1])<<16 | uint32(key[2])<<8 | uint32(key[3])
			if prefix == 2000 {
				nodeCount++
			} else {
				return false // Stop scanning when we hit different prefix
			}
		}
		return true
	})

	// Get database file size
	var dbSize int64
	if fileInfo, err := os.Stat(s.kv.Path); err == nil {
		dbSize = fileInfo.Size()
	}

	// Estimate documents (rough estimate - 1 document per unique policy ID)
	// For simplicity, we'll use opCounts["StoreDocument"]
	docCount := s.opCounts["StoreDocument"]

	return &pb.StatsResponse{
		TotalDocuments:  docCount,
		TotalNodes:      nodeCount,
		TotalVersions:   0, // Would need to scan version keys
		DbSizeBytes:     dbSize,
		OperationCounts: s.opCounts,
	}, nil
}
