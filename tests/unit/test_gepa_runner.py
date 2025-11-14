# ABOUTME: Tests for GEPA dataset loading and evaluation runner caching.
# ABOUTME: Ensures filesystem loader and runner behave predictably.
"""Unit tests for GEPA dataset loader and evaluation runner."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from reasoning_service.models.schema import (
    CaseBundle,
    CitationInfo,
    ConfidenceBreakdown,
    CriterionResult,
    DecisionStatus,
    ReasoningStep,
    RetrievalMethod,
)
from reasoning_service.services.gepa_runner import (
    EvaluationCase,
    EvaluationCache,
    FileSystemDatasetLoader,
    GEPAEvaluationRunner,
)


def _case_bundle() -> CaseBundle:
    return CaseBundle(
        case_id="case-gepa",
        policy_id="LCD-L34220",
        fields=[],
        metadata={"criteria": ["crit-a"]},
    )


def _criterion_result() -> CriterionResult:
    return CriterionResult(
        criterion_id="crit-a",
        status=DecisionStatus.MET,
        confidence=0.9,
        confidence_breakdown=ConfidenceBreakdown(c_tree=0.9, c_span=0.9, c_final=0.95, c_joint=0.9),
        citation=CitationInfo(doc="doc", version="v1", section="A", pages=[1]),
        rationale="ok",
        search_trajectory=["root"],
        retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
        reasoning_trace=[ReasoningStep(step=1, action="think", observation="test")],
    )


def test_filesystem_dataset_loader_reads_cases():
    loader = FileSystemDatasetLoader(Path("tests/data/cases/case_demo.json"))
    cases = loader.load()
    assert cases
    assert isinstance(cases[0], EvaluationCase)
    assert cases[0].policy_document_id


@pytest.mark.asyncio
async def test_evaluation_runner_reuses_cache():
    case = EvaluationCase(
        case_bundle=_case_bundle(),
        policy_document_id="doc-123",
        source="unit-test",
    )
    cache = EvaluationCache(ttl_seconds=60)
    call_counter = {"count": 0}

    class StubController:
        def __init__(self):
            self.system_prompt = "baseline"
            self.prompt_version = "baseline"

        async def evaluate_case(self, *args, **kwargs):
            call_counter["count"] += 1
            return [_criterion_result()]

    @asynccontextmanager
    async def provider(prompt_text: str):
        yield StubController()

    runner = GEPAEvaluationRunner(controller_provider=provider, cache=cache)
    await runner.evaluate_prompt("prompt-a", [case])
    await runner.evaluate_prompt("prompt-a", [case])

    assert call_counter["count"] == 1
