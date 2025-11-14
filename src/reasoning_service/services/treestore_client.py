# ABOUTME: Provides the TreeStoreClient abstraction for policy version lookups.
# ABOUTME: Enables TreeStore-backed tools such as temporal lookup and policy xref.
"""TreeStore client abstractions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re
from typing import Dict, List, Optional, Tuple


@dataclass
class TreeStoreNode:
    node_id: str
    title: Optional[str] = None
    section_path: Optional[str] = None
    pages: List[int] = field(default_factory=list)
    summary: Optional[str] = None
    parent_id: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    see_also: List[str] = field(default_factory=list)
    text: Optional[str] = None


@dataclass
class TreeStoreVersion:
    policy_id: str
    version_id: str
    effective_start: Optional[str]
    effective_end: Optional[str]
    pageindex_doc_id: Optional[str]
    previous_version_id: Optional[str] = None
    node_ids: Optional[List[str]] = None


class TreeStoreClientError(RuntimeError):
    """Raised when TreeStore calls fail."""


class TreeStoreClient:
    def __init__(
        self,
        version_catalog: Optional[Dict[str, List[TreeStoreVersion]]] = None,
        node_store: Optional[Dict[Tuple[str, str], Dict[str, TreeStoreNode]]] = None,
        cross_reference_index: Optional[Dict[Tuple[str, str], List[TreeStoreNode]]] = None,
    ) -> None:
        self._version_catalog = version_catalog or {}
        self._node_store = node_store or {}
        self._xref_index = cross_reference_index or {}

    def get_version_as_of(self, policy_id: str, as_of_date: str) -> TreeStoreVersion:
        """Return the version that was active on the given date."""
        catalog = self._version_catalog.get(policy_id)
        if not catalog:
            raise TreeStoreClientError(f"No version catalog found for {policy_id}")

        target = _parse_date(as_of_date)
        if target is None:
            raise TreeStoreClientError(f"Invalid as_of_date: {as_of_date}")

        # Sort by effective_start descending to find latest matching version.
        sorted_versions = sorted(
            catalog,
            key=lambda v: _parse_date(v.effective_start) or date.min,
            reverse=True,
        )

        for version in sorted_versions:
            start = _parse_date(version.effective_start) or date.min
            end = _parse_date(version.effective_end) or date.max
            if start <= target <= end:
                return version

        raise TreeStoreClientError(
            f"No version active for {policy_id} on {as_of_date}"
        )

    def get_nodes(self, policy_id: str, version_id: str, node_ids: List[str]) -> Dict[str, TreeStoreNode]:
        """Return nodes by id for a specific policy/version pair."""
        store = self._node_store.get((policy_id, version_id))
        if store is None:
            raise TreeStoreClientError(
                f"No nodes found for policy {policy_id} version {version_id}"
            )

        if not node_ids:
            return store

        return {node_id: store[node_id] for node_id in node_ids if node_id in store}

    def find_related_nodes(
        self,
        policy_id: str,
        version_id: Optional[str],
        criterion_id: str,
        tokens: List[str],
        limit: int = 5,
    ) -> List[Tuple[TreeStoreNode, str]]:
        """Return related nodes with reasons."""
        hits: List[Tuple[TreeStoreNode, str]] = []
        seen: set[str] = set()
        key = (policy_id, criterion_id)

        # 1) Curated cross references.
        curated = self._xref_index.get(key, [])
        for node in curated:
            if node.node_id in seen:
                continue
            hits.append((node, "xref"))
            seen.add(node.node_id)
            if len(hits) >= limit:
                return hits

        nodes = self._node_store.get((policy_id, version_id or ""), {})
        if not nodes:
            # If explicit version missing, fall back to first available version.
            for (p_id, _v_id), value in self._node_store.items():
                if p_id == policy_id:
                    nodes = value
                    break

        if not nodes:
            return hits

        tokens_lower = [t.lower() for t in tokens if t]
        if not tokens_lower:
            tokens_lower = []

        # 2) Keyword search within titles/summaries.
        keyword_hits: List[Tuple[int, TreeStoreNode]] = []
        for node in nodes.values():
            haystack = " ".join(
                filter(
                    None,
                    [
                        node.title or "",
                        node.summary or "",
                        " ".join(node.keywords),
                    ],
                )
            ).lower()
            score = sum(1 for tok in tokens_lower if tok in haystack)
            if score > 0:
                keyword_hits.append((score, node))

        keyword_hits.sort(key=lambda item: (-item[0], item[1].node_id))
        keyword_nodes = [node for _score, node in keyword_hits]
        for _score, node in keyword_hits:
            if node.node_id in seen:
                continue
            hits.append((node, "keyword"))
            seen.add(node.node_id)
            if len(hits) >= limit:
                return hits

        # 3) Siblings via parent relationship.
        sibling_parents = {node.parent_id for node in keyword_nodes if node.parent_id}
        if sibling_parents:
            for node in nodes.values():
                if node.node_id in seen:
                    continue
                if node.parent_id and node.parent_id in sibling_parents:
                    hits.append((node, "sibling"))
                    seen.add(node.node_id)
                    if len(hits) >= limit:
                        return hits

        # 4) See-also references.
        for node in nodes.values():
            for target_id in node.see_also:
                target = nodes.get(target_id)
                if not target or target.node_id in seen:
                    continue
                hits.append((target, "see_also"))
                seen.add(target.node_id)
                if len(hits) >= limit:
                    return hits

        # If still empty, return at most two anchors to give operator context.
        if not hits:
            for node in list(nodes.values())[: limit]:
                if node.node_id in seen:
                    continue
                hits.append((node, "context"))
                seen.add(node.node_id)
                if len(hits) >= limit:
                    return hits

        return hits

    def latest_version(self, policy_id: str) -> Optional[TreeStoreVersion]:
        """Return the latest known version for a policy."""
        catalog = self._version_catalog.get(policy_id)
        if catalog:
            return catalog[-1]
        for (pid, _vid), _ in self._node_store.items():
            if pid == policy_id:
                return TreeStoreVersion(
                    policy_id=pid,
                    version_id=_vid,
                    effective_start=None,
                    effective_end=None,
                    pageindex_doc_id=None,
                )
        return None

    def get_node(
        self,
        policy_id: str,
        version_id: Optional[str],
        node_id: str,
    ) -> Optional[TreeStoreNode]:
        version_id, store = self._resolve_node_store(policy_id, version_id)
        if not store:
            return None
        return store.get(node_id)

    def search_nodes(
        self,
        policy_id: str,
        query: str,
        version_id: Optional[str],
        top_k: int = 3,
    ) -> Tuple[Optional[str], List[TreeStoreNode]]:
        """Search nodes by keyword relevance."""
        version_id, store = self._resolve_node_store(policy_id, version_id)
        if not store or not query:
            return version_id, []

        tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", query.lower()) if tok]
        if not tokens:
            return version_id, list(store.values())[:top_k]

        ranked: List[Tuple[float, TreeStoreNode]] = []
        for node in store.values():
            haystack = " ".join(
                filter(
                    None,
                    [
                        node.title or "",
                        node.summary or "",
                        node.text or "",
                        " ".join(node.keywords),
                    ],
                )
            ).lower()
            if not haystack:
                continue
            score = sum(haystack.count(token) for token in tokens)
            if score > 0:
                ranked.append((score, node))

        ranked.sort(key=lambda item: (-item[0], item[1].node_id))
        return version_id, [node for _score, node in ranked[:top_k]]

    def _resolve_node_store(
        self,
        policy_id: str,
        version_id: Optional[str],
    ) -> Tuple[Optional[str], Dict[str, TreeStoreNode]]:
        if version_id and (policy_id, version_id) in self._node_store:
            return version_id, self._node_store[(policy_id, version_id)]

        latest = self.latest_version(policy_id)
        if latest and (policy_id, latest.version_id) in self._node_store:
            return latest.version_id, self._node_store[(policy_id, latest.version_id)]

        for (pid, vid), store in self._node_store.items():
            if pid == policy_id:
                return vid, store

        return None, {}


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise TreeStoreClientError(f"Invalid date value: {value}") from exc
