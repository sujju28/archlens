#!/usr/bin/env python3
"""Impact analysis helper script."""
from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--elements", nargs="*", default=None)
    parser.add_argument("--depth", type=int, default=5)
    parser.add_argument("--output", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    from archlens.analysis.impact_analyzer import ImpactAnalyzer
    from archlens.config import load_config
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(args.repo_path)).get_latest_snapshot()
    if not snap:
        print("ERROR: No snapshots. Run 'archlens scan' first.", file=sys.stderr)
        sys.exit(1)

    report = ImpactAnalyzer(load_config(args.repo_path)).analyze(
        snap, files=args.files, elements=args.elements, depth=args.depth
    )
    print(json.dumps(report.model_dump(), indent=2))


if __name__ == "__main__":
    main()
