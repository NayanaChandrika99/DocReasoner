# PageIndex Documentation Snapshot (offline)

Local digest of the PageIndex Quickstart + README so we can integrate without live docs. For authoritative instructions, see https://docs.pageindex.ai/quickstart and https://github.com/vectifyai/pageindex.

## 1. Concepts

- PageIndex builds a hierarchical tree index (titles, `node_id`, `page_start`, `page_end`, optional summaries, child nodes) instead of chunk/embedding vectors.
- Retrieval runs an LLM-driven tree search that returns node candidates, a search trajectory, page references, and often `relevant_paragraphs` for direct use.
- Hybrid Tree Search augments the LLM with a learned value function; use it when LLM search shows high ambiguity.
- Nodes provide paragraph spans; if spans are too broad, fall back to local bm25/rerankers for span tightening.

## 2. Hosted API Quickstart (docs.pageindex.ai/quickstart)

1. **Get API credentials** via the PageIndex dashboard. Store `PAGEINDEX_API_KEY` and (if applicable) a custom `PAGEINDEX_BASE_URL` in `.env`.

2. **Upload PDF** using the API:
   ```bash
   # Submit PDF for processing
   curl -X POST "$PAGEINDEX_BASE_URL/api/doc/" \
     -H "Authorization: Bearer $PAGEINDEX_API_KEY" \
     -F file=@"data/Dockerfile.pdf"
   ```
   Response: `{"doc_id": "abc123def456"}`

3. **Check processing status & get tree**:
   ```bash
   curl -H "Authorization: Bearer $PAGEINDEX_API_KEY" \
     "$PAGEINDEX_BASE_URL/api/doc/{doc_id}/?type=tree&format=page&summary=true"
   ```
   Response: Tree structure with nodes containing `title`, `node_id`, `page_index`, `text`, `prefix_summary`, and child `nodes`.

4. **Run LLM Tree Search** for retrieval:
   ```bash
   # Submit retrieval query
   curl -X POST "$PAGEINDEX_BASE_URL/api/retrieval/" \
     -H "Authorization: Bearer $PAGEINDEX_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"doc_id":"abc123def456","query":"eligibility criteria","thinking":true}'
   ```
   Response: `{"retrieval_id": "xyz789ghi012"}`

5. **Get retrieval results**:
   ```bash
   curl -H "Authorization: Bearer $PAGEINDEX_API_KEY" \
     "$PAGEINDEX_BASE_URL/api/retrieval/{retrieval_id}/"
   ```
   Response: Retrieved nodes with:
   - `title`: Section title
   - `node_id`: Unique identifier
   - `relevant_contents`: Array of `{page_index, relevant_content}` with text snippets
   - `nodes`: Child nodes with additional context

> All hosted calls should be wrapped with timeouts/retries (see plan) and degrade to `status:"uncertain"` when the API is unavailable.

## 3. Self-Hosted CLI (open-source repo)

From https://github.com/vectifyai/pageindex:

1. Install deps
   ```bash
   pip3 install --upgrade -r requirements.txt
   ```
2. Set OpenAI key in `.env`
   ```bash
   CHATGPT_API_KEY=your_openai_key_here
   ```
3. Run the processor against a PDF or Markdown
   ```bash
   python3 run_pageindex.py --pdf_path /path/to/document.pdf
   # or
   python3 run_pageindex.py --md_path /path/to/document.md
   ```
4. Optional flags (excerpt):
   - `--model gpt-4o-2024-11-20` (default)
   - `--toc-check-pages 20`
   - `--max-pages-per-node 10`
   - `--max-tokens-per-node 20000`
   - `--if-add-node-summary yes|no`

Self-hosting gives you the same tree JSON that the hosted API would provide, but without OCR/page-image enhancements.

## 4. Response Shape (tree + search)

**Tree nodes** (from GET `/api/doc/{doc_id}/?type=tree`):

```json
{
  "title": "Section Title",
  "node_id": "0006",
  "page_index": 21,
  "text": "Full section text content...",
  "prefix_summary": "Contextual summary of this section",
  "nodes": [
    {
      "title": "Subsection Title",
      "node_id": "0007",
      "page_index": 22,
      "text": "...",
      "nodes": [...]
    }
  ]
}
```

**Search responses** (from GET `/api/retrieval/{retrieval_id}/`):

```json
{
  "title": "Relevant Section",
  "node_id": "0004",
  "relevant_contents": [
    {
      "page_index": 10,
      "relevant_content": "Eligible patients must meet criteria X, Y, Z..."
    },
    {
      "page_index": 11,
      "relevant_content": "Additional requirements include..."
    }
  ],
  "nodes": [
    {
      "title": "Subsection",
      "node_id": "0005",
      "relevant_contents": [
        {
          "page_index": 12,
          "relevant_content": "More specific details..."
        }
      ]
    }
  ]
}
```

**Key fields**:
- `node_id`: Unique identifier for each node
- `page_index`: Page number from original document
- `relevant_contents`: Array with `page_index` and `relevant_content` (text snippets)
- `nodes`: Hierarchical child nodes structure
- `text`: Full content of the node (when `format=page`)
- `prefix_summary`: Section summary (when `summary=true`)

## 5. Integration Notes

- Configure env vars: `PAGEINDEX_API_KEY`, `PAGEINDEX_BASE_URL`, and storage pointers for cached trees/markdown.
- Persist `{policy_version_used, tree_json_ptr, search_trajectory, retrieval_method, reasoning_trace}` for audit.
- Default flow: LLM Tree Search → use PageIndex spans; escalate to Hybrid search or local FTS5 only if spans exceed token budget or retrieval ambiguity crosses threshold.
- The CLI command `uv run python -m src.cli ingest-policy --policy-id <id> --version-id <version>` now uploads the PDF, caches `data/pageindex_tree.json`, and writes the PageIndex doc id plus every tree node into Postgres (`policy_versions` and `policy_nodes`). Run `uv run alembic upgrade head` once before the first ingest, and use `uv run python -m src.cli show-policy --policy-id <id> --version-id <version>` to verify the snapshot.

## 5. Complete API Endpoints Reference

**Base URL:** `https://api.pageindex.ai`
**Authentication:** All endpoints require `Authorization: Bearer {api_key}` header

### PDF Processing
- `POST /api/doc/` - Upload PDF for processing
  - Body: `multipart/form-data` with `file` (PDF binary)
  - Response: `{"doc_id": "string"}`

- `GET /api/doc/{doc_id}/` - Get processing status & results
  - Query params:
    - `type`: "tree" or "ocr"
    - `format`: "page" (default), "node", or "raw" (for OCR)
    - `summary`: true/false (include node summaries for tree)
  - Response: Processing status and tree/markdown results

- `DELETE /api/doc/{doc_id}/` - Delete document

### Retrieval
- `POST /api/retrieval/` - Submit retrieval query
  - Body: `{"doc_id": "string", "query": "string", "thinking": boolean}`
  - Response: `{"retrieval_id": "string"}`

- `GET /api/retrieval/{retrieval_id}/` - Get retrieval results
  - Response: Retrieved nodes with `relevant_contents`, `node_id`, `title`, and child `nodes`

### Markdown Processing
- `POST /api/markdown/` - Convert markdown to tree structure
  - Body: `multipart/form-data` with `file` (markdown file)
  - Optional params: `if_add_node_id`, `if_add_node_summary`, `if_add_node_text`, `if_add_doc_description`
  - Response: `{"success": true, "doc_name": "string", "structure": [...]}`

## 6. References

- Quickstart/API: https://docs.pageindex.ai/quickstart
- Tree Search tutorial: https://docs.pageindex.ai/tree-search/basic
- Open-source repo + CLI: https://github.com/vectifyai/pageindex
