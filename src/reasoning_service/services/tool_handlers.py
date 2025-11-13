"""Tool execution handlers for ReAct controller."""

from __future__ import annotations

import json
from typing import Dict, Any, Optional, List, Tuple
import re

from reasoning_service.models.schema import CaseBundle
from reasoning_service.observability.react_metrics import record_tool_call


class ToolExecutor:
    """Executes tools called by the LLM."""

    def __init__(
        self,
        retrieval_service: Any,
        case_bundle: CaseBundle,
        fts5_service: Optional[Any] = None,
    ):
        """Initialize tool executor.

        Args:
            retrieval_service: RetrievalService instance for policy search
            case_bundle: CaseBundle with VLM-extracted fields
            fts5_service: Optional FTS5Fallback service for span tightening
        """
        self.retrieval_service = retrieval_service
        self.case_bundle = case_bundle
        self.fts5_service = fts5_service
        self._retrieval_cache: Dict[str, Any] = {}

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """Execute a tool and return JSON-formatted result.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments as dictionary

        Returns:
            JSON string with tool result
        """
        if tool_name == "pi_search":
            result = await self._pi_search(
                query=arguments["query"],
                top_k=arguments.get("top_k", 3),
            )
        elif tool_name == "facts_get":
            result = self._facts_get(
                field_name=arguments["field_name"],
            )
        elif tool_name == "spans_tighten":
            result = await self._spans_tighten(
                node_id=arguments["node_id"],
                query=arguments["query"],
            )
        elif tool_name == "policy_xref":
            result = self._policy_xref(
                criterion_id=arguments["criterion_id"],
            )
        elif tool_name == "temporal_lookup":
            result = self._temporal_lookup(
                policy_id=arguments["policy_id"],
                as_of_date=arguments["as_of_date"],
            )
        elif tool_name == "confidence_score":
            result = self._confidence_score(
                criteria_results=arguments["criteria_results"],
            )
        elif tool_name == "contradiction_detector":
            result = self._contradiction_detector(
                findings=arguments["findings"],
            )
        elif tool_name == "pubmed_search":
            result = self._pubmed_search(
                condition=arguments["condition"],
                treatment=arguments["treatment"],
            )
        elif tool_name == "code_validator":
            result = self._code_validator(
                icd10=arguments.get("icd10"),
                cpt=arguments.get("cpt"),
            )
        elif tool_name == "finish":
            # This shouldn't be executed - it signals completion
            result = {"success": True, "status": "completed", "decision": arguments}
        else:
            result = {"success": False, "error": f"Unknown tool: {tool_name}"}

        record_tool_call(tool_name, bool(result.get("success")))
        return json.dumps(result)

    async def _pi_search(self, query: str, top_k: int) -> Dict[str, Any]:
        """Execute PageIndex search.

        Args:
            query: Search query
            top_k: Number of nodes to retrieve

        Returns:
            Dictionary with search results
        """
        try:
            # Get policy document ID from case bundle metadata or use default
            policy_doc_id = self.case_bundle.metadata.get("policy_document_id")
            if not policy_doc_id:
                return {
                    "success": False,
                    "error": "policy_document_id not found in case bundle metadata",
                    "message": "Cannot search policy without document ID.",
                }

            retrieval_result = await self.retrieval_service.retrieve(
                document_id=policy_doc_id,
                query=query,
                top_k=top_k,
            )

            # Cache node references for potential spans_tighten calls
            for node in retrieval_result.node_refs:
                self._retrieval_cache[node.node_id] = {
                    "node_id": node.node_id,
                    "title": node.title,
                    "pages": node.pages,
                    "summary": node.summary,
                }

            # Extract span text for preview
            span_texts = [span.text for span in retrieval_result.spans]

            return {
                "success": True,
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "title": node.title or "Untitled",
                        "pages": node.pages,
                        "text_preview": (
                            (span_texts[0][:200] + "...") if span_texts and len(span_texts[0]) > 200
                            else (span_texts[0] if span_texts else "")
                        ),
                    }
                    for node in retrieval_result.node_refs
                ],
                "trajectory": retrieval_result.search_trajectory,
                "confidence": retrieval_result.confidence,
                "retrieval_method": retrieval_result.retrieval_method,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "PageIndex search failed. Consider using uncertain status.",
            }

    def _facts_get(self, field_name: str) -> Dict[str, Any]:
        """Get case field value.

        Args:
            field_name: Name of the field to retrieve

        Returns:
            Dictionary with field value and metadata
        """
        # Normalize field name (handle variations)
        normalized_name = field_name.lower().replace(" ", "_").replace("-", "_")

        for field in self.case_bundle.fields:
            field_normalized = field.field_name.lower().replace(" ", "_").replace("-", "_")
            if field_normalized == normalized_name:
                return {
                    "success": True,
                    "field_name": field.field_name,
                    "value": field.value,
                    "confidence": field.confidence,
                    "doc_id": field.doc_id,
                    "page": field.page,
                    "bbox": field.bbox,
                }

        # Return available fields for debugging
        available_fields = [f.field_name for f in self.case_bundle.fields]
        return {
            "success": False,
            "message": f"Field '{field_name}' not found in case bundle.",
            "available_fields": available_fields,
        }

    async def _spans_tighten(self, node_id: str, query: str) -> Dict[str, Any]:
        """Use BM25 to narrow spans within a node.

        Args:
            node_id: Node ID from pi_search result
            query: Query to rank paragraphs

        Returns:
            Dictionary with ranked spans
        """
        if not self.fts5_service:
            return {
                "success": False,
                "message": "FTS5 service not configured",
            }

        # Get node from cache
        node_info = self._retrieval_cache.get(node_id)
        if not node_info:
            return {
                "success": False,
                "message": f"Node {node_id} not found. Call pi_search first.",
            }

        # For now, return error since we need to integrate with FTS5 service properly
        # This will be enhanced when FTS5 integration is complete
        return {
            "success": False,
            "message": "spans_tighten requires FTS5 integration. Use pi_search results directly.",
            "node_id": node_id,
        }

    def _policy_xref(self, criterion_id: str) -> Dict[str, Any]:
        """Cross-reference related policy sections for a given criterion.

        Uses cached retrieval nodes as a lightweight heuristic to surface possible
        related sections. This is a minimal end-to-end implementation that can be
        upgraded to database-backed lookups.
        """
        related_nodes: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []

        # Heuristic: match words from criterion_id to cached node titles
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", criterion_id.lower()) if t]
        for node in self._retrieval_cache.values():
            title_l = (node.get("title") or "").lower()
            if any(t in title_l for t in tokens):
                related_nodes.append(
                    {
                        "node_id": node["node_id"],
                        "title": node.get("title") or "Untitled",
                        "path": node.get("title") or "",  # path unavailable in cache
                        "reason": "title_match",
                    }
                )
                for p in (node.get("pages") or []):
                    citations.append({"page": p, "section": node.get("title") or ""})

        return {
            "success": True,
            "criterion_id": criterion_id,
            "related_nodes": related_nodes,
            "citations": citations,
        }

    def _temporal_lookup(self, policy_id: str, as_of_date: str) -> Dict[str, Any]:
        """Resolve policy version as of a date.

        Minimal implementation: returns metadata from case bundle when present;
        otherwise returns a placeholder version without diffs.
        """
        meta = self.case_bundle.metadata or {}
        version_id = meta.get("policy_version_id") or meta.get("version_id") or "unknown"
        effective_start = meta.get("effective_start")
        effective_end = meta.get("effective_end")
        diffs: List[Dict[str, Any]] = []

        return {
            "success": True,
            "policy_id": policy_id,
            "as_of_date": as_of_date,
            "version_id": version_id,
            "effective_start": effective_start,
            "effective_end": effective_end,
            "diffs": diffs,
        }

    def _confidence_score(self, criteria_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate confidence across criteria.

        If per-criterion confidence provided, use it; otherwise map status:
        met=0.85, missing=0.15, uncertain=0.5.
        """
        def map_conf(res: Dict[str, Any]) -> float:
            if isinstance(res.get("confidence"), (int, float)):
                c = float(res["confidence"])
                return max(0.0, min(1.0, c))
            status = (res.get("status") or "").lower()
            if status == "met":
                return 0.85
            if status == "missing":
                return 0.15
            return 0.5

        per_criterion: List[Dict[str, Any]] = []
        scores: List[float] = []
        for res in criteria_results:
            cid = res.get("id") or "unknown"
            sc = map_conf(res)
            scores.append(sc)
            drivers: List[str] = []
            if res.get("status"):
                drivers.append(f"status:{res['status']}")
            if "confidence" in res:
                drivers.append("provided_confidence")
            per_criterion.append({"id": cid, "score": sc, "drivers": drivers})

        overall = sum(scores) / len(scores) if scores else 0.0
        return {"success": True, "score": overall, "per_criterion": per_criterion}

    def _contradiction_detector(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect conflicting evidence for each criterion."""
        conflicts: List[Dict[str, Any]] = []
        for f in findings:
            cid = f.get("criterion_id") or "unknown"
            ev = f.get("evidence") or []
            support = [e for e in ev if (e.get("stance") or "").lower() == "support"]
            oppose = [e for e in ev if (e.get("stance") or "").lower() == "oppose"]
            if support and oppose:
                conflicts.append(
                    {
                        "criterion_id": cid,
                        "reason": "support_and_oppose_present",
                        "conflicting_evidence": {
                            "support": support[:5],
                            "oppose": oppose[:5],
                        },
                    }
                )
        return {"success": True, "conflicts": conflicts, "resolved": False}

    def _pubmed_search(self, condition: str, treatment: str) -> Dict[str, Any]:
        """Search PubMed (placeholder, offline-friendly).

        Returns empty study list with a summary indicating offline mode.
        """
        return {
            "success": True,
            "condition": condition,
            "treatment": treatment,
            "studies": [],
            "summary": "PubMed search not connected; returning no studies in offline mode.",
        }

    def _code_validator(self, icd10: Optional[str], cpt: Optional[str]) -> Dict[str, Any]:
        """Validate and normalize ICD-10 and CPT codes with simple patterns."""
        def validate_icd(code: Optional[str]) -> Tuple[bool, Optional[str], List[str]]:
            if code is None:
                return False, None, []
            raw = code.strip().upper()
            # Exclude 'U' per ICD-10-CM reserved blocks; allow A-TV-Z
            pattern = re.compile(r"^[A-TV-Z][0-9]{2}(?:\.[A-Z0-9]{1,4})?$")
            valid = bool(pattern.match(raw))
            suggestions: List[str] = []
            if not valid:
                # Try inserting a dot after 3 chars if missing
                if len(raw) >= 4 and "." not in raw:
                    candidate = raw[:3] + "." + raw[3:]
                    if pattern.match(candidate):
                        suggestions.append(candidate)
            return valid, raw, suggestions

        def validate_cpt(code: Optional[str]) -> Tuple[bool, Optional[str], List[str]]:
            if code is None:
                return False, None, []
            raw = code.strip()
            pattern = re.compile(r"^[0-9]{5}$")
            valid = bool(pattern.match(raw))
            suggestions: List[str] = []
            # No robust suggestion logic here; keep minimal
            return valid, raw, suggestions

        icd_valid, icd_norm, icd_suggestions = validate_icd(icd10)
        cpt_valid, cpt_norm, cpt_suggestions = validate_cpt(cpt)

        return {
            "success": True,
            "valid": bool(icd_valid or cpt_valid),
            "normalized": {"icd10": icd_norm, "cpt": cpt_norm},
            "suggested": list(set(icd_suggestions + cpt_suggestions)),
        }
