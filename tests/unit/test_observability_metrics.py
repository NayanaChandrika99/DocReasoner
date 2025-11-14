# ABOUTME: Tests for Prometheus observability helpers.
# ABOUTME: Verifies tool latency histograms and confidence gauges.
"""Unit tests for Prometheus metrics helpers."""

import types

from reasoning_service.observability import react_metrics
from reasoning_service.services.prompt_evaluator import EvaluationMetrics


def _enable_metrics(monkeypatch):
    monkeypatch.setattr(react_metrics, "_enabled", lambda: True)


def test_record_tool_latency(monkeypatch):
    """react_tool_latency_seconds should observe latency per tool."""
    _enable_metrics(monkeypatch)

    observed = []

    class DummyMetric:
        def labels(self, **labels):
            observed.append({"labels": labels, "value": None})
            return self

        def observe(self, value):
            observed[-1]["value"] = value

    monkeypatch.setattr(react_metrics, "REACT_TOOL_LATENCY_SECONDS", DummyMetric())

    react_metrics.record_tool_latency("pi_search", 0.42)

    assert observed
    assert observed[0]["labels"]["tool_name"] == "pi_search"
    assert observed[0]["value"] == 0.42


def test_record_confidence_score(monkeypatch):
    """Gauge should store latest confidence."""
    _enable_metrics(monkeypatch)

    recorded = {}

    class DummyGauge:
        def set(self, value):
            recorded["value"] = value

    monkeypatch.setattr(react_metrics, "REACT_LAST_CONFIDENCE_SCORE", DummyGauge())

    react_metrics.record_confidence_score(0.77)
    assert recorded["value"] == 0.77


def test_record_gepa_run(monkeypatch):
    """GEPA run metrics should update counters and histograms."""
    _enable_metrics(monkeypatch)

    statuses = []
    durations = []
    evaluations = []

    class DummyCounter:
        def labels(self, **labels):
            statuses.append(labels["status"])
            return self

        def inc(self):
            statuses.append("inc")

    class DummyHistogram:
        def observe(self, value):
            durations.append(value)

    class DummyEvalHistogram:
        def observe(self, value):
            evaluations.append(value)

    monkeypatch.setattr(react_metrics, "GEPA_OPTIMIZATIONS_TOTAL", DummyCounter())
    monkeypatch.setattr(react_metrics, "GEPA_OPTIMIZATION_DURATION_SECONDS", DummyHistogram())
    monkeypatch.setattr(react_metrics, "GEPA_EVALUATIONS_PER_RUN", DummyEvalHistogram())

    react_metrics.record_gepa_run(status="success", duration_seconds=120, evaluation_count=5)

    assert statuses[0] == "success"
    assert durations[0] == 120
    assert evaluations[0] == 5


def test_record_gepa_prompt_metrics(monkeypatch):
    """Prompt metric gauge should set all metric labels."""
    _enable_metrics(monkeypatch)

    recorded = {}

    class DummyGauge:
        def labels(self, **labels):
            key = labels["metric_type"]

            class Setter:
                def set(self, value):
                    recorded[key] = value

            return Setter()

    monkeypatch.setattr(react_metrics, "GEPA_PROMPT_SCORE", DummyGauge())

    metrics = EvaluationMetrics(aggregate_score=0.75, citation_accuracy=0.8, reasoning_coherence=0.7, confidence_calibration=0.65, status_correctness=0.9)
    react_metrics.record_gepa_prompt_metrics(metrics)

    assert recorded["aggregate"] == 0.75
    assert recorded["citation_accuracy"] == 0.8
