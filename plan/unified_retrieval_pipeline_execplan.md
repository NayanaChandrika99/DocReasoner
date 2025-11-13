# Unified Retrieval Pipeline ExecPlan


## Purpose

The controller and CLI currently call two different retrieval stacks: `src/retrieval/tree_search.py` (used by the CLI) and `src/reasoning_service/services/retrieval.py` (referenced by the FastAPI service). Neither implements the hybrid PageIndex flow or the FTS5 fallback from the docs, which means we cannot measure `retrieval_method`, trigger bm25 tightening, or reuse code between the CLI and API. This plan delivers a single retrieval service that:

1. Calls PageIndex LLM Tree Search by default, with a switch to Hybrid Tree Search when ambiguity exceeds the configured threshold.
2. Falls back to a local bm25 + optional reranker when PageIndex provides spans longer than the 800-token threshold.
3. Exposes a consistent `RetrievalResult` object (nodes, spans, trajectory, `retrieval_method`, `reason_code`) for both CLI and FastAPI callers.

When finished, anyone can run `uv run python -m tests.unit.test_retrieval` (new tests) to see the fallback logic in action, and the CLI will report which method (pageindex-llm, pageindex-hybrid, bm25-fallback) answered each query.


## Starting Point

- `src/retrieval/tree_search.py` performs either PageIndex API calls or an offline JSON scan, but never invokes FTS5.
- `src/retrieval/fts5_fallback.py` offers an in-memory bm25 helper, yet no caller wires it to the token threshold or exposes its results.
- `src/reasoning_service/services/retrieval.py` sketches a richer pipeline (hybrid search, bm25 + reranker) but leaves `hybrid_tree_search` and `get_node_content` unimplemented and is not used by the CLI.
- Configuration defaults live in `src/reasoning_service/config.py` (e.g., `hybrid_tree_search_threshold = 0.15`, `node_span_token_threshold = 2000`), so we have a single source for thresholds.

We will consolidate everything under a new module (`src/retrieval/service.py`) and then update both the CLI (`src/cli.py`) and FastAPI service (`src/reasoning_service/services/retrieval.py` or its replacement) to use it.


## Milestone 1 — Consolidate retrieval service

1. Create `src/retrieval/service.py`. Define:
   - `RetrievalConfig` dataclass pulling thresholds from `settings`.
   - `RetrievalResult` dataclass with `node_refs`, `relevant_contents`, `search_trajectory`, `spans`, `retrieval_method`, `reason_code`, `confidence`.
   - `RetrievalService` class that accepts a `PageIndexClient`, optional `FTS5Fallback`, and config.
2. Move shared parsing helpers from `tree_search.py` into the new service (e.g., `_parse_remote_payload`), ensuring node references carry `node_id`, `title`, `page_index/start/end`, and `prefix_summary`.
3. Update the CLI to import `RetrievalService` from the new module. Keep the offline JSON scan in `tree_search.py` for “no API” mode, but wrap it so both online and offline paths return `RetrievalResult`.

Acceptance: `uv run python -m src.cli run_decision tests/data/cases/case_straightforward.json` still works, and the logs include `retrieval_method` (at this point always `pageindex-llm` or `pageindex-offline`).


## Milestone 2 — Implement hybrid + bm25 fallbacks

1. Implement `PageIndexClient.hybrid_tree_search` and `get_node_content` in `src/reasoning_service/services/pageindex.py` (or a new `policy_ingest/pageindex_client.py` async variant) using the documented REST endpoints. Both methods should accept `doc_id`/`node_id` and honor the same headers/timeouts as `upload_pdf`.
2. In `RetrievalService.retrieve(query, doc_id)`:
   - Call `llm_tree_search` first. Compute ambiguity (use the existing heuristic: score variance or normalized gaps). If it exceeds `settings.hybrid_tree_search_threshold`, call `hybrid_tree_search` and set `retrieval_method="pageindex-hybrid"`.
   - Collect the spans (`relevant_contents`). If their combined token length (approximate via word count) exceeds `settings.node_span_token_threshold` (default 800 per docs), fetch the full node text via `get_node_content`, load it into `FTS5Fallback`, run bm25 top-k (and reranker if configured), and set `retrieval_method="bm25-fallback"`.
   - Record which fallback triggered via a boolean (for logging) and include the final spans in `RetrievalResult`.
3. Ensure the `FTS5Fallback` helper gracefully handles empty texts and is reused per service (do not recreate sqlite for every call; reset the table via `load_paragraphs`).
4. Update logging: whenever `retrieve` returns, emit a telemetry entry with `retrieval_method`, `node_count`, and `fallback_used`.

Acceptance: add a unit test suite (`tests/unit/test_retrieval_service.py`) that mocks the PageIndex client to produce (a) low ambiguity (stays in LLM mode), (b) high ambiguity (triggers hybrid), and (c) long spans (triggers bm25). Each test asserts `RetrievalResult.retrieval_method` matches expectations and the fallback was invoked.


## Milestone 3 — Integrate everywhere & document

1. CLI: switch `_build_services` to instantiate the new `RetrievalService` (with real PageIndex client or offline fallback). Update `_run_case` to use the `spans` from `RetrievalResult` (rather than the old `relevant_contents` list) and log the method.
2. FastAPI: replace `src/reasoning_service/services/retrieval.py` with a thin wrapper around the shared service (or delete it if redundant). Update `reason.py` to inject the unified retrieval service so both CLI and API rely on the same codepath.
3. Docs: in `README.md` and `docs/plan.md`, mention that retrieval now supports hybrid + bm25 fallback automatically. Document the new config knobs (thresholds, reranker model). Add a short “Verification” note referencing `uv run pytest tests/unit/test_retrieval_service.py`.
4. Telemetry: ensure both CLI and API log `retrieval_method` and `reason_code` for every decision for later analytics.

Acceptance:
   - `uv run pytest tests/unit/test_retrieval_service.py` passes.
   - `uv run python -m src.cli run_decision tests/data/cases/case_straightforward.json` prints a decision with the `retrieval_method` field reflecting the mode used.
   - FastAPI’s `/reason/auth-review` endpoint (with mock dependencies) can be called locally (e.g., via `uv run uvicorn reasoning_service.api.app:create_app --factory`) and returns a response containing the `retrieval_method`.


## Progress

- [x] Milestone 1 — Consolidate retrieval service
- [x] Milestone 2 — Implement hybrid + bm25 fallbacks
- [x] Milestone 3 — Integrate everywhere & document


## Change Log

2025-11-08 — Initial ExecPlan created to unify PageIndex/Hybrid/FTS5 retrieval pipeline per `.agent/PLANS.md`.  
2025-11-08 — Milestone 1 completed: added shared `RetrievalService`, dataclasses, and wired the CLI to use it while preserving offline fallback.  
2025-11-08 — Milestone 2 completed: implemented `PageIndexClient` hybrid/node-content helpers, wired ambiguity-based hybrid switch + bm25 fallback in `RetrievalService`, and added unit tests (`tests/unit/test_retrieval_service.py`) covering LLM, hybrid, and bm25 paths.  
2025-11-08 — Milestone 3 completed: FastAPI now uses the shared retrieval wrapper, ReAct controller consumes the new `RetrievalResult` shape, CLI/API log retrieval methods, and README/docs/plan document the hybrid + bm25 behavior.
