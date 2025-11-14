"""
TreeStore Python Client

High-level Python client for TreeStore gRPC service.
"""

import grpc
from datetime import datetime
from typing import List, Dict, Optional, Any

from . import treestore_pb2 as pb
from . import treestore_pb2_grpc as pb_grpc


class TreeStoreClient:
    """
    High-level Python client for TreeStore.

    Provides convenient methods for all TreeStore operations:
    - Document storage and retrieval
    - Hierarchical node queries
    - Full-text search
    - Version management
    - Tool result tracking
    - Trajectory storage
    - Cross-reference management
    """

    def __init__(self, host: str = "localhost", port: int = 50051):
        """
        Initialize TreeStore client.

        Args:
            host: TreeStore server hostname
            port: TreeStore server port
        """
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = pb_grpc.TreeStoreServiceStub(self.channel)

    def close(self):
        """Close the gRPC channel."""
        self.channel.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # ========== Document Operations ==========

    def store_document(self, document: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Store a hierarchical document with nodes.

        Args:
            document: Document metadata dict with keys: policy_id, version_id, root_node_id, etc.
            nodes: List of node dicts with keys: node_id, parent_id, title, page_start, page_end, etc.

        Returns:
            Response dict with success status and message
        """
        doc_msg = pb.Document(
            policy_id=document["policy_id"],
            version_id=document.get("version_id", ""),
            pageindex_doc_id=document.get("pageindex_doc_id", ""),
            root_node_id=document["root_node_id"],
            metadata=document.get("metadata", {}),
        )

        node_msgs = []
        for node in nodes:
            node_msg = pb.Node(
                node_id=node["node_id"],
                policy_id=node["policy_id"],
                parent_id=node.get("parent_id", ""),
                title=node.get("title", ""),
                page_start=node.get("page_start", 0),
                page_end=node.get("page_end", 0),
                summary=node.get("summary", ""),
                text=node.get("text", ""),
                section_path=node.get("section_path", ""),
                child_ids=node.get("child_ids", []),
                depth=node.get("depth", 0),
            )
            node_msgs.append(node_msg)

        request = pb.StoreDocumentRequest(document=doc_msg, nodes=node_msgs)
        response = self.stub.StoreDocument(request)

        return {
            "success": response.success,
            "message": response.message,
        }

    def get_document(self, policy_id: str) -> Dict[str, Any]:
        """
        Get a complete document with all nodes.

        Args:
            policy_id: Policy document ID

        Returns:
            Dict with 'document' and 'nodes' keys
        """
        request = pb.GetDocumentRequest(policy_id=policy_id)
        response = self.stub.GetDocument(request)

        return {
            "document": self._pb_document_to_dict(response.document),
            "nodes": [self._pb_node_to_dict(node) for node in response.nodes],
        }

    def delete_document(self, policy_id: str) -> Dict[str, Any]:
        """
        Delete a document and all its nodes.

        Args:
            policy_id: Policy document ID

        Returns:
            Response dict with success status
        """
        request = pb.DeleteDocumentRequest(policy_id=policy_id)
        response = self.stub.DeleteDocument(request)

        return {
            "success": response.success,
            "message": response.message,
        }

    # ========== Node Operations ==========

    def get_node(self, policy_id: str, node_id: str) -> Dict[str, Any]:
        """
        Get a single node by ID.

        Args:
            policy_id: Policy document ID
            node_id: Node ID

        Returns:
            Node dict
        """
        request = pb.GetNodeRequest(policy_id=policy_id, node_id=node_id)
        response = self.stub.GetNode(request)

        return self._pb_node_to_dict(response.node)

    def get_children(self, policy_id: str, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get child nodes of a parent (or root nodes if parent_id is None).

        Args:
            policy_id: Policy document ID
            parent_id: Parent node ID (None for root nodes)

        Returns:
            List of node dicts
        """
        request = pb.GetChildrenRequest(
            policy_id=policy_id,
            parent_id=parent_id or "",
        )
        response = self.stub.GetChildren(request)

        return [self._pb_node_to_dict(node) for node in response.children]

    def get_subtree(self, policy_id: str, node_id: str, max_depth: int = 0) -> List[Dict[str, Any]]:
        """
        Get a node and all its descendants.

        Args:
            policy_id: Policy document ID
            node_id: Root node ID for subtree
            max_depth: Maximum depth to traverse (0 = unlimited)

        Returns:
            List of node dicts in BFS order
        """
        request = pb.GetSubtreeRequest(
            policy_id=policy_id,
            node_id=node_id,
            max_depth=max_depth,
        )
        response = self.stub.GetSubtree(request)

        return [self._pb_node_to_dict(node) for node in response.nodes]

    def get_ancestor_path(self, policy_id: str, node_id: str) -> List[Dict[str, Any]]:
        """
        Get the path from root to a node.

        Args:
            policy_id: Policy document ID
            node_id: Target node ID

        Returns:
            List of ancestor nodes from root to target
        """
        request = pb.GetAncestorPathRequest(policy_id=policy_id, node_id=node_id)
        response = self.stub.GetAncestorPath(request)

        return [self._pb_node_to_dict(node) for node in response.ancestors]

    # ========== Search Operations ==========

    def search(self, policy_id: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Full-text search within a policy document.

        Args:
            policy_id: Policy document ID
            query: Search query string
            limit: Maximum results to return

        Returns:
            List of search results with node and score
        """
        request = pb.SearchRequest(policy_id=policy_id, query=query, limit=limit)
        response = self.stub.SearchByKeyword(request)

        return [
            {
                "node": self._pb_node_to_dict(result.node),
                "score": result.score,
            }
            for result in response.results
        ]

    def get_nodes_by_page(self, policy_id: str, page_number: int) -> List[Dict[str, Any]]:
        """
        Get all nodes that reference a specific page number.

        Args:
            policy_id: Policy document ID
            page_number: Page number

        Returns:
            List of node dicts
        """
        request = pb.GetNodesByPageRequest(policy_id=policy_id, page_number=page_number)
        response = self.stub.GetNodesByPage(request)

        return [self._pb_node_to_dict(node) for node in response.nodes]

    # ========== Version Operations ==========

    def get_version_as_of(self, policy_id: str, as_of_time: datetime) -> Dict[str, Any]:
        """
        Get the policy version that was active at a specific time (temporal query).

        Args:
            policy_id: Policy document ID
            as_of_time: Point in time

        Returns:
            Version dict
        """
        from google.protobuf.timestamp_pb2 import Timestamp
        ts = Timestamp()
        ts.FromDatetime(as_of_time)

        request = pb.GetVersionAsOfRequest(policy_id=policy_id, as_of_time=ts)
        response = self.stub.GetVersionAsOf(request)

        return self._pb_version_to_dict(response)

    def list_versions(self, policy_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List all versions of a policy document.

        Args:
            policy_id: Policy document ID
            limit: Maximum versions to return

        Returns:
            List of version dicts
        """
        request = pb.ListVersionsRequest(policy_id=policy_id, limit=limit)
        response = self.stub.ListVersions(request)

        return [self._pb_version_to_dict(v) for v in response.versions]

    # ========== Metadata Operations ==========

    def store_tool_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store a tool execution result.

        Args:
            result: Tool result dict with keys: tool_name, execution_id, policy_id, node_id, result_data, etc.

        Returns:
            Response dict with success status
        """
        result_msg = pb.ToolResult(
            tool_name=result["tool_name"],
            execution_id=result["execution_id"],
            policy_id=result.get("policy_id", ""),
            node_id=result.get("node_id", ""),
            result_data=result.get("result_data", ""),
            success=result.get("success", True),
            error_message=result.get("error_message", ""),
        )

        request = pb.StoreToolResultRequest(result=result_msg)
        response = self.stub.StoreToolResult(request)

        return {
            "success": response.success,
            "message": response.message,
        }

    def get_tool_results(self, policy_id: str, tool_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get tool execution results for a policy.

        Args:
            policy_id: Policy document ID
            tool_name: Filter by tool name (optional)
            limit: Maximum results

        Returns:
            List of tool result dicts
        """
        request = pb.GetToolResultsRequest(
            policy_id=policy_id,
            tool_name=tool_name or "",
            limit=limit,
        )
        response = self.stub.GetToolResults(request)

        return [self._pb_tool_result_to_dict(r) for r in response.results]

    # ========== Health & Status ==========

    def health(self) -> Dict[str, Any]:
        """
        Check server health.

        Returns:
            Health status dict
        """
        request = pb.HealthRequest()
        response = self.stub.Health(request)

        return {
            "healthy": response.healthy,
            "version": response.version,
            "uptime_seconds": response.uptime_seconds,
        }

    def stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Stats dict with document counts, node counts, etc.
        """
        request = pb.StatsRequest()
        response = self.stub.Stats(request)

        return {
            "total_documents": response.total_documents,
            "total_nodes": response.total_nodes,
            "total_versions": response.total_versions,
            "db_size_bytes": response.db_size_bytes,
            "operation_counts": dict(response.operation_counts),
        }

    # ========== Helper Methods ==========

    def _pb_document_to_dict(self, doc: pb.Document) -> Dict[str, Any]:
        """Convert protobuf Document to dict."""
        return {
            "policy_id": doc.policy_id,
            "version_id": doc.version_id,
            "pageindex_doc_id": doc.pageindex_doc_id,
            "root_node_id": doc.root_node_id,
            "metadata": dict(doc.metadata),
            "created_at": doc.created_at.ToDatetime() if doc.HasField("created_at") else None,
            "updated_at": doc.updated_at.ToDatetime() if doc.HasField("updated_at") else None,
        }

    def _pb_node_to_dict(self, node: pb.Node) -> Dict[str, Any]:
        """Convert protobuf Node to dict."""
        return {
            "node_id": node.node_id,
            "policy_id": node.policy_id,
            "parent_id": node.parent_id if node.parent_id else None,
            "title": node.title,
            "page_start": node.page_start,
            "page_end": node.page_end,
            "summary": node.summary,
            "text": node.text,
            "section_path": node.section_path,
            "child_ids": list(node.child_ids),
            "depth": node.depth,
            "created_at": node.created_at.ToDatetime() if node.HasField("created_at") else None,
            "updated_at": node.updated_at.ToDatetime() if node.HasField("updated_at") else None,
        }

    def _pb_version_to_dict(self, version: pb.PolicyVersion) -> Dict[str, Any]:
        """Convert protobuf PolicyVersion to dict."""
        return {
            "policy_id": version.policy_id,
            "version_id": version.version_id,
            "document_id": version.document_id,
            "created_at": version.created_at.ToDatetime() if version.HasField("created_at") else None,
            "created_by": version.created_by,
            "description": version.description,
            "tags": list(version.tags),
        }

    def _pb_tool_result_to_dict(self, result: pb.ToolResult) -> Dict[str, Any]:
        """Convert protobuf ToolResult to dict."""
        return {
            "tool_name": result.tool_name,
            "execution_id": result.execution_id,
            "policy_id": result.policy_id,
            "node_id": result.node_id,
            "result_data": result.result_data,
            "success": result.success,
            "error_message": result.error_message,
            "executed_at": result.executed_at.ToDatetime() if result.HasField("executed_at") else None,
        }
