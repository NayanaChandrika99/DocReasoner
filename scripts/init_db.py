#!/usr/bin/env python3
"""
Database initialization script for reasoning-service.

This script:
1. Creates database tables using Alembic migrations
2. Optionally seeds initial data
3. Validates database connectivity and schema

Usage:
    uv run python scripts/init_db.py [--seed]
"""

import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text
from reasoning_service.config import get_async_engine, settings
from reasoning_service.models.policy import Base
import typer

app = typer.Typer()


async def check_connection():
    """Test database connectivity."""
    engine = get_async_engine()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.scalar()
            if row == 1:
                typer.echo("✓ Database connection successful")
                return True
    except Exception as e:
        typer.echo(f"✗ Database connection failed: {e}", err=True)
        return False
    return False


async def create_tables():
    """Create all database tables."""
    engine = get_async_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        typer.echo("✓ Database tables created successfully")
        return True
    except Exception as e:
        typer.echo(f"✗ Failed to create tables: {e}", err=True)
        return False


async def verify_schema():
    """Verify all expected tables exist."""
    engine = get_async_engine()
    expected_tables = {
        "policy_versions",
        "policy_nodes",
        "reasoning_outputs",
        "policy_validation_issues",
    }

    try:
        async with engine.connect() as conn:
            # Query information_schema for table names
            result = await conn.execute(
                text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
            )
            existing_tables = {row[0] for row in result.all()}

            missing = expected_tables - existing_tables
            if missing:
                typer.echo(f"✗ Missing tables: {', '.join(missing)}", err=True)
                return False

            typer.echo(f"✓ All {len(expected_tables)} tables present")
            return True
    except Exception as e:
        typer.echo(f"✗ Schema verification failed: {e}", err=True)
        return False


async def seed_test_data():
    """Optionally seed test policy data."""
    from datetime import datetime
    from reasoning_service.models.policy import PolicyVersion
    from reasoning_service.config import get_async_session_factory

    async_session = get_async_session_factory()

    try:
        async with async_session() as session:
            # Check if test policy already exists
            from sqlalchemy import select

            result = await session.execute(
                select(PolicyVersion).where(PolicyVersion.policy_id == "LCD-L34220")
            )
            existing = result.scalar_one_or_none()

            if existing:
                typer.echo("ℹ Test policy already exists, skipping seed")
                return True

            # Create test policy version
            test_policy = PolicyVersion(
                policy_id="LCD-L34220",
                version_id="2025-Q1",
                pageindex_doc_id="pi-cmhppdets02r308pjqnaukvnt",
                pdf_sha256="test_sha256_placeholder",
                markdown_ptr="data/policy_markdown.md",
                tree_json_ptr="data/pageindex_tree.json",
                source_url="https://example.com/policy",
                effective_date=datetime(2025, 1, 1),
                ingested_at=datetime.utcnow(),
            )

            session.add(test_policy)
            await session.commit()

            typer.echo("✓ Test policy data seeded successfully")
            return True

    except Exception as e:
        typer.echo(f"✗ Failed to seed data: {e}", err=True)
        return False


@app.command()
def main(
    seed: bool = typer.Option(False, "--seed", help="Seed test data after initialization"),
    check_only: bool = typer.Option(
        False, "--check-only", help="Only check connection, don't create tables"
    ),
):
    """Initialize the reasoning-service database."""
    typer.echo("=" * 60)
    typer.echo("Database Initialization")
    typer.echo("=" * 60)
    typer.echo(f"Database URL: {settings.database_url[:50]}...")
    typer.echo()

    async def run():
        # Step 1: Check connection
        typer.echo("Step 1: Checking database connection...")
        if not await check_connection():
            typer.echo("\n✗ Initialization failed: Cannot connect to database", err=True)
            raise typer.Exit(1)
        typer.echo()

        if check_only:
            typer.echo("✓ Connection check passed (--check-only mode)")
            return

        # Step 2: Create tables
        typer.echo("Step 2: Creating database tables...")
        if not await create_tables():
            typer.echo("\n✗ Initialization failed: Could not create tables", err=True)
            raise typer.Exit(1)
        typer.echo()

        # Step 3: Verify schema
        typer.echo("Step 3: Verifying schema...")
        if not await verify_schema():
            typer.echo("\n✗ Initialization failed: Schema verification failed", err=True)
            raise typer.Exit(1)
        typer.echo()

        # Step 4: Seed data (optional)
        if seed:
            typer.echo("Step 4: Seeding test data...")
            if not await seed_test_data():
                typer.echo("\n⚠ Warning: Seeding failed, but tables are created", err=True)
            typer.echo()

        # Success!
        typer.echo("=" * 60)
        typer.echo("✓ Database initialization complete!")
        typer.echo("=" * 60)
        typer.echo()
        typer.echo("Next steps:")
        typer.echo("  1. Run migrations: uv run alembic upgrade head")
        typer.echo("  2. Ingest policy: uv run python -m src.cli ingest-policy data/Dockerfile.pdf")
        typer.echo("  3. Start API: uv run uvicorn reasoning_service.api.app:create_app --factory")

    asyncio.run(run())


if __name__ == "__main__":
    app()
