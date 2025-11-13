from __future__ import annotations

import argparse
from pathlib import Path

from src.cli import ingest_policy_command, TREE_CACHE_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload policy PDF to PageIndex and cache the tree.")
    parser.add_argument(
        "--pdf",
        dest="pdf_path",
        type=Path,
        default=Path("data/Dockerfile.pdf"),
        help="Path to the policy PDF.",
    )
    parser.add_argument(
        "--cache",
        dest="cache_path",
        type=Path,
        default=TREE_CACHE_PATH,
        help="Where to store the cached tree JSON.",
    )
    parser.add_argument(
        "--policy-id",
        dest="policy_id",
        default="LCD-L34220",
        help="Unique policy identifier to persist.",
    )
    parser.add_argument(
        "--version-id",
        dest="version_id",
        default="2025-Q1",
        help="Version label for this ingestion snapshot.",
    )
    parser.add_argument(
        "--source-url",
        dest="source_url",
        default=None,
        help="Optional canonical URL for the policy PDF.",
    )
    args = parser.parse_args()
    doc_id, ready = ingest_policy_command(
        pdf_path=args.pdf_path,
        cache_path=args.cache_path,
        policy_id=args.policy_id,
        version_id=args.version_id,
        source_url=args.source_url,
    )
    status = "ready" if ready else "cached"
    print(f"Ingestion complete. doc_id={doc_id} status={status} cache={args.cache_path}")


if __name__ == "__main__":
    main()
