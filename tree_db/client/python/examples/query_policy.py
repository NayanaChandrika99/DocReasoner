#!/usr/bin/env python3
"""
Example: Querying Policy Documents in TreeStore

This script demonstrates various query patterns for policy documents:
- Full-text search
- Hierarchical navigation
- Ancestor path lookup
- Subtree retrieval

Usage:
    python query_policy.py <policy_id>
"""

import sys
from treestore import TreeStoreClient


def print_node(node, indent=0):
    """Pretty-print a node."""
    prefix = "  " * indent
    print(f"{prefix}• {node['title']}")
    print(f"{prefix}  ID: {node['node_id']}")
    if node.get('page_start') and node.get('page_end'):
        print(f"{prefix}  Pages: {node['page_start']}-{node['page_end']}")
    if node.get('summary'):
        print(f"{prefix}  Summary: {node['summary'][:80]}...")
    print()


def explore_document_structure(client, policy_id):
    """Explore the hierarchical structure of a document."""
    print(f"=== Document Structure: {policy_id} ===\n")

    try:
        # Get full document
        doc_data = client.get_document(policy_id)
        document = doc_data["document"]
        all_nodes = doc_data["nodes"]

        print(f"Document: {policy_id}")
        print(f"  - Root Node: {document['root_node_id']}")
        print(f"  - Total Nodes: {len(all_nodes)}")
        print(f"  - Version: {document.get('version_id', 'N/A')}")
        print()

        # Get root and its immediate children
        root_node_id = document["root_node_id"]
        root = client.get_node(policy_id, root_node_id)
        children = client.get_children(policy_id, root_node_id)

        print("Root Node:")
        print_node(root)

        if children:
            print(f"Direct Children ({len(children)}):")
            for child in children:
                print_node(child, indent=1)

    except Exception as e:
        print(f"Error exploring structure: {e}")


def search_document(client, policy_id, query):
    """Search within a policy document."""
    print(f"=== Searching '{query}' in {policy_id} ===\n")

    try:
        results = client.search(policy_id, query, limit=5)

        if not results:
            print("No results found")
            return

        print(f"Found {len(results)} results:\n")

        for i, result in enumerate(results, 1):
            node = result["node"]
            score = result["score"]

            print(f"{i}. {node['title']} (score: {score:.2f})")
            print(f"   Node ID: {node['node_id']}")
            if node.get('summary'):
                print(f"   Summary: {node['summary'][:100]}...")
            if node.get('page_start'):
                print(f"   Pages: {node['page_start']}-{node.get('page_end', '?')}")
            print()

    except Exception as e:
        print(f"Search error: {e}")


def trace_node_ancestry(client, policy_id, node_id):
    """Trace the ancestry of a node back to the root."""
    print(f"=== Ancestor Path for {node_id} ===\n")

    try:
        path = client.get_ancestor_path(policy_id, node_id)

        print("Path from root to node:\n")

        for i, ancestor in enumerate(path):
            indent = "  " * i
            arrow = "→" if i > 0 else ""
            print(f"{indent}{arrow} {ancestor['title']}")
            print(f"{indent}  (ID: {ancestor['node_id']}, Depth: {ancestor.get('depth', 'N/A')})")

    except Exception as e:
        print(f"Error tracing ancestry: {e}")


def explore_subtree(client, policy_id, node_id, max_depth=2):
    """Explore a subtree starting from a node."""
    print(f"=== Subtree from {node_id} (max depth: {max_depth}) ===\n")

    try:
        nodes = client.get_subtree(policy_id, node_id, max_depth=max_depth)

        print(f"Found {len(nodes)} nodes in subtree:\n")

        # Group by depth for hierarchical display
        by_depth = {}
        for node in nodes:
            depth = node.get('depth', 0)
            if depth not in by_depth:
                by_depth[depth] = []
            by_depth[depth].append(node)

        for depth in sorted(by_depth.keys()):
            print(f"Level {depth}:")
            for node in by_depth[depth]:
                print_node(node, indent=depth)

    except Exception as e:
        print(f"Error exploring subtree: {e}")


def interactive_query(client, policy_id):
    """Interactive query mode."""
    print(f"\n=== Interactive Query Mode for {policy_id} ===")
    print("\nCommands:")
    print("  search <query>     - Search for text")
    print("  node <node_id>     - Get specific node")
    print("  children <node_id> - Get children of node")
    print("  path <node_id>     - Show ancestor path")
    print("  subtree <node_id>  - Show subtree")
    print("  quit               - Exit")
    print()

    while True:
        try:
            cmd = input(f"{policy_id}> ").strip()

            if not cmd:
                continue

            if cmd == "quit":
                break

            parts = cmd.split(maxsplit=1)
            command = parts[0].lower()

            if command == "search" and len(parts) == 2:
                query = parts[1]
                search_document(client, policy_id, query)

            elif command == "node" and len(parts) == 2:
                node_id = parts[1]
                node = client.get_node(policy_id, node_id)
                print_node(node)

            elif command == "children" and len(parts) == 2:
                node_id = parts[1]
                children = client.get_children(policy_id, node_id)
                print(f"\nChildren of {node_id} ({len(children)}):")
                for child in children:
                    print_node(child, indent=1)

            elif command == "path" and len(parts) == 2:
                node_id = parts[1]
                trace_node_ancestry(client, policy_id, node_id)

            elif command == "subtree" and len(parts) == 2:
                node_id = parts[1]
                explore_subtree(client, policy_id, node_id)

            else:
                print("Unknown command or missing arguments")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python query_policy.py <policy_id> [search_query]")
        print("\nExamples:")
        print("  python query_policy.py LCD-12345")
        print("  python query_policy.py LCD-12345 'diabetes coverage'")
        sys.exit(1)

    policy_id = sys.argv[1]
    search_query = sys.argv[2] if len(sys.argv) > 2 else None

    # Connect to TreeStore
    print("Connecting to TreeStore...")
    with TreeStoreClient(host="localhost", port=50051) as client:
        # Check health
        health = client.health()
        if not health["healthy"]:
            print("✗ TreeStore server is not healthy")
            sys.exit(1)

        print(f"✓ Connected to TreeStore v{health['version']}\n")

        # Explore document structure
        explore_document_structure(client, policy_id)

        # If search query provided, search
        if search_query:
            search_document(client, policy_id, search_query)
        else:
            # Interactive mode
            interactive_query(client, policy_id)


if __name__ == "__main__":
    main()
