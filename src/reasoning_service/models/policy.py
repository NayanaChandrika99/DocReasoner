"""Database models for policy storage."""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, DateTime, Text, Index, ForeignKeyConstraint, CheckConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class PolicyVersion(Base):
    """Policy version tracking."""

    __tablename__ = "policy_versions"

    policy_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    pageindex_doc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    markdown_ptr: Mapped[str] = mapped_column(Text, nullable=False)
    tree_json_ptr: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    effective_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revision_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tree_validated_by: Mapped[Optional[str]] = mapped_column(String(100))
    tree_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_policy_versions_ingested", "policy_id", "ingested_at"),
    )


class PolicyNode(Base):
    """Hierarchical policy document nodes from PageIndex tree."""
    
    __tablename__ = "policy_nodes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version_id: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(100))
    section_path: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    page_index: Mapped[Optional[int]] = mapped_column(Integer)
    page_start: Mapped[Optional[int]] = mapped_column(Integer)
    page_end: Mapped[Optional[int]] = mapped_column(Integer)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[Optional[str]] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_id", "version_id"],
            ["policy_versions.policy_id", "policy_versions.version_id"],
        ),
        CheckConstraint(
            "validation_status IN ('pending', 'approved', 'flagged')",
            name="ck_validation_status"
        ),
        CheckConstraint(
            "(page_start IS NULL AND page_end IS NULL) OR (page_start <= page_end)",
            name="ck_page_range"
        ),
        Index("ix_policy_nodes_lookup", "policy_id", "version_id", "node_id"),
        Index("ix_policy_nodes_parent", "policy_id", "version_id", "parent_id"),
    )


class ReasoningOutput(Base):
    """Outputs from reasoning decisions."""

    __tablename__ = "reasoning_outputs"

    case_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    criterion_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    citation_section_path: Mapped[str] = mapped_column(String(500), nullable=False)
    citation_pages: Mapped[str] = mapped_column(String(100), nullable=False)  # JSON array
    c_tree: Mapped[float] = mapped_column(nullable=False)
    c_span: Mapped[float] = mapped_column(nullable=False)
    c_final: Mapped[float] = mapped_column(nullable=False)
    c_joint: Mapped[float] = mapped_column(nullable=False)
    search_trajectory: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    retrieval_method: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_id", "version_id"],
            ["policy_versions.policy_id", "policy_versions.version_id"],
        ),
        CheckConstraint(
            "status IN ('ready', 'not_ready', 'uncertain')",
            name="ck_reasoning_status"
        ),
        Index("ix_reasoning_outputs_case", "case_id"),
        Index("ix_reasoning_outputs_policy", "policy_id", "version_id"),
    )


class PolicyValidationIssue(Base):
    """Issues found during policy tree validation."""

    __tablename__ = "policy_validation_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version_id: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[Optional[str]] = mapped_column(String(100))
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_id", "version_id"],
            ["policy_versions.policy_id", "policy_versions.version_id"],
        ),
        Index("ix_validation_issues_unresolved", "resolved_at"),
    )
