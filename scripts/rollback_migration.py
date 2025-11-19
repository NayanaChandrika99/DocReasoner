#!/usr/bin/env python3
"""
Rollback script to clear TreeStore data and revert to PageIndex.

This script:
1. Connects to TreeStore gRPC server
2. Deletes all policy documents from TreeStore
3. Optionally updates environment to use PageIndex backend

Usage:
    python scripts/rollback_migration.py [--policy-id POLICY_ID] [--confirm]
"""

import asyncio
import argparse
import logging
import sys
from typing import List

# Add parent directory to path
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.reasoning_service.models.policy import PolicyVersion
from src.reasoning_service.config import Settings
from src.reasoning_service.services.treestore_client import create_treestore_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TreeStoreRollback:
    """Handles rollback of TreeStore migration."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_async_engine(
            settings.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
            echo=False
        )
        self.session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        # Create TreeStore client
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

    async def get_policy_ids(self, policy_id: str = None) -> List[str]:
        """Get list of policy IDs from PostgreSQL."""
        async with self.session_maker() as session:
            if policy_id:
                stmt = select(PolicyVersion.policy_id).where(
                    PolicyVersion.policy_id == policy_id
                ).distinct()
            else:
                stmt = select(PolicyVersion.policy_id).distinct()

            result = await session.execute(stmt)
            policy_ids = [row[0] for row in result.all()]
            return policy_ids

    def delete_policy_from_treestore(self, policy_id: str) -> bool:
        """Delete a policy document from TreeStore."""
        try:
            response = self.treestore_client._grpc_client.delete_document(
                policy_id=policy_id
            )

            if response.get("success"):
                logger.info(f"  ✓ Deleted {policy_id}")
                return True
            else:
                logger.warning(f"  ⚠ Could not delete {policy_id}: {response.get('message', 'Unknown error')}")
                return False

        except Exception as e:
            logger.error(f"  ✗ Error deleting {policy_id}: {e}")
            return False

    async def run(self, policy_id: str = None, confirm: bool = False):
        """Run the rollback."""
        logger.info("=" * 80)
        logger.info("TreeStore Rollback Starting")
        logger.info("=" * 80)

        # Get policy IDs
        policy_ids = await self.get_policy_ids(policy_id)

        if not policy_ids:
            logger.warning("No policies found to rollback")
            return

        logger.info(f"\nFound {len(policy_ids)} policy/policies to delete from TreeStore:")
        for pid in policy_ids:
            logger.info(f"  - {pid}")

        if not confirm:
            logger.warning("\n⚠ WARNING: This will permanently delete data from TreeStore!")
            logger.warning("Run with --confirm to proceed")
            return

        # Delete each policy
        success_count = 0
        failed_count = 0

        for i, pid in enumerate(policy_ids, 1):
            logger.info(f"\n[{i}/{len(policy_ids)}] Deleting {pid}")

            success = self.delete_policy_from_treestore(pid)
            if success:
                success_count += 1
            else:
                failed_count += 1

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("Rollback Summary")
        logger.info("=" * 80)
        logger.info(f"Total policies: {len(policy_ids)}")
        logger.info(f"Successfully deleted: {success_count}")
        logger.info(f"Failed: {failed_count}")

        if success_count > 0:
            logger.info("\n✓ Rollback completed")
            logger.info("\nTo complete rollback, update your environment:")
            logger.info("  export RETRIEVAL_BACKEND=pageindex")
            logger.info("  # or update .env file: RETRIEVAL_BACKEND=pageindex")

    async def close(self):
        """Clean up resources."""
        await self.engine.dispose()
        if hasattr(self.treestore_client, 'close'):
            self.treestore_client.close()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Rollback TreeStore migration')
    parser.add_argument(
        '--policy-id',
        type=str,
        help='Rollback only a specific policy ID'
    )
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Confirm deletion (required)'
    )

    args = parser.parse_args()

    # Load settings
    settings = Settings()
    settings.treestore_use_stub = False  # Force gRPC for rollback

    # Run rollback
    rollback = TreeStoreRollback(settings)

    try:
        await rollback.run(
            policy_id=args.policy_id,
            confirm=args.confirm
        )
    finally:
        await rollback.close()


if __name__ == "__main__":
    asyncio.run(main())
