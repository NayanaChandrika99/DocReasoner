# ReActController Architecture

This document captures how the reasoning-service implements its ReAct (Reason + Act) controllers across the CLI and FastAPI surfaces.

## Overview

The controller consumes `RetrievalResult` objects from `retrieval.service`, reasons about the applicable policy requirement, links case evidence, and emits structure decisions with:

- Status (`ready/not_ready/uncertain` in CLI, `met/missing/uncertain` in API)
- Citations and evidence metadata
- Multi-factor confidence scores
- ReAct reasoning traces (Think → Retrieve → Read → Link → Decide)

Two implementations exist today:

| Surface | Module | Notes |
| --- | --- | --- |
| CLI (sync) | `src/controller/react_controller.py` | Lightweight heuristic, returns `Decision` dataclass consumed by `src/cli.py` |
| FastAPI (async) | `src/reasoning_service/services/controller.py` | Async orchestration for `/reason/auth-review`, returns `CriterionResult` Pydantic models |

Both controllers now share the same core concepts so QA can diff their outputs directly.

## ReAct Loop

Each criterion evaluation executes five steps:

1. **Think** — Decide what evidence to look for (currently rule-based from criterion metadata)
2. **Retrieve** — Call the retrieval service (PageIndex or offline tree cache)
3. **Read** — Extract requirement-style statements from the returned spans
4. **Link Evidence** — Match VLM-extracted case fields to the requirements
5. **Decide** — Emit a structured status with rationale, citations, and confidence

The async controller stores every step in `CriterionResult.reasoning_trace`, while the sync controller keeps a `ReasoningStep` list in its `Decision` object.

## Confidence Scoring

Confidence is composed of three factors:

| Symbol | Description | Source |
| --- | --- | --- |
| `c_tree` | Retrieval confidence | `RetrievalResult.confidence` |
| `c_span` | Span/evidence alignment | Evidence matcher score |
| `c_final` | Decision-level certainty | Status-specific constant (0.95 for MET, 0.9 for MISSING, 0.6 for UNCERTAIN) |

The joint score is `c_joint = c_tree * c_span * c_final`. CLI responses surface `confidence: {c_tree, c_span, c_final, c_joint}`. API responses include both `confidence` (the joint scalar) and `confidence_breakdown` mirroring the CLI structure.

## Status Mapping

CLI statuses map to API enums via `controller.status_mapping.map_cli_status_to_api`:

| CLI | API |
| --- | --- |
| `ready` | `DecisionStatus.MET` |
| `not_ready` | `DecisionStatus.MISSING` |
| `uncertain` | `DecisionStatus.UNCERTAIN` |

Use the helper whenever CLI decisions must be translated for API contracts.

## Controller Configuration & Rollout

The FastAPI surface now instantiates the delegator defined in `src/reasoning_service/services/controller.py`. It decides whether to run the heuristic controller, the LLM controller, or both (shadow mode) based on environment flags loaded through `settings`:

- `REACT_USE_LLM_CONTROLLER` – when `true`, the LLM controller handles live traffic (unless shadow mode is enabled).
- `REACT_SHADOW_MODE` – when `true`, the service runs both controllers but returns the heuristic result while logging discrepancies and emitting metrics for each controller.
- `REACT_FALLBACK_ENABLED` – when `true`, any LLM failure triggers an automatic fallback to the heuristic output with `reason_code="llm_fallback"`.
- `REACT_AB_TEST_RATIO` – floating-point ratio between `0` and `1`. When set, that percentage of requests is routed to the LLM controller (and the assignment is recorded via Prometheus metrics) so you can roll out gradually.

Shadow mode is the recommended first step: enable it, monitor the logs for `Shadow comparison mismatch` entries, and inspect the Prometheus dashboards described below. Once metrics look good, disable `REACT_SHADOW_MODE` and set `REACT_USE_LLM_CONTROLLER=true` (optionally keeping a small `REACT_AB_TEST_RATIO` while you ramp).

## Observability

`src/reasoning_service/observability/react_metrics.py` defines the Prometheus metrics consumed by both controllers. Key series include:

- `react_evaluations_total{controller,mode,status}` – counts evaluations per controller (heuristic/llm), distinguishing between primary, shadow, and fallback modes.
- `react_latency_seconds{controller,mode}` – measures latency per controller.
- `react_tool_calls_total{tool_name,success}` – emitted by the tool executor for every `pi_search`, `facts_get`, `spans_tighten`, and `finish` call.
- `react_fallback_total{reason}` – increments whenever we return the heuristic result because of an LLM error.
- `react_ab_assignments_total{bucket}` – records A/B routing decisions so you can confirm the rollout ratio.

Enable the existing `/metrics` endpoint via `METRICS_ENABLED=true` (already on in production templates) and scrape these series to monitor rollout health.

## Usage Examples

### CLI

```bash
uv run python -m src.cli run-decision tests/data/cases/case_straightforward.json
uv run python -m src.cli run-decision tests/data/cases/case_straightforward.json --controller llm  # Uses the LLM agent (requires API keys and PageIndex access)
```

Sample output:

```json
{
  "criterion_id": "lumbar-mri-pt",
  "status": "ready",
  "rationale": "Case facts align with policy requirement. Reasoning trace: ...",
  "confidence": {
    "c_tree": 0.9,
    "c_span": 0.85,
    "c_final": 0.9,
    "c_joint": 0.689
  },
  "reasoning_trace": [
    {"step": 1, "action": "search", "observation": "..."},
    {"step": 2, "action": "analyze", "observation": "..."},
    {"step": 3, "action": "decide", "observation": "..."}
  ],
  "retrieval_method": "pageindex-llm"
}
```

### FastAPI

```bash
uv run uvicorn reasoning_service.api.app:create_app --factory --reload
curl -X POST http://localhost:8000/reason/auth-review \
  -H "Content-Type: application/json" \
  -d @tests/data/cases/case_straightforward.json
```

Response excerpt:

```json
{
  "case_id": "case-123",
  "results": [
    {
      "criterion_id": "lumbar-mri-pt",
      "status": "met",
      "confidence": 0.689,
      "confidence_breakdown": {
        "c_tree": 0.9,
        "c_span": 0.85,
        "c_final": 0.9,
        "c_joint": 0.689
      },
      "reasoning_trace": [
        {"step": 1, "action": "think", "observation": "Retrieve sections ..."},
        {"step": 2, "action": "retrieve", "observation": "nodes=2, spans=3"},
        {"step": 3, "action": "read", "observation": "requirements=1"},
        {"step": 4, "action": "link_evidence", "observation": "matched"},
        {"step": 5, "action": "decide", "observation": "Case evidence aligns ..."}
      ]
    }
  ]
}
```

## Troubleshooting

- **Missing retrieval results**: Both controllers return `uncertain` with `reason_code` explaining the failure (e.g., `pageindex_error` or `no_matches_offline`).
- **Low confidence**: If `c_joint < 0.65`, sync controller abstains (`uncertain`). Async controller records `reason_code` with `missing_evidence` or `insufficient_policy_context`.
- **Out-of-sync schemas**: Ensure API clients depend on `CriterionResult` fields rather than hard-coded keys. Confidence breakdown and reasoning trace are now part of the contract.

Refer to `plan/react_controller_implementation_execplan.md` for the full delivery history.
