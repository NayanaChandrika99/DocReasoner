#!/usr/bin/env python3
"""
Migrate policy data from PostgreSQL to TreeStore.

This script reads policy versions and nodes from PostgreSQL and writes them
to TreeStore via gRPC using the TreeStore Python client.

Usage:
    # Migrate all policies
    python scripts/migrate_postgres_to_treestore.py --all

    # Migrate specific policy
    python scripts/migrate_postgres_to_treestore.py --policy-id LCD-L34220 --version-id 2025-Q1

    # Dry run (preview without writing)
    python scripts/migrate_postgres_to_treestore.py --all --dry-run

    # Validate existing migration
    python scripts/migrate_postgres_to_treestore.py --validate --policy-id LCD-L34220
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add tree_db client to path
sys.path.insert(0, str(Path(__file__).parent.parent / "tree_db" / "client" / "python"))

from treestore.client import TreeStoreClient

from src.policy_ingest.persistence import session_scope
from src.reasoning_service.models.policy import PolicyVersion, PolicyNode
from sqlalchemy import select

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when migration fails."""
    pass


class MigrationStats:
    """Track migration statistics."""

    def __init__(self):
        self.policies_attempted = 0
        self.policies_success = 0
        self.policies_failed = 0
        self.nodes_migrated = 0
        self.errors: List[str] = []

    def record_success(self, policy_id: str, version_id: str, node_count: int):
        """Record successful migration."""
        self.policies_success += 1
        self.nodes_migrated += node_count
        logger.info(f"✓ Migrated {policy_id}/{version_id}: {node_count} nodes")

    def record_failure(self, policy_id: str, version_id: str, error: str):
        """Record failed migration."""
        self.policies_failed += 1
        error_msg = f"✗ Failed {policy_id}/{version_id}: {error}"
        self.errors.append(error_msg)
        logger.error(error_msg)

    def print_summary(self):
        """Print migration summary."""
        logger.info("\n" + "=" * 60)
        logger.info("Migration Summary")
        logger.info("=" * 60)
        logger.info(f"Policies attempted: {self.policies_attempted}")
        logger.info(f"Policies succeeded: {self.policies_success}")
        logger.info(f"Policies failed:    {self.policies_failed}")
        logger.info(f"Total nodes migrated: {self.nodes_migrated}")

        if self.errors:
            logger.info("\nErrors:")
            for error in self.errors:
                logger.info(f"  {error}")
        logger.info("=" * 60)


def calculate_node_depth(node: PolicyNode, nodes_by_id: Dict[str, PolicyNode]) -> int:
    """Calculate depth of node in tree (root = 0)."""
    if not node.parent_id:
        return 0

    parent = nodes_by_id.get(node.parent_id)
    if not parent:
        return 0

    return 1 + calculate_node_depth(parent, nodes_by_id)


def build_children_map(nodes: List[PolicyNode]) -> Dict[str, List[str]]:
    """Build map of parent_id -> list of child node_ids."""
    children: Dict[str, List[str]] = defaultdict(list)

    for node in nodes:
        if node.parent_id:
            children[node.parent_id].append(node.node_id)

    return children


def migrate_policy(
    client: TreeStoreClient,
    policy_id: str,
    version_id: str,
    dry_run: bool = False
) -> int:
    """
    Migrate a single policy version from PostgreSQL to TreeStore.

    Args:
        client: TreeStore gRPC client
        policy_id: Policy document ID
        version_id: Version ID
        dry_run: If True, preview without writing

    Returns:
        Number of nodes migrated

    Raises:
        MigrationError: If migration fails
    """
    with session_scope() as session:
        # Get policy version
        version = session.get(PolicyVersion, (policy_id, version_id))
        if not version:
            raise MigrationError(f"Policy version not found: {policy_id}/{version_id}")

        # Get all nodes for this policy version
        stmt = select(PolicyNode).where(
            PolicyNode.policy_id == policy_id,
            PolicyNode.version_id == version_id
        ).order_by(PolicyNode.id)

        nodes = list(session.scalars(stmt))
        if not nodes:
            raise MigrationError(f"No nodes found for {policy_id}/{version_id}")

        logger.info(f"Found {len(nodes)} nodes for {policy_id}/{version_id}")

        # Build node lookup and children map
        nodes_by_id = {node.node_id: node for node in nodes}
        children_map = build_children_map(nodes)

        # Find root node (node with no parent)
        root_nodes = [n for n in nodes if not n.parent_id]
        if not root_nodes:
            raise MigrationError(f"No root node found for {policy_id}/{version_id}")
        if len(root_nodes) > 1:
            logger.warning(f"Multiple root nodes found, using first: {root_nodes[0].node_id}")

        root_node = root_nodes[0]

        # Create TreeStore document metadata
        document = {
            "policy_id": policy_id,
            "version_id": version_id,
            "pageindex_doc_id": version.pageindex_doc_id,
            "root_node_id": root_node.node_id,
            "metadata": {
                "pdf_sha256": version.pdf_sha256,
                "source_url": version.source_url or "",
                "effective_date": version.effective_date.isoformat() if version.effective_date else "",
                "ingested_at": version.ingested_at.isoformat() if version.ingested_at else "",
                "markdown_ptr": version.markdown_ptr or "",
                "tree_json_ptr": version.tree_json_ptr or "",
            }
        }

        # Transform nodes to TreeStore format
        treestore_nodes = []
        for node in nodes:
            treestore_nodes.append({
                "node_id": node.node_id,
                "policy_id": policy_id,
                "parent_id": node.parent_id or "",
                "title": node.title or "",
                "page_start": node.page_start or 0,
                "page_end": node.page_end or 0,
                "summary": node.summary or "",
                "text": node.text or "",
                "section_path": node.section_path or "",
                "child_ids": children_map.get(node.node_id, []),
                "depth": calculate_node_depth(node, nodes_by_id),
            })

        if dry_run:
            logger.info(f"[DRY RUN] Would migrate {policy_id}/{version_id} with {len(treestore_nodes)} nodes")
            logger.info(f"[DRY RUN] Root node: {root_node.node_id}")
            logger.info(f"[DRY RUN] Document metadata: {document['metadata']}")
            return len(treestore_nodes)

        # Write to TreeStore
        try:
            response = client.store_document(document, treestore_nodes)
            if not response.get("success"):
                raise MigrationError(f"TreeStore rejected document: {response.get('message')}")

            logger.info(f"TreeStore response: {response.get('message')}")
            return len(treestore_nodes)

        except Exception as e:
            raise MigrationError(f"Failed to write to TreeStore: {e}") from e


def validate_migration(
    client: TreeStoreClient,
    policy_id: str,
    version_id: str
) -> bool:
    """
    Validate that migration was successful by comparing PostgreSQL and TreeStore.

    Args:
        client: TreeStore gRPC client
        policy_id: Policy document ID
        version_id: Version ID

    Returns:
        True if validation passes, False otherwise
    """
    with session_scope() as session:
        # Count PostgreSQL nodes
        stmt = select(PolicyNode).where(
            PolicyNode.policy_id == policy_id,
            PolicyNode.version_id == version_id
        )
        pg_nodes = list(session.scalars(stmt))
        pg_count = len(pg_nodes)

        logger.info(f"PostgreSQL: {pg_count} nodes")

        # Get TreeStore document
        try:
            response = client.get_document(policy_id)
            ts_nodes = response.get("nodes", [])
            ts_count = len(ts_nodes)

            logger.info(f"TreeStore: {ts_count} nodes")

            # Compare counts
            if pg_count != ts_count:
                logger.error(f"Node count mismatch: PostgreSQL={pg_count}, TreeStore={ts_count}")
                return False

            # Verify all node IDs present
            pg_node_ids = {node.node_id for node in pg_nodes}
            ts_node_ids = {node["node_id"] for node in ts_nodes}

            missing_in_ts = pg_node_ids - ts_node_ids
            extra_in_ts = ts_node_ids - pg_node_ids

            if missing_in_ts:
                logger.error(f"Missing in TreeStore: {missing_in_ts}")
                return False

            if extra_in_ts:
                logger.error(f"Extra in TreeStore: {extra_in_ts}")
                return False

            logger.info("✓ Validation passed: All nodes present and counts match")
            return True

        except Exception as e:
            logger.error(f"Failed to validate: {e}")
            return False


def get_all_policy_versions() -> List[tuple[str, str]]:
    """Get all (policy_id, version_id) pairs from PostgreSQL."""
    with session_scope() as session:
        stmt = select(PolicyVersion.policy_id, PolicyVersion.version_id).order_by(
            PolicyVersion.policy_id, PolicyVersion.version_id
        )
        return list(session.execute(stmt))


def main():
    """Main migration entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate policy data from PostgreSQL to TreeStore"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Migrate all policies from PostgreSQL"
    )
    parser.add_argument(
        "--policy-id",
        type=str,
        help="Migrate specific policy ID"
    )
    parser.add_argument(
        "--version-id",
        type=str,
        help="Migrate specific version ID (requires --policy-id)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without writing to TreeStore"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate migration instead of migrating"
    )
    parser.add_argument(
        "--treestore-host",
        type=str,
        default="localhost",
        help="TreeStore server hostname (default: localhost)"
    )
    parser.add_argument(
        "--treestore-port",
        type=int,
        default=50051,
        help="TreeStore server port (default: 50051)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.policy_id:
        parser.error("Must specify either --all or --policy-id")

    if args.version_id and not args.policy_id:
        parser.error("--version-id requires --policy-id")

    # Connect to TreeStore
    logger.info(f"Connecting to TreeStore at {args.treestore_host}:{args.treestore_port}")
    client = TreeStoreClient(host=args.treestore_host, port=args.treestore_port)

    # Check TreeStore health
    try:
        health = client.health()
        logger.info(f"TreeStore health: {health}")
    except Exception as e:
        logger.error(f"Failed to connect to TreeStore: {e}")
        logger.error("Make sure TreeStore server is running")
        sys.exit(1)

    # Determine which policies to migrate
    if args.all:
        policies = get_all_policy_versions()
        logger.info(f"Found {len(policies)} policy versions to migrate")
    else:
        if args.version_id:
            policies = [(args.policy_id, args.version_id)]
        else:
            # Get all versions for this policy
            with session_scope() as session:
                stmt = select(PolicyVersion.version_id).where(
                    PolicyVersion.policy_id == args.policy_id
                )
                version_ids = list(session.scalars(stmt))
                policies = [(args.policy_id, vid) for vid in version_ids]
            logger.info(f"Found {len(policies)} versions for policy {args.policy_id}")

    if not policies:
        logger.warning("No policies found to migrate")
        sys.exit(0)

    # Validate mode
    if args.validate:
        logger.info("Running validation...")
        all_valid = True
        for policy_id, version_id in policies:
            logger.info(f"\nValidating {policy_id}/{version_id}")
            if not validate_migration(client, policy_id, version_id):
                all_valid = False

        sys.exit(0 if all_valid else 1)

    # Migration mode
    stats = MigrationStats()

    for policy_id, version_id in policies:
        stats.policies_attempted += 1
        logger.info(f"\nMigrating {policy_id}/{version_id}")

        try:
            node_count = migrate_policy(client, policy_id, version_id, dry_run=args.dry_run)
            stats.record_success(policy_id, version_id, node_count)
        except MigrationError as e:
            stats.record_failure(policy_id, version_id, str(e))
        except Exception as e:
            stats.record_failure(policy_id, version_id, f"Unexpected error: {e}")

    # Print summary
    stats.print_summary()

    # Close client
    client.close()

    # Exit with error if any migrations failed
    sys.exit(0 if stats.policies_failed == 0 else 1)


if __name__ == "__main__":
    main()
