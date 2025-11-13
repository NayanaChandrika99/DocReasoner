# Reasoning Service (Single-Policy Demo)

This repository contains the PageIndex-powered reasoning layer for prior-authorization readiness reviews. See `docs/project.md` and `docs/plan.md` for the full specification and implementation plan.  

- Ingest the Lumbar MRI LCD via the PageIndex API (`data/Dockerfile.pdf`, doc_id `pi-cmhppdets02r308pjqnaukvnt`).  
- Retrieve relevant sections with PageIndex LLM Tree Search (automatically switching to hybrid search or a bm25 fallback when ambiguity or span length requires it).  
- Run the ReAct controller to emit citable `ready|not_ready|uncertain` decisions with reasoning traces. The architecture and contracts for both controllers live in [`docs/react_controller.md`](docs/react_controller.md).

## Development

Use [uv](https://docs.astral.sh/uv) for dependency management:

```bash
uv sync --extra dev   # install runtime + dev deps
uv run python -m src.cli --help
uv run pytest tests/unit/test_retrieval_service.py
```

## ReAct controller quick start

- CLI: `uv run python -m src.cli run-decision tests/data/cases/case_straightforward.json`
- CLI (LLM agent): append `--controller llm` to the command above (requires PageIndex + LLM API keys in your environment).
- API: `uv run uvicorn reasoning_service.api.app:create_app --factory --reload` then `curl -X POST http://localhost:8000/reason/auth-review`
- Contracts: Both surfaces emit confidence breakdowns, reasoning traces, and retrieval metadata; use `docs/react_controller.md` as the canonical reference.

## Controller configuration

Set the following environment variables in `.env` (or the production template) to drive the new LLM controller rollout. All of them default to the safe heuristic controller so you can opt in gradually.

- `REACT_USE_LLM_CONTROLLER`: When `true`, FastAPI requests use the LLM controller unless shadow or A/B settings override it.
- `REACT_SHADOW_MODE`: When `true`, the service runs both controllers but only returns the heuristic result while logging differences (use this first).
- `REACT_FALLBACK_ENABLED`: When `true`, failures in the LLM controller automatically fall back to the heuristic result with `reason_code="llm_fallback"`.
- `REACT_AB_TEST_RATIO`: Floating-point value between `0.0` and `1.0`; routes that fraction of traffic to the LLM controller to support gradual rollouts.

All other controller options (max iterations, temperature, provider, model) remain in the same section of the `.env.*` templates.

Prompt optimization uses its own knobs:

- `GEPA_ENABLED`, `GEPA_AUTO_MODE`, `GEPA_MAX_ITERATIONS`, and `GEPA_TARGET_SCORE` control whether the optimizer runs automatically and what score qualifies as success.
- `GEPA_REFLECTION_MODEL` and `GEPA_TASK_MODEL` define the evaluator and task models used during GEPA runs.
- `GEPA_DATASET_PATH` points at a directory of sample cases or serialized `CriterionResult`s used for dry runs.

## Prompt optimization (GEPA)

The repo ships a scaffold for GEPA-style prompt improvement:

1. Configure the environment variables listed above (at minimum `GEPA_ENABLED=true` and `GEPA_DATASET_PATH` pointing to a directory of case fixtures).
2. Run `uv run python scripts/optimize_react_prompt.py --dry-run` to exercise the optimizer without making live LLM calls. The script evaluates the current prompt against synthetic CriterionResults, records the best candidate under `optimization_results/latest.json`, and appends it to `data/prompt_registry.json`.
3. For live tuning, wire the `ReActControllerAdapter` evaluate function to your evaluation harness (see `src/reasoning_service/services/prompt_optimizer.py`) and rerun the script without `--dry-run`. The optimizer will stop once the aggregate score exceeds `GEPA_TARGET_SCORE`.
4. Use `PromptRegistry` to inspect previous prompt versions and compare aggregate scores before promoting a new prompt to production.

## Policy ingestion workflow

1. Ensure Postgres is running and the `DATABASE_URL` in `.env` points to it (the repo ships with `postgresql://postgres:password@localhost:5432/reasoning_service`).  
2. Apply the schema once via `uv run alembic upgrade head`.  
3. Upload/cache the policy with `uv run python -m src.cli ingest-policy --policy-id LCD-L34220 --version-id 2025-Q1 --pdf data/Dockerfile.pdf`. This command now persists the PageIndex doc id, PDF hash, markdown pointer, and every tree node in the Postgres tables.  
4. Inspect what was stored using `uv run python -m src.cli show-policy --policy-id LCD-L34220 --version-id 2025-Q1` and confirm the node count matches expectations.
