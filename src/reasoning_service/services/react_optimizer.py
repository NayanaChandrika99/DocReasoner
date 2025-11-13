"""Service for triggering GEPA prompt optimization runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from reasoning_service.config import settings
from reasoning_service.prompts.react_system_prompt import REACT_SYSTEM_PROMPT
from reasoning_service.services.prompt_evaluator import MetricWeights, PolicyEvaluator
from reasoning_service.services.prompt_optimizer import (
    OptimizationConfig,
    PromptOptimizer,
    ReActControllerAdapter,
)
from reasoning_service.services.prompt_registry import PromptRegistry


@dataclass
class QualitySnapshot:
    """Represents rolling quality metrics from production."""

    citation_accuracy: float
    reasoning_coherence: float
    confidence_calibration: float
    status_correctness: float


class ReActOptimizerService:
    """High level interface used by operators or scheduled jobs."""

    def __init__(
        self,
        registry: Optional[PromptRegistry] = None,
    ) -> None:
        self.registry = registry or PromptRegistry()
        self.registry.load()

    async def maybe_optimize(
        self,
        quality_snapshot: QualitySnapshot,
        test_cases: List[Dict[str, Any]],
        evaluate_fn,
    ):
        """Kick off optimization if quality drops below thresholds."""
        if not settings.gepa_enabled:
            return None
        if quality_snapshot.citation_accuracy >= settings.gepa_target_score:
            return None

        config = OptimizationConfig(
            auto_mode=settings.gepa_auto_mode,
            max_metric_calls=settings.gepa_max_iterations,
            target_aggregate_score=settings.gepa_target_score,
            citation_accuracy_weight=0.4,
            reasoning_coherence_weight=0.3,
            confidence_calibration_weight=0.2,
            status_correctness_weight=0.1,
        )

        evaluator = PolicyEvaluator(
            weights=MetricWeights(
                citation_accuracy=config.citation_accuracy_weight,
                reasoning_coherence=config.reasoning_coherence_weight,
                confidence_calibration=config.confidence_calibration_weight,
                status_correctness=config.status_correctness_weight,
            )
        )

        adapter = ReActControllerAdapter(
            evaluate_fn=evaluate_fn,
            evaluator=evaluator,
        )
        optimizer = PromptOptimizer(adapter=adapter, registry=self.registry, config=config)
        return await optimizer.optimize(REACT_SYSTEM_PROMPT, test_cases)
