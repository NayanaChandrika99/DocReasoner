# TreeStore Python Client

Python client library for TreeStore hierarchical document database.

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from treestore import TreeStoreClient
from datetime import datetime

# Connect to TreeStore server
client = TreeStoreClient(host="localhost", port=50051)

# Store a document
document = {
    "policy_id": "LCD-12345",
    "version_id": "v1.0",
    "root_node_id": "root",
}

nodes = [
    {
        "node_id": "root",
        "policy_id": "LCD-12345",
        "title": "Policy Document",
        "page_start": 1,
        "page_end": 100,
    },
    {
        "node_id": "section-1",
        "policy_id": "LCD-12345",
        "parent_id": "root",
        "title": "Section 1",
        "page_start": 1,
        "page_end": 25,
        "depth": 1,
    },
]

result = client.store_document(document, nodes)
print(f"Stored: {result['message']}")

# Get a node
node = client.get_node("LCD-12345", "section-1")
print(f"Node: {node['title']}")

# Search
results = client.search("LCD-12345", "eligibility", limit=10)
for result in results:
    print(f"- {result['node']['title']} (score: {result['score']})")

# Get children
children = client.get_children("LCD-12345", "root")
print(f"Root has {len(children)} children")

# Temporal query
as_of = datetime(2024, 1, 1)
version = client.get_version_as_of("LCD-12345", as_of)
print(f"Version at {as_of}: {version['version_id']}")

# Health check
health = client.health()
print(f"Server healthy: {health['healthy']}, uptime: {health['uptime_seconds']}s")

client.close()
```

## Using Context Manager

```python
with TreeStoreClient() as client:
    node = client.get_node("LCD-12345", "root")
    print(node['title'])
```

## API Methods

### Document Operations
- `store_document(document, nodes)` - Store a hierarchical document
- `get_document(policy_id)` - Get complete document with all nodes
- `delete_document(policy_id)` - Delete a document

### Node Operations
- `get_node(policy_id, node_id)` - Get a single node
- `get_children(policy_id, parent_id)` - Get child nodes
- `get_subtree(policy_id, node_id, max_depth)` - Get subtree
- `get_ancestor_path(policy_id, node_id)` - Get path from root

### Search Operations
- `search(policy_id, query, limit)` - Full-text search
- `get_nodes_by_page(policy_id, page_number)` - Get nodes by page

### Version Operations
- `get_version_as_of(policy_id, datetime)` - Temporal query
- `list_versions(policy_id, limit)` - List all versions

### Metadata Operations
- `store_tool_result(result)` - Store tool execution result
- `get_tool_results(policy_id, tool_name, limit)` - Get tool results

### Health & Status
- `health()` - Check server health
- `stats()` - Get database statistics

## Development

Run tests:
```bash
python -m pytest tests/
```

## License

MIT License
