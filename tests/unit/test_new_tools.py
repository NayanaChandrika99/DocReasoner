"""Unit tests for newly added tools (schemas and handlers)."""

import json
import pytest
from unittest.mock import AsyncMock

from reasoning_service.services.tools import get_tool_definitions
from reasoning_service.services.tool_handlers import ToolExecutor
from reasoning_service.models.schema import CaseBundle


def _case_bundle(**overrides):
    payload = {
        "case_id": "case-tools-001",
        "policy_id": "LCD-L34220",
        "fields": [
            {
                "field_name": "diagnosis_code",
                "value": "M54.5",
                "confidence": 0.9,
                "doc_id": "doc-1",
                "page": 1,
                "bbox": [0, 0, 10, 10],
                "field_class": "icd10",
            }
        ],
        "metadata": {
            "criterion_id": "lumbar-mri-pt",
            "policy_version_id": "2025-Q1",
        },
    }
    payload.update(overrides)
    return CaseBundle(**payload)


def _tool_map():
    tools = get_tool_definitions()
    return {t["function"]["name"]: t["function"] for t in tools}


def test_tools_definitions_include_new_tools():
    func_map = _tool_map()
    expected = {
        "policy_xref",
        "temporal_lookup",
        "confidence_score",
        "contradiction_detector",
        "pubmed_search",
        "code_validator",
    }
    for name in expected:
        assert name in func_map, f"Tool '{name}' missing from definitions"

    # spot-check parameters
    assert "criterion_id" in func_map["policy_xref"]["parameters"]["properties"]
    assert "as_of_date" in func_map["temporal_lookup"]["parameters"]["properties"]
    assert "criteria_results" in func_map["confidence_score"]["parameters"]["properties"]
    assert "findings" in func_map["contradiction_detector"]["parameters"]["properties"]
    assert "condition" in func_map["pubmed_search"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_confidence_score_handler():
    retrieval_service = AsyncMock()
    executor = ToolExecutor(retrieval_service=retrieval_service, case_bundle=_case_bundle())
    out = await executor.execute(
        "confidence_score",
        {
            "criteria_results": [
                {"id": "c1", "status": "met"},
                {"id": "c2", "status": "missing"},
                {"id": "c3", "status": "uncertain", "confidence": 0.55},
            ]
        },
    )
    data = json.loads(out)
    assert data["success"] is True
    assert 0.0 <= data["score"] <= 1.0
    assert len(data["per_criterion"]) == 3


@pytest.mark.asyncio
async def test_contradiction_detector_handler():
    retrieval_service = AsyncMock()
    executor = ToolExecutor(retrieval_service=retrieval_service, case_bundle=_case_bundle())
    out = await executor.execute(
        "contradiction_detector",
        {
            "findings": [
                {
                    "criterion_id": "crit1",
                    "evidence": [
                        {"stance": "support", "node_id": "n1"},
                        {"stance": "oppose", "node_id": "n2"},
                    ],
                }
            ]
        },
    )
    data = json.loads(out)
    assert data["success"] is True
    assert len(data["conflicts"]) == 1
    assert data["resolved"] is False


@pytest.mark.asyncio
async def test_code_validator_handler():
    retrieval_service = AsyncMock()
    executor = ToolExecutor(retrieval_service=retrieval_service, case_bundle=_case_bundle())
    out = await executor.execute("code_validator", {"icd10": "m54.5", "cpt": "72148"})
    data = json.loads(out)
    assert data["success"] is True
    assert data["normalized"]["icd10"] == "M54.5"
    assert data["normalized"]["cpt"] == "72148"
    assert isinstance(data["valid"], bool)


@pytest.mark.asyncio
async def test_temporal_lookup_handler():
    retrieval_service = AsyncMock()
    executor = ToolExecutor(retrieval_service=retrieval_service, case_bundle=_case_bundle())
    out = await executor.execute(
        "temporal_lookup", {"policy_id": "LCD-L34220", "as_of_date": "2025-01-01"}
    )
    data = json.loads(out)
    assert data["success"] is True
    assert data["policy_id"] == "LCD-L34220"
    assert data["version_id"] is not None


@pytest.mark.asyncio
async def test_policy_xref_handler():
    retrieval_service = AsyncMock()
    executor = ToolExecutor(retrieval_service=retrieval_service, case_bundle=_case_bundle())
    out = await executor.execute("policy_xref", {"criterion_id": "lumbar-mri-pt"})
    data = json.loads(out)
    assert data["success"] is True
    assert "related_nodes" in data
    assert "citations" in data


@pytest.mark.asyncio
async def test_pubmed_search_handler():
    retrieval_service = AsyncMock()
    executor = ToolExecutor(retrieval_service=retrieval_service, case_bundle=_case_bundle())
    out = await executor.execute(
        "pubmed_search", {"condition": "low back pain", "treatment": "lumbar MRI"}
    )
    data = json.loads(out)
    assert data["success"] is True
    assert "studies" in data and isinstance(data["studies"], list)

