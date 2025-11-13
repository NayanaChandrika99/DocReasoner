
# Reasoning Layer — Project Brief v2.1 (PageIndex-aligned)

*(Auth Review + Doc-level QA. **NCCI / code-mapping deferred**. Architecture: **PageIndex LLM Tree Search** (optionally Hybrid), **use PageIndex spans by default**, fall back to **BM25 + cross-encoder reranker** inside a node only when spans are too broad; **small ReAct controller LLM**; **calibration + self-consistency + conformal abstention**.)*

---

## 0) Scope & Rationale

**Goal.** Decide if a referral is **ready to file** by checking VLM-extracted facts against **current payer policy**; emit **citable, structured** decisions and route **uncertain** cases to humans.

**Approach.**

* **Reasoning-based, hierarchical retrieval** using **PageIndex**: PDF → **tree** (titles + page indices + summaries), then **LLM Tree Search** over the tree (and **Hybrid Tree Search**—LLM + value function—if ambiguity remains). **No vector DB / no chunking at retrieval**; outputs include **search trajectories** and **page-exact references**. ([PageIndex Documentation][1])
* **Inside selected nodes**: **Use PageIndex’s relevant paragraphs** directly. Only if node spans are still long/noisy, run **BM25 shortlist + cross-encoder reranker** to pick precise spans for the reasoner. ([PageIndex Documentation][1])
* **ReAct** controller to interleave reasoning and tool calls; improves faithfulness and auditability. ([arXiv][2])
* **Calibration + selective self-consistency + conformal abstention** for safe automation gates. ([arXiv][3])

**Why PageIndex?** Their tree search has shown **SOTA** style results on long, structured docs (e.g., **Mafin 2.5**: **98.7%** on FinanceBench) while preserving **section/page** grounding and transparent **trajectories**—ideal for medical policy audits. ([PageIndex][4])

> **Latency note.** PageIndex’s API can return multiple relevant nodes; we’ll **process top-3 locally** for latency while still storing the **full trajectory** for audit. ([PageIndex Documentation][5])

---

## 1) Architecture (high-level)

```
VLM JSON (fields + confidence + page/bbox provenance)
   │
   ▼
PageIndex Policy Tree  (hierarchy + page ranges + summaries)
   │  — LLM Tree Search → node_ids + trajectory + page refs
   │  — (Escalate to Hybrid Tree Search if ambiguity > threshold)
   │
   ▼
Inside-node narrowing
   │  Default: use PageIndex relevant paragraphs
   │  Fallback: BM25 shortlist → cross-encoder rerank → top spans
   │
   ▼
ReAct Controller (∼3B class LLM)
   plan → retrieve → read spans → evidence link → strict JSON
   (policy citation + rationale + calibrated confidence)
   │
   ▼
Safety & Routing
   Temperature scaling (tree & final)
   + Self-Consistency (gated)
   + Conformal abstention → UNCERTAIN + reason_code → HITL
```

* **PageIndex tree & retrieval (LLM / Hybrid)** with **page-exact** references and **trajectories**. ([PageIndex Documentation][1])
* **BM25 + cross-encoder** only when node spans are too broad; models like **`ms-marco-MiniLM-L6-v2`** or **`bge-reranker-base`** are standard, fast, and well-documented. ([Sentence Transformers][6])
* **ReAct** for reasoning + acting with tools. ([arXiv][2])
* **Calibration & conformal** for trustworthy thresholds. ([arXiv][3])

---

## 2) ASCII Diagrams

### 2.1 Retrieval & Evidence

```
          ┌────────────────────────────────────────────┐
          │        PageIndex Policy Tree (JSON)        │
          │  sections + page_start/end + summaries     │
          └───────────────┬────────────────────────────┘
                          │
VLM facts ───────────────►│  LLM Tree Search (PageIndex)
(fields+provenance)       │  → node_ids + trajectory + pages
                          ▼
                 ┌───────────────────────────────┐
                 │ Inside-node narrowing         │
                 │  Default: use PI paragraphs   │
                 │  Fallback: BM25 → Reranker    │
                 └───────────────┬───────────────┘
                                 ▼
                       ┌──────────────────┐
                       │  ReAct LLM       │
                       │  think → act →   │
                       │  observe → JSON  │
                       └──────────────────┘
```

### 2.2 Safety & Routing

```
Decision JSON ──► Temp Scaling ──► (low conf & high-impact) Self-Consistency k=3
                                     │
                                     └─► Conformal set ambiguous?
                                              │
                           YES ──► UNCERTAIN + reason_code → HITL
                           NO  ──► Autopilot
```

---

## 3) Fit with Tennr / Tennr-like Products

* **Upstream:** Document VLM outputs **fields + page/bbox**.
* **Here:** PageIndex **finds the right policy sections** (with **pages & trajectory**), we optionally **tighten spans** (BM25 + reranker if needed), then **ReAct** produces **met/missing/uncertain** with **citations**. ([PageIndex Documentation][1])
* **Downstream:** Staff or PA automation consumes our **auditable checklist** and **QA report**.

---

## 4) Requirements

### Functional

* Accept `case_bundle` (VLM JSON `{field,value,confidence,doc_id,page,bbox,class}`).
* **Policy trees via PageIndex** (OCR → Tree → Retrieval). Store `policy_version_used`, **trajectory**, node ids, and page refs. ([PageIndex Documentation][1])
* **Retrieval path:** Start with **LLM Tree Search**; if cross-node ambiguity > **15%**, **switch to Hybrid Tree Search** (LLM + value function). ([PageIndex Documentation][5])
* **Inside-node spans:** Use PageIndex **relevant paragraphs**; if total tokens > threshold or noisy, run **BM25 + cross-encoder**. ([PageIndex Documentation][1])
* Emit **strict JSON** with citations (policy id, **section path, page(s)**), rationale, confidences, and **trajectory**.

### Non-functional

* **SLOs:** P50 < **5 s**, P95 < **15 s** per case.
* **Availability:** ≥ **99.9%**.
* **Calibration:** temperature scaling for **node selection** and **final decision** (evaluate on test split only). ([arXiv][3])
* **Audit:** persist `{policy_version_used, retrieval_digest, controller_version, prompt_id, search_trajectory}`.

---

## 5) Data Model (policy)

```
policy_versions(
  policy_id, version_id, effective_date, revision_date, source_url,
  tree_validated_by, tree_validated_at
)

policy_nodes(
  policy_id, version_id, node_id, parent_id,
  section_path, title, page_start, page_end,
  summary, content_hash, updated_at,
  validation_status  -- pending/approved/flagged
)

policy_validation_issues(
  policy_id, version_id, node_id, issue_type, description,
  reported_by, resolved_at
)
```

*(Tracks PageIndex-style sections + pages; adds our human-validation metadata.)* ([PageIndex Documentation][1])

---

## 6) Interfaces (v1)

**POST `/reason/auth-review`**
**In:** `case_bundle`, options (`self_consistency=true|false`)
**Out:** items like:

```json
{
  "criterion_id": "LCD-33822:Sec3.b",
  "status": "met|missing|uncertain",
  "evidence": { "doc_id": "abc123", "page": 5, "bbox": [x0,y0,x1,y1] },
  "citation": { "doc": "LCD-33822", "version": "2025-Q1", "section": "3.b", "pages": [5] },
  "rationale": "≥6 weeks PT documented (note 2025-09-14).",
  "confidence": 0.97,
  "search_trajectory": ["1","1.1","1.1.a"],
  "retrieval_method": "pageindex-llm|pageindex-hybrid|bm25+reranker"
}
```

**POST `/reason/qa`** → contradictions / missing attachments / date inconsistencies (with pages).

---

## 7) Build Specs

### 7.0 PageIndex Integration & Tree Validation

* **Use PageIndex** for OCR, Tree Generation, and Retrieval; store **trajectories** and **page refs**. ([PageIndex Documentation][1])
* **Validation UI** (our addition): tree viz + diff + checklist; **tiered review** (spot-check vs full) based on auto-triage heuristics (span length anomalies, missing pages, repeated headings).

### 7.1 Retrieval Logic

* **Start:** **LLM Tree Search**; **measure** cross-node ambiguity. If > **15%**, **switch to Hybrid Tree Search** (PageIndex’s value-function + LLM). ([PageIndex Documentation][5])
* **Inside nodes:** Prefer **PageIndex paragraphs**; only run **BM25 + reranker** if spans exceed token threshold or look noisy. ([PageIndex Documentation][1])

  * Rerankers: `ms-marco-MiniLM-L6-v2` (fast) → consider `bge-reranker-base` if needed. ([Hugging Face][7])
* **Parallelize** inside-node reranking across top nodes to protect P50 latency.

### 7.2 Controller & Safety

* **ReAct** loop; every **met/missing** requires a section citation + page(s). ([arXiv][2])
* **Calibration:** temperature scaling for **C_tree** (selection), **C_final** (decision). Track **joint confidence**
  (C_{joint} = C_{tree} \times C_{span} \times C_{final}). ([arXiv][3])
* **Self-Consistency (k=3):** only when **confidence < 0.7** and criterion **high-impact**.
* **Conformal abstention:** output **UNCERTAIN** with reason_code when prediction set is ambiguous. ([arXiv][8])

### 7.3 Error Handling

* Any retrieval/tool failure → **UNCERTAIN + reason_code**; log and alert.
* If BM25/reranker fails, try **exact string match**; else HITL.

### 7.4 Policy Refresh

* **Daily** monitoring of LCD/NCD sources; **re-parse → validate → index**; **rollback** if needed. Pin in-flight cases to **snapshot at intake**.

---

## 8) Success Metrics (per sprint, binary “done”)

| Sprint | Metric                                   | Target                    |
| -----: | ---------------------------------------- | ------------------------- |
|   0.75 | PageIndex PoC Node-Hit@3                 | **≥ 85%**                 |
|     1a | Node-Hit@3 (on policy queries)           | **≥ 95%**                 |
|     1a | Tree validation approval (human)         | **100% pre-prod**         |
|     1b | Citation accuracy (doc + section + page) | **≥ 95%**                 |
|     1b | Inside-node P@5 (if reranker used)       | **≥ 90%**                 |
|      3 | Final decision ECE (calibrated)          | **< 3%**                  |
|      4 | Latency                                  | **P50 < 5 s, P95 < 15 s** |
|    4.5 | Degraded-graceful coverage               | **100% reason-coded**     |

---

## 9) Iterative Roadmap (solo; NCCI deferred)

* **Sprint 0 — Foundations (4 wks):** 500–600 adjudicated cases; 60/20/20 split; κ ≥ 0.8 on 100 double-labeled; test harness.
* **Sprint 0.5 — Tree Tooling (2 wks):** viz/diff/validation UI.
* **Sprint 0.75 — PageIndex PoC (1 wk):** see **PoC task list** below.
* **Sprint 1a — Policy trees (5 wks):** PageIndex OCR/Tree; **human validation**; **Node-Hit@3 ≥ 95%**. ([PageIndex Documentation][1])
* **Sprint 1b — Retrieval (3 wks):** LLM Tree Search; switch to **Hybrid** if needed; consume PageIndex spans; only fallback to **BM25 + reranker** when spans too broad. ([PageIndex Documentation][5])
* **Sprint 2 — ReAct skeleton (2 wks):** tools, evidence linker, strict JSON. ([arXiv][2])
* **Sprint 3 — Calibration (2 wks):** temp scaling; thresholds; report on **test** only. ([arXiv][3])
* **Sprint 4 — Self-Consistency + Conformal (2 wks):** safety-first; monitor latency. ([arXiv][8])
* **Sprint 4.5 — Observability (2 wks):** dashboards (node accuracy, tool failures, ECE, abstention, latency, tree overrides).

**Total:** ~**22 weeks** (5.5 months) solo.

---

## 10) Sprint 0.75 — PageIndex PoC (1 week)

**Inputs.**

* 1–2 real LCD PDFs; 20 representative policy questions (e.g., “Where is 6-week PT requirement?”).
* PageIndex API keys (hosted) or sandbox. ([PageIndex Documentation][1])

**Procedure.**

1. **OCR → Tree Generation** via PageIndex; store trees and metadata. ([PageIndex Documentation][1])
2. **LLM Tree Search** on all 20 queries; capture **node_ids + trajectory + pages + relevant paragraphs**. ([PageIndex Documentation][5])
3. **Measure**:

   * **Node-Hit@3** (is gold section in top-3?)
   * **Span usefulness** (do `relevant_contents` suffice without extra narrowing?)
   * **Latency** (API round-trip, end-to-end)
4. **Fallback probe:** For queries where spans are long/noisy, run **BM25 + cross-encoder** inside the node and measure P@5 and added latency. ([Sentence Transformers][6])

**Go / No-Go Gates.**

* **Go with LLM Tree Search only** if: Node-Hit@3 ≥ 85% **and** PageIndex spans are usually sufficient.
* **Switch to Hybrid Tree Search** if **cross-node ambiguity > 15%**. ([PageIndex Documentation][5])
* **Enable BM25+reranker fallback** if **> 25%** of queries have overly long/noisy spans.

---

## 11) Non-functional Targets

* **Throughput:** design for **100 concurrent** reviews; shard tree store; cache hot node texts and reranker results.
* **Auditability:** each item includes **policy citation** (policy id, version, **section path, page(s)**), **VLM evidence** (doc/page/bbox), and **search trajectory**. ([PageIndex Documentation][1])
* **Security:** per-tenant indices; PHI minimization.

---

## References

* **PageIndex Docs & Product**

  * Intro; tools (OCR/Tree/Retrieval/MCP), vectorless RAG, page-exact references & trajectories. ([PageIndex Documentation][1])
  * LLM Tree Search (prompt/JSON format). ([PageIndex Documentation][5])
  * API endpoints (Markdown/Tree). ([PageIndex Documentation][9])
  * Product site (transparency, section/page refs). ([PageIndex][10])
  * **Mafin 2.5** 98.7% FinanceBench: blog, product page, repo. ([PageIndex][4])

* **ReAct**

  * Paper (ICLR 2023), PDF, code, blog explainer. ([arXiv][2])

* **Calibration & Conformal**

  * Temperature scaling (Guo et al.). ([arXiv][3])
  * Conformal prediction tutorial/monograph. ([arXiv][8])

* **Hybrid retrieval & reranking**

  * Hybrid search rationale (sparse+dense). ([Weaviate][11])
  * Cross-encoder rerankers (Sentence-Transformers docs & model cards). ([Sentence Transformers][6])

---	


[1]: https://docs.pageindex.ai/?utm_source=chatgpt.com "Introduction - PageIndex"
[2]: https://arxiv.org/abs/2210.03629?utm_source=chatgpt.com "ReAct: Synergizing Reasoning and Acting in Language Models"
[3]: https://arxiv.org/abs/1706.04599?utm_source=chatgpt.com "On Calibration of Modern Neural Networks"
[4]: https://pageindex.ai/blog/Mafin2.5?utm_source=chatgpt.com "PageIndex Powers State-of-the-Art Financial QA Benchmark"
[5]: https://docs.pageindex.ai/tree-search/basic?utm_source=chatgpt.com "LLM Tree Search"
[6]: https://www.sbert.net/docs/pretrained-models/ce-msmarco.html?utm_source=chatgpt.com "MS MARCO Cross-Encoders"
[7]: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2?utm_source=chatgpt.com "cross-encoder/ms-marco-MiniLM-L6-v2"
[8]: https://arxiv.org/abs/2107.07511?utm_source=chatgpt.com "A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification"
[9]: https://docs.pageindex.ai/endpoints?utm_source=chatgpt.com "PageIndex PDF Processing API Endpoints"
[10]: https://pageindex.ai/?utm_source=chatgpt.com "PageIndex AI"
[11]: https://weaviate.io/blog/hybrid-search-explained?utm_source=chatgpt.com "Hybrid Search Explained"
