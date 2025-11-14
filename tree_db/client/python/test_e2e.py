#!/usr/bin/env python3
"""Simple end-to-end test for TreeStore."""

import sys
sys.path.insert(0, '.')

from treestore import TreeStoreClient
from datetime import datetime

def main():
    print("=== TreeStore End-to-End Test ===\n")

    # Connect
    print("1. Connecting to TreeStore...")
    client = TreeStoreClient(host="localhost", port=50051)

    # Health check
    print("2. Checking server health...")
    health = client.health()
    assert health["healthy"], "Server not healthy"
    print(f"   ✓ Server v{health['version']} is healthy (uptime: {health['uptime_seconds']}s)")

    # Store document
    print("\n3. Storing test document...")
    document = {
        "policy_id": "E2E-TEST-001",
        "version_id": "v1.0",
        "root_node_id": "root",
    }

    nodes = [
        {
            "node_id": "root",
            "policy_id": "E2E-TEST-001",
            "title": "End-to-End Test Document",
            "page_start": 1,
            "page_end": 50,
            "summary": "This is a test document for end-to-end testing",
            "text": "Testing TreeStore with Python client",
        },
        {
            "node_id": "section-1",
            "policy_id": "E2E-TEST-001",
            "parent_id": "root",
            "title": "Test Section 1",
            "page_start": 1,
            "page_end": 25,
            "summary": "First test section",
            "text": "This section tests basic functionality",
            "depth": 1,
        },
    ]

    result = client.store_document(document, nodes)
    assert result["success"], "Failed to store document"
    print(f"   ✓ {result['message']}")

    # Get document
    print("\n4. Retrieving document...")
    retrieved = client.get_document("E2E-TEST-001")
    assert retrieved["document"]["policy_id"] == "E2E-TEST-001"
    assert len(retrieved["nodes"]) == 2
    print(f"   ✓ Retrieved document with {len(retrieved['nodes'])} nodes")

    # Get node
    print("\n5. Getting specific node...")
    node = client.get_node("E2E-TEST-001", "root")
    assert node["node_id"] == "root"
    assert node["title"] == "End-to-End Test Document"
    print(f"   ✓ Retrieved node: {node['title']}")

    # Get children
    print("\n6. Getting children...")
    children = client.get_children("E2E-TEST-001", "root")
    assert len(children) == 1
    assert children[0]["node_id"] == "section-1"
    print(f"   ✓ Found {len(children)} child node(s)")

    # Search
    print("\n7. Searching document...")
    results = client.search("E2E-TEST-001", "testing", limit=5)
    assert len(results) > 0
    print(f"   ✓ Search found {len(results)} result(s)")
    for result in results:
        print(f"      - {result['node']['title']} (score: {result['score']:.2f})")

    # Get subtree
    print("\n8. Getting subtree...")
    subtree = client.get_subtree("E2E-TEST-001", "root")
    assert len(subtree) == 2
    print(f"   ✓ Subtree has {len(subtree)} nodes")

    # Stats
    print("\n9. Getting database stats...")
    stats = client.stats()
    assert "operation_counts" in stats
    print(f"   ✓ Stats: {stats['operation_counts']}")

    # Close
    client.close()

    print("\n" + "="*50)
    print("✓ All end-to-end tests passed!")
    print("="*50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
