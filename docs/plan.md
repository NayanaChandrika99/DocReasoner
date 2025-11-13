# Reasoning Layer — Project Brief v2.3 (Single‑Policy Demo, PageIndex‑aligned)

This plan describes how we will refresh every documentation file to reflect the finalized single-policy demo architecture: PageIndex-powered ingestion/retrieval, a ReAct controller with reasoning traces, FTS5 fallback, curated fixtures, and strict auditing. No extra inputs are required beyond the existing policy PDF in `data/Dockerfile.pdf` (LCD - Lumbar MRI (L34220), doc_id `pi-cmhppdets02r308pjqnaukvnt`) and the PageIndex API access you already have configured.

*(Auth Review + Doc-level QA. NCCI/code-mapping deferred. Architecture: **PageIndex LLM Tree Search** (vectorless), **PageIndex spans by default**, optional **SQLite FTS5 (bm25) paragraph fallback** inside a selected node when spans are long/noisy; **small ReAct controller LLM**; **simple abstention rule**.)*

---

## Documentation Refresh Plan

Each doc gets its own short summary paragraph plus implementation-ready details. No new data, API keys, or links are needed beyond the existing PageIndex credentials and Lumbar MRI policy PDF.

1. **`docs/project.md`** — Summarize the end-to-end goal (policy-grounded prior-auth readiness) in a fresh intro paragraph and highlight that CPT/HCPCS/ICD codes are sourced directly from the Lumbar MRI PDF. Expand “What we’re building” and “Why this approach” to emphasize PageIndex reasoning-first retrieval, ReAct explanations, and pointerized PHI. Add an “External Requirements” note that explicitly states the only dependencies are the policy PDF in `data/` and PageIndex API credentials already on hand.

2. **`docs/architecture.md`** — Open with a short description of the architecture update, then reorganize sections around ingestion → retrieval → controller → safety → observability. Call out circuit breakers (PageIndex timeout ⇒ UNCERTAIN), caching of tree JSON, and telemetry sinks. Reuse the existing assets; no further data or secrets are required.

3. **`docs/structure.md`** — Introduce the schema refresh with a paragraph that explains why the contracts changed. Update every request/response to include `reasoning_trace`, `reason_code`, and the error payload described in this plan, plus UNCERTAIN/HITL metadata. Ensure storage records capture retry counts and fallback usage. These adjustments rely solely on the current policy PDF + API responses—no extra inputs needed.

4. **`docs/MVP.md`** — Start with a concise summary of the MVP deliverables, then align scope, acceptance criteria, and runbook with the latest expectations: curated fixtures, `run_test_suite`, reasoning-quality metrics, and UNCERTAIN routing. Mention that the fixtures will be handcrafted from the Lumbar MRI policy; no other datasets are required.

5. **`docs/tools.md`** — Add a brief overview paragraph, expand each tool’s responsibilities (PageIndex API usage, abstract ReAct controller, SQLite FTS5 fallback, billing-code considerations), and explicitly list secret/config needs (PageIndex API key, controller LLM key when applicable). Note that CPT references come from the policy PDF but full CPT dictionaries still require AMA licensing.

6. **`docs/pageindex.md`** — Keep the intro paragraph but tighten Quickstart details: emphasize curl usage for `/api/doc/` and `/api/retrieval/`, add guidance on polling cadence and hybrid search triggers, and remind readers to log retries/timeouts per the architectural plan. Examples should continue to reference the Lumbar MRI PDF path; no additional data or keys are required.

---

## Code Repo Build Outline

This section captures how the codebase should be structured once documentation is updated. No further inputs are required: we will continue using the Lumbar MRI PDF from `data/` and the existing PageIndex API credentials.

1. **Environment & Secrets**
   - Store `PAGEINDEX_API_KEY` and `PAGEINDEX_BASE_URL` in `.env` or `.env.local`.
   - Optional: controller LLM key (e.g., OpenAI OSS endpoint) once a concrete model is selected.
   - Dependency management uses `uv`; run `uv sync` (optionally `uv sync --group dev`) after cloning. A `uv.lock` should live at the repo root once generated locally.

2. **Policy Ingestion Module (`src/policy_ingest/`)**
   - CLI command `ingest_policy` that uploads `data/Dockerfile.pdf`, polls `/api/doc/{doc_id}` for `type=tree&format=page&summary=true`, and caches the resulting tree JSON + markdown pointer locally.
   - Persist metadata in `policy_versions` and `policy_nodes` tables (or JSON files during the demo).

3. **Retrieval Module (`src/retrieval/`)**
   - Unified wrapper that calls PageIndex LLM Tree Search, switches to Hybrid Tree Search when ambiguity > threshold, and logs `search_trajectory`, `retrieval_method`, and fallback triggers.
   - Local SQLite FTS5 index to tighten spans when node token count > threshold (default 800) and record when fallback activates.

4. **Controller Module (`src/controller/`)**
   - ReAct loop that calls `pi.search`, reads spans, compares them to pointerized case facts, and emits the strict JSON (status, citation, confidence breakdown, reasoning_trace, retrieval_method, error payload when needed).
   - Implement abstention rule (`final_confidence < 0.65 ⇒ UNCERTAIN`) and reason-coded handoff payloads.

5. **Case Bundles & Fixtures (`tests/data/cases/`)**
   - Handcraft 10–20 JSON cases derived from the Lumbar MRI policy, covering straightforward, synthesis, conflict, missing-evidence, and policy-gap scenarios.
   - Each fixture stores expected citations, pages, reasoning summary, and difficulty tag.

6. **CLI Commands (`src/cli.py` or `scripts/`)**
   - `ingest_policy`, `validate_tree`, `run_decision --case <file>`, `run_test_suite` (executes every fixture, scores reasoning rubric, reports infra errors).

7. **Telemetry & Storage**
   - Record `tree_search_ms`, `ft s5_ms`, `controller_ms`, retry counts, fallback usage, and error codes in `reasoning_outputs` (or a structured log) for each run.

8. **Testing & Linting**
   - Unit tests for ingestion/retrieval wrappers (mocking PageIndex responses).
   - Integration tests that run `run_decision` against a subset of fixtures using cached tree data.

This outline ensures the repo implementation matches the refreshed documentation without introducing new dependencies.

### Target Repository Structure

```
reasoning-service/
├── data/
│   └── Dockerfile.pdf
├── docs/
│   ├── architecture.md
│   ├── MVP.md
│   ├── pageindex.md
│   ├── plan.md
│   ├── project.md
│   ├── structure.md
│   └── tools.md
├── openspec/
│   ├── AGENTS.md
│   ├── changes/
│   └── project.md
├── scripts/
│   ├── ingest_policy.py (entry point)
│   └── run_decision.py
├── src/
│   ├── cli.py
│   ├── controller/
│   │   ├── __init__.py
│   │   └── react_controller.py
│   ├── policy_ingest/
│   │   ├── __init__.py
│   │   └── pageindex_client.py
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── tree_search.py
│   │   └── fts5_fallback.py
│   └── telemetry/
│       └── logger.py
├── tests/
│   ├── data/
│   │   └── cases/
│   │       ├── case_straightforward.json
│   │       └── ...
│   ├── test_controller.py
│   ├── test_retrieval.py
│   └── test_cli.py
├── .env.example
├── pyproject.toml
└── README.md (optional future addition)
```

The scripts and modules above map directly to the ingestion/retrieval/controller flow described earlier; no extra files or external data sources are required.

---

## 0) Scope & Rationale

**Goal.** Determine whether a referral is **ready to file** by comparing VLM-extracted case facts to the **current policy** and emit **citable, structured** decisions. Route low-confidence cases to humans.

**Approach (demo scope).**
- **Vectorless, reasoning-based retrieval with PageIndex:** PDF → OCR’d Markdown → **Tree Generation** → **LLM Tree Search** returning **page-exact** references and **search trajectories**.
- **Inside selected nodes:** Use **PageIndex relevant paragraphs**. If the node text exceeds a token threshold, run **SQLite FTS5 bm25()** locally to narrow paragraphs.
- **Controller:** Lightweight **ReAct** planner that interleaves tool calls (retrieve → read spans → justify) and returns strict JSON with citations.
- **Safety:** Simple gate — if **final confidence < 0.65 ⇒ UNCERTAIN** (no silent guesses).

**Why PageIndex (for demo):** Reasoning-based, **tree-search retrieval** designed for **long, structured PDFs**, providing **section/page grounding** and **transparent trajectories**, avoiding vector DBs and brittle chunking.

### Demo Assets
- **Policy PDF:** `data/Dockerfile.pdf` (LCD - Lumbar MRI (L34220), doc_id `pi-cmhppdets02r308pjqnaukvnt`, source for both ingestion and evidence snippets).
- **Test cases:** handcrafted JSON bundles (10‑20) derived from the PDF, covering straightforward matches, conflicting evidence, missing documentation, OCR noise, and true policy gaps. Each case encodes expected section/page citations and reasoning notes so the demo can score reasoning quality, not just status.

---

## 1) Architecture (high-level)

```
VLM Case Bundle (facts + confidence + doc/page/bbox)
   │
   ▼
PageIndex Policy Pipeline
  OCR → Markdown → Tree Generation → (persist tree + pages)
   │
   ├─► Query-time: LLM Tree Search → node_ids + trajectory + page refs
   │                    │
   │                    └─► Relevant paragraphs (PageIndex)
   │
   └─► [If node text > threshold] FTS5 bm25 fallback → top spans
                                   │
                                   ▼
ReAct Controller (small LLM)
  plan → retrieve → read spans → compare vs facts → strict JSON
  (status + policy citation + rationale + confidence + trajectory)
   │
   ▼
Safety & Routing
  if confidence < 0.65 → UNCERTAIN → Human-in-the-loop
  else → Ready/Not Ready
```

**Key properties**
- **Vectorless retrieval first (PageIndex)**; no external vector store for the demo.
- **Local paragraph fallback (FTS5 bm25)** only inside chosen nodes when needed.
- **Auditable**: Every decision carries **section path + page(s)** and the **search trajectory**.

---

## 2) Components & Responsibilities

- **policy_ingest**  
  - Upload policy PDF to PageIndex; persist **markdown_ptr**, **tree_json**, version info.  
  - Maintain `policy_id`, `version_id`, `source_url`, `pdf_sha256` and snapshot binding at intake.

- **retrieval**  
  - Run **LLM Tree Search** for each question/criterion; capture `selected_node_ids`, `search_trajectory`, `page_refs`, and `relevant_paragraphs`.  
  - Wrap every PageIndex call with circuit breakers (1.5 s timeout, 2 retries, jittered backoff). If calls continue to fail return `retrieval_method:"pageindex-llm"`, `status:"uncertain"`, and `reason_code:"pageindex_timeout"`.  
  - Trigger **FTS5 bm25** fallback when total tokens in selected node exceed threshold (default `800`, tunable per policy density) and log when fallback activates for later tuning.

- **controller**  
  - **LLM-Driven ReAct loop** with dynamic tool selection and reasoning. The controller uses an LLM to decide which tools to call and when, rather than following fixed heuristics.
  - **Multi-Provider Support**: OpenAI, Anthropic, and vLLM compatibility through unified client interface.
  - **Tools**: `pi.search(query)`, `facts.get(field)`, `spans.tighten(node_id)`, `finish(status, rationale, confidence, citations)`.
  - **GEPA Optimization** (Advanced): Autonomous prompt improvement using DSPy's Genetic-Pareto optimizer. Continuously optimizes controller performance through evolutionary prompt refinement based on 4 evaluation metrics:
    - Citation accuracy (40%): Correct policy section/page references
    - Reasoning coherence (30%): Quality of reasoning trace clarity
    - Confidence calibration (20%): Correlation between confidence and correctness  
    - Status correctness (10%): Correct met/missing/uncertain decisions
  - Automated retraining triggers when quality metrics degrade below thresholds.
  - Emit **strict JSON** plus a `reasoning_trace` array mirroring the ReAct steps so reviewers can audit the logic.
  - **Implementation Details**: See `openspec/changes/add-real-react-controller/` for complete specification, GEPA implementation guide, and additional tool capabilities.

- **data**  
  - Store PageIndex artifacts, pointerized case bundles, decisions, and telemetry.  
  - PHI minimization: store **doc/page/bbox pointers**; avoid raw text where possible.

---

## 3) Requirements (demo‑level)

### Functional
- Accept a pointerized **`case_bundle`** (fields, value, confidence, `doc_id/page/bbox`).  
- **Ingest policy** via PageIndex; persist tree and page ranges.  
- **Retrieve** with PageIndex LLM Tree Search; optionally run **FTS5 bm25** fallback inside node if token budget exceeded.  
- **Reason** with ReAct controller and return **strict JSON** with **page‑level citations**, **confidence**, and **reasoning_trace**.  
- **Abstain** if confidence < 0.65.

### Non‑functional
- **CLI‑only** for demo: `ingest_policy`, `validate_tree`, `run_decision`, plus `run_test_suite` to replay curated fixtures.  
- **Auditability**: persist `{policy_version_used, search_trajectory, retrieval_method, reasoning_trace}` with each decision.  
- **Security**: per‑tenant isolation or row‑level ACLs; logs exclude PHI; pointerized storage.  
- **Reasoning quality**: each curated case stores expected citations and trace summaries; evaluate accuracy (≥80% correct reasoning across the suite).

---

## Failure Handling & Error Contract
- **Circuit breakers:** PageIndex ingest/search/span calls enforce 1.5 s timeouts, retry twice with jitter, then surface `status:"uncertain"` + `reason_code:"pageindex_timeout"`.
- **Fallback ordering:** try PageIndex spans → FTS5 bm25 → if still empty, emit `status:"uncertain"`, `reason_code:"no_relevant_nodes"`.
- **Controller errors:** tool exceptions or JSON schema violations return `status:"error"`, `error:"tool_failure"`, and `error_details` (string) so downstream UI can flag infra vs reasoning issues.
- **Logging:** capture retries, fallback activations, and error codes per case for later analysis.

---

## 4) Interfaces (concise)

### 4.1 Controller input (shape)
```json
{
  "case_id": "string",
  "policy_id": "string",
  "version_id": "string",
  "question": "string",
  "case_bundle": {
    "patient_key": "string",
    "facts": [{
      "field": "string",
      "value": "string|number",
      "confidence": 0.0,
      "doc_id": "string",
      "page": 0,
      "bbox": [0,0,0,0],
      "class": "string"
    }]
  }
}
```

### 4.2 Controller output (strict)
```json
{
  "criterion_id": "string",
  "status": "ready|not_ready|uncertain",
  "citation": {
    "policy_id": "string",
    "version": "string",
    "section_path": "string",
    "pages": [0]
  },
  "rationale": "string",
  "confidence": {
    "c_tree": 0.0,
    "c_span": 0.0,
    "c_final": 0.0,
    "c_joint": 0.0
  },
  "search_trajectory": ["node_id", "node_id"],
  "reasoning_trace": [
    {"step": 1, "action": "search", "input": "PT requirement", "result": ["1.2"]},
    {"step": 2, "action": "read", "node_id": "1.2", "pages": [5], "summary": "PT ≥6 weeks"},
    {"step": 3, "action": "decide", "finding": "meets PT"}
  ],
  "retrieval_method": "pageindex-llm|bm25-fallback"
}

Error payload (for infra/tool failures):

```json
{
  "status": "error",
  "error": "pageindex_timeout|no_relevant_nodes|tool_failure",
  "error_details": "string"
}
```
```

---

## 5) Minimal Data Model

```
policy_versions(
  policy_id, version_id, effective_date, revision_date, source_url,
  pdf_sha256, markdown_ptr, tree_json_ptr
)

policy_nodes(
  policy_id, version_id, node_id, parent_id,
  section_path, title, page_start, page_end, summary
)

reasoning_outputs(
  case_id, criterion_id, policy_id, version_id,
  status, rationale, citation_section_path, citation_pages,
  c_tree, c_span, c_final, c_joint,
  search_trajectory, retrieval_method, created_at
)
```

---

## 6) Demo Plan & Deliverables

**Scope:** one policy PDF + a handful of curated test cases.

**Deliverables**
- **Policy ingest + validate (CLI)**: upload to PageIndex, persist tree, print heading/page diff.
- **Retrieval (CLI)**: run **LLM Tree Search**, show `section_path + page(s)` and `trajectory`; trigger **FTS5 bm25** only if node too long.  
- **Decision runner (CLI)**: compare spans vs case facts; output decision JSON with citations and confidence; apply abstention rule.

**Definition of Demo Done**
- For each test case, the system returns **Ready / Not Ready / Uncertain** with:  
  - **Section path + page(s)** (PageIndex),  
  - **Search trajectory**,  
  - **Retrieval method** (`pageindex-llm` or `bm25-fallback`).

---

## 6.5) Controller Enhancement: LLM-Driven ReAct with GEPA Optimization

### Evolution from Heuristic to LLM-Driven

The ReAct controller is being enhanced from a simple heuristic implementation to a true LLM-driven agent capable of autonomous improvement:

**From**: Fixed workflow (Think → Retrieve → Read → Link → Decide)  
**To**: Dynamic tool selection where LLM decides which tools to call and when

### Key Enhancements

#### 1. Multi-Provider LLM Support
- **OpenAI**: GPT-4o, GPT-4o-mini with function calling
- **Anthropic**: Claude models with tool use
- **vLLM**: Self-hosted models via OpenAI-compatible API
- Unified client interface abstracts provider differences

#### 2. GEPA Prompt Optimization
Autonomous prompt improvement using DSPy's Genetic-Pareto optimizer:

**Evaluation Metrics** (Multi-objective optimization):
- Citation accuracy (40%): Correct policy section/page references
- Reasoning coherence (30%): Quality and clarity of reasoning traces
- Confidence calibration (20%): Correlation between confidence and correctness
- Status correctness (10%): Accurate met/missing/uncertain determinations

**Target**: Aggregate score > 80% across all metrics

**Workflow**:
1. Quality monitor tracks recent decisions from database
2. When metrics degrade below threshold (e.g., citation accuracy < 85%), trigger optimization
3. GEPA runs evolutionary search with reflection LLM analyzing failures
4. Generate prompt candidates through mutation and reflection
5. Evaluate candidates on training set, select best via Pareto optimization
6. Validate on separate validation set
7. Register optimized prompt for manual review/approval
8. Activate new prompt after approval

#### 3. Extended Tool Capabilities
Beyond core tools (`pi_search`, `facts_get`, `spans_tighten`, `finish`):

**Medical Knowledge Tools**:
- PubMed literature search for evidence-based guidelines
- ICD-10 code lookup and validation
- Drug interaction checking

**Policy Analysis Tools**:
- Cross-reference checker (find related requirements across sections)
- Temporal policy analysis (check version effective dates)

**Evidence Synthesis Tools**:
- Confidence aggregator (Bayesian updating)
- Contradiction detector (flag conflicting case data)

**Multi-Agent Collaboration**:
- Specialized agents for complex cases (clinical reviewer, policy expert, compliance officer)
- Consensus-based decision synthesis

#### 4. Monitoring & Observability
- Prompt version registry with A/B testing
- Quality metrics dashboards (Prometheus/Grafana)
- Cost tracking and token budgets
- Automated alerts on quality degradation

### Implementation Status
- **Phase 1-4**: Core LLM-driven ReAct controller (Complete)
- **Phase 5**: Migration with shadow mode and A/B testing (In Progress)
- **GEPA Integration**: Full specification complete, ready for implementation

### Documentation
Complete implementation guides available in `openspec/changes/add-real-react-controller/`:
- `gepa_implementation.md` - Full GEPA integration guide with code examples
- `additional_tools.md` - Extended tool catalog with implementations
- `README.md` - Navigation and quick start
- `IMPLEMENTATION_SUMMARY.md` - Executive summary
- `tasks.md` - Detailed implementation checklist

### Expected Impact
- **Quality**: >80% aggregate reasoning score (from ~70% baseline)
- **Consistency**: Reduced uncertain cases by 15%
- **Adaptability**: Continuous improvement without manual prompt engineering
- **Extensibility**: Easy addition of domain-specific tools

---

## 7) Test Data & Evaluation

- **Fixture set:** 10–20 handcrafted case bundles stored under `tests/data/cases/`. Each file includes: case facts, expected `criterion_id`, required policy section/page, expected status, acceptable reasoning summary, and a `difficulty` tag (`straightforward`, `synthesis`, `conflict`, `missing_evidence`, `policy_gap`).
- **Evaluation CLI:** `run_test_suite` executes the decision runner on every fixture, asserts citation/page matches, and scores reasoning via rubric (citation accuracy 40%, reasoning trace coherence 30%, confidence alignment 20%, status correctness 10%).
- **Success bar:** ≥80% aggregate reasoning score, ≥95% citation accuracy, ≤10% infra errors (timeouts, tool failures).
- **Review workflow:** UNCERTAIN outputs materialize as JSON payloads containing `reason_code`, cited spans, and reasoning trace for manual adjudication; reviewers can append overrides to feed future training data.

---

## 8) References (authoritative)

### Core Technologies
- **PageIndex** — Intro/Tools (OCR, Tree Generation, Retrieval, MCP): https://docs.pageindex.ai/  
- **PageIndex** — LLM Tree Search (tutorial & API shape): https://docs.pageindex.ai/tree-search/basic  
- **PageIndex** — Project repo (vectorless RAG, tree indexing): https://github.com/VectifyAI/PageIndex  
- **ReAct** — Paper & PDF: https://arxiv.org/abs/2210.03629 , https://arxiv.org/pdf/2210.03629  
- **SQLite FTS5** — bm25 ranking function: https://sqlite.org/fts5.html

### Advanced Features (LLM-Driven ReAct & GEPA Optimization)
- **GEPA Paper** — Reflective Prompt Evolution: https://arxiv.org/abs/2507.19457
- **GEPA GitHub** — Official implementation: https://github.com/gepa-ai/gepa
- **DSPy Framework** — Programming LLMs: https://dspy.ai/
- **DSPy GEPA API** — Optimizer documentation: https://dspy.ai/api/optimizers/GEPA/overview/
- **Implementation Guide** — Complete specification and code examples: `openspec/changes/add-real-react-controller/gepa_implementation.md`
- **Additional Tools** — Extended capabilities catalog: `openspec/changes/add-real-react-controller/additional_tools.md`
