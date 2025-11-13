"""create_policy_tables

Revision ID: 693889b485e5
Revises: 
Create Date: 2025-11-08 11:12:20.337845

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '693889b485e5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_versions",
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("version_id", sa.String(length=50), nullable=False),
        sa.Column("pageindex_doc_id", sa.String(length=64), nullable=False),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("markdown_ptr", sa.Text(), nullable=False),
        sa.Column("tree_json_ptr", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.DateTime(), nullable=True),
        sa.Column("revision_date", sa.DateTime(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("tree_validated_by", sa.String(length=100), nullable=True),
        sa.Column("tree_validated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("policy_id", "version_id"),
    )
    op.create_index(
        "ix_policy_versions_ingested",
        "policy_versions",
        ["policy_id", "ingested_at"],
    )

    op.create_table(
        "policy_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("version_id", sa.String(length=50), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("parent_id", sa.String(length=100), nullable=True),
        sa.Column("section_path", sa.String(length=500), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["policy_id", "version_id"],
            ["policy_versions.policy_id", "policy_versions.version_id"],
        ),
        sa.CheckConstraint(
            "(page_start IS NULL AND page_end IS NULL) OR (page_start <= page_end)",
            name="ck_page_range",
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending', 'approved', 'flagged')",
            name="ck_validation_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_nodes_lookup",
        "policy_nodes",
        ["policy_id", "version_id", "node_id"],
    )
    op.create_index(
        "ix_policy_nodes_parent",
        "policy_nodes",
        ["policy_id", "version_id", "parent_id"],
    )

    op.create_table(
        "reasoning_outputs",
        sa.Column("case_id", sa.String(length=100), nullable=False),
        sa.Column("criterion_id", sa.String(length=100), nullable=False),
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("version_id", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("citation_section_path", sa.String(length=500), nullable=False),
        sa.Column("citation_pages", sa.String(length=100), nullable=False),
        sa.Column("c_tree", sa.Float(), nullable=False),
        sa.Column("c_span", sa.Float(), nullable=False),
        sa.Column("c_final", sa.Float(), nullable=False),
        sa.Column("c_joint", sa.Float(), nullable=False),
        sa.Column("search_trajectory", sa.Text(), nullable=False),
        sa.Column("retrieval_method", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["policy_id", "version_id"],
            ["policy_versions.policy_id", "policy_versions.version_id"],
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'not_ready', 'uncertain')",
            name="ck_reasoning_status",
        ),
        sa.PrimaryKeyConstraint("case_id", "criterion_id"),
    )
    op.create_index(
        "ix_reasoning_outputs_case",
        "reasoning_outputs",
        ["case_id"],
    )
    op.create_index(
        "ix_reasoning_outputs_policy",
        "reasoning_outputs",
        ["policy_id", "version_id"],
    )

    op.create_table(
        "policy_validation_issues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.String(length=100), nullable=False),
        sa.Column("version_id", sa.String(length=50), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=True),
        sa.Column("issue_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reported_by", sa.String(length=100), nullable=False),
        sa.Column("reported_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["policy_id", "version_id"],
            ["policy_versions.policy_id", "policy_versions.version_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_issues_unresolved",
        "policy_validation_issues",
        ["resolved_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_validation_issues_unresolved", table_name="policy_validation_issues")
    op.drop_table("policy_validation_issues")

    op.drop_index("ix_reasoning_outputs_policy", table_name="reasoning_outputs")
    op.drop_index("ix_reasoning_outputs_case", table_name="reasoning_outputs")
    op.drop_table("reasoning_outputs")

    op.drop_index("ix_policy_nodes_parent", table_name="policy_nodes")
    op.drop_index("ix_policy_nodes_lookup", table_name="policy_nodes")
    op.drop_table("policy_nodes")

    op.drop_index("ix_policy_versions_ingested", table_name="policy_versions")
    op.drop_table("policy_versions")
