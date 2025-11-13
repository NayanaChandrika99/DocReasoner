"""GEPA-inspired prompt optimization orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from reasoning_service.models.schema import CriterionResult
from reasoning_service.services.prompt_evaluator import EvaluationMetrics, PolicyEvaluator


@dataclass
class OptimizationConfig:
    """Configuration options for prompt optimization."""

    auto_mode: str = "medium"
    max_metric_calls: int = 150
    reflection_minibatch_size: int = 3
    candidate_selection_strategy: str = "pareto"
    target_aggregate_score: float = 0.8
    track_stats: bool = True
    skip_perfect_score: bool = True
    citation_accuracy_weight: float = 0.4
    reasoning_coherence_weight: float = 0.3
    confidence_calibration_weight: float = 0.2
    status_correctness_weight: float = 0.1


@dataclass
class EvaluationResult:
    """Result of evaluating a single candidate."""

    candidate_id: str
    prompt_text: str
    metrics: EvaluationMetrics
    feedback: str
    case_results: List[CriterionResult]
    evaluation_time_ms: int


class ReActControllerAdapter:
    """Adapters connect the optimizer to actual controller executions."""

    def __init__(
        self,
        evaluate_fn: Optional[
            Callable[[Dict[str, Any], List[Dict[str, Any]]], Awaitable[List[CriterionResult]]]
        ] = None,
        evaluator: Optional[PolicyEvaluator] = None,
    ) -> None:
        self._evaluate_fn = evaluate_fn
        self._policy_evaluator = evaluator or PolicyEvaluator()

    async def evaluate_candidate(
        self,
        candidate: Dict[str, Any],
        minibatch: List[Dict[str, Any]],
    ) -> EvaluationResult:
        """Run the controller for every case in the minibatch."""
        if self._evaluate_fn is None:
            raise RuntimeError(
                "No evaluation function supplied; provide evaluate_fn to ReActControllerAdapter."
            )
        start = asyncio.get_running_loop().time()
        case_results: List[CriterionResult] = await self._evaluate_fn(candidate, minibatch)
        metrics = self._policy_evaluator.evaluate(case_results)
        feedback = self._build_feedback(metrics)
        candidate_id = hashlib.sha256(candidate["system_prompt"].encode()).hexdigest()[:8]
        elapsed_ms = int((asyncio.get_running_loop().time() - start) * 1000)
        return EvaluationResult(
            candidate_id=candidate_id,
            prompt_text=candidate["system_prompt"],
            metrics=metrics,
            feedback=feedback,
            case_results=case_results,
            evaluation_time_ms=elapsed_ms,
        )

    def _build_feedback(self, metrics: EvaluationMetrics) -> str:
        weaknesses = []
        if metrics.citation_accuracy < 0.85:
            weaknesses.append("Citations frequently missing or incomplete.")
        if metrics.reasoning_coherence < 0.75:
            weaknesses.append("Reasoning trace too shallow or repetitive.")
        if metrics.confidence_calibration < 0.7:
            weaknesses.append("Confidence not calibrated; teach agent to abstain earlier.")
        if metrics.status_correctness < 0.9:
            weaknesses.append("Final status mismatches expectations.")
        if not weaknesses:
            return "Prompt satisfies all targets; refine wording for efficiency."
        return " ".join(weaknesses)


class PromptOptimizer:
    """Iteratively improves the system prompt using evaluation feedback."""

    def __init__(
        self,
        adapter: ReActControllerAdapter,
        registry,
        config: Optional[OptimizationConfig] = None,
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.config = config or OptimizationConfig()
        self.history: List[EvaluationResult] = []

    async def optimize(
        self,
        base_prompt: str,
        test_cases: List[Dict[str, Any]],
        generations: int = 3,
    ) -> Optional[EvaluationResult]:
        """Run GEPA-style optimization and persist the winning prompt."""
        if not test_cases:
            raise ValueError("PromptOptimizer requires at least one test case.")

        best_result: Optional[EvaluationResult] = None
        current_prompt = base_prompt

        for generation in range(generations):
            minibatch = self._select_minibatch(test_cases)
            candidate_payload = {"system_prompt": current_prompt}
            evaluation = await self.adapter.evaluate_candidate(candidate_payload, minibatch)
            self.history.append(evaluation)

            if not best_result or evaluation.metrics.aggregate_score > best_result.metrics.aggregate_score:
                best_result = evaluation

            if evaluation.metrics.aggregate_score >= self.config.target_aggregate_score:
                break

            current_prompt = self._reflect_prompt(current_prompt, evaluation.feedback, generation)

        if best_result:
            self.registry.add_version(
                prompt_text=best_result.prompt_text,
                metadata={
                    "aggregate_score": best_result.metrics.aggregate_score,
                    "citation_accuracy": best_result.metrics.citation_accuracy,
                },
            )
        return best_result

    def _select_minibatch(self, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(test_cases) <= self.config.reflection_minibatch_size:
            return test_cases
        return random.sample(test_cases, self.config.reflection_minibatch_size)

    def _reflect_prompt(self, prompt: str, feedback: str, generation: int) -> str:
        """Produce a naive reflection by appending remediation comments."""
        sanitized_feedback = feedback.strip().replace("\n", " ")
        return f"{prompt}\n\n# Reflection {generation + 1}\n# {sanitized_feedback}"
