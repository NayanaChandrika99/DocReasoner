"""Prometheus metrics for ReAct controller execution."""

from __future__ import annotations

from typing import Iterable, Optional

from prometheus_client import Counter, Histogram

from reasoning_service.config import settings


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
