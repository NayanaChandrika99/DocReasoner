"""
Offline PageIndex tree search that scans the cached JSON when API access is
unavailable. Shares dataclasses with the unified RetrievalService.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from policy_ingest.pageindex_client import PageIndexClient, PageIndexError

from .service import NodeReference, RetrievalResult, Span


class TreeSearchService:
    def __init__(
        self,
        client: Optional[PageIndexClient] = None,
        tree_cache_path: Optional[Path] = None,
        fallback_method: str = "offline-tree-scan",
    ) -> None:
        self.client = client
        self.tree_cache_path = tree_cache_path or Path("data/pageindex_tree.json")
        self.fallback_method = fallback_method

    def search(self, query: str, doc_id: Optional[str] = None) -> RetrievalResult:
        if self.client and self.client.available and doc_id:
            try:
                retrieval_id = self.client.submit_retrieval(doc_id=doc_id, query=query)
                payload = self.client.poll_retrieval(retrieval_id)
                return self._parse_remote_payload(payload)
            except PageIndexError as exc:
                return RetrievalResult.empty(reason_code="pageindex_error", error=str(exc))
        return self._offline_search(query)

    def _parse_remote_payload(self, payload: Dict[str, Any]) -> RetrievalResult:
        nodes = payload.get("nodes") or payload.get("results") or []
        node_refs: List[NodeReference] = []
        spans: List[Span] = []
        trajectory: List[str] = payload.get("search_trajectory", [])

        for node in nodes:
            node_id = node.get("node_id", "")
            page_index = node.get("page_index")
            title = node.get("title")
            summary = node.get("prefix_summary")
            pages = [page_index] if isinstance(page_index, int) else []
            node_refs.append(NodeReference(node_id=node_id, pages=pages, title=title, summary=summary))
            for content in node.get("relevant_contents", []):
                spans.append(
                    Span(
                        node_id=node_id,
                        page_index=content.get("page_index"),
                        text=content.get("relevant_content", ""),
                    )
                )

        confidence = 0.9 if node_refs else 0.0
        return RetrievalResult(
            node_refs=node_refs,
            spans=spans,
            search_trajectory=trajectory,
            retrieval_method="pageindex-llm",
            confidence=confidence,
            reason_code=None if node_refs else "no_relevant_nodes",
        )

    def _offline_search(self, query: str) -> RetrievalResult:
        if not self.tree_cache_path.exists():
            return RetrievalResult.empty(
                reason_code="no_tree_cache",
                error=f"tree cache not found at {self.tree_cache_path}",
            )
        tree_data = json.loads(self.tree_cache_path.read_text())
        nodes = tree_data.get("result") or tree_data.get("nodes") or tree_data.get("tree") or []
        matched_refs: List[NodeReference] = []
        matched_spans: List[Span] = []
        trajectory: List[str] = []
        lowered_query = query.lower()

        def walk(node: Dict[str, Any], path: List[str]) -> None:
            node_id = node.get("node_id", "")
            content = " ".join(
                filter(
                    None,
                    [
                        node.get("text", ""),
                        node.get("prefix_summary", ""),
                        node.get("title", ""),
                    ],
                )
            )
            combined = content.lower()
            if lowered_query in combined:
                pages = []
                if isinstance(node.get("page_index"), int):
                    pages = [node["page_index"]]
                elif isinstance(node.get("page_start"), int):
                    pages = list(range(node["page_start"], node.get("page_end", node["page_start"]) + 1))
                matched_refs.append(
                    NodeReference(
                        node_id=node_id,
                        pages=pages,
                        title=node.get("title"),
                        summary=node.get("prefix_summary"),
                    )
                )
                matched_spans.append(
                    Span(node_id=node_id, page_index=pages[0] if pages else None, text=node.get("text", ""))
                )
                if not trajectory:
                    trajectory.extend(path + [node_id])
            for child in node.get("nodes", []):
                walk(child, path + [node_id])

        for top_node in nodes:
            walk(top_node, [])

        confidence = 0.6 if matched_refs else 0.0
        method = "pageindex-offline" if matched_refs else self.fallback_method
        reason_code = None if matched_refs else "no_matches_offline"
        return RetrievalResult(
            node_refs=matched_refs,
            spans=matched_spans,
            search_trajectory=trajectory,
            retrieval_method=method,
            confidence=confidence,
            reason_code=reason_code,
            error=None if matched_refs else "query not found in cached tree",
        )
