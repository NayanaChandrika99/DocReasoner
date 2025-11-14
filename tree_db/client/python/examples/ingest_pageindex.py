#!/usr/bin/env python3
"""
Example: Ingesting PageIndex Output into TreeStore

This script demonstrates how to ingest a hierarchical document tree
from PageIndex into TreeStore for structured storage and querying.

Usage:
    python ingest_pageindex.py <pageindex_json_file>
"""

import sys
import json
from datetime import datetime
from treestore import TreeStoreClient


def load_pageindex_output(json_file):
    """Load PageIndex JSON output."""
    with open(json_file, 'r') as f:
        return json.load(f)


def convert_to_treestore_format(pageindex_data):
    """
    Convert PageIndex hierarchical tree to TreeStore format.

    PageIndex output structure:
    {
        "policy_id": "LCD-12345",
        "root": {
            "node_id": "root",
            "title": "Policy Title",
            "page_start": 1,
            "page_end": 100,
            "children": [...]
        }
    }
    """
    policy_id = pageindex_data["policy_id"]
    root = pageindex_data["root"]

    # Build document
    document = {
        "policy_id": policy_id,
        "version_id": f"v{datetime.now().strftime('%Y%m%d')}",
        "root_node_id": root["node_id"],
        "pageindex_doc_id": pageindex_data.get("document_id", ""),
    }

    # Flatten tree into list of nodes
    nodes = []

    def traverse(node, parent_id=None, depth=0):
        """Recursively traverse tree and collect nodes."""
        node_data = {
            "node_id": node["node_id"],
            "policy_id": policy_id,
            "title": node.get("title", ""),
            "page_start": node.get("page_start", 0),
            "page_end": node.get("page_end", 0),
            "summary": node.get("summary", ""),
            "text": node.get("text", ""),
            "section_path": node.get("section_path", ""),
            "depth": depth,
        }

        if parent_id:
            node_data["parent_id"] = parent_id

        # Get child IDs
        if "children" in node:
            node_data["child_ids"] = [child["node_id"] for child in node["children"]]

        nodes.append(node_data)

        # Traverse children
        if "children" in node:
            for child in node["children"]:
                traverse(child, parent_id=node["node_id"], depth=depth + 1)

    traverse(root)

    return document, nodes


def ingest_document(client, document, nodes):
    """Ingest document into TreeStore."""
    print(f"Ingesting document: {document['policy_id']}")
    print(f"  - Version: {document['version_id']}")
    print(f"  - Total nodes: {len(nodes)}")
    print(f"  - Root node: {document['root_node_id']}")

    # Store document
    result = client.store_document(document, nodes)

    if result["success"]:
        print(f"✓ Successfully ingested: {result['message']}")
        return True
    else:
        print(f"✗ Failed to ingest: {result['message']}")
        return False


def verify_ingestion(client, policy_id):
    """Verify document was ingested correctly."""
    print(f"\nVerifying ingestion of {policy_id}...")

    try:
        # Get document
        retrieved = client.get_document(policy_id)
        print(f"✓ Retrieved document with {len(retrieved['nodes'])} nodes")

        # Get root node
        root_node_id = retrieved["document"]["root_node_id"]
        root = client.get_node(policy_id, root_node_id)
        print(f"✓ Root node: {root['title']}")

        # Get children of root
        children = client.get_children(policy_id, root_node_id)
        print(f"✓ Root has {len(children)} direct children")

        # Get full subtree
        subtree = client.get_subtree(policy_id, root_node_id)
        print(f"✓ Full subtree has {len(subtree)} nodes")

        return True

    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python ingest_pageindex.py <pageindex_json_file>")
        print("\nExample PageIndex JSON format:")
        print(json.dumps({
            "policy_id": "LCD-12345",
            "document_id": "doc-abc",
            "root": {
                "node_id": "root",
                "title": "Policy Document Title",
                "page_start": 1,
                "page_end": 100,
                "summary": "Document summary",
                "text": "Full text content...",
                "section_path": "1",
                "children": [
                    {
                        "node_id": "section-1",
                        "title": "Section 1",
                        "page_start": 1,
                        "page_end": 25,
                        "summary": "Section summary",
                        "text": "Section content...",
                        "section_path": "1.1",
                        "children": []
                    }
                ]
            }
        }, indent=2))
        sys.exit(1)

    json_file = sys.argv[1]

    # Connect to TreeStore
    print("Connecting to TreeStore...")
    with TreeStoreClient(host="localhost", port=50051) as client:
        # Check server health
        health = client.health()
        if not health["healthy"]:
            print("✗ TreeStore server is not healthy")
            sys.exit(1)
        print(f"✓ Connected to TreeStore v{health['version']}")

        # Load PageIndex output
        print(f"\nLoading PageIndex output from {json_file}...")
        pageindex_data = load_pageindex_output(json_file)
        print(f"✓ Loaded PageIndex output for {pageindex_data['policy_id']}")

        # Convert to TreeStore format
        print("\nConverting to TreeStore format...")
        document, nodes = convert_to_treestore_format(pageindex_data)
        print(f"✓ Converted {len(nodes)} nodes")

        # Ingest document
        print("\nIngesting into TreeStore...")
        success = ingest_document(client, document, nodes)

        if success:
            # Verify ingestion
            verify_ingestion(client, document["policy_id"])
            print(f"\n✓ Document {document['policy_id']} successfully ingested!")
        else:
            print("\n✗ Ingestion failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
