from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli import run_decision_command, TREE_CACHE_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the decision pipeline for a single case.")
    parser.add_argument("--case", dest="case_path", type=Path, required=True, help="Case bundle JSON path.")
    parser.add_argument(
        "--tree",
        dest="tree_path",
        type=Path,
        default=TREE_CACHE_PATH,
        help="Cached PageIndex tree JSON path.",
    )
    args = parser.parse_args()
    decision = run_decision_command(args.case_path, args.tree_path)
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
