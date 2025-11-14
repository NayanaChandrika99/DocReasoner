"""TreeStore-backed tool behavior for temporal_lookup and policy_xref."""

import json
from unittest.mock import AsyncMock

import pytest

from reasoning_service.models.schema import CaseBundle
from reasoning_service.services.tool_handlers import ToolExecutor
from reasoning_service.services.treestore_client import TreeStoreClient, TreeStoreNode, TreeStoreVersion


def _case_bundle(**overrides):
    payload = {
        "case_id": "case-treestore-001",
        "policy_id": "LCD-L34220",
        "fields": [],
        "metadata": {
            "criterion_id": "lumbar-mri-pt",
            "policy_version_id": "2024-Q4",
            "service_date": "2025-01-10",
        },
    }
    payload.update(overrides)
    return CaseBundle(**payload)


@pytest.fixture
def treestore_client():
    policy_id = "LCD-L34220"
    versions = [
        TreeStoreVersion(
            policy_id=policy_id,
            version_id="2024-Q4",
            effective_start="2024-10-01",
            effective_end="2024-12-31",
            pageindex_doc_id="pi-old",
            previous_version_id=None,
            node_ids=["n-pt", "n-cc", "n-ex"],
        ),
        TreeStoreVersion(
            policy_id=policy_id,
            version_id="2025-Q1",
            effective_start="2025-01-01",
            effective_end=None,
            pageindex_doc_id="pi-new",
            previous_version_id="2024-Q4",
            node_ids=["n-pt", "n-cc", "n-ex"],
        ),
    ]

    node_store = {
        (policy_id, "2024-Q4"): {
            "n-pt": TreeStoreNode(
                node_id="n-pt",
                title="Physical Therapy",
                section_path="2.1",
                pages=[10],
                summary="Requires 4 weeks of PT",
                parent_id="n-root",
                see_also=["n-cc"],
                text="Requires four weeks of supervised physical therapy.\n\nDocument improvements before imaging.",
            ),
            "n-cc": TreeStoreNode(
                node_id="n-cc",
                title="Conservative Care",
                section_path="2.0",
                pages=[9],
                summary="General conservative care requirements",
                parent_id="n-root",
            ),
            "n-ex": TreeStoreNode(
                node_id="n-ex",
                title="Exceptions",
                section_path="2.2",
                pages=[11],
                summary="Exceptions for red flags",
                parent_id="n-root",
            ),
        },
        (policy_id, "2025-Q1"): {
            "n-pt": TreeStoreNode(
                node_id="n-pt",
                title="Physical Therapy",
                section_path="2.1",
                pages=[10],
                summary="Requires 6 weeks of PT",
                parent_id="n-root",
                see_also=["n-cc"],
                text="Updated policy now requires six weeks of conservative care including PT.\n\nDocument failure of PT before MRI.",
            ),
            "n-cc": TreeStoreNode(
                node_id="n-cc",
                title="Conservative Care",
                section_path="2.0",
                pages=[9],
                summary="General conservative care requirements",
                parent_id="n-root",
            ),
            "n-ex": TreeStoreNode(
                node_id="n-ex",
                title="Exceptions",
                section_path="2.2",
                pages=[11],
                summary="Exceptions for red flags",
                parent_id="n-root",
            ),
        },
    }

    cross_refs = {
        (policy_id, "lumbar-mri-pt"): [
            TreeStoreNode(
                node_id="n-pt",
                title="Physical Therapy",
                section_path="2.1",
                pages=[10],
                summary="Requires 6 weeks of PT",
                parent_id="n-root",
            ),
            TreeStoreNode(
                node_id="n-cc",
                title="Conservative Care",
                section_path="2.0",
                pages=[9],
                summary="See also Physical Therapy",
                parent_id="n-root",
            ),
        ]
    }

    return TreeStoreClient(
        version_catalog={policy_id: versions},
        node_store=node_store,
        cross_reference_index=cross_refs,
    )


@pytest.mark.asyncio
async def test_temporal_lookup_uses_treestore_version_and_diffs(treestore_client):
    executor = ToolExecutor(
        retrieval_service=AsyncMock(),
        case_bundle=_case_bundle(),
        treestore_client=treestore_client,
    )
    payload = await executor.execute(
        "temporal_lookup",
        {"policy_id": "LCD-L34220", "as_of_date": "2025-01-10"},
    )
    data = json.loads(payload)
    assert data["version_id"] == "2025-Q1"
    assert data["effective_start"] == "2025-01-01"
    assert data["diffs"], "Expected diffs when node content changes"
    changed = {item["node_id"] for item in data["diffs"]}
    assert "n-pt" in changed


@pytest.mark.asyncio
async def test_policy_xref_surfaces_related_nodes_with_citations(treestore_client):
    executor = ToolExecutor(
        retrieval_service=AsyncMock(),
        case_bundle=_case_bundle(),
        treestore_client=treestore_client,
    )
    payload = await executor.execute("policy_xref", {"criterion_id": "lumbar-mri-pt"})
    data = json.loads(payload)
    assert data["success"] is True
    assert data["related_nodes"], "Expected related nodes from TreeStore"
    assert any(node["reason"] == "xref" for node in data["related_nodes"])
    assert data["citations"], "Citations should include section and page references"


@pytest.mark.asyncio
async def test_spans_tighten_uses_treestore_text(treestore_client):
    metadata = {
        "policy_document_id": "LCD-L34220",
        "policy_version_id": "2025-Q1",
    }
    case_bundle = _case_bundle(metadata=metadata)
    executor = ToolExecutor(
        retrieval_service=AsyncMock(),
        case_bundle=case_bundle,
        treestore_client=treestore_client,
    )
    executor._retrieval_cache["n-pt"] = {"node_id": "n-pt"}
    result = await executor._spans_tighten("n-pt", "conservative care")
    assert result["success"] is True
    assert result["spans"]
