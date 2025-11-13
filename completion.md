# Completion Assessment

This document summarizes how far the current repository implementation has progressed toward the single-policy demo described in `docs/project.md`, `docs/plan.md`, and `docs/MVP.md`. The documentation is treated as the authoritative specification.

## What’s Complete
- **Documentation + specs.** The `docs/` folder fully describes the architecture, data contracts, runbook, and 10 curated test scenarios, serving as a reliable ground-truth reference for expected behavior.
- **Policy ingestion CLI.** `src/cli.py` wires `ingest_policy`, `validate_tree`, `run_decision`, and `run_test_suite` around the PageIndex ingest workflow, using `policy_ingest/pageindex_client.py` for uploads and caching the tree to `data/pageindex_tree.json`.
- **Minimal retrieval fallback.** `retrieval/tree_search.py` can call live PageIndex (when creds exist) or scan the cached tree; `retrieval/fts5_fallback.py` implements an in-memory bm25 helper ready to tighten spans once plugged in.
- **Demo controller & fixtures.** `controller/react_controller.py` produces Ready/Not Ready/Uncertain JSON with citations/confidence, and the CLI consumes the sample case in `tests/data/cases`. The repo-standard policy (`data/Dockerfile.pdf`, doc_id `pi-cmhppdets02r308pjqnaukvnt`) is referenced across README/docs/tests.
- **API skeleton & safety utilities.** `src/reasoning_service/api`, `models`, and `services/safety.py` define FastAPI routes, Pydantic contracts, and stubs for calibration/self-consistency/conformal logic, giving a clear blueprint for the hosted service.
- **Basic automated tests.** Health-check endpoints and the safety service have coverage (`tests/integration/test_api.py`, `tests/unit/test_safety.py`); the suite currently reports 6 passes / 1 skip / ~51 % coverage.

## Major Gaps vs. Spec
- **Policy persistence & metadata.** `docs/structure.md` mandates `policy_versions`, `policy_nodes`, markdown pointers, PDF hashes, and version tracking. None of those are wired up—`ingest_policy` only emits `data/pageindex_tree.json`, and there are no Alembic migrations for the SQLAlchemy models.
- **Incomplete tree cache.** The cached JSON currently contains only high-level headings from `Dockerfile.pdf`; there is no validation that all sections/summaries from the 19-page LCD are represented, so ingestion cannot yet prove the policy snapshot is complete.
- **Retrieval depth + duplication.** `retrieval/tree_search.py` (CLI) never calls the FTS5 fallback, while `reasoning_service/services/retrieval.py` defines a second, partially implemented pipeline (hybrid search, reranker, node-content fetch) with unimplemented methods (`hybrid_tree_search`, `get_node_content`) and placeholder ambiguity math. The “inside-node bm25 fallback when >800 tokens” called out in docs never activates in practice.
- **Controller realism.** The CLI controller reduces “meets criteria” to a substring check (`_compare_facts`), and the FastAPI controller (`reasoning_service/services/controller.py`) is entirely TODO-scaffolded. No ReAct planning, tool calls (`pi.search`, `facts.get`, `spans.tighten`), or LLM reasoning traces exist despite the doc requirements.
- **Safety enforcement.** Temperature scaling, self-consistency, and conformal routing are defined but unused. AC‑4 (“confidence <0.65 ⇒ Uncertain”) only works for the heuristic controller; the API path never invokes the safety layer.
- **Hosted API execution.** `/reason/auth-review` hardcodes `policy-doc-123`, relies on the unfinished controller, and performs no dependency readiness checks; `/reason/qa` returns a static “clean” response. There is still no persistence of `policy_version_used`, `search_trajectory`, or telemetry.
- **Environment + ops gaps.** There is no `.env.example` enumerating the required `PAGEINDEX_*` keys, and Docker/deployment artifacts called for by the doc runbook are absent.
- **Testing & fixtures.** Only 1 of the 10–20 handcrafted cases described in `docs/test_cases.md`/`docs/plan.md` exists (`tests/data/cases/case_straightforward.json`). The CLI `run_test_suite` therefore cannot exercise red-flag, boundary, or contradictory scenarios, and there are no automated tests covering ingestion, retrieval, controller decisions, or the FastAPI endpoints.

## Suggested Next Steps
1. Implement the policy metadata stores (`policy_versions`, `policy_nodes`), persist the full PageIndex response (tree + markdown pointers + SHA256) during ingestion, and add an Alembic migration so the FastAPI path can read/write audited policy versions.
2. Finish the retrieval pipeline: consolidate on one service, wire the FTS5 fallback to trigger when node spans exceed the configured 800-token threshold, implement `hybrid_tree_search`/`get_node_content`, and make the bm25+rerranker branch observable via `retrieval_method`.
3. Replace the heuristic controller with the documented ReAct loop (plan → pi.search → spans.tighten → decide) shared between CLI and API, and integrate the safety service so conformal/self-consistency/temperature scaling govern Ready vs. Uncertain decisions.
4. Flesh out `/reason/auth-review` and `/reason/qa`: resolve real doc_ids from stored policies, ensure dependency readiness checks, persist every decision with `{policy_version_used, search_trajectory, retrieval_method, timings}`, and log telemetry.
5. Expand fixtures/tests: implement the remaining 9 documented case bundles (plus extras), add CLI + FastAPI end-to-end tests, and track coverage for ingestion, retrieval, controller, and safety behaviors before declaring the single-policy demo complete.
6. Provide operational polish—`.env.example`, environment docs, and (optionally) Docker/run scripts—so others can replicate the workflow without reverse-engineering required secrets or commands.
