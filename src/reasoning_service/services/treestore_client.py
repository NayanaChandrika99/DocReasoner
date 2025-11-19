# ABOUTME: Provides the TreeStoreClient abstraction for policy version lookups.
# ABOUTME: Enables TreeStore-backed tools such as temporal lookup and policy xref.
# ABOUTME: Supports both in-memory stub (for development) and gRPC client (for production).
"""TreeStore client abstractions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re
from typing import Dict, List, Optional, Tuple, Protocol
import logging

logger = logging.getLogger(__name__)


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


class TreeStoreClientProtocol(Protocol):
    """Protocol defining the TreeStore client interface."""

    def get_version_as_of(self, policy_id: str, as_of_date: str) -> TreeStoreVersion:
        ...

    def get_nodes(self, policy_id: str, version_id: str, node_ids: List[str]) -> Dict[str, TreeStoreNode]:
        ...

    def find_related_nodes(
        self,
        policy_id: str,
        version_id: Optional[str],
        criterion_id: str,
        tokens: List[str],
        limit: int = 5,
    ) -> List[Tuple[TreeStoreNode, str]]:
        ...

    def latest_version(self, policy_id: str) -> Optional[TreeStoreVersion]:
        ...

    def get_node(
        self,
        policy_id: str,
        version_id: Optional[str],
        node_id: str,
    ) -> Optional[TreeStoreNode]:
        ...

    def search_nodes(
        self,
        policy_id: str,
        query: str,
        version_id: Optional[str],
        top_k: int = 3,
    ) -> Tuple[Optional[str], List[TreeStoreNode]]:
        ...


class TreeStoreClientStub:
    """In-memory stub implementation for development and testing."""

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


class TreeStoreClientGRPC:
    """gRPC-based TreeStore client for production use."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        enable_compression: bool = True,
    ):
        """
        Initialize gRPC TreeStore client.

        Args:
            host: TreeStore server hostname
            port: TreeStore server port
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            enable_compression: Enable gRPC compression
        """
        try:
            # Import gRPC client from tree_db/client/python
            # This needs to be in the Python path
            import sys
            import os
            tree_db_client_path = os.path.join(
                os.path.dirname(__file__),
                "..", "..", "..", "tree_db", "client", "python"
            )
            sys.path.insert(0, os.path.abspath(tree_db_client_path))
            from treestore.client import TreeStoreClient as GRPCClient

            self._grpc_client = GRPCClient(host=host, port=port)
            self.timeout = timeout
            self.max_retries = max_retries
            self.retry_delay = retry_delay
            logger.info(f"Connected to TreeStore gRPC server at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to initialize gRPC client: {e}")
            raise TreeStoreClientError(f"gRPC client initialization failed: {e}") from e

    def _dict_to_node(self, node_dict: dict) -> TreeStoreNode:
        """Convert gRPC node dict to TreeStoreNode."""
        return TreeStoreNode(
            node_id=node_dict.get("node_id", ""),
            title=node_dict.get("title"),
            section_path=node_dict.get("section_path"),
            pages=list(range(
                node_dict.get("page_start", 0),
                node_dict.get("page_end", 0) + 1
            )),
            summary=node_dict.get("summary"),
            parent_id=node_dict.get("parent_id") or None,
            keywords=[],  # TODO: Add keywords field to protobuf
            see_also=[],  # TODO: Add see_also field to protobuf
            text=node_dict.get("text"),
        )

    def get_version_as_of(self, policy_id: str, as_of_date: str) -> TreeStoreVersion:
        """Return the version that was active on the given date."""
        try:
            response = self._grpc_client.get_version_as_of(
                policy_id=policy_id,
                as_of_date=as_of_date
            )
            if not response or not response.get("version"):
                raise TreeStoreClientError(
                    f"No version found for {policy_id} on {as_of_date}"
                )

            version_data = response["version"]
            return TreeStoreVersion(
                policy_id=version_data.get("policy_id", policy_id),
                version_id=version_data.get("version_id", ""),
                effective_start=version_data.get("effective_start"),
                effective_end=version_data.get("effective_end"),
                pageindex_doc_id=version_data.get("pageindex_doc_id"),
                previous_version_id=version_data.get("previous_version_id"),
            )
        except Exception as e:
            logger.error(f"get_version_as_of failed: {e}")
            raise TreeStoreClientError(f"Failed to get version: {e}") from e

    def get_nodes(self, policy_id: str, version_id: str, node_ids: List[str]) -> Dict[str, TreeStoreNode]:
        """Return nodes by id for a specific policy/version pair."""
        try:
            # Get all nodes for the policy (gRPC API doesn't have batch get by IDs)
            # So we fetch the document and filter
            doc_response = self._grpc_client.get_document(policy_id=policy_id)
            nodes_dict = {}

            for node_dict in doc_response.get("nodes", []):
                node = self._dict_to_node(node_dict)
                if not node_ids or node.node_id in node_ids:
                    nodes_dict[node.node_id] = node

            if not nodes_dict:
                raise TreeStoreClientError(
                    f"No nodes found for policy {policy_id}"
                )

            return nodes_dict
        except Exception as e:
            logger.error(f"get_nodes failed: {e}")
            raise TreeStoreClientError(f"Failed to get nodes: {e}") from e

    def find_related_nodes(
        self,
        policy_id: str,
        version_id: Optional[str],
        criterion_id: str,
        tokens: List[str],
        limit: int = 5,
    ) -> List[Tuple[TreeStoreNode, str]]:
        """Return related nodes with reasons using keyword search."""
        try:
            # Use search API to find related nodes
            query = " ".join(tokens)
            results = self._grpc_client.search(
                policy_id=policy_id,
                query=query,
                limit=limit
            )

            related_nodes = []
            for result in results:
                node = self._dict_to_node(result["node"])
                reason = "keyword"  # Search is keyword-based
                related_nodes.append((node, reason))

            return related_nodes
        except Exception as e:
            logger.warning(f"find_related_nodes failed, returning empty: {e}")
            return []

    def latest_version(self, policy_id: str) -> Optional[TreeStoreVersion]:
        """Return the latest known version for a policy."""
        try:
            versions = self._grpc_client.list_versions(policy_id=policy_id)
            if not versions or not versions.get("versions"):
                return None

            # Get the last version (should be latest)
            latest = versions["versions"][-1]
            return TreeStoreVersion(
                policy_id=policy_id,
                version_id=latest.get("version_id", ""),
                effective_start=latest.get("effective_start"),
                effective_end=latest.get("effective_end"),
                pageindex_doc_id=latest.get("pageindex_doc_id"),
                previous_version_id=latest.get("previous_version_id"),
            )
        except Exception as e:
            logger.warning(f"latest_version failed: {e}")
            return None

    def get_node(
        self,
        policy_id: str,
        version_id: Optional[str],
        node_id: str,
    ) -> Optional[TreeStoreNode]:
        """Get a single node by ID."""
        try:
            response = self._grpc_client.get_node(
                policy_id=policy_id,
                node_id=node_id
            )
            if not response or not response.get("node"):
                return None

            return self._dict_to_node(response["node"])
        except Exception as e:
            logger.warning(f"get_node failed: {e}")
            return None

    def search_nodes(
        self,
        policy_id: str,
        query: str,
        version_id: Optional[str],
        top_k: int = 3,
    ) -> Tuple[Optional[str], List[TreeStoreNode]]:
        """Search nodes by keyword relevance."""
        try:
            results = self._grpc_client.search(
                policy_id=policy_id,
                query=query,
                limit=top_k
            )

            nodes = [self._dict_to_node(result["node"]) for result in results]
            return version_id, nodes
        except Exception as e:
            logger.warning(f"search_nodes failed: {e}")
            return version_id, []

    def close(self):
        """Close the gRPC connection."""
        if hasattr(self, "_grpc_client"):
            self._grpc_client.close()


def create_treestore_client(
    use_stub: bool = False,
    host: str = "localhost",
    port: int = 50051,
    timeout: int = 30,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    enable_compression: bool = True,
    # Stub-specific parameters
    version_catalog: Optional[Dict[str, List[TreeStoreVersion]]] = None,
    node_store: Optional[Dict[Tuple[str, str], Dict[str, TreeStoreNode]]] = None,
    cross_reference_index: Optional[Dict[Tuple[str, str], List[TreeStoreNode]]] = None,
) -> TreeStoreClientProtocol:
    """
    Factory function to create the appropriate TreeStore client.

    Args:
        use_stub: If True, use in-memory stub; otherwise use gRPC client
        host: gRPC server host (used if use_stub=False)
        port: gRPC server port (used if use_stub=False)
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries
        enable_compression: Enable gRPC compression
        version_catalog: Version catalog for stub
        node_store: Node store for stub
        cross_reference_index: Cross-reference index for stub

    Returns:
        TreeStoreClient implementation (stub or gRPC)
    """
    if use_stub:
        logger.info("Using TreeStore stub (in-memory)")
        return TreeStoreClientStub(
            version_catalog=version_catalog,
            node_store=node_store,
            cross_reference_index=cross_reference_index,
        )
    else:
        logger.info(f"Using TreeStore gRPC client at {host}:{port}")
        return TreeStoreClientGRPC(
            host=host,
            port=port,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            enable_compression=enable_compression,
        )


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise TreeStoreClientError(f"Invalid date value: {value}") from exc


# Backward compatibility: Keep TreeStoreClient as alias to stub for now
TreeStoreClient = TreeStoreClientStub
