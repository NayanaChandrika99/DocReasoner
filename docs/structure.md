# Data Contracts — Inputs & Outputs (Demo)

Below are **schema-level** structures (types & fields). Values shown indicate **shape only**.

---

## A) Policy ingestion → PageIndex

### A.1 Submit PDF
**POST** PageIndex — Submit Document for Processing

**Request**
```json
{
  "source_url": "string|null",
  "filename": "string",
  "bytes_b64": "base64-string"
}
```

**Response**
```json
{ "doc_id": "string" }
```

### A.2 Get processing results (tree & markdown)
**GET** PageIndex — Get Processing Status & Results

**Response**
```json
{
  "doc_id": "string",
  "status": "processing|done|error",
  "markdown_ptr": "uri",
  "tree_json": {
    "nodes": [
      {
        "node_id": "string",
        "parent_id": "string|null",
        "section_path": "string",
        "title": "string",
        "page_start": 0,
        "page_end": 0,
        "summary": "string|null"
      }
    ]
  }
}
```

---

## B) Query-time retrieval

### B.1 LLM Tree Search
**POST** PageIndex — Retrieval

**Request**
```json
{
  "doc_id": "string",
  "query": "string",
  "options": {
    "max_nodes": 3,
    "return_paragraphs": true
  }
}
```

**Response**
```json
{
  "doc_id": "string",
  "selected_node_ids": ["string"],
  "search_trajectory": ["node_id", "node_id", "node_id"],
  "page_refs": [{ "node_id": "string", "pages": [0] }],
  "relevant_paragraphs": [
    { "node_id": "string", "paragraph_id": "string", "text": "string" }
  ],
  "runtime_ms": 0
}
```

### B.2 Optional inside-node fallback (FTS5 bm25)
_Local module only; no remote API_

**Input**
```json
{
  "node_texts": ["string"],
  "query": "string",
  "threshold_tokens": 800
}
```

**Output**
```json
{
  "top_spans": [
    { "span_id": "string", "start": 0, "end": 0, "score": 0.0 }
  ]
}
```

---

## C) Case bundle (pointerized PHI)

**Input to controller**
```json
{
  "case_id": "string",
  "patient_key": "string",
  "facts": [
    {
      "field": "string",
      "value": "string|number",
      "confidence": 0.0,
      "doc_id": "string",
      "page": 0,
      "bbox": [0, 0, 0, 0],
      "class": "string"
    }
  ],
  "attachments": [
    { "doc_id": "string", "type": "string", "pages": 0 }
  ]
}
```

---

## D) Decision output (strict)

**Response from controller**
```json
{
  "case_id": "string",
  "criterion_id": "string",
  "status": "ready|not_ready|uncertain",
  "citation": {
    "policy_id": "string",
    "version": "string",
    "section_path": "string",
    "pages": [0]
  },
  "codes": {
    "icd10_cm": ["string"],
    "hcpcs": ["string"],
    "cpt": ["string"]
  },
  "rationale": "string",
  "confidence": {
    "c_tree": 0.0,
    "c_span": 0.0,
    "c_final": 0.0,
    "c_joint": 0.0
  },
  "search_trajectory": ["node_id", "node_id"],
  "retrieval_method": "pageindex-llm|bm25-fallback"
}
```

---

## E) Storage records (minimal)

### E.1 `policy_versions`
```
policy_id: string
version_id: string
effective_date: date
revision_date: date|null
source_url: string
pdf_sha256: string
markdown_ptr: uri
tree_json_ptr: uri
```

### E.2 `policy_nodes`
```
(policy_id, version_id, node_id, parent_id,
 section_path, title, page_start, page_end, summary)
```

### E.3 `reasoning_outputs`
```
(case_id, criterion_id, policy_id, version_id,
 status, rationale, citation_section_path, citation_pages,
 c_tree, c_span, c_final, c_joint, search_trajectory,
 retrieval_method, created_at)
```
