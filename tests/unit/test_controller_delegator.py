"""Tests for the controller delegator that switches between heuristic and LLM implementations."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from reasoning_service.models.schema import (
    CaseBundle,
    CriterionResult,
    DecisionStatus,
    ConfidenceBreakdown,
    CitationInfo,
    RetrievalMethod,
)
from reasoning_service.services import controller as controller_module
from reasoning_service.services.controller import ReActController
from reasoning_service.services.prompt_registry import PromptRegistry
from reasoning_service.prompts.react_system_prompt import REACT_SYSTEM_PROMPT


def _case_bundle():
    return CaseBundle(
        case_id="case-shadow",
        policy_id="LCD-L34220",
        fields=[],
        metadata={},
    )


def _criterion_result(status: DecisionStatus) -> CriterionResult:
    return CriterionResult(
        criterion_id="crit-1",
        status=status,
        confidence=0.8,
        confidence_breakdown=ConfidenceBreakdown(c_tree=0.9, c_span=0.9, c_final=0.95, c_joint=0.77),
        citation=CitationInfo(doc="doc", version="v1", section="A", pages=[1]),
        rationale="test",
        search_trajectory=[],
        retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
    )


@pytest.mark.asyncio
async def test_delegator_defaults_to_heuristic(monkeypatch):
    """Ensure heuristic controller is used when no LLM flags are enabled."""

    async def fake_eval(self, case_bundle, policy_document_id):
        return [_criterion_result(DecisionStatus.MET)]

    monkeypatch.setattr(
        controller_module.HeuristicReActController, "evaluate_case", fake_eval, raising=False
    )

    # Prevent the delegator from instantiating the LLM controller
    monkeypatch.setattr(controller_module.settings, "react_use_llm_controller", False)
    monkeypatch.setattr(controller_module.settings, "react_shadow_mode", False)
    monkeypatch.setattr(controller_module.settings, "react_ab_test_ratio", 0.0)
    monkeypatch.setattr(controller_module.settings, "prompt_ab_test_ratio", 0.0)

    retrieval_service = AsyncMock()
    controller = ReActController(retrieval_service=retrieval_service)

    results = await controller.evaluate_case(_case_bundle(), policy_document_id="doc-123")

    assert results[0].status == DecisionStatus.MET


@pytest.mark.asyncio
async def test_delegator_falls_back_when_llm_fails(monkeypatch):
    """If the LLM controller raises, we fall back to heuristic output."""

    async def fake_heuristic(self, case_bundle, policy_document_id):
        return [_criterion_result(DecisionStatus.UNCERTAIN)]

    class FailingLLM:
        def __init__(self, *args, **kwargs):
            pass

        async def evaluate_case(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        controller_module.HeuristicReActController, "evaluate_case", fake_heuristic, raising=False
    )
    monkeypatch.setattr(controller_module, "LLMReActController", FailingLLM)

    monkeypatch.setattr(controller_module.settings, "react_use_llm_controller", True)
    monkeypatch.setattr(controller_module.settings, "react_shadow_mode", False)
    monkeypatch.setattr(controller_module.settings, "react_ab_test_ratio", 0.0)
    monkeypatch.setattr(controller_module.settings, "react_fallback_enabled", True)
    monkeypatch.setattr(controller_module.settings, "prompt_ab_test_ratio", 0.0)

    retrieval_service = AsyncMock()
    controller = ReActController(retrieval_service=retrieval_service)

    results = await controller.evaluate_case(_case_bundle(), policy_document_id="doc-123")

    assert results[0].status == DecisionStatus.UNCERTAIN


@pytest.mark.asyncio
async def test_llm_prompt_uses_registry_when_ratio_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(controller_module.settings, "react_use_llm_controller", True)
    monkeypatch.setattr(controller_module.settings, "react_shadow_mode", False)
    monkeypatch.setattr(controller_module.settings, "react_ab_test_ratio", 0.0)
    monkeypatch.setattr(controller_module.settings, "prompt_ab_test_ratio", 0.0)

    registry = PromptRegistry(path=tmp_path / "prompts.json")
    registry.add_version(prompt_text="OPTIMIZED PROMPT")

    class CapturingLLM:
        def __init__(self, *args, **kwargs):
            self.system_prompt = kwargs.get("system_prompt")
            self.prompt_version = "baseline"
            self.captured: List[str] = []

        async def evaluate_case(self, *args, **kwargs):
            self.captured.append(self.system_prompt)
            return [_criterion_result(DecisionStatus.MET)]

    monkeypatch.setattr(controller_module, "LLMReActController", CapturingLLM)
    retrieval_service = AsyncMock()
    controller = ReActController(
        retrieval_service=retrieval_service,
        prompt_registry=registry,
    )

    await controller.evaluate_case(_case_bundle(), policy_document_id="doc-123")

    assert controller._llm_controller.captured[-1] == "OPTIMIZED PROMPT"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_prompt_ab_ratio_allows_baseline(monkeypatch, tmp_path):
    monkeypatch.setattr(controller_module.settings, "react_use_llm_controller", True)
    monkeypatch.setattr(controller_module.settings, "react_shadow_mode", False)
    monkeypatch.setattr(controller_module.settings, "react_ab_test_ratio", 0.0)
    monkeypatch.setattr(controller_module.settings, "prompt_ab_test_ratio", 0.5)

    registry = PromptRegistry(path=tmp_path / "prompts.json")
    registry.add_version(prompt_text="OPTIMIZED PROMPT")

    class CapturingLLM:
        def __init__(self, *args, **kwargs):
            self.system_prompt = kwargs.get("system_prompt")
            self.prompt_version = "baseline"
            self.captured: List[str] = []

        async def evaluate_case(self, *args, **kwargs):
            self.captured.append(self.system_prompt)
            return [_criterion_result(DecisionStatus.MET)]

    class FixedRandom:
        def __init__(self, value: float):
            self.value = value

        def random(self) -> float:
            return self.value

    monkeypatch.setattr(controller_module, "LLMReActController", CapturingLLM)
    retrieval_service = AsyncMock()
    controller = ReActController(
        retrieval_service=retrieval_service,
        prompt_registry=registry,
    )
    controller._rng = FixedRandom(0.99)  # Force baseline selection

    await controller.evaluate_case(_case_bundle(), policy_document_id="doc-123")

    assert controller._llm_controller.captured[-1] == REACT_SYSTEM_PROMPT  # type: ignore[attr-defined]
