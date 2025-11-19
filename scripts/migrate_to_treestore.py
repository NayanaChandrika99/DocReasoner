#!/usr/bin/env python3
"""
Migration script to populate TreeStore from PostgreSQL policy data.

This script:
1. Reads all policy versions and nodes from PostgreSQL
2. Connects to TreeStore gRPC server
3. Stores hierarchical documents in TreeStore
4. Validates data integrity after migration

Usage:
    python scripts/migrate_to_treestore.py [--dry-run] [--policy-id POLICY_ID]
"""

import asyncio
import argparse
import logging
import sys
from typing import List, Dict, Any
from datetime import datetime

# Add parent directory to path
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.reasoning_service.models.policy import PolicyVersion, PolicyNode
from src.reasoning_service.config import Settings
from src.reasoning_service.services.treestore_client import create_treestore_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TreeStoreMigration:
    """Handles migration from PostgreSQL to TreeStore."""

    def __init__(self, settings: Settings, dry_run: bool = False):
        self.settings = settings
        self.dry_run = dry_run
        self.engine = create_async_engine(
            settings.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
            echo=False
        )
        self.session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        # Create TreeStore client
        self.treestore_client = None
        if not dry_run:
            try:
                self.treestore_client = create_treestore_client(
                    use_stub=settings.treestore_use_stub,
                    host=settings.treestore_host,
                    port=settings.treestore_port,
                    timeout=settings.treestore_timeout,
                    max_retries=settings.treestore_max_retries,
                    retry_delay=settings.treestore_retry_delay,
                )
                logger.info(f"Connected to TreeStore at {settings.treestore_host}:{settings.treestore_port}")
            except Exception as e:
                logger.error(f"Failed to connect to TreeStore: {e}")
                raise

    async def get_policy_versions(self, policy_id: str = None) -> List[PolicyVersion]:
        """Fetch policy versions from PostgreSQL."""
        async with self.session_maker() as session:
            if policy_id:
                stmt = select(PolicyVersion).where(PolicyVersion.policy_id == policy_id)
            else:
                stmt = select(PolicyVersion).order_by(PolicyVersion.policy_id, PolicyVersion.ingested_at)

            result = await session.execute(stmt)
            versions = result.scalars().all()
            return list(versions)

    async def get_policy_nodes(self, policy_id: str, version_id: str) -> List[PolicyNode]:
        """Fetch all nodes for a specific policy version."""
        async with self.session_maker() as session:
            stmt = (
                select(PolicyNode)
                .where(
                    PolicyNode.policy_id == policy_id,
                    PolicyNode.version_id == version_id
                )
                .order_by(PolicyNode.section_path)
            )
            result = await session.execute(stmt)
            nodes = result.scalars().all()
            return list(nodes)

    def find_root_node(self, nodes: List[PolicyNode]) -> str:
        """Find the root node (node with no parent)."""
        for node in nodes:
            if not node.parent_id:
                return node.node_id

        # Fallback: return first node
        if nodes:
            logger.warning(f"No root node found, using first node: {nodes[0].node_id}")
            return nodes[0].node_id

        raise ValueError("No nodes found to determine root")

    def build_document_dict(self, version: PolicyVersion, root_node_id: str) -> Dict[str, Any]:
        """Build document dict for TreeStore."""
        return {
            "policy_id": version.policy_id,
            "version_id": version.version_id,
            "pageindex_doc_id": version.pageindex_doc_id,
            "root_node_id": root_node_id,
            "metadata": {
                "effective_date": version.effective_date.isoformat() if version.effective_date else None,
                "revision_date": version.revision_date.isoformat() if version.revision_date else None,
                "ingested_at": version.ingested_at.isoformat() if version.ingested_at else None,
                "source_url": version.source_url or "",
                "pdf_sha256": version.pdf_sha256,
            }
        }

    def build_node_dicts(self, nodes: List[PolicyNode]) -> List[Dict[str, Any]]:
        """Build node dicts for TreeStore."""
        node_dicts = []

        for node in nodes:
            # Build child_ids from parent relationships
            child_ids = [
                n.node_id for n in nodes
                if n.parent_id == node.node_id
            ]

            # Calculate depth from section path
            depth = len(node.section_path.split('/')) - 1 if node.section_path else 0

            node_dict = {
                "node_id": node.node_id,
                "policy_id": node.policy_id,
                "parent_id": node.parent_id or "",
                "title": node.title,
                "page_start": node.page_start or 0,
                "page_end": node.page_end or 0,
                "summary": node.summary or "",
                "text": node.text or "",
                "section_path": node.section_path,
                "child_ids": child_ids,
                "depth": depth,
            }
            node_dicts.append(node_dict)

        return node_dicts

    async def migrate_policy_version(self, version: PolicyVersion) -> bool:
        """Migrate a single policy version to TreeStore."""
        logger.info(f"Migrating {version.policy_id} v{version.version_id}...")

        try:
            # Fetch nodes
            nodes = await self.get_policy_nodes(version.policy_id, version.version_id)
            if not nodes:
                logger.warning(f"No nodes found for {version.policy_id} v{version.version_id}, skipping")
                return False

            logger.info(f"  Found {len(nodes)} nodes")

            # Find root node
            root_node_id = self.find_root_node(nodes)

            # Build document and node dicts
            document = self.build_document_dict(version, root_node_id)
            node_dicts = self.build_node_dicts(nodes)

            if self.dry_run:
                logger.info(f"  [DRY RUN] Would store document with {len(node_dicts)} nodes")
                logger.info(f"  Document: {document}")
                logger.info(f"  Root node: {root_node_id}")
                return True

            # Store in TreeStore
            response = self.treestore_client._grpc_client.store_document(
                document=document,
                nodes=node_dicts
            )

            if response.get("success"):
                logger.info(f"  ✓ Migrated successfully: {response.get('message', '')}")
                return True
            else:
                logger.error(f"  ✗ Migration failed: {response.get('message', 'Unknown error')}")
                return False

        except Exception as e:
            logger.error(f"  ✗ Error migrating {version.policy_id} v{version.version_id}: {e}")
            return False

    async def validate_migration(self, policy_id: str, version_id: str) -> bool:
        """Validate that a policy version was migrated correctly."""
        try:
            # Fetch from PostgreSQL
            pg_nodes = await self.get_policy_nodes(policy_id, version_id)
            pg_node_count = len(pg_nodes)

            # Fetch from TreeStore
            ts_doc = self.treestore_client._grpc_client.get_document(policy_id=policy_id)
            ts_node_count = len(ts_doc.get("nodes", []))

            if pg_node_count == ts_node_count:
                logger.info(f"  ✓ Validation passed: {ts_node_count} nodes match")
                return True
            else:
                logger.error(f"  ✗ Validation failed: PG has {pg_node_count}, TreeStore has {ts_node_count}")
                return False

        except Exception as e:
            logger.error(f"  ✗ Validation error: {e}")
            return False

    async def run(self, policy_id: str = None, validate: bool = True):
        """Run the full migration."""
        logger.info("=" * 80)
        logger.info("TreeStore Migration Starting")
        logger.info("=" * 80)

        if self.dry_run:
            logger.info("DRY RUN MODE - No data will be written to TreeStore")

        # Fetch policy versions
        versions = await self.get_policy_versions(policy_id)
        logger.info(f"\nFound {len(versions)} policy version(s) to migrate")

        if not versions:
            logger.warning("No policy versions found in database")
            return

        # Migrate each version
        success_count = 0
        failed_count = 0

        for i, version in enumerate(versions, 1):
            logger.info(f"\n[{i}/{len(versions)}] Processing {version.policy_id} v{version.version_id}")

            success = await self.migrate_policy_version(version)
            if success:
                success_count += 1

                # Validate if requested and not dry run
                if validate and not self.dry_run:
                    await self.validate_migration(version.policy_id, version.version_id)
            else:
                failed_count += 1

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("Migration Summary")
        logger.info("=" * 80)
        logger.info(f"Total versions: {len(versions)}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {failed_count}")

        if self.dry_run:
            logger.info("\nDRY RUN completed - no data was written")
        else:
            logger.info(f"\nMigration completed to {self.settings.treestore_host}:{self.settings.treestore_port}")

    async def close(self):
        """Clean up resources."""
        await self.engine.dispose()
        if self.treestore_client and hasattr(self.treestore_client, 'close'):
            self.treestore_client.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Migrate policy data to TreeStore')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run migration without writing to TreeStore'
    )
    parser.add_argument(
        '--policy-id',
        type=str,
        help='Migrate only a specific policy ID'
    )
    parser.add_argument(
        '--no-validate',
        action='store_true',
        help='Skip validation after migration'
    )

    args = parser.parse_args()

    # Load settings
    settings = Settings()

    # Override to use gRPC client for migration
    if not args.dry_run:
        settings.treestore_use_stub = False

    # Run migration
    migration = TreeStoreMigration(settings, dry_run=args.dry_run)

    try:
        await migration.run(
            policy_id=args.policy_id,
            validate=not args.no_validate
        )
    finally:
        await migration.close()


if __name__ == "__main__":
    asyncio.run(main())
