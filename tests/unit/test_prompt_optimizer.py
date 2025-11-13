"""Tests for the PromptOptimizer orchestration."""

import pytest

from reasoning_service.models.schema import CitationInfo, CriterionResult, DecisionStatus, RetrievalMethod
from reasoning_service.services.prompt_evaluator import EvaluationMetrics
from reasoning_service.services.prompt_optimizer import EvaluationResult, OptimizationConfig, PromptOptimizer
from reasoning_service.services.prompt_registry import PromptRegistry


class FakeAdapter:
    def __init__(self):
        self.calls = 0

    async def evaluate_candidate(self, candidate, minibatch):
        self.calls += 1
        score = 0.5 + self.calls * 0.1
        metrics = EvaluationMetrics(
            aggregate_score=score,
            citation_accuracy=0.8,
            reasoning_coherence=0.7,
            confidence_calibration=0.6,
            status_correctness=0.9,
        )
        fake_result = CriterionResult(
            criterion_id="demo",
            status=DecisionStatus.MET,
            citation=CitationInfo(doc="LCD-L34220", version="v1", section="A", pages=[1]),
            rationale="ok",
            confidence=0.9,
            confidence_breakdown=None,
            search_trajectory=["root"],
            retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
            reasoning_trace=[],
        )
        return EvaluationResult(
            candidate_id=f"id-{self.calls}",
            prompt_text=candidate["system_prompt"],
            metrics=metrics,
            feedback="Improve citations.",
            case_results=[fake_result],
            evaluation_time_ms=10,
        )


@pytest.mark.asyncio
async def test_prompt_optimizer_persists_best_prompt(tmp_path):
    adapter = FakeAdapter()
    registry = PromptRegistry(path=tmp_path / "registry.json")
    optimizer = PromptOptimizer(
        adapter=adapter,
        registry=registry,
        config=OptimizationConfig(target_aggregate_score=0.8),
    )

    result = await optimizer.optimize(
        base_prompt="Base prompt",
        test_cases=[{"criterion_result": None}],
        generations=3,
    )

    assert result is not None
    assert registry.latest() is not None
    assert adapter.calls >= 1
