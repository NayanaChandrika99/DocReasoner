"""Prometheus metrics for ReAct controller execution."""

from __future__ import annotations

from typing import Iterable, Optional

from prometheus_client import Counter, Gauge, Histogram

from reasoning_service.config import settings
from reasoning_service.services.prompt_evaluator import EvaluationMetrics


REACT_EVALUATIONS_TOTAL = Counter(
    "react_evaluations_total",
    "Total ReAct evaluations by controller, mode, and status",
    ["controller", "mode", "status"],
)

REACT_LATENCY_SECONDS = Histogram(
    "react_latency_seconds",
    "Latency of ReAct evaluations",
    ["controller", "mode"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

REACT_ITERATIONS = Histogram(
    "react_iterations",
    "Iteration counts for LLM-driven evaluations",
    ["controller"],
    buckets=tuple(range(1, 12)),
)

REACT_TOOL_CALLS_TOTAL = Counter(
    "react_tool_calls_total",
    "Tool calls issued by the LLM controller",
    ["tool_name", "success"],
)

REACT_TOOL_LATENCY_SECONDS = Histogram(
    "react_tool_latency_seconds",
    "Latency per tool invocation issued by the controller",
    ["tool_name"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

REACT_LAST_CONFIDENCE_SCORE = Gauge(
    "react_last_confidence_score",
    "Stores the most recent decision confidence score emitted by the controller",
)

REACT_FALLBACK_TOTAL = Counter(
    "react_fallback_total",
    "Number of times the system returned a fallback decision",
    ["reason"],
)

REACT_AB_ASSIGNMENTS = Counter(
    "react_ab_assignments_total",
    "A/B assignments for controller routing",
    ["bucket"],
)

GEPA_OPTIMIZATIONS_TOTAL = Counter(
    "gepa_optimizations_total",
    "Total number of GEPA optimization runs",
    ["status"],
)

GEPA_OPTIMIZATION_DURATION_SECONDS = Histogram(
    "gepa_optimization_duration_seconds",
    "Duration of GEPA optimization runs",
    buckets=(60, 300, 600, 1800, 3600),
)

GEPA_PROMPT_SCORE = Gauge(
    "gepa_prompt_score",
    "Most recent prompt quality metrics",
    ["metric_type"],
)

GEPA_EVALUATIONS_PER_RUN = Histogram(
    "gepa_evaluations_per_run",
    "Number of candidate evaluations per optimization run",
    buckets=(3, 10, 25, 50, 100, 200),
)


def _enabled() -> bool:
    """Check whether metrics are enabled."""
    return bool(settings.metrics_enabled)


def record_evaluation(
    controller: str,
    mode: str,
    statuses: Iterable[str],
    latency_seconds: Optional[float] = None,
    iterations: Optional[int] = None,
) -> None:
    """Record evaluation level metrics."""
    if not _enabled():
        return

    for status in statuses:
        REACT_EVALUATIONS_TOTAL.labels(
            controller=controller,
            mode=mode,
            status=status.lower(),
        ).inc()

    if latency_seconds is not None:
        REACT_LATENCY_SECONDS.labels(
            controller=controller,
            mode=mode,
        ).observe(max(latency_seconds, 0.0))

    if iterations is not None:
        REACT_ITERATIONS.labels(controller=controller).observe(max(iterations, 0))


def record_tool_call(tool_name: str, success: bool) -> None:
    """Record a tool invocation."""
    if not _enabled():
        return

    REACT_TOOL_CALLS_TOTAL.labels(
        tool_name=tool_name,
        success=str(bool(success)).lower(),
    ).inc()


def record_tool_latency(tool_name: str, latency_seconds: float) -> None:
    """Record tool latency histogram."""
    if not _enabled():
        return

    REACT_TOOL_LATENCY_SECONDS.labels(tool_name=tool_name).observe(
        max(latency_seconds, 0.0)
    )


def record_fallback(reason: str) -> None:
    """Record fallback usage."""
    if not _enabled():
        return

    REACT_FALLBACK_TOTAL.labels(reason=reason).inc()


def record_ab_assignment(bucket: str) -> None:
    """Record an A/B routing assignment."""
    if not _enabled():
        return

    REACT_AB_ASSIGNMENTS.labels(bucket=bucket).inc()


def record_confidence_score(confidence: float) -> None:
    """Record the final confidence gauge."""
    if not _enabled():
        return

    REACT_LAST_CONFIDENCE_SCORE.set(max(0.0, min(1.0, confidence)))


def record_gepa_run(
    status: str,
    duration_seconds: Optional[float] = None,
    evaluation_count: Optional[int] = None,
) -> None:
    """Record GEPA optimization run metadata."""
    if not _enabled():
        return

    GEPA_OPTIMIZATIONS_TOTAL.labels(status=status).inc()
    if duration_seconds is not None:
        GEPA_OPTIMIZATION_DURATION_SECONDS.observe(max(duration_seconds, 0.0))
    if evaluation_count is not None:
        GEPA_EVALUATIONS_PER_RUN.observe(max(evaluation_count, 0))


def record_gepa_prompt_metrics(metrics: EvaluationMetrics) -> None:
    """Record the latest prompt quality metrics."""
    if not _enabled():
        return

    GEPA_PROMPT_SCORE.labels(metric_type="aggregate").set(metrics.aggregate_score)
    GEPA_PROMPT_SCORE.labels(metric_type="citation_accuracy").set(metrics.citation_accuracy)
    GEPA_PROMPT_SCORE.labels(metric_type="reasoning_coherence").set(metrics.reasoning_coherence)
    GEPA_PROMPT_SCORE.labels(metric_type="confidence_calibration").set(metrics.confidence_calibration)
    GEPA_PROMPT_SCORE.labels(metric_type="status_correctness").set(metrics.status_correctness)
