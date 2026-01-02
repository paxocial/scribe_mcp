#!/usr/bin/env python3
"""Reindex managed docs/logs into the vector indexer (deprecated wrapper).

Prefer scripts/reindex_vector.py for unified doc/log reindexing.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List


ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT_DIR

# Ensure Scribe sees this repo as its root and keeps state under the repo
# instead of ~/.scribe when the CLI is used.
os.environ.setdefault("SCRIBE_ROOT", str(REPO_ROOT))
os.environ.setdefault("SCRIBE_STATE_PATH", str(REPO_ROOT / "tmp_state_cli.json"))

PARENT_ROOT = REPO_ROOT.parent
if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

from scripts.reindex_vector import main as reindex_vector_main


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reindex Scribe-managed docs into the vector indexer (deprecated)."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to use (defaults to current scribe_mcp root).",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    print("⚠️  scripts/reindex_docs.py is deprecated. Use scripts/reindex_vector.py instead.")
    return reindex_vector_main(["--docs", "--repo-root", str(args.repo_root)])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
