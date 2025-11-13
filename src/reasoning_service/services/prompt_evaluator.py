"""Evaluation utilities for GEPA prompt optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from reasoning_service.models.schema import CriterionResult


@dataclass
class MetricWeights:
    """Weighting scheme for aggregate score calculation."""

    citation_accuracy: float = 0.4
    reasoning_coherence: float = 0.3
    confidence_calibration: float = 0.2
    status_correctness: float = 0.1


@dataclass
class EvaluationMetrics:
    """Represents the metrics computed for a prompt candidate."""

    aggregate_score: float
    citation_accuracy: float
    reasoning_coherence: float
    confidence_calibration: float
    status_correctness: float


class PolicyEvaluator:
    """Calculates quality metrics for a batch of CriterionResult objects."""

    def __init__(self, weights: MetricWeights | None = None) -> None:
        self.weights = weights or MetricWeights()

    def evaluate(self, results: Iterable[CriterionResult]) -> EvaluationMetrics:
        """Compute metrics using heuristics described in the GEPA spec."""
        results_list: List[CriterionResult] = list(results)
        if not results_list:
            return EvaluationMetrics(0.0, 0.0, 0.0, 0.0, 0.0)

        citation_accuracy = self._compute_citation_accuracy(results_list)
        reasoning_coherence = self._compute_reasoning_coherence(results_list)
        confidence_calibration = self._compute_confidence_calibration(results_list)
        status_correctness = self._compute_status_correctness(results_list)

        aggregate = (
            citation_accuracy * self.weights.citation_accuracy
            + reasoning_coherence * self.weights.reasoning_coherence
            + confidence_calibration * self.weights.confidence_calibration
            + status_correctness * self.weights.status_correctness
        )

        return EvaluationMetrics(
            aggregate_score=round(aggregate, 4),
            citation_accuracy=round(citation_accuracy, 4),
            reasoning_coherence=round(reasoning_coherence, 4),
            confidence_calibration=round(confidence_calibration, 4),
            status_correctness=round(status_correctness, 4),
        )

    def _compute_citation_accuracy(self, results: List[CriterionResult]) -> float:
        valid = 0
        for result in results:
            citation = result.citation
            if citation.doc != "N/A" and citation.section != "N/A" and citation.pages:
                valid += 1
        return valid / len(results)

    def _compute_reasoning_coherence(self, results: List[CriterionResult]) -> float:
        scores = []
        for result in results:
            trace = result.reasoning_trace
            if not trace:
                scores.append(0.0)
                continue
            trace_len_score = min(len(trace) / 5.0, 1.0)
            actions = {step.action for step in trace}
            action_diversity = min(len(actions) / 4.0, 1.0)
            detailed_observations = sum(
                1 for step in trace if step.observation and len(step.observation) > 20
            )
            observation_quality = detailed_observations / len(trace)
            score = (
                trace_len_score * 0.4 + action_diversity * 0.3 + observation_quality * 0.3
            )
            scores.append(score)
        return sum(scores) / len(scores) if scores else 0.0

    def _compute_confidence_calibration(self, results: List[CriterionResult]) -> float:
        calibrated = 0
        for result in results:
            status = result.status.value
            conf = result.confidence
            if status == "met" and conf > 0.75:
                calibrated += 1
            elif status == "missing" and 0.6 < conf < 0.9:
                calibrated += 1
            elif status == "uncertain" and conf < 0.65:
                calibrated += 1
        return calibrated / len(results)

    def _compute_status_correctness(self, results: List[CriterionResult]) -> float:
        """Heuristic correctness score (ground truth unavailable in automation)."""
        correct = 0
        for result in results:
            has_citation = result.citation.doc != "N/A" and bool(result.citation.pages)
            if result.status.value in {"met", "missing"} and result.confidence > 0.7 and has_citation:
                correct += 1
            elif result.status.value == "uncertain" and result.confidence < 0.65:
                correct += 1
        return correct / len(results)
