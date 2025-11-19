"""Unit tests for TreeStore client integration."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.reasoning_service.services.treestore_client import (
    TreeStoreClientStub,
    TreeStoreClientGRPC,
    TreeStoreNode,
    TreeStoreVersion,
    TreeStoreClientError,
    create_treestore_client,
)


class TestTreeStoreClientStub:
    """Tests for in-memory stub implementation."""

    def test_get_version_as_of_valid_date(self):
        """Test retrieving version by date."""
        version = TreeStoreVersion(
            policy_id="test-policy",
            version_id="v1",
            effective_start="2024-01-01",
            effective_end="2024-12-31",
            pageindex_doc_id="doc123",
        )

        client = TreeStoreClientStub(
            version_catalog={"test-policy": [version]}
        )

        result = client.get_version_as_of("test-policy", "2024-06-15")
        assert result.version_id == "v1"
        assert result.policy_id == "test-policy"

    def test_get_version_as_of_no_catalog(self):
        """Test error when policy not found."""
        client = TreeStoreClientStub()

        with pytest.raises(TreeStoreClientError, match="No version catalog"):
            client.get_version_as_of("nonexistent-policy", "2024-01-01")

    def test_get_version_as_of_invalid_date(self):
        """Test error with invalid date."""
        version = TreeStoreVersion(
            policy_id="test-policy",
            version_id="v1",
            effective_start="2024-01-01",
            effective_end="2024-12-31",
            pageindex_doc_id="doc123",
        )

        client = TreeStoreClientStub(
            version_catalog={"test-policy": [version]}
        )

        with pytest.raises(TreeStoreClientError, match="Invalid as_of_date"):
            client.get_version_as_of("test-policy", "invalid-date")

    def test_get_nodes_success(self):
        """Test retrieving nodes."""
        node1 = TreeStoreNode(node_id="n1", title="Node 1")
        node2 = TreeStoreNode(node_id="n2", title="Node 2")

        client = TreeStoreClientStub(
            node_store={
                ("policy1", "v1"): {"n1": node1, "n2": node2}
            }
        )

        result = client.get_nodes("policy1", "v1", ["n1"])
        assert len(result) == 1
        assert result["n1"].title == "Node 1"

    def test_get_nodes_all(self):
        """Test retrieving all nodes."""
        node1 = TreeStoreNode(node_id="n1", title="Node 1")
        node2 = TreeStoreNode(node_id="n2", title="Node 2")

        client = TreeStoreClientStub(
            node_store={
                ("policy1", "v1"): {"n1": node1, "n2": node2}
            }
        )

        result = client.get_nodes("policy1", "v1", [])
        assert len(result) == 2

    def test_get_nodes_not_found(self):
        """Test error when nodes not found."""
        client = TreeStoreClientStub()

        with pytest.raises(TreeStoreClientError, match="No nodes found"):
            client.get_nodes("policy1", "v1", ["n1"])

    def test_find_related_nodes_keyword_match(self):
        """Test finding related nodes by keyword."""
        node1 = TreeStoreNode(
            node_id="n1",
            title="Lumbar MRI Guidelines",
            summary="Guidelines for lumbar MRI procedures",
        )
        node2 = TreeStoreNode(
            node_id="n2",
            title="Thoracic Imaging",
            summary="Thoracic imaging protocols",
        )

        client = TreeStoreClientStub(
            node_store={
                ("policy1", "v1"): {"n1": node1, "n2": node2}
            }
        )

        results = client.find_related_nodes(
            "policy1", "v1", "crit1", ["lumbar", "MRI"], limit=5
        )

        assert len(results) > 0
        assert results[0][0].node_id == "n1"
        assert results[0][1] == "keyword"

    def test_search_nodes_basic(self):
        """Test basic keyword search."""
        node1 = TreeStoreNode(
            node_id="n1",
            title="Lumbar MRI Guidelines",
            text="Detailed guidelines for lumbar MRI procedures",
        )
        node2 = TreeStoreNode(
            node_id="n2",
            title="Thoracic Imaging",
            text="Thoracic imaging protocols",
        )

        client = TreeStoreClientStub(
            node_store={
                ("policy1", "v1"): {"n1": node1, "n2": node2}
            }
        )

        version_id, results = client.search_nodes("policy1", "lumbar MRI", "v1", top_k=3)

        assert version_id == "v1"
        assert len(results) > 0
        assert results[0].node_id == "n1"

    def test_latest_version(self):
        """Test getting latest version."""
        v1 = TreeStoreVersion(
            policy_id="policy1",
            version_id="v1",
            effective_start="2024-01-01",
            effective_end=None,
            pageindex_doc_id="doc1",
        )
        v2 = TreeStoreVersion(
            policy_id="policy1",
            version_id="v2",
            effective_start="2024-06-01",
            effective_end=None,
            pageindex_doc_id="doc2",
        )

        client = TreeStoreClientStub(
            version_catalog={"policy1": [v1, v2]}
        )

        latest = client.latest_version("policy1")
        assert latest.version_id == "v2"


class TestTreeStoreClientGRPC:
    """Tests for gRPC client implementation."""

    @patch('src.reasoning_service.services.treestore_client.sys.path')
    def test_initialization_failure(self, mock_path):
        """Test gRPC client initialization failure."""
        with patch('src.reasoning_service.services.treestore_client.sys.path.insert'):
            with patch('builtins.__import__', side_effect=ImportError("Module not found")):
                with pytest.raises(TreeStoreClientError, match="gRPC client initialization failed"):
                    TreeStoreClientGRPC(host="localhost", port=50051)

    def test_dict_to_node_conversion(self):
        """Test conversion from gRPC dict to TreeStoreNode."""
        # Mock gRPC client
        mock_grpc = MagicMock()
        mock_grpc.get_document.return_value = {"nodes": []}

        with patch('src.reasoning_service.services.treestore_client.sys.path.insert'):
            with patch('builtins.__import__'):
                with patch('src.reasoning_service.services.treestore_client.TreeStoreClientGRPC._grpc_client', mock_grpc):
                    client = TreeStoreClientGRPC.__new__(TreeStoreClientGRPC)
                    client._grpc_client = mock_grpc

                    node_dict = {
                        "node_id": "n1",
                        "title": "Test Node",
                        "section_path": "1.2.3",
                        "page_start": 5,
                        "page_end": 10,
                        "summary": "Test summary",
                        "parent_id": "root",
                        "text": "Test text",
                    }

                    node = client._dict_to_node(node_dict)

                    assert node.node_id == "n1"
                    assert node.title == "Test Node"
                    assert node.pages == [5, 6, 7, 8, 9, 10]
                    assert node.summary == "Test summary"
                    assert node.parent_id == "root"


class TestCreateTreeStoreClient:
    """Tests for factory function."""

    def test_create_stub_client(self):
        """Test creating stub client."""
        client = create_treestore_client(use_stub=True)

        assert isinstance(client, TreeStoreClientStub)

    @patch('src.reasoning_service.services.treestore_client.TreeStoreClientGRPC')
    def test_create_grpc_client(self, mock_grpc_class):
        """Test creating gRPC client."""
        mock_instance = MagicMock()
        mock_grpc_class.return_value = mock_instance

        client = create_treestore_client(
            use_stub=False,
            host="test-host",
            port=12345,
            timeout=60,
        )

        mock_grpc_class.assert_called_once_with(
            host="test-host",
            port=12345,
            timeout=60,
            max_retries=3,
            retry_delay=1.0,
            enable_compression=True,
        )

    def test_create_stub_with_data(self):
        """Test creating stub with initial data."""
        version = TreeStoreVersion(
            policy_id="test",
            version_id="v1",
            effective_start="2024-01-01",
            effective_end=None,
            pageindex_doc_id="doc1",
        )

        client = create_treestore_client(
            use_stub=True,
            version_catalog={"test": [version]}
        )

        latest = client.latest_version("test")
        assert latest.version_id == "v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
