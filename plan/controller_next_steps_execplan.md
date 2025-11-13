# Controller Next Steps — ExecPlan

## Why
Strengthen the LLM-driven ReAct controller with production-grade tools orchestration, observability, version-aware policy reasoning, and a repeatable optimization loop (GEPA). This plan focuses on pragmatic, incremental steps that improve correctness, auditability, and reliability without over-engineering.

## Scope
- In-scope: DB-backed `temporal_lookup` and `policy_xref`, minimal PubMed integration (gated), Prometheus observability, GEPA production harness, rollout runbook, tree_db retrieval integration, tests.
- Out-of-scope: Full UI, EHR integrations, external data pipelines beyond minimal stubs.

## Guiding Principles
- Keep changes small and testable (TDD). 
- Favor simple designs and clear contracts. 
- Always emit auditable citations and version info.

---

## Milestone A — TreeStore-Backed Tools (policy awareness)

### A1) `temporal_lookup` via TreeStore gRPC
- Goal: Resolve policy version as of `as_of_date` using TreeStore as the source of truth and surface `{version_id, effective_start, effective_end, diffs[]}`.
- Tasks:
  - Define a lightweight VersionCatalog in TreeStore (or a small KV in TreeStore) to map `policy_id -> [{version_id, effective_start, effective_end, pageindex_doc_id}]`.
  - Implement a Python `TreeStoreClient` (gRPC) in `src/reasoning_service/services/treestore_client.py` with methods:
    - `get_version_as_of(policy_id, as_of_date)`
    - `get_nodes(policy_id, version_id, node_ids)`
  - For diffs: when adjacent versions exist, fetch nodes for both and compute content hash diffs at the controller layer (titles, page ranges, text summaries). Return changed `node_id`s.
  - Update `temporal_lookup` handler to call `TreeStoreClient` and return version metadata and diffs.
- TDD:
  - Stub the client with fixtures: two versions and three nodes; assert correct version selection and non-empty diffs when content changes.
- Acceptance:
  - Given a service date, controller re-runs retrieval under resolved `version_id` and cites it in results.

### A2) `policy_xref` via TreeStore document APIs
- Goal: Cross-reference related sections for a criterion using TreeStore hierarchy and search.
- Tasks:
  - Strategy (ordered attempts):
    1) Use `GetAncestorPath` + siblings (shared parent) for topical proximity.
    2) Use `SearchByKeyword` with “see also”, “exceptions”, and key tokens from `criterion_id` to pull candidate nodes.
    3) Optionally maintain a curated XRef KV in TreeStore for manual links.
  - Handler returns `{related_nodes[], citations[]}` with `section_path` and page refs (via `GetNode/GetSubtree`).
- TDD:
  - Fixtures with “Conservative Care (see also Physical Therapy)”; assert xref pulls the PT section and cites pages.
- Acceptance:
  - Ambiguous criteria trigger xref; controller cites related nodes in the reasoning trace.

---

## Milestone B — Observability & Safety

### B1) Prometheus per-tool metrics
- Tasks:
  - Counters: `react_tool_calls_total{tool,success}`
  - Histograms: `react_tool_latency_seconds{tool}`
  - Gauge: `react_last_confidence_score`
  - Emit tool usage sequence on decision (structured log).
- TDD:
  - Unit test metric increments; integration test asserts counters after a run.
- Acceptance:
  - Dashboards show tool mix, latencies, and confidence trends.

### B2) Timeouts and fallback
- Tasks:
  - Per-tool timeouts with graceful errors; controller recovery policy (one retry or abstain).
- TDD:
  - Simulate timeouts; assert controller returns “uncertain” with clear reason_code.
- Acceptance:
  - No unbounded tool hang; decisions degrade gracefully.

---

## Milestone C — Evidence Tool (gated)

### C1) `pubmed_search` integration (minimal)
- Tasks:
  - Gate by config; inject API client; add simple caching layer by `(condition,treatment)`.
  - Summarize N best studies with basic quality tags.
- TDD:
  - Mock client returning 2 studies; assert summary present and tool usage recorded.
- Acceptance:
  - Only called on borderline cases or policy instruction; costs remain controlled.

---

## Milestone D — GEPA Production Harness

### D1) Real evaluation runner
- Tasks:
  - Dataset loader abstraction (fixtures today; DB/S3 later).
  - Wire `_evaluate_with_controller` to call real controller with configurable providers.
  - Cache evaluations to avoid redundant calls (hash by case+prompt).
- TDD:
  - Dry-run uses synthetic CriterionResults; “real-run” calls controller mock.
- Acceptance:
  - GEPA loop can run with budgets, produce best prompt, and register a new version.

### D2) Prompt Registry + A/B
- Tasks:
  - Register optimized prompt with version/metadata; enable A/B via delegator weights.
  - Emit `gepa_prompt_score` gauge and per-run counters.
- TDD:
  - Assert registry writes and delegator selects per configured weights.
- Acceptance:
  - Operators can safely trial optimized prompts with rollback.

---

## Milestone E — Rollout Runbook (Shadow/A‑B)

### E1) Operator guide
- Tasks:
  - Expand `docs/react_controller.md`: 
    - Config flags (shadow, A/B, fallback).
    - How to interpret metrics.
    - Rollback procedure.
  - CLI examples: shadow compare, A/B ratios, capture diffs.
- Acceptance:
  - Runbook enables staged rollout with clear success criteria and safe rollback.

---

## Milestone F — TreeStore Integration (primary retrieval backend)

### F1) Retrieval adapter (TreeStoreClient)
- Tasks:
  - Implement `retrieve(policy_id, version_id, query, top_k)` using TreeStore:
    - `SearchByKeyword(policy_id, query)` → BM25-ranked node_ids
    - For each node_id, fetch node metadata (title, page ranges, section path) and a short text preview.
    - Provide a simple “trajectory” based on ancestor path for auditability.
  - Implement `spans_tighten` by scoring paragraphs in `Node.Text` locally (BM25) until TreeStore FTS paragraph-level support lands.
  - Config flag to switch retrieval backend TreeStore|PageIndex (TreeStore default).
- TDD:
  - Integration test hitting adapter with a sample tree; assert ranked nodes and ancestor-based trajectory returned.
- Acceptance:
  - Controller uses TreeStore as default backend with no change to call sites.

---

## Milestone G — Testing Matrix

### G1) Unit coverage (new tools)
- `policy_xref`, `temporal_lookup`, `confidence_score`, `contradiction_detector`, `code_validator`, `pubmed_search`.

### G2) Integration
- `/reason/auth-review` route override tests with delegator + tool call assertions.
- A/B mode test ensuring both prompts/controller paths function.

### G3) Datasets
- Expand fixture set for boundary cases: ambiguous policy, code normalization edge cases, version changes.

Acceptance:
- CI runs green with coverage targets; flaky tests eliminated.

---

## Milestone H — Security, Limits, Operations

### H1) Secrets & rate limits
- Tasks:
  - Store provider keys via env/secret manager.
  - Per-provider rate limiter and budget guardrails.
- Acceptance:
  - Exceeding budgets degrades to “uncertain” with explicit reason_code.

### H2) Error taxonomy
- Tasks:
  - Standardize `reason_code` for tool failures, timeouts, version mismatch, evidence conflict.
- Acceptance:
  - Logs and responses show actionable, consistent codes.

---

## Configuration Changes
- `RETRIEVAL_BACKEND`: treestore | pageindex
- `PUBMED_ENABLED`: bool
- `GEPA_ENABLED`: bool, `GEPA_TARGET_SCORE`, `GEPA_MAX_ITERATIONS`, `GEPA_AUTO_MODE`
- `AB_SPLIT`: e.g., 0.2 for optimized prompt trial
- Timeouts per tool and controller

---

## Deliverables & Acceptance Summary
- DB-backed `temporal_lookup` and `policy_xref` with tests.
- Prometheus metrics for tools + confidence; timeouts and safe fallback.
- Gated `pubmed_search` with cache and tests.
- GEPA runner wired to controller and registry; A/B rollout control.
- Operator runbook for shadow/A‑B with rollback.
- `tree_db` retrieval adapter; backend-switch config.
- CI passing with expanded unit/integration test suite.

---

## TDD & Execution Notes
- For each item, write the failing test first, then implement minimal code to pass, and refactor while keeping tests green.
- Keep PRs small and focused; feature flags for anything risky.

---

## Timeline & Dependencies (suggested)
- Week 1: Milestone A (TreeStore-backed tools) + B (observability/safety)
- Week 2: Milestone F (TreeStore retrieval adapter) + E (runbook)
- Week 3: Milestone D (GEPA runner + A/B) + C (gated PubMed)
- Ongoing: Milestone G/H hardening based on test and metrics feedback


