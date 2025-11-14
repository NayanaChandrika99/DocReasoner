"""
Integration tests for TreeStore Python client.

These tests require a running TreeStore server.
Start the server with:
    ./treestore-server -port 50051 -db /tmp/test_treestore.db
"""

import pytest
import subprocess
import time
import os
import signal
from datetime import datetime

from treestore import TreeStoreClient


@pytest.fixture(scope="module")
def server_process():
    """Start TreeStore server for tests."""
    # Build server if not exists
    server_path = "../../treestore-server"
    if not os.path.exists(server_path):
        print("Building TreeStore server...")
        subprocess.run(["go", "build", "-o", "../../treestore-server", "../../cmd/treestore/"],
                       check=True, cwd=os.path.dirname(__file__))

    # Start server
    db_path = "/tmp/test_treestore_pytest.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    process = subprocess.Popen(
        [server_path, "-port", "50051", "-db", db_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(1)

    yield process

    # Cleanup
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=5)
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client():
    """Create TreeStore client."""
    client = TreeStoreClient(host="localhost", port=50051)
    yield client
    client.close()


def test_health_check(client):
    """Test server health check."""
    health = client.health()

    assert health["healthy"] is True
    assert health["version"] == "1.0.0"
    assert health["uptime_seconds"] >= 0


def test_store_and_get_document(client):
    """Test storing and retrieving a document."""
    # Store document
    document = {
        "policy_id": "TEST-PY-001",
        "version_id": "v1.0",
        "root_node_id": "root",
        "pageindex_doc_id": "pageindex-123",
        "metadata": {"author": "pytest", "department": "testing"},
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "TEST-PY-001",
            "title": "Test Policy Document",
            "page_start": 1,
            "page_end": 100,
            "summary": "Test policy summary",
            "text": "This is test content for the policy document",
            "section_path": "1",
            "depth": 0,
        },
        {
            "node_id": "section-1",
            "policy_id": "TEST-PY-001",
            "parent_id": "root",
            "title": "Section 1: Coverage Criteria",
            "page_start": 1,
            "page_end": 25,
            "summary": "Coverage criteria section",
            "text": "Coverage is provided for eligible members",
            "section_path": "1.1",
            "depth": 1,
        },
        {
            "node_id": "section-2",
            "policy_id": "TEST-PY-001",
            "parent_id": "root",
            "title": "Section 2: Eligibility Requirements",
            "page_start": 26,
            "page_end": 50,
            "summary": "Eligibility requirements",
            "text": "Members must meet specific eligibility criteria",
            "section_path": "1.2",
            "depth": 1,
        },
    ]

    result = client.store_document(document, nodes)
    assert result["success"] is True
    assert "TEST-PY-001" in result["message"]

    # Get document back
    retrieved = client.get_document("TEST-PY-001")
    assert retrieved["document"]["policy_id"] == "TEST-PY-001"
    assert retrieved["document"]["root_node_id"] == "root"
    assert len(retrieved["nodes"]) == 3


def test_get_node(client):
    """Test getting a single node."""
    # First store a document
    document = {
        "policy_id": "TEST-PY-002",
        "version_id": "v1.0",
        "root_node_id": "root",
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "TEST-PY-002",
            "title": "Root Node",
            "page_start": 1,
            "page_end": 50,
        }
    ]

    client.store_document(document, nodes)

    # Get the node
    node = client.get_node("TEST-PY-002", "root")
    assert node["node_id"] == "root"
    assert node["policy_id"] == "TEST-PY-002"
    assert node["title"] == "Root Node"
    assert node["page_start"] == 1
    assert node["page_end"] == 50


def test_get_children(client):
    """Test getting child nodes."""
    # Store document with children
    document = {
        "policy_id": "TEST-PY-003",
        "version_id": "v1.0",
        "root_node_id": "root",
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "TEST-PY-003",
            "title": "Root",
            "depth": 0,
        },
        {
            "node_id": "child-1",
            "policy_id": "TEST-PY-003",
            "parent_id": "root",
            "title": "Child 1",
            "depth": 1,
        },
        {
            "node_id": "child-2",
            "policy_id": "TEST-PY-003",
            "parent_id": "root",
            "title": "Child 2",
            "depth": 1,
        },
    ]

    client.store_document(document, nodes)

    # Get children
    children = client.get_children("TEST-PY-003", "root")
    assert len(children) == 2

    child_ids = {child["node_id"] for child in children}
    assert "child-1" in child_ids
    assert "child-2" in child_ids


def test_get_subtree(client):
    """Test getting a subtree."""
    # Store multi-level hierarchy
    document = {
        "policy_id": "TEST-PY-004",
        "version_id": "v1.0",
        "root_node_id": "root",
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "TEST-PY-004",
            "title": "Root",
            "depth": 0,
        },
        {
            "node_id": "level1",
            "policy_id": "TEST-PY-004",
            "parent_id": "root",
            "title": "Level 1",
            "depth": 1,
        },
        {
            "node_id": "level2",
            "policy_id": "TEST-PY-004",
            "parent_id": "level1",
            "title": "Level 2",
            "depth": 2,
        },
    ]

    client.store_document(document, nodes)

    # Get full subtree
    subtree = client.get_subtree("TEST-PY-004", "root", max_depth=0)
    assert len(subtree) == 3

    # Get limited depth
    subtree = client.get_subtree("TEST-PY-004", "root", max_depth=1)
    assert len(subtree) == 2


def test_search(client):
    """Test full-text search."""
    # Store document with searchable content
    document = {
        "policy_id": "TEST-PY-005",
        "version_id": "v1.0",
        "root_node_id": "root",
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "TEST-PY-005",
            "title": "Diabetes Treatment Policy",
            "summary": "Coverage for diabetes medications and supplies",
            "text": "This policy covers diabetes treatment including insulin and glucose monitors",
        },
        {
            "node_id": "eligibility",
            "policy_id": "TEST-PY-005",
            "parent_id": "root",
            "title": "Eligibility for Diabetes Coverage",
            "summary": "Who qualifies for diabetes coverage",
            "text": "Patients diagnosed with diabetes mellitus type 1 or type 2 are eligible",
            "depth": 1,
        },
    ]

    client.store_document(document, nodes)

    # Search for "diabetes"
    results = client.search("TEST-PY-005", "diabetes", limit=10)
    assert len(results) > 0

    # Verify results
    for result in results:
        assert "node" in result
        assert "score" in result
        assert result["score"] > 0
        # Check that the node contains "diabetes" (case-insensitive)
        node_text = (result["node"]["title"] + " " +
                     result["node"].get("summary", "") + " " +
                     result["node"].get("text", "")).lower()
        assert "diabetes" in node_text


def test_get_ancestor_path(client):
    """Test getting ancestor path."""
    # Store multi-level hierarchy
    document = {
        "policy_id": "TEST-PY-006",
        "version_id": "v1.0",
        "root_node_id": "root",
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "TEST-PY-006",
            "title": "Root",
            "depth": 0,
        },
        {
            "node_id": "parent",
            "policy_id": "TEST-PY-006",
            "parent_id": "root",
            "title": "Parent",
            "depth": 1,
        },
        {
            "node_id": "child",
            "policy_id": "TEST-PY-006",
            "parent_id": "parent",
            "title": "Child",
            "depth": 2,
        },
    ]

    client.store_document(document, nodes)

    # Get ancestor path
    path = client.get_ancestor_path("TEST-PY-006", "child")
    assert len(path) == 3

    # Verify order: root -> parent -> child
    assert path[0]["node_id"] == "root"
    assert path[1]["node_id"] == "parent"
    assert path[2]["node_id"] == "child"


def test_context_manager(server_process):
    """Test using client with context manager."""
    with TreeStoreClient() as client:
        health = client.health()
        assert health["healthy"] is True


def test_stats(client):
    """Test getting database stats."""
    # Store some data first
    document = {
        "policy_id": "TEST-PY-007",
        "version_id": "v1.0",
        "root_node_id": "root",
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "TEST-PY-007",
            "title": "Test",
        }
    ]

    client.store_document(document, nodes)

    # Get stats
    stats = client.stats()
    assert "operation_counts" in stats
    assert stats["operation_counts"]["StoreDocument"] > 0


def test_tool_result_storage(client):
    """Test storing and retrieving tool results."""
    result = {
        "tool_name": "check_eligibility",
        "execution_id": "exec-001",
        "policy_id": "TEST-PY-008",
        "node_id": "eligibility-section",
        "result_data": '{"eligible": true, "reason": "meets criteria"}',
        "success": True,
    }

    response = client.store_tool_result(result)
    assert response["success"] is True

    # Get tool results
    results = client.get_tool_results("TEST-PY-008", limit=10)
    assert len(results) > 0


if __name__ == "__main__":
    # Can run tests manually
    pytest.main([__file__, "-v"])
