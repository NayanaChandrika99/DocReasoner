"""End-to-end integration tests for TreeStore."""

import pytest
import asyncio
import subprocess
import time
import os
from pathlib import Path

from src.reasoning_service.services.treestore_client import (
    create_treestore_client,
    TreeStoreNode,
    TreeStoreVersion,
    TreeStoreClientError,
)


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def treestore_server():
    """Start TreeStore server for tests."""
    # Path to treestore server binary
    server_path = Path(__file__).parent.parent.parent / "tree_db" / "treestore-server"

    if not server_path.exists():
        pytest.skip("TreeStore server binary not found. Run: cd tree_db && go build -o treestore-server ./cmd/treestore/")

    # Start server on a test port
    db_path = "/tmp/test_treestore_e2e.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    process = subprocess.Popen(
        [
            str(server_path),
            "-port", "50053",
            "-metrics-port", "9093",
            "-db", db_path,
            "-log-level", "error",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(2)

    # Check if server started successfully
    if process.poll() is not None:
        stdout, stderr = process.communicate()
        pytest.fail(f"TreeStore server failed to start: {stderr.decode()}")

    yield {
        "host": "localhost",
        "port": 50053,
        "process": process,
    }

    # Cleanup
    process.terminate()
    process.wait(timeout=5)
    if os.path.exists(db_path):
        os.remove(db_path)


class TestTreeStoreE2E:
    """End-to-end tests with real TreeStore server."""

    def test_store_and_retrieve_document(self, treestore_server):
        """Test storing and retrieving a complete document."""
        client = create_treestore_client(
            use_stub=False,
            host=treestore_server["host"],
            port=treestore_server["port"],
            timeout=10,
        )

        try:
            # Create test document
            document = {
                "policy_id": "test-policy-001",
                "version_id": "v1.0",
                "pageindex_doc_id": "doc-12345",
                "root_node_id": "root",
                "metadata": {
                    "effective_date": "2024-01-01",
                    "source_url": "https://example.com/policy.pdf",
                }
            }

            nodes = [
                {
                    "node_id": "root",
                    "policy_id": "test-policy-001",
                    "parent_id": "",
                    "title": "Root Node",
                    "page_start": 1,
                    "page_end": 10,
                    "summary": "Root node of the document",
                    "text": "This is the root node",
                    "section_path": "/",
                    "child_ids": ["child1", "child2"],
                    "depth": 0,
                },
                {
                    "node_id": "child1",
                    "policy_id": "test-policy-001",
                    "parent_id": "root",
                    "title": "Child Node 1",
                    "page_start": 2,
                    "page_end": 5,
                    "summary": "First child node",
                    "text": "Content of child 1",
                    "section_path": "/1",
                    "child_ids": [],
                    "depth": 1,
                },
                {
                    "node_id": "child2",
                    "policy_id": "test-policy-001",
                    "parent_id": "root",
                    "title": "Child Node 2",
                    "page_start": 6,
                    "page_end": 10,
                    "summary": "Second child node",
                    "text": "Content of child 2",
                    "section_path": "/2",
                    "child_ids": [],
                    "depth": 1,
                },
            ]

            # Store document
            response = client._grpc_client.store_document(document=document, nodes=nodes)
            assert response["success"] == True, f"Failed to store document: {response.get('message')}"

            # Retrieve document
            retrieved = client._grpc_client.get_document(policy_id="test-policy-001")
            assert retrieved is not None
            assert retrieved["document"]["policy_id"] == "test-policy-001"
            assert len(retrieved["nodes"]) == 3

        finally:
            client.close()

    def test_search_nodes(self, treestore_server):
        """Test searching nodes by keyword."""
        client = create_treestore_client(
            use_stub=False,
            host=treestore_server["host"],
            port=treestore_server["port"],
        )

        try:
            # Store a document first
            document = {
                "policy_id": "search-test-policy",
                "version_id": "v1.0",
                "pageindex_doc_id": "doc-search",
                "root_node_id": "root",
                "metadata": {},
            }

            nodes = [
                {
                    "node_id": "root",
                    "policy_id": "search-test-policy",
                    "parent_id": "",
                    "title": "Lumbar MRI Guidelines",
                    "page_start": 1,
                    "page_end": 5,
                    "summary": "Guidelines for lumbar spine MRI procedures",
                    "text": "This document covers lumbar MRI imaging protocols",
                    "section_path": "/",
                    "child_ids": [],
                    "depth": 0,
                },
            ]

            client._grpc_client.store_document(document=document, nodes=nodes)

            # Search for nodes
            results = client._grpc_client.search(
                policy_id="search-test-policy",
                query="lumbar MRI",
                limit=10
            )

            assert len(results) > 0
            assert "lumbar" in results[0]["node"]["title"].lower() or "lumbar" in results[0]["node"]["text"].lower()

        finally:
            client.close()

    def test_get_node(self, treestore_server):
        """Test retrieving a single node."""
        client = create_treestore_client(
            use_stub=False,
            host=treestore_server["host"],
            port=treestore_server["port"],
        )

        try:
            # Store document
            document = {
                "policy_id": "single-node-test",
                "version_id": "v1.0",
                "pageindex_doc_id": "doc-single",
                "root_node_id": "test-node-123",
                "metadata": {},
            }

            nodes = [
                {
                    "node_id": "test-node-123",
                    "policy_id": "single-node-test",
                    "parent_id": "",
                    "title": "Test Node",
                    "page_start": 1,
                    "page_end": 2,
                    "summary": "A test node",
                    "text": "Test content",
                    "section_path": "/",
                    "child_ids": [],
                    "depth": 0,
                },
            ]

            client._grpc_client.store_document(document=document, nodes=nodes)

            # Get specific node
            node = client.get_node(
                policy_id="single-node-test",
                version_id="v1.0",
                node_id="test-node-123"
            )

            assert node is not None
            assert node.node_id == "test-node-123"
            assert node.title == "Test Node"
            assert 1 in node.pages

        finally:
            client.close()

    def test_hierarchical_queries(self, treestore_server):
        """Test hierarchical node queries."""
        client = create_treestore_client(
            use_stub=False,
            host=treestore_server["host"],
            port=treestore_server["port"],
        )

        try:
            # Create hierarchical document
            document = {
                "policy_id": "hierarchy-test",
                "version_id": "v1.0",
                "pageindex_doc_id": "doc-hierarchy",
                "root_node_id": "root",
                "metadata": {},
            }

            nodes = [
                {
                    "node_id": "root",
                    "policy_id": "hierarchy-test",
                    "parent_id": "",
                    "title": "Root",
                    "page_start": 1,
                    "page_end": 10,
                    "summary": "Root",
                    "text": "Root",
                    "section_path": "/",
                    "child_ids": ["child1", "child2"],
                    "depth": 0,
                },
                {
                    "node_id": "child1",
                    "policy_id": "hierarchy-test",
                    "parent_id": "root",
                    "title": "Child 1",
                    "page_start": 2,
                    "page_end": 5,
                    "summary": "Child 1",
                    "text": "Child 1",
                    "section_path": "/1",
                    "child_ids": ["grandchild1"],
                    "depth": 1,
                },
                {
                    "node_id": "child2",
                    "policy_id": "hierarchy-test",
                    "parent_id": "root",
                    "title": "Child 2",
                    "page_start": 6,
                    "page_end": 10,
                    "summary": "Child 2",
                    "text": "Child 2",
                    "section_path": "/2",
                    "child_ids": [],
                    "depth": 1,
                },
                {
                    "node_id": "grandchild1",
                    "policy_id": "hierarchy-test",
                    "parent_id": "child1",
                    "title": "Grandchild 1",
                    "page_start": 3,
                    "page_end": 4,
                    "summary": "Grandchild 1",
                    "text": "Grandchild 1",
                    "section_path": "/1/1",
                    "child_ids": [],
                    "depth": 2,
                },
            ]

            client._grpc_client.store_document(document=document, nodes=nodes)

            # Get children of root
            children = client._grpc_client.get_children(
                policy_id="hierarchy-test",
                parent_id="root"
            )

            assert len(children) == 2
            child_ids = [c["node_id"] for c in children]
            assert "child1" in child_ids
            assert "child2" in child_ids

            # Get subtree
            subtree = client._grpc_client.get_subtree(
                policy_id="hierarchy-test",
                node_id="child1",
                max_depth=0
            )

            assert len(subtree) >= 2  # child1 and grandchild1
            node_ids = [n["node_id"] for n in subtree]
            assert "child1" in node_ids
            assert "grandchild1" in node_ids

        finally:
            client.close()

    def test_error_handling(self, treestore_server):
        """Test error handling for invalid requests."""
        client = create_treestore_client(
            use_stub=False,
            host=treestore_server["host"],
            port=treestore_server["port"],
        )

        try:
            # Try to get non-existent document
            node = client.get_node(
                policy_id="nonexistent-policy",
                version_id="v1.0",
                node_id="nonexistent-node"
            )

            # Should return None for not found
            assert node is None

        finally:
            client.close()


class TestRetrievalServiceIntegration:
    """Integration tests for RetrievalService with TreeStore."""

    @pytest.mark.asyncio
    async def test_retrieval_service_treestore_backend(self, treestore_server):
        """Test RetrievalService with TreeStore backend."""
        from src.reasoning_service.services.retrieval import RetrievalService

        # Create TreeStore client
        treestore_client = create_treestore_client(
            use_stub=False,
            host=treestore_server["host"],
            port=treestore_server["port"],
        )

        try:
            # Store test document
            document = {
                "policy_id": "retrieval-test",
                "version_id": "v1.0",
                "pageindex_doc_id": "doc-retrieval",
                "root_node_id": "root",
                "metadata": {},
            }

            nodes = [
                {
                    "node_id": "root",
                    "policy_id": "retrieval-test",
                    "parent_id": "",
                    "title": "Diagnostic Imaging Policy",
                    "page_start": 1,
                    "page_end": 5,
                    "summary": "Policy for diagnostic imaging procedures",
                    "text": "This policy covers MRI, CT, and X-ray procedures",
                    "section_path": "/",
                    "child_ids": [],
                    "depth": 0,
                },
            ]

            treestore_client._grpc_client.store_document(document=document, nodes=nodes)

            # Create retrieval service with TreeStore backend
            retrieval_service = RetrievalService(
                treestore_client=treestore_client,
                backend="treestore"
            )

            # Test retrieval
            results = await retrieval_service.retrieve(
                document_id="retrieval-test",
                query="MRI procedures",
                top_k=5
            )

            assert results is not None
            # Results format depends on TreeStoreRetrievalService implementation

        finally:
            treestore_client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
