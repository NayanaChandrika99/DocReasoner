"""
Unified retrieval service that wraps PageIndex LLM Tree Search responses and
exposes a consistent result object for both CLI and API callers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from policy_ingest.pageindex_client import PageIndexClient, PageIndexError
from reasoning_service.config import settings
from reasoning_service.services.treestore_client import TreeStoreClient, TreeStoreNode
from reasoning_service.utils.error_codes import ReasonCode
from retrieval.fts5_fallback import FTS5Fallback

logger = logging.getLogger(__name__)


@dataclass
class RetrievalConfig:
    hybrid_threshold: float = settings.hybrid_tree_search_threshold
    node_span_token_threshold: int = settings.node_span_token_threshold


@dataclass
class NodeReference:
    node_id: str
    pages: List[int] = field(default_factory=list)
    title: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class Span:
    node_id: str
    page_index: Optional[int]
    text: str


@dataclass
class RetrievalResult:
    node_refs: List[NodeReference] = field(default_factory=list)
    spans: List[Span] = field(default_factory=list)
    search_trajectory: List[str] = field(default_factory=list)
    retrieval_method: str = "pageindex-llm"
    confidence: float = 0.0
    reason_code: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return not self.error and bool(self.node_refs)

    @property
    def relevant_contents(self) -> List[Span]:
        """Backwards-compatibility alias for existing controller code."""
        return self.spans

    @classmethod
    def empty(cls, reason_code: str, error: Optional[str] = None) -> "RetrievalResult":
        return cls(reason_code=reason_code, error=error, confidence=0.0)


class RetrievalService:
    """
    High-level retrieval orchestrator. At this milestone it only executes the
    PageIndex LLM Tree Search path; later milestones will add hybrid and bm25 fallback.
    """

    def __init__(
        self,
        client: PageIndexClient,
        config: Optional[RetrievalConfig] = None,
        fts5_fallback: Optional[FTS5Fallback] = None,
    ) -> None:
        self.client = client
        self.config = config or RetrievalConfig()
        self.fts5 = fts5_fallback or FTS5Fallback()

    def search(self, query: str, doc_id: Optional[str]) -> RetrievalResult:
        if not doc_id:
            return RetrievalResult.empty(reason_code="missing_doc_id", error="doc_id is required for retrieval")
        if not self.client.available:
            return RetrievalResult.empty(reason_code="pageindex_unavailable", error="PAGEINDEX_API_KEY is not configured")
        try:
            payload = self.client.llm_tree_search(doc_id=doc_id, query=query)
            result = self._parse_payload(payload, method="pageindex-llm")
            ambiguity = self._calculate_ambiguity(payload)
            if ambiguity > self.config.hybrid_threshold:
                hybrid_payload = self.client.hybrid_tree_search(doc_id=doc_id, query=query)
                result = self._parse_payload(hybrid_payload, method="pageindex-hybrid")
            if result.spans and self._should_use_bm25(result.spans):
                tightened = self._bm25_fallback(query, doc_id, result.node_refs)
                if tightened:
                    result.spans = tightened
                    result.retrieval_method = "bm25-fallback"
            logger.info(
                "retrieval_completed",
                extra={
                    "retrieval_method": result.retrieval_method,
                    "node_count": len(result.node_refs),
                    "span_count": len(result.spans),
                },
            )
            return result
        except PageIndexError as exc:
            return RetrievalResult.empty(reason_code="pageindex_error", error=str(exc))

    def _parse_payload(self, payload: Dict[str, Any], method: str) -> RetrievalResult:
        nodes = payload.get("nodes") or payload.get("results") or []
        node_refs: List[NodeReference] = []
        spans: List[Span] = []
        trajectory: List[str] = payload.get("search_trajectory", [])

        for node in nodes:
            node_id = node.get("node_id", "")
            page_index = node.get("page_index")
            title = node.get("title")
            summary = node.get("prefix_summary")
            pages: List[int] = []
            if isinstance(page_index, int):
                pages = [page_index]
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
            retrieval_method=method,
            confidence=confidence,
            reason_code=None if node_refs else "no_relevant_nodes",
        )

    def _calculate_ambiguity(self, payload: Dict[str, Any]) -> float:
        nodes = payload.get("nodes") or payload.get("results") or []
        scores = [node.get("score") for node in nodes if isinstance(node.get("score"), (int, float))]
        if len(scores) < 2:
            return 0.0
        max_score = max(scores)
        if max_score == 0:
            return 1.0
        normalized = [score / max_score for score in scores]
        mean = sum(normalized) / len(normalized)
        variance = sum((val - mean) ** 2 for val in normalized) / len(normalized)
        return variance

    def _should_use_bm25(self, spans: List[Span]) -> bool:
        total_tokens = sum(len(span.text.split()) for span in spans)
        return total_tokens > self.config.node_span_token_threshold

    def _bm25_fallback(self, query: str, doc_id: str, node_refs: List[NodeReference]) -> List[Span]:
        tightened: List[Span] = []
        for ref in node_refs:
            try:
                node_payload = self.client.get_node_content(doc_id=doc_id, node_id=ref.node_id)
            except PageIndexError:
                continue
            text = node_payload.get("text") or ""
            paragraphs = [para.strip() for para in text.split("\n\n") if para.strip()]
            if not paragraphs:
                continue
            indexed = [(idx, para) for idx, para in enumerate(paragraphs)]
            self.fts5.load_paragraphs(indexed)
            hits = self.fts5.top_spans(query)
            for idx, content, _score in hits:
                tightened.append(Span(node_id=ref.node_id, page_index=None, text=content))
        return tightened


class TreeStoreRetrievalService:
    """Retrieval adapter backed by TreeStore search APIs."""

    def __init__(self, client: TreeStoreClient) -> None:
        self.client = client

    def search(
        self,
        query: str,
        policy_id: str,
        version_id: Optional[str],
        top_k: int,
    ) -> RetrievalResult:
        resolved_version, nodes = self.client.search_nodes(
            policy_id=policy_id,
            query=query,
            version_id=version_id,
            top_k=top_k,
        )
        if not nodes:
            return RetrievalResult.empty(
                reason_code=ReasonCode.TREESTORE_NO_NODES,
                error=f"No TreeStore nodes found for {policy_id}",
            )

        node_refs: List[NodeReference] = []
        spans: List[Span] = []
        for node in nodes:
            node_refs.append(
                NodeReference(
                    node_id=node.node_id,
                    pages=node.pages,
                    title=node.title,
                    summary=node.summary,
                )
            )
            preview = self._preview_text(node)
            if preview:
                spans.append(Span(node_id=node.node_id, page_index=None, text=preview))

        trajectory = self._build_trajectory(nodes[0], policy_id, resolved_version)
        return RetrievalResult(
            node_refs=node_refs,
            spans=spans,
            search_trajectory=trajectory,
            retrieval_method="treestore",
            confidence=0.85,
            reason_code=None,
        )

    @staticmethod
    def _preview_text(node: TreeStoreNode) -> str:
        if node.summary:
            return node.summary
        if node.text:
            snippet = node.text.split("\n\n", 1)[0]
            return snippet[:400]
        return ""

    def _build_trajectory(
        self,
        node: TreeStoreNode,
        policy_id: str,
        version_id: Optional[str],
    ) -> List[str]:
        path: List[str] = []
        current: Optional[TreeStoreNode] = node
        while current:
            label = current.title or current.node_id
            path.append(label)
            if not current.parent_id:
                break
            current = self.client.get_node(policy_id, version_id, current.parent_id)
        return list(reversed(path))
