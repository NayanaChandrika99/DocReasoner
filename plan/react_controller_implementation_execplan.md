# Add Real ReAct Controller ExecPlan

This ExecPlan supersedes prior controller work. Treat this document as the only source of truth for delivering the LLM-driven ReAct controller described in docs/react_controller.md and openspec/changes/add-real-react-controller/.

---

## Purpose / Big Picture

Medical reviewers need consistent, auditable determinations across both the CLI and FastAPI surfaces. The repository already contains an LLM-driven controller that can interleave reasoning with tool calls, but the FastAPI route still instantiates the older heuristic controller, so customers never see the improved behavior. We must finish the integration, add the rollout and observability tooling promised in the spec, and ensure the GEPA optimizer can keep the prompt tuned. Success means an operator can run `uv run python -m src.cli run-decision ...` or hit `/reason/auth-review` and observe genuine Thought → Action → Observation traces produced by the new controller, while operators have metrics, toggles, and prompt-optimization workflows to manage the rollout safely.

---

## Current State Snapshot

Two controller implementations ship today:

* `src/reasoning_service/services/react_controller.py` is the LLM-driven agent. It already wires in `LLMClient`, tool schemas, tool executors, message history, and finish detection, and it passes mocked-unit tests.
* `src/reasoning_service/services/controller.py` is the legacy heuristic controller. The FastAPI dependency injection in `reasoning_service/api/routes/reason.py` still imports this class, so API callers continue to receive heuristic outputs rather than the LLM-based reasoning promised in docs.

The CLI path (`src/controller/react_controller.py`) also uses heuristic logic, which is acceptable for now but must remain functional when the API switches. Observability, GEPA prompt optimization, migration toggles (shadow mode, A/B testing), and integration tests referenced in openspec/changes/add-real-react-controller/tasks.md have not been implemented. Metrics and rollout levers therefore do not exist, and there is no production-ready way to compare the two controllers during migration.

---

## Desired End State

At completion, a novice can follow this plan to:

1. Enable the LLM controller for FastAPI (and optionally CLI) via configuration flags, safe fallbacks, and documented rollout steps.
2. Run the API and see the LLM controller iterate through tool calls until it issues `finish()` with validated status, rationale, confidence, and citation arguments, matching the schema already defined in `reasoning_service.models.schema`.
3. Observe Prometheus metrics and logs that expose evaluation counts, tool usage, latency, confidence calibration, and GEPA optimization activity.
4. Execute CLI and API regression tests, mocked unit tests, and (optionally) real LLM integration tests to verify the controller and shadow/fallback modes.
5. Launch the GEPA optimizer script to retrain prompts, push the result into a prompt registry, and tie the optimized prompt to controller deployments.
6. Toggle shadow mode or A/B routing from configuration, compare heuristic vs LLM outputs, and roll forward with confidence that fallback paths work.

Behaviorally, the system must return UNCERTAIN when `c_joint < 0.65`, include the reasoning trace in every response, and fall back to the heuristic controller automatically when permanent LLM/tool failures occur or when rollout flags demand it.

---

## Architecture & Interfaces

The building blocks already exist:

1. `src/reasoning_service/services/llm_client.py` implements provider adapters (OpenAI, Anthropic, vLLM) with structured tool calling responses.
2. `src/reasoning_service/prompts/react_system_prompt.py` defines the ReAct instructions and confidence guidelines.
3. `src/reasoning_service/services/tools.py` and `tool_handlers.py` define the tool schemas and executor with caching.
4. `src/reasoning_service/services/react_controller.py` orchestrates message history, tool execution, finish detection, and result construction.

The remaining architectural work focuses on wiring the new controller into FastAPI with rollout toggles and extending the ecosystem:

5. `src/reasoning_service/services/controller.py` should become a delegator or compatibility shim that chooses between the LLM controller and the heuristic fallback based on configuration.
6. `src/reasoning_service/observability/react_metrics.py` must emit Prometheus counters/histograms for evaluations, tool calls, iterations, latency, and LLM cost, and should be imported by the FastAPI app and the CLI when possible.
7. `src/reasoning_service/services/prompt_optimizer.py`, `prompt_evaluator.py`, `prompt_registry.py`, and `services/react_optimizer.py` must be added per the GEPA specification. They integrate with DSPy to evolve prompts and store versions.
8. `scripts/optimize_react_prompt.py` provides the operational entry point for GEPA runs, including dry-run and approval flows.

All modules must remain ASCII-only unless policy content dictates otherwise. Comments are limited to non-obvious logic such as retry heuristics or cache invalidation.

---

## Milestones & Execution Details

### Milestone 1 — Integrate the LLM Controller with FastAPI (and document fallbacks)

1. Update `reasoning_service/services/__init__.py` and `reasoning_service/api/routes/reason.py` so dependency injection returns the LLM controller from `services/react_controller.py`, not the heuristic implementation. Instantiate it with the existing `LLMClient`, `RetrievalService`, and `ToolExecutor`.
2. Add configuration flags in `reasoning_service/config.py` (if missing) such as `react_use_llm_controller`, `react_shadow_mode`, and `react_fallback_enabled`. Defaults: LLM controller enabled in shadow mode so the heuristic remains the source of truth until rollout finishes.
3. Teach `services/controller.py` to act as a wrapper that can run the heuristic controller, the LLM controller, or both (shadow mode). When shadow mode is on, run both controllers, log differences (status, citations, confidence), and return the heuristic decision while storing the LLM output for comparison. When `react_use_llm_controller` is true and shadow mode is off, return the LLM decision; if an LLM error occurs and fallback is enabled, return the heuristic result with reason_code `llm_fallback`.
4. Update CLI documentation and `docs/react_controller.md` to describe the new configuration flags and clarify which controller each surface uses during rollout.
5. Verification: start FastAPI with `react_shadow_mode=true`, post a case, and confirm logs show both controller outputs; flip `react_use_llm_controller=true` and ensure the response payload now includes the LLM reasoning trace and tool-driven data.

### Milestone 2 — Observability, Metrics, and Shadow/A/B Infrastructure

1. Implement `react_metrics.py` with Prometheus metrics: counters for evaluations and tool calls, histograms for latency and iteration counts, gauges for joint confidence and GEPA scores, and counters for fallback events. Plug the metric collector into the FastAPI app (router dependencies) and into the CLI path via lightweight logging (if Prometheus is unavailable there).
2. Extend the controller wrapper to emit metrics for every evaluation, including whether it ran in shadow mode, which controller produced the final answer, and whether fallback triggered.
3. Introduce an A/B routing mechanism if required by the spec (e.g., `react_ab_test_ratio` environment variable). The delegator should randomly route a percentage of requests to the LLM controller, record the assignment, and expose metrics so operators can compare results.
4. Add a structured audit log format (JSON lines written via `structlog` or existing logging helpers) that captures request IDs, controller used, status, joint confidence, tool sequence, and citations. Operators will use this log during rollout to investigate discrepancies.
5. Verification: run `uv run pytest tests/unit/test_react_controller_wrapper.py` (new test) to confirm metric increments and fallback behavior; manually hit the API and observe Prometheus metrics via `/metrics` or logging.

### Milestone 3 — GEPA Prompt Optimization Pipeline

1. Implement `prompt_registry.py` (stores prompt versions with metadata like author, date, evaluation scores), `prompt_evaluator.py` (calculates citation accuracy, reasoning coherence, confidence calibration, and status correctness), and `prompt_optimizer.py` (orchestrates GEPA loops, interacting with DSPy). These modules must be deterministic and testable without live LLM calls by allowing dependency injection of mock evaluators.
2. Add `services/react_optimizer.py` as the integration layer between the controller and the prompt optimizer. It should know how to fetch current prompt versions, queue optimization jobs, and publish new prompts after approval.
3. Build `scripts/optimize_react_prompt.py` with CLI arguments for dataset paths, run modes (dry-run vs commit), max iterations, and target score thresholds. Provide clear console output so an operator can follow progress.
4. Include unit tests for the optimizer modules (`tests/unit/test_prompt_optimizer.py` etc.) that mock DSPy interfaces and verify metric weighting (40/30/20/10) as stated in the spec.
5. Document the GEPA workflow in `docs/react_controller.md` (or a dedicated GEPA doc referenced from there) so operators know when to trigger optimization, how to approve prompts, and how to roll back to earlier versions.

### Milestone 4 — Testing, Integration, and Final Rollout

1. Expand the unit test suite: ensure the delegator wrapper, metrics, shadow mode, fallback logic, and GEPA modules all have coverage. Confirm existing tests for `react_controller.py`, `llm_client.py`, and tool handlers remain green.
2. Create or update integration tests (`tests/integration/test_react_real_policy.py`) that exercise the LLM controller end-to-end. Mark them with `@pytest.mark.skipif` so they only run when API keys and PageIndex access are available.
3. Add migration documentation detailing the rollout phases (shadow → A/B → full switch) and explicit commands for toggling configuration knobs, restarting workers, and monitoring metrics/dashboards. Reference `openspec/changes/add-real-react-controller/tasks.md` to ensure every Phase 4/5 requirement is covered.
4. Update README, `docs/react_controller.md`, and `openspec/changes/add-real-react-controller/IMPLEMENTATION_SUMMARY.md` with the final instructions, test commands, and verification steps so reviewers and operators can confirm the feature works.
5. Verification: run `uv run pytest tests/unit -q`, run the integration test (if configured), and perform a manual FastAPI run in shadow mode followed by LLM-only mode to ensure no regressions. Capture example outputs and store them in this plan’s artifacts section once available.

---

## Testing & Verification Strategy

Unit tests must cover the controller delegator, metric emission, shadow mode logging, GEPA components, and existing LLM/tool logic. Integration tests remain optional but should be runnable whenever API keys are supplied. Manual verification requires launching the FastAPI app, posting sample cases, enabling/disabling shadow mode, and verifying that reasoning traces and metrics change accordingly. CLI verification involves running `uv run python -m src.cli run-decision ...` to ensure the heuristic controller still works (until CLI migration occurs) and logging clearly indicates which controller served the request.

---

## Risk Management & Recovery

Transient LLM errors continue to use the retry/backoff logic in `LLMClient`. If the LLM controller fails permanently or exceeds iteration limits, the delegator must return an UNCERTAIN decision with `reason_code="llm_error"` and log the fallback. Shadow mode ensures we can compare outputs safely before flipping the switch. GEPA runs occur offline and only publish prompts after human approval, limiting blast radius. Caches are per-criterion, so re-running evaluations is idempotent. Configuration flags always allow falling back to the heuristic controller instantly if system health degrades.

---

## Progress

- [x] Milestone 1 complete (LLM controller integrated with FastAPI, wrapper + config flags + docs updated)
- [x] Milestone 2 complete (metrics, shadow/A-B infrastructure, structured audit logs)
- [x] Milestone 3 complete (GEPA optimizer modules and script with tests)
- [ ] Milestone 4 complete (enhanced testing, integration scenarios, rollout docs)

Update this checklist after every work session so future contributors know exactly what remains.

---

## Surprises & Discoveries

- 2025-11-13 – Discovered that the LLM controller is implemented but unused because the FastAPI dependency injection still points at the heuristic controller. This plan now treats wiring and rollout as the top priority before adding GEPA and observability work.

---

## Decision Log

- 2025-11-13 – Decided to keep both controllers temporarily by wrapping them in a delegator that supports shadow mode, A/B routing, and fallback. This allows safe rollout without breaking existing clients while still meeting the spec’s requirement for an LLM-driven controller.

---

## Outcomes & Retrospective

Leave this empty until the change ships. Afterwards, summarize what succeeded, what hurt, and what to automate next time (for example, auto-retries, better test fixtures, or earlier integration of new controllers).

---

Change Log

- 2025-11-13 – Replaced the outdated milestone plan with an integration-focused roadmap that reflects the current codebase.
- 2025-11-13 – Logged the discovery that the LLM controller is already implemented but not wired into the API, and updated milestones accordingly.
