# MVP.md — Reasoning Layer v2.3 (Single‑Policy Demo)

## 1) Purpose (one screen)
Stand up a **minimal, auditable system** that decides **Ready / Not Ready / Uncertain** for referrals against **one policy PDF**, using **PageIndex** as the vectorless retrieval backbone with **page‑level grounding** and visible **search trajectories**, a lightweight **ReAct** controller for tool‑use reasoning, and an optional **SQLite FTS5 (bm25)** paragraph fallback **inside** the selected policy node. No UI, no training, no vector DB.  
*Refs: PageIndex overview & docs; LLM Tree Search; ReAct; SQLite FTS5 bm25.*

- PageIndex (vectorless, tree‑search over long PDFs).  
- ReAct (interleaving reasoning with tool calls).  
- FTS5 bm25 (local paragraph narrowing).

## 2) Scope
**In‑scope**
- One **policy PDF** → PageIndex: OCR → Markdown → **Tree**; persist tree + page ranges.  
- **Query‑time retrieval** via PageIndex **LLM Tree Search**; store `node_ids`, `page_refs`, `search_trajectory`, and `relevant_paragraphs`.  
- **Inside‑node fallback** using **SQLite FTS5 bm25()** only when the selected node’s text exceeds a token threshold (default **800** tokens).  
- **ReAct controller** produces **strict JSON** decision with **page‑exact citation**, rationale, confidence, trajectory, retrieval_method.  
- **CLI‑only** runbook; pointerized PHI storage (doc/page/bbox).

**Out‑of‑scope**
- UI, hybrid/vector retrieval, cross‑encoder rerankers, model training/fine‑tuning, complex dashboards/CI.

## 3) Acceptance criteria (demo)
- **AC‑1 (Ingestion):** Policy ingested and versioned via PageIndex; tree saved with section titles and **page_start/page_end**.  
- **AC‑2 (Retrieval):** For each curated test case/question, system returns **section path + page(s)** and **search trajectory** from PageIndex.  
- **AC‑3 (Decision):** Controller emits **Ready / Not Ready / Uncertain** with **citation** and **confidence**; includes `retrieval_method = pageindex-llm` or `bm25-fallback`.  
- **AC‑4 (Safety):** If `final_confidence < 0.65` ⇒ status **Uncertain** (no silent guesses).  
- **AC‑5 (Audit):** Persist `{policy_version_used, search_trajectory, retrieval_method, timings}` with each decision.

## 4) Architecture snapshot (condensed)
```
VLM Case Bundle (facts + doc/page/bbox)
   │
   ▼
PageIndex Pipeline: OCR → Markdown → Tree  (persist tree + pages)  [docs.pageindex.ai]
   │
   ├─► Query: LLM Tree Search → node_ids + trajectory + page refs + paragraphs
   │
   └─► [If node text > 800 tokens] FTS5 bm25() → narrowed spans
                                      │
                                      ▼
ReAct Controller: plan → retrieve → read spans → compare vs facts → strict JSON
Safety: final_confidence < 0.65 ⇒ UNCERTAIN
```

- **PageIndex** provides vectorless **tree search** with **page‑exact grounding** and **trajectories**.  
- **FTS5 bm25** is *local*, only for paragraph narrowing within the chosen node.  
- **ReAct** makes tool use and reasoning **inspectable**.

## 5) Interfaces (concise; see `structure.md` for full contracts)
- **Policy ingestion:** submit PDF ⇒ `doc_id`; fetch results ⇒ `markdown_ptr`, `tree_json{nodes: [section_path, page_start/end, title]}`.  
- **Retrieval:** PageIndex **LLM Tree Search** ⇒ `selected_node_ids`, `page_refs`, `relevant_paragraphs`, `search_trajectory`.  
- **Inside‑node fallback:** **FTS5 bm25()** over node text when threshold exceeded ⇒ top spans.  
- **Decision output:** strict JSON with `status`, `citation{policy_id, version, section_path, pages}`, `rationale`, confidences (`c_tree`, `c_span`, `c_final`, `c_joint`), `search_trajectory`, `retrieval_method`.

## 6) Data model (minimal)
```
policy_versions(policy_id, version_id, effective_date, revision_date,
  source_url, pdf_sha256, markdown_ptr, tree_json_ptr)

policy_nodes(policy_id, version_id, node_id, parent_id,
  section_path, title, page_start, page_end, summary)

reasoning_outputs(case_id, criterion_id, policy_id, version_id,
  status, rationale, citation_section_path, citation_pages,
  c_tree, c_span, c_final, c_joint, search_trajectory,
  retrieval_method, created_at)
```

## 7) Configuration (defaults)
- `bm25_threshold_tokens = 800` (trigger fallback beyond this).  
- `abstain_confidence_threshold = 0.65`.  
- `max_nodes = 3` (cap PageIndex nodes processed locally).

## 8) Runbook (CLI only)
- `ingest_policy`: download or read PDF, upload to PageIndex, store `tree_json`, print heading/page diff.  
- `retrieve`: run **LLM Tree Search** for a question; show `section_path + page(s)` and `trajectory`; if node too long, run FTS5 narrowing.  
- `run_decision`: load case bundle + policy; execute controller; write decision JSON and timings.

## 9) Telemetry (demo‑level)
Record `tree_search_ms`, `inside_node_ms`, `llm_ms`, `total_ms`, `cache_hits`, `alt_nodes_considered`. Persist per decision for audit.

## 10) Security & privacy
- **Pointerization:** store doc/page/bbox references for PHI; avoid raw text.  
- **Isolation & secrets:** per‑tenant schema/ACL; env‑based secrets; encrypted at rest.  
- **Audit trail:** keep `policy_version_used`, `search_trajectory`, `retrieval_method`, timings.

## 11) Milestones
- **M0 (Day 1–2):** PageIndex ingest; tree persisted; CLI validate.  
- **M1 (Day 3–4):** Retrieval wired; FTS5 fallback behind threshold flag.  
- **M2 (Day 5–7):** Controller emits strict JSON; abstention gate in place; demo run on curated cases.

## 12) Risks & mitigations
- **OCR/tree variance:** add `validate_tree` CLI and allow manual override of bad headings; cache markdown.  
- **Latency spikes:** cap nodes at 3; parallelize FTS5 narrowing if triggered; cache hot spans.  
- **Policy drift:** snapshot‑at‑intake; store `version_id`; re‑ingest when hash changes.

## 13) References (authoritative)
- **PageIndex — Intro/Tools (OCR → Tree → Retrieval; vectorless RAG)**: https://docs.pageindex.ai/
- **PageIndex — LLM Tree Search (tutorial)**: https://docs.pageindex.ai/tree-search/basic
- **PageIndex — OSS repo (vectorless, tree‑indexed retrieval)**: https://github.com/VectifyAI/PageIndex
- **ReAct — paper & PDF (reasoning + acting)**: https://arxiv.org/abs/2210.03629 , https://arxiv.org/pdf/2210.03629
- **SQLite FTS5 — bm25 ranking**: https://sqlite.org/fts5.html
