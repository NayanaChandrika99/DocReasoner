"""Unit tests for the synchronous ReActController."""

import pytest

from controller.react_controller import ReActController
from controller.status_mapping import map_cli_status_to_api
from reasoning_service.models.schema import DecisionStatus
from retrieval.service import NodeReference, RetrievalResult, Span


def _build_retrieval(spans_text, confidence=0.9, reason_code=None):
    spans = [Span(node_id="n1", page_index=1, text=text) for text in spans_text]
    node_refs = [NodeReference(node_id="n1", pages=[1, 2], title="Section A")]
    return RetrievalResult(
        node_refs=node_refs,
        spans=spans,
        retrieval_method="pageindex-llm",
        confidence=confidence,
        reason_code=reason_code,
        search_trajectory=["root", "n1"],
    )


def _build_case(facts, policy=None):
    policy_data = (
        {
            "policy_id": "LCD-L34220",
            "version_id": "2025-Q1",
            "section_path": "Coverage Guidance",
        }
        if policy is None
        else policy
    )
    # If facts is a list of dicts (proper format), use as-is
    # If facts is a list of strings (old format), convert to fact dicts
    if facts and isinstance(facts[0], dict):
        fact_list = facts
    else:
        fact_list = [{"value": fact} for fact in facts]

    return {
        "criterion_id": "criterion-1",
        "policy": policy_data,
        "case_bundle": {"facts": fact_list},
    }


def test_ready_when_fact_matches_span():
    controller = ReActController()
    # Provide proper structured facts with all required fields
    case_data = _build_case(
        [
            {"field": "age", "value": 45, "confidence": 1.0},
            {"field": "primary_diagnosis", "value": "M54.5", "confidence": 0.95},
            {"field": "conservative_treatment_weeks", "value": 8, "confidence": 0.90},
        ]
    )
    retrieval = _build_retrieval(["Patient completed 6 weeks of PT"])

    decision = controller.decide(case_data, retrieval)

    assert decision.status == "ready"
    assert decision.reason_code is None
    assert decision.confidence.c_joint >= controller.abstain_threshold


def test_not_ready_when_high_conflict():
    controller = ReActController()
    # Case with patient under 18 (fails age requirement)
    case_data = _build_case(
        [
            {"field": "age", "value": 16, "confidence": 1.0},
            {"field": "primary_diagnosis", "value": "M54.5", "confidence": 0.95},
            {"field": "conservative_treatment_weeks", "value": 8, "confidence": 0.90},
        ]
    )
    retrieval = _build_retrieval(
        ["Policy requires surgical documentation which is absent"],
        confidence=0.95,
    )

    decision = controller.decide(case_data, retrieval)

    assert decision.status == "not_ready"
    assert decision.reason_code == "criteria_not_met"
    assert decision.confidence.c_joint >= controller.abstain_threshold


def test_uncertain_when_low_confidence():
    controller = ReActController()
    # Case with low confidence diagnosis
    case_data = _build_case(
        [
            {"field": "age", "value": 45, "confidence": 1.0},
            {"field": "primary_diagnosis", "value": "M54.5", "confidence": 0.50},  # Low confidence
            {"field": "conservative_treatment_weeks", "value": 8, "confidence": 0.90},
        ]
    )
    retrieval = _build_retrieval(["Patient completed 6 weeks of PT"], confidence=0.2)

    decision = controller.decide(case_data, retrieval)

    assert decision.status == "uncertain"
    assert decision.reason_code == "insufficient_documentation"
    assert decision.confidence.c_joint < controller.abstain_threshold


def test_citation_falls_back_to_retrieval_metadata():
    controller = ReActController()
    case_data = _build_case(["x"], policy={})
    retrieval = _build_retrieval(["text"])
    retrieval.node_refs[0].title = "Fallback Section"

    decision = controller.decide(case_data, retrieval)

    assert decision.citation is not None
    assert decision.citation.section_path == "Fallback Section"
    assert decision.citation.pages == [1, 2]


def test_cli_status_mapping_to_api_enum():
    assert map_cli_status_to_api("ready") == DecisionStatus.MET
    assert map_cli_status_to_api("not_ready") == DecisionStatus.MISSING
    assert map_cli_status_to_api("unknown") == DecisionStatus.UNCERTAIN
