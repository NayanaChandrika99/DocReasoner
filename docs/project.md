# Project: Policy-Grounded Prior-Auth Readiness (Single-Policy Demo)

## What we’re building
A small, auditable service that decides **Ready / Not Ready / Uncertain** for a referral by:
1) Turning a **policy PDF** into a **hierarchical tree** with **page-level** references (PageIndex),
2) Retrieving the **most relevant sections** via **LLM Tree Search** (vectorless),
3) Comparing those spans to **case facts** (pointerized PHI),
4) Emitting a **citable** decision (+ codes referenced in the policy spans).

## Why this approach
- **Long-PDF robustness:** Reasoning-based, section-aware search instead of chunk nearest-neighbor.
- **Explainability:** Search **trajectory** + **page refs** and **ReAct** reasoning traces.
- **Lean fallback:** Local **FTS5 bm25** only inside chosen nodes—no new services or vector DB.

## Links
- PageIndex: Introduction / Tools / Endpoints / LLM Tree Search — https://docs.pageindex.ai/
- ReAct (paper): https://arxiv.org/abs/2210.03629
- SQLite FTS5 (bm25): https://www.sqlite.org/fts5.html
- Code systems:
  - ICD-10-CM (CDC/NCHS): https://www.cdc.gov/nchs/icd/icd-10-cm.htm
  - HCPCS Level II (CMS): https://www.cms.gov/medicare/coding/medhcpcsgeninfo
  - CPT® (AMA license): https://www.ama-assn.org/amaone/cpt-current-procedural-terminology
