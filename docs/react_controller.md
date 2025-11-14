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
- `PROMPT_AB_TEST_RATIO` – percentage of LLM-routed traffic that should use the latest prompt registry version instead of the baked-in system prompt. Use this to trial an optimized prompt while keeping the previous prompt as the fallback.

Shadow mode is the recommended first step: enable it, monitor the logs for `Shadow comparison mismatch` entries, and inspect the Prometheus dashboards described below. Once metrics look good, disable `REACT_SHADOW_MODE` and set `REACT_USE_LLM_CONTROLLER=true` (optionally keeping a small `REACT_AB_TEST_RATIO` while you ramp).

### Retrieval and Evidence Feature Flags

- `RETRIEVAL_BACKEND` – choose `pageindex` (default) or `treestore`. When set to `treestore`, the async retrieval service uses the gRPC-compatible `TreeStoreClient` for keyword search and span tightening. Cases must supply `case_bundle.metadata.policy_document_id` (typically the policy ID) and optionally `policy_version_id` so the adapter can resolve the correct version.
- `PUBMED_ENABLED` / `PUBMED_MAX_RESULTS` / `PUBMED_CACHE_TTL_SECONDS` – gate the PubMed evidence tool and control caching. When disabled, the `pubmed_search` tool returns a deterministic “disabled” summary.
- `GEPA_ENABLED`, `GEPA_AUTO_MODE`, `GEPA_MAX_ITERATIONS`, `GEPA_TARGET_SCORE` – control whether the optimizer service is allowed to launch prompt experiments automatically.

## Rollout Playbook

1. **Shadow comparisons**
   - Set `REACT_SHADOW_MODE=true`, leave `REACT_USE_LLM_CONTROLLER=false`.
   - Send representative traffic (e.g., `curl` requests or `pytest -k auth_review`).
   - Inspect logs for `Shadow comparison mismatch` and check the metrics described below to ensure both controllers are producing results.

2. **Gradual ramp**
   - Disable shadow mode, set `REACT_USE_LLM_CONTROLLER=true`.
   - Choose an initial `REACT_AB_TEST_RATIO` (e.g., 0.1) and validate Prometheus shows matching assignment counts.
   - Increase the ratio in stages until 1.0. If an issue surfaces, set `REACT_USE_LLM_CONTROLLER=false` to fall back.

3. **Prompt experiments / A/B**
   - Run `uv run python scripts/optimize_react_prompt.py --cases-path tests/data/cases --dry-run` to validate the pipeline.
   - When ready, run without `--dry-run`. The script loads cases via the new dataset loader, uses the `GEPAEvaluationRunner` to call the live controller (with caching), and writes the result under `optimization_results/`.
   - Approved prompts are committed to the registry automatically. Set `PROMPT_AB_TEST_RATIO` (e.g., 0.25) to send a slice of traffic to the new prompt while observing `gepa_prompt_score` and `react_evaluations_total`.

4. **Rollback**
   - Set `REACT_USE_LLM_CONTROLLER=false` to revert to the heuristic controller for all traffic.
   - To revert a prompt, remove or edit the latest entry in `data/prompt_registry.json` (or use your preferred change-management process) and restart.

CLI aids:

```bash
# Shadow run a single case and print both controllers in the logs
REACT_SHADOW_MODE=true uv run python -m src.cli run-decision tests/data/cases/case_conservative_4weeks.json

# Force the LLM controller for diagnostics
REACT_USE_LLM_CONTROLLER=true uv run curl -X POST http://localhost:8000/reason/auth-review -d @tests/data/cases/case_demo.json -H 'Content-Type: application/json'
```

## Observability

`src/reasoning_service/observability/react_metrics.py` defines the Prometheus metrics consumed by both controllers. Key series include:

- `react_evaluations_total{controller,mode,status}` – counts evaluations per controller (heuristic/llm), distinguishing between primary, shadow, and fallback modes.
- `react_latency_seconds{controller,mode}` – measures latency per controller.
- `react_tool_calls_total{tool_name,success}` – emitted by the tool executor for every `pi_search`, `facts_get`, `spans_tighten`, and `finish` call.
- `react_fallback_total{reason}` – increments whenever we return the heuristic result because of an LLM error.
- `react_ab_assignments_total{bucket}` – records A/B routing decisions so you can confirm the rollout ratio.
- `gepa_optimizations_total{status}` / `gepa_optimization_duration_seconds` / `gepa_evaluations_per_run` – describe each GEPA run.
- `gepa_prompt_score{metric_type}` – records the latest aggregate, citation accuracy, reasoning coherence, confidence calibration, and status correctness metrics for the active prompt.

Enable the existing `/metrics` endpoint via `METRICS_ENABLED=true` (already on in production templates) and scrape these series to monitor rollout health.

## Error Taxonomy & Rate Limits

- `rate_limited` – tool invocation denied because it exceeded `TOOL_RATE_LIMIT_PER_MINUTE`. Tune limits in settings (defaults: `pi_search=120`, `pubmed_search=30`). Operators should watch for repeated rate-limit responses and adjust quotas or query batching.
- `missing_policy_document_id` – case bundles must supply `metadata.policy_document_id` (or a resolvable policy ID) before calling `pi_search`. The tool executor enforces this so misconfigured cases degrade gracefully.
- `treestore_no_nodes` / `treestore_missing_text` – emitted when the TreeStore backend lacks search nodes or span text. Indicates ingestion gaps rather than controller bugs.
- `pubmed_disabled`, `pubmed_client_missing`, `pubmed_error` – help distinguish config gating from upstream failures.
- `tool_timeout` – standardized reason code when per-tool timeouts trigger. The controller retries once (configurable) before returning UNCERTAIN with this code.

All codes live in `reasoning_service/utils/error_codes.py` to keep logs, metrics, and responses consistent.

## TreeStore Retrieval Backend

When `RETRIEVAL_BACKEND=treestore`, the controller uses `TreeStoreClient` for keyword search and span tightening:

1. Populate TreeStore with nodes and version metadata (see `tree_db/README.md`).
2. Ensure each case sets `case_bundle.metadata.policy_document_id` to the policy ID and, if available, `policy_version_id`.
3. Start the API with `RETRIEVAL_BACKEND=treestore` (and optional `POLICY_VERSION_ID` env if you want to default to a specific version).
4. Use `pi_search` as usual; the response now includes TreeStore trajectories and short previews, and `spans_tighten` ranks node paragraphs locally without FTS.

If TreeStore is unavailable, leave the backend at `pageindex` and existing behavior remains unchanged.

## PubMed Evidence Tool

Set `PUBMED_ENABLED=true` (and `PUBMED_API_KEY` if rate limits require) to allow the `pubmed_search` tool. The handler caches `(condition, treatment)` lookups via `PUBMED_CACHE_TTL_SECONDS`, records summaries with quality tags, and degrades gracefully when disabled or offline. Operators should monitor `react_tool_calls_total{tool_name="pubmed_search"}` to ensure usage stays within expected budgets.

## GEPA Workflow

1. Assemble a dataset (folder or JSON file) of evaluation cases. The new filesystem loader understands both `cases: [...]` envelopes and single-case files.
2. Run `uv run python scripts/optimize_react_prompt.py --cases-path <path>` (add `--dry-run` for a fast smoke test).
3. The script orchestrates evaluations via `GEPAEvaluationRunner`, which caches `(prompt, case)` results so repeated candidates do not hammer the controller.
4. Prometheus tracks each run via `gepa_optimizations_total`, run duration histograms, and `gepa_prompt_score`.
5. Approved prompts are appended to the registry (`data/prompt_registry.json`). Use `PROMPT_AB_TEST_RATIO` to canary the new prompt.

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
