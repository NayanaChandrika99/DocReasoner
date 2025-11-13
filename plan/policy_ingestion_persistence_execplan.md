# Policy Ingestion Persistence ExecPlan


## Purpose

The goal is to make every policy ingestion run persist its results in Postgres so later services can trust that the LCD snapshot is versioned, queryable, and auditable. After finishing this plan a contributor can upload `data/Dockerfile.pdf` via `uv run python -m src.cli ingest-policy`, inspect the `policy_versions` and `policy_nodes` tables, and see the expected metadata (policy id, doc id, version, hash, markdown pointer, tree text, page ranges). Nothing in the reasoning pipeline should rely on ad-hoc JSON files once this work is complete.


## Starting Point

The CLI already uploads PDFs and caches the PageIndex tree in `data/pageindex_tree.json`, but it never writes to the database. SQLAlchemy models for `policy_versions` and `policy_nodes` live in `src/reasoning_service/models/policy.py`, yet there are no Alembic migrations and no code that populates these tables. Postgres is provisioned via `docker-compose.yml`, with `DATABASE_URL` defaulting to `postgresql://postgres:password@localhost:5432/reasoning_service`. We will treat PageIndex as the single source of truth about PDF structure (doc id, tree nodes, markdown pointer) and store both metadata and per-node content locally.


## Milestone 1 — Stand up the persistence layer

1. Ensure Postgres is running. From the repo root run `docker compose up db -d` so a fresh database is available at `postgresql://postgres:password@localhost:5432/reasoning_service`. Create a `.env` file (if it does not already exist) that sets `DATABASE_URL` to that value so CLI commands inherit it.

2. Review `src/reasoning_service/models/policy.py`. Confirm it exposes SQLAlchemy `PolicyVersion` and `PolicyNode` classes with the columns documented in `docs/structure.md` (policy id, version id, effective dates, source url, pdf hash, markdown pointer, tree json pointer; node id, parent id, section path, title, page start/end, summaries). Add any missing columns or helpers now so the schema matches the doc. Keep all field names lowercase snake_case to align with Alembic autogeneration.

3. Generate the first Alembic migration. Run `alembic revision --autogenerate -m "create policy tables"` and inspect the new file under `alembic/versions/`. The upgrade function must create the two tables plus any indexes or constraints (e.g., composite primary key on policy_id + version_id + node_id for `policy_nodes`). The downgrade should drop them in reverse order. Do not rely on autogen guesses; edit the migration until it exactly matches the models.

4. Apply the migration with `alembic upgrade head` and verify via `psql -d reasoning_service -U postgres -h localhost` that both tables exist. Keep the commands in this section idempotent so repeating them resets the schema cleanly.


## Milestone 2 — Persist PageIndex artifacts during ingestion

1. Define a small persistence helper in `src/policy_ingest/` (for example `persistence.py`) that exposes pure functions to upsert a `PolicyVersion` row and bulk insert related `PolicyNode` rows. This helper should accept simple Python dictionaries parsed from the PageIndex API rather than SQLAlchemy instances so the CLI layer stays thin. Document the expected keys inline so maintainers do not need to read other files.

2. Update `src/cli.py`’s `ingest_policy_command`. After the PageIndex tree JSON is fetched (and before returning), compute:
   * `policy_id` — use the existing CLI policy metadata if provided, or fall back to a constant like `LCD-L34220` for the demo.
   * `version_id` — derive from the CLI argument or default to `2025-Q1`.
   * `doc_id` — the PageIndex doc id returned from upload.
   * `pdf_sha256` — hash the PDF bytes during upload so future runs can detect changes.
   * `tree_cache_path` and `markdown_ptr` — the local JSON path plus the pointer returned by PageIndex, stored for auditing.
   * `ingested_at` timestamp (UTC).
   Gather these fields plus the raw tree nodes and pass them to the persistence helper so Postgres reflects the latest ingest.

3. When persisting nodes, recursively walk the PageIndex `result` array. For each node capture `node_id`, `parent_node_id` (or `None` for root), `section_path` (build from titles joined with ` > `), `title`, `page_index`, `page_start`, `page_end`, `prefix_summary`, and the raw text. Convert any missing integers to `None` to keep inserts clean. Use SQLAlchemy `Session` (e.g., via a short-lived context manager in the helper) to bulk insert and commit. To keep reruns idempotent, delete existing nodes for the `(policy_id, version_id)` pair before inserting the fresh tree.

4. Log what was persisted. Extend `telemetry/logger.py` usage in `ingest_policy_command` so every run emits `policy_persisted` with `policy_id`, `version_id`, `doc_id`, and counts of nodes inserted. This makes it trivial to confirm ingestion succeeded without querying the database manually.


## Milestone 3 — Expose and verify persisted metadata

1. Add a verification command. Extend `src/cli.py` with `@app.command("show_policy")` (or similar) that reads the latest `policy_versions` record and prints the basic metadata plus a node count. This provides an immediate feedback loop for operators.

2. Document the workflow in `README.md` and `docs/pageindex.md`: mention that ingestion now writes to Postgres, that `alembic upgrade head` must run before the first ingest, and that `show_policy` can be used to validate success.

3. Acceptance: With Postgres running and migrations applied, execute `uv run python -m src.cli ingest-policy` (ensuring `PAGEINDEX_API_KEY` is set). Afterwards run `uv run python -m src.cli show_policy --policy-id LCD-L34220 --version-id 2025-Q1` and expect to see the stored doc id, pdf hash, markdown pointer, and node count. Finally, in `psql` run `SELECT COUNT(*) FROM policy_nodes WHERE policy_id='LCD-L34220' AND version_id='2025-Q1';` and confirm the count matches the CLI output. These steps must pass for the milestone to be considered complete.


## Progress

- [x] Milestone 1 — Stand up the persistence layer
- [x] Milestone 2 — Persist PageIndex artifacts during ingestion
- [x] Milestone 3 — Expose and verify persisted metadata


## Change Log

2025-11-08 — Initial ExecPlan drafted to scope policy ingestion persistence work per `.agent/PLANS.md`.  
2025-11-08 — All milestones completed (migration authored/applied against Supabase, CLI + helper now persist PageIndex artifacts, `show_policy` command + docs verified).
