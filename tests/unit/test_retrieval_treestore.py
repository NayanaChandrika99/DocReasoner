# ABOUTME: Tests TreeStore retrieval adapter behavior.
# ABOUTME: Ensures search results include node refs, spans, and trajectory.
"""Unit tests for TreeStore-backed retrieval adapter."""

from reasoning_service.services.treestore_client import TreeStoreClient, TreeStoreNode, TreeStoreVersion
from retrieval.service import TreeStoreRetrievalService


def _client() -> TreeStoreClient:
    policy_id = "LCD-L34220"
    versions = [
        TreeStoreVersion(
            policy_id=policy_id,
            version_id="2025-Q1",
            effective_start="2025-01-01",
            effective_end=None,
            pageindex_doc_id="pi-lcd",
            previous_version_id=None,
            node_ids=["node-1", "node-2"],
        )
    ]
    node_store = {
        (policy_id, "2025-Q1"): {
            "node-1": TreeStoreNode(
                node_id="node-1",
                title="Physical Therapy Requirements",
                section_path="2.1",
                pages=[10],
                summary="Requires 6 weeks of PT.",
                parent_id=None,
                keywords=["physical", "therapy"],
                text="Requires at least six weeks of conservative care including physical therapy.",
            ),
            "node-2": TreeStoreNode(
                node_id="node-2",
                title="Exceptions",
                section_path="2.2",
                pages=[11],
                summary="Exceptions for red flags",
                parent_id="node-1",
                keywords=["exception"],
                text="Exceptions exist when red flags are present.",
            ),
        }
    }
    return TreeStoreClient(version_catalog={policy_id: versions}, node_store=node_store)


def test_treestore_retrieval_returns_nodes_and_trajectory():
    client = _client()
    adapter = TreeStoreRetrievalService(client)

    result = adapter.search(
        query="physical therapy",
        policy_id="LCD-L34220",
        version_id="2025-Q1",
        top_k=2,
    )

    assert result.retrieval_method == "treestore"
    assert len(result.node_refs) == 1
    assert result.search_trajectory
    assert result.spans
