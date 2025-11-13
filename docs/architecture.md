# Reasoning Layer — Single-Policy Demo Architecture

This system answers: “Is this referral **ready to file** according to the current policy?” It uses **PageIndex** for vectorless, reasoning-based retrieval over long PDFs, a lightweight **ReAct** controller for tool use + explanation, and an optional **SQLite FTS5 (bm25)** paragraph-narrowing step inside a selected node.

## High-level flow

```
                 ┌──────────────────────────────────────────────┐
                 │                Policy PDF                    │
                 └───────────────┬──────────────────────────────┘
                                 │  (Upload)
                                 ▼
                        PageIndex OCR → Markdown
                                 │
                                 ▼
                       PageIndex Tree Generation
                                 │
                                 ▼
                 Stored Tree JSON (sections + page ranges)
                                 │
     ┌───────────────────────────┼─────────────────────────────┐
     │                           │                             │
     │ (Query-time)              │                             │
     ▼                           ▼                             ▼
 Case Bundle              ReAct Controller              Audit Store
 (facts with               (tool-using LLM)              (trees, runs,
 doc/page/bbox)                    │                     trajectories)
     │                            │
     │  "Find where policy talks  │
     │   about this criterion"    │
     │                            ▼
     │                   PageIndex LLM Tree Search
     │                      → node_ids + trajectory + page refs
     │                            │
     │                            ▼
     │                   Relevant paragraphs (PageIndex)
     │                            │
     │          [If node text > threshold → FTS5 bm25 fallback]
     │                            │
     └────────────────────────────┴───────────────► Compare policy spans
                                                  vs case facts → Decision
```

## Components & responsibilities

```
[policy_ingest]
  - Calls PageIndex endpoints to process the PDF
  - Persists tree + metadata; versions policy (policy_id, version_id)

[retrieval]
  - Runs PageIndex LLM Tree Search for each question
  - Captures node_ids, page_refs, relevant_paragraphs, trajectory
  - Optional: FTS5 bm25 narrowing when token_count > threshold

[controller]
  - ReAct loop using tools: {pi.search, facts.get, spans.tighten}
  - Produces strict JSON decision + citation + confidence

[data]
  - Stores PageIndex artifacts, case bundles (pointerized PHI),
    outputs, telemetry
```

## Key decisions

- **Vectorless first:** PageIndex tree search is the primary retriever; no vector DB.
- **Inside-node fallback:** SQLite FTS5 bm25 only when a selected node exceeds a token threshold (default 800).
- **Abstention rule:** If final confidence < 0.65 → `UNCERTAIN`.
