# Tools & Libraries (Demo Scope)

## PageIndex (core retrieval backbone)
- Converts PDFs to structure-preserving Markdown → builds **Tree** → runs **LLM Tree Search** (and documented hybrid variant) → returns **node_ids**, **page refs**, **relevant paragraphs**, **trajectory**.
- Why: Vectorless, reasoning-based retrieval for long, structured policies; **page-exact** citations and auditable **trajectories**.
- Docs: https://docs.pageindex.ai/

## ReAct Controller (reasoning + tool use)
- Interleaves **reasoning traces** with **actions** (tool calls) for faithful, inspectable workflows.
- Role here: Plan → retrieve with PageIndex → read spans → justify decisions with citations.
- Paper: https://arxiv.org/abs/2210.03629

## Local paragraph fallback: SQLite **FTS5** (bm25)
- Lightweight `bm25()` ranking inside a selected node to tighten spans when the node text exceeds a token threshold.
- Keeps fallback local and simple; no external indices or vector infra.
- Docs: https://www.sqlite.org/fts5.html

## Code systems (policy-referenced extraction)
- **ICD-10-CM** (CDC/NCHS) — diagnosis codes: https://www.cdc.gov/nchs/icd/icd-10-cm.htm
- **HCPCS Level II** (CMS) — supplies/other services; quarterly updates: https://www.cms.gov/medicare/coding/medhcpcsgeninfo
- **CPT®** (AMA) — procedure codes; **license required**: https://www.ama-assn.org/amaone/cpt-current-procedural-terminology

---

## Controller Tools (API shape and usage)

These tools are available to the ReAct controller. Inputs/outputs are returned via OpenAI function calling schemas.

1) pi.search(query)
- input: query: string; top_k?: int=3
- output: nodes[{node_id,title,pages,text_preview}], trajectory, confidence, retrieval_method
- use: first step to find relevant policy sections

2) facts.get(field_name)
- input: field_name: string
- output: value, confidence, doc_id, page, bbox
- use: retrieve patient facts from case bundle

3) spans.tighten(node_id, query)
- input: node_id: string, query: string
- output: ranked paragraphs within a node (FTS5 required; falls back if absent)
- use: when spans are long/noisy

4) policy_xref(criterion_id)
- input: criterion_id: string
- output: related_nodes[{node_id,title,path,reason}], citations[{page,section}]
- use: resolve ambiguous criteria; gather “see also” sections

5) temporal_lookup(policy_id, as_of_date)
- input: policy_id: string, as_of_date: YYYY-MM-DD
- output: version_id, effective_start, effective_end, diffs[]
- use: ensure the correct policy version for case date

6) code_validator(icd10?, cpt?)
- input: icd10?: string, cpt?: string
- output: valid: bool, normalized:{icd10,cpt}, suggested:string[]
- use: normalize and validate codes before inclusion/exclusion checks

7) contradiction_detector(findings)
- input: findings:[{criterion_id, evidence:[{node_id?, snippet?, stance}]}]
- output: conflicts:[{criterion_id, reason, conflicting_evidence:{support[],oppose[]}}], resolved:false
- use: when signals disagree; triggers re-reads

8) pubmed_search(condition, treatment)
- input: condition: string, treatment: string
- output: studies[{pmid,title,year,conclusion,strength}], summary
- use: only for borderline cases or when policy instructs; gated by config

9) confidence_score(criteria_results)
- input: criteria_results:[{id,status,confidence?}]
- output: score: float (0–1), per_criterion:[{id,score,drivers[]}]
- use: compute final confidence before finish()

10) finish(status, rationale, confidence, citations…)
- input: status: met/missing/uncertain, rationale: string, confidence: float, policy_section, policy_pages[], evidence_doc_id?, evidence_page?
- output: final decision
- use: always end with finish()
