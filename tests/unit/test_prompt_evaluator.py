"""Tests for PolicyEvaluator metric calculations."""

from reasoning_service.models.schema import (
    CitationInfo,
    ConfidenceBreakdown,
    CriterionResult,
    DecisionStatus,
    ReasoningStep,
    RetrievalMethod,
)
from reasoning_service.services.prompt_evaluator import MetricWeights, PolicyEvaluator


def _result(status: DecisionStatus, confidence: float, pages: list[int]) -> CriterionResult:
    return CriterionResult(
        criterion_id=f"{status.value}-criterion",
        status=status,
        citation=CitationInfo(doc="LCD-L34220", version="v1", section="Guidance", pages=pages),
        rationale="test",
        confidence=confidence,
        confidence_breakdown=ConfidenceBreakdown(
            c_tree=0.9,
            c_span=0.9,
            c_final=0.95,
            c_joint=confidence,
        ),
        search_trajectory=["root", "node-1"],
        retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
        reasoning_trace=[
            ReasoningStep(step=1, action="think", observation="Long observation text for coherence."),
            ReasoningStep(step=2, action="decide", observation="Decision details."),
        ],
    )


def test_policy_evaluator_weights_scores():
    evaluator = PolicyEvaluator(weights=MetricWeights())
    results = [
        _result(DecisionStatus.MET, 0.9, [1]),
        _result(DecisionStatus.MISSING, 0.8, [2]),
        _result(DecisionStatus.UNCERTAIN, 0.55, []),
    ]

    metrics = evaluator.evaluate(results)

    assert 0 <= metrics.aggregate_score <= 1
    # Citation accuracy should reflect that one result lacks pages.
    assert 0 < metrics.citation_accuracy < 1
    # Calibration rewards high confidence MET and low confidence UNCERTAIN.
    assert metrics.confidence_calibration > 0.3
