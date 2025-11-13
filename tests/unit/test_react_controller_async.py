"""Tests for the async ReActController."""

import pytest
from unittest.mock import AsyncMock

from reasoning_service.models.schema import CaseBundle
from reasoning_service.services.controller import HeuristicReActController, DecisionStatus
from retrieval.service import NodeReference, RetrievalResult, Span


def _case_bundle(**overrides):
    payload = {
        "case_id": "case-001",
        "policy_id": "LCD-L34220",
        "fields": [
            {
                "field_name": "physical_therapy_duration",
                "value": "6 weeks of PT",
                "confidence": 0.92,
                "doc_id": "doc-1",
                "page": 5,
                "bbox": [0, 0, 100, 200],
                "field_class": "clinical_note",
            }
        ],
        "metadata": {"criterion_id": "lumbar-mri-pt"},
    }
    payload.update(overrides)
    return CaseBundle(**payload)


def _retrieval(spans, confidence=0.9, error=None, reason_code=None):
    return RetrievalResult(
        node_refs=[NodeReference(node_id="n1", pages=[1], title="Section A")],
        spans=[Span(node_id="n1", page_index=1, text=text) for text in spans],
        retrieval_method="pageindex-llm",
        confidence=confidence,
        error=error,
        reason_code=reason_code,
        search_trajectory=["root", "n1"],
    )


@pytest.mark.asyncio
async def test_evaluate_case_returns_met_decision():
    retrieval_service = AsyncMock()
    retrieval_service.retrieve.return_value = _retrieval(["Policy must document 6 weeks of PT prior to MRI."])
    controller = HeuristicReActController(retrieval_service=retrieval_service)
    case_bundle = _case_bundle()

    results = await controller.evaluate_case(case_bundle, policy_document_id="doc-123")

    assert len(results) == 1
    result = results[0]
    assert result.status == DecisionStatus.MET
    assert result.evidence is not None
    assert result.confidence > 0.6
    assert result.confidence_breakdown is not None
    assert result.confidence_breakdown.c_joint == result.confidence
    assert len(result.reasoning_trace) >= 1
    assert result.reason_code is None


@pytest.mark.asyncio
async def test_evaluate_case_handles_retrieval_error():
    retrieval_service = AsyncMock()
    retrieval_service.retrieve.return_value = _retrieval(
        spans=[],
        confidence=0.0,
        error="pageindex failure",
        reason_code="pageindex_error",
    )
    controller = HeuristicReActController(retrieval_service=retrieval_service)
    case_bundle = _case_bundle()

    results = await controller.evaluate_case(case_bundle, policy_document_id="doc-123")

    assert results[0].status == DecisionStatus.UNCERTAIN
    assert results[0].reason_code == "pageindex_error"
    assert results[0].confidence == 0.0
    assert results[0].confidence_breakdown.c_joint == 0.0
    assert len(results[0].reasoning_trace) >= 1


@pytest.mark.asyncio
async def test_identify_criteria_fallback():
    retrieval_service = AsyncMock()
    controller = HeuristicReActController(retrieval_service=retrieval_service)
    case_bundle = _case_bundle(metadata={})

    criteria = await controller._identify_criteria(case_bundle, policy_document_id="doc-123")

    assert criteria == ["LCD-L34220:default"]
