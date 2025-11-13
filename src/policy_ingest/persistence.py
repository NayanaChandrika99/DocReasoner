"""
Helpers for persisting PageIndex artifacts into Postgres.

These helpers intentionally work with plain dictionaries so CLI commands can
call them without pulling in SQLAlchemy model details or session plumbing.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterator, List, Optional, Sequence

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from reasoning_service.config import settings
from reasoning_service.models.policy import PolicyNode, PolicyVersion

_ENGINE = create_engine(settings.database_url, future=True)
_SessionLocal = sessionmaker(bind=_ENGINE, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:  # pragma: no cover - defensive rollback
        session.rollback()
        raise
    finally:
        session.close()


def persist_policy_snapshot(
    *,
    policy_id: str,
    version_id: str,
    pageindex_doc_id: str,
    pdf_sha256: str,
    markdown_ptr: str,
    tree_json_ptr: str,
    tree_payload: Dict[str, object],
    source_url: Optional[str] = None,
    effective_date: Optional[datetime] = None,
) -> int:
    """
    Upsert the policy version metadata and replace all tree nodes for that version.

    Returns the number of nodes written so callers can log progress.
    """
    nodes = list(_flatten_tree(tree_payload))
    with session_scope() as session:
        _upsert_policy_version(
            session=session,
            policy_id=policy_id,
            version_id=version_id,
            pageindex_doc_id=pageindex_doc_id,
            pdf_sha256=pdf_sha256,
            markdown_ptr=markdown_ptr,
            tree_json_ptr=tree_json_ptr,
            source_url=source_url,
            effective_date=effective_date,
        )
        _replace_nodes(session, policy_id, version_id, nodes)
    return len(nodes)


def fetch_policy_summary(policy_id: str, version_id: str) -> Dict[str, object]:
    """Return persisted metadata plus node counts for a stored policy snapshot."""
    with session_scope() as session:
        version = session.get(PolicyVersion, (policy_id, version_id))
        if not version:
            raise ValueError(f"No snapshot found for policy_id={policy_id} version_id={version_id}")
        node_count = session.scalar(
            select(func.count(PolicyNode.id)).where(
                PolicyNode.policy_id == policy_id,
                PolicyNode.version_id == version_id,
            )
        )
        return {
            "policy_id": version.policy_id,
            "version_id": version.version_id,
            "pageindex_doc_id": version.pageindex_doc_id,
            "pdf_sha256": version.pdf_sha256,
            "markdown_ptr": version.markdown_ptr,
            "tree_json_ptr": version.tree_json_ptr,
            "source_url": version.source_url,
            "effective_date": version.effective_date.isoformat() if version.effective_date else None,
            "revision_date": version.revision_date.isoformat() if version.revision_date else None,
            "ingested_at": version.ingested_at.isoformat() if version.ingested_at else None,
            "node_count": int(node_count or 0),
        }


def _upsert_policy_version(
    *,
    session: Session,
    policy_id: str,
    version_id: str,
    pageindex_doc_id: str,
    pdf_sha256: str,
    markdown_ptr: str,
    tree_json_ptr: str,
    source_url: Optional[str],
    effective_date: Optional[datetime],
) -> None:
    """Insert or update the policy_versions row."""
    existing = session.get(PolicyVersion, (policy_id, version_id))
    timestamp = datetime.utcnow()
    if existing:
        existing.pageindex_doc_id = pageindex_doc_id
        existing.pdf_sha256 = pdf_sha256
        existing.markdown_ptr = markdown_ptr
        existing.tree_json_ptr = tree_json_ptr
        existing.source_url = source_url
        existing.effective_date = effective_date
        existing.ingested_at = timestamp
    else:
        session.add(
            PolicyVersion(
                policy_id=policy_id,
                version_id=version_id,
                pageindex_doc_id=pageindex_doc_id,
                pdf_sha256=pdf_sha256,
                markdown_ptr=markdown_ptr,
                tree_json_ptr=tree_json_ptr,
                source_url=source_url,
                effective_date=effective_date,
                ingested_at=timestamp,
            )
        )


def _replace_nodes(session: Session, policy_id: str, version_id: str, nodes: Sequence[Dict[str, object]]) -> None:
    """Delete any existing nodes for (policy_id, version_id) and insert the new set."""
    session.execute(
        delete(PolicyNode).where(
            PolicyNode.policy_id == policy_id,
            PolicyNode.version_id == version_id,
        )
    )
    enriched = []
    for node in nodes:
        enriched.append({**node, "policy_id": policy_id, "version_id": version_id})
    if enriched:
        session.bulk_insert_mappings(PolicyNode, enriched)


def _safe_int(value: object) -> Optional[int]:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _flatten_tree(tree_payload: Dict[str, object]) -> List[Dict[str, object]]:
    """Return dictionaries ready for PolicyNode bulk inserts (excluding policy ids)."""
    root_nodes = tree_payload.get("result") or tree_payload.get("nodes") or []

    def walk(node: Dict[str, object], ancestors: List[str], parent_node_id: Optional[str]) -> None:
        node_id = str(node.get("node_id") or "")
        title = str(node.get("title") or "").strip() or "Untitled"
        current_path = " > ".join(list(filter(None, ancestors + [title])))
        text = (node.get("text") or "") if isinstance(node.get("text"), str) else ""
        summary = (node.get("prefix_summary") or "") if isinstance(node.get("prefix_summary"), str) else None
        content_material = text or summary or title
        content_hash = hashlib.sha256(content_material.encode("utf-8")).hexdigest()
        yield_dict = {
            "node_id": node_id,
            "parent_id": parent_node_id,
            "section_path": current_path,
            "title": title,
            "page_index": _safe_int(node.get("page_index")),
            "page_start": _safe_int(node.get("page_start")),
            "page_end": _safe_int(node.get("page_end")),
            "summary": summary,
            "text": text or None,
            "content_hash": content_hash,
            "validation_status": "pending",
            "updated_at": datetime.utcnow(),
        }
        _pending_nodes.append(yield_dict)
        for child in node.get("nodes") or []:
            if isinstance(child, dict):
                walk(child, ancestors + [title], node_id or parent_node_id)

    _pending_nodes: List[Dict[str, object]] = []
    for root in root_nodes:
        if isinstance(root, dict):
            walk(root, [], None)
    return _pending_nodes
