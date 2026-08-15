#!/usr/bin/env python3
"""Natural language → architecture query translator (3-tier)."""
from __future__ import annotations

import argparse
import json
import sys

from archlens.analysis.nl_query import run_nl_query
from archlens.storage.sqlite_store import SQLiteStore, default_db_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", choices=["json", "table"], default="table")
    args = parser.parse_args()

    snap = SQLiteStore(default_db_path(args.repo_path)).get_latest_snapshot()
    if not snap:
        print(json.dumps({"error": "No snapshots. Run archlens scan first."}))
        sys.exit(1)

    result = run_nl_query(snap, args.query)
    if args.output == "json":
        print(json.dumps(result, indent=2))
        return

    if result.get("tier") == "tier3":
        print(f"Error: {result.get('error')}", file=sys.stderr)
        print(result.get("hint", ""), file=sys.stderr)
        sys.exit(1)

    print(f"Query: {args.query}")
    print(f"Tier: {result.get('tier')} | Type: {result.get('query_type')}")
    print(f"Results: {result.get('result_count', 0)}")
    for row in result.get("results") or []:
        print(" | ".join(str(v) for v in row.values()))


if __name__ == "__main__":
    main()
