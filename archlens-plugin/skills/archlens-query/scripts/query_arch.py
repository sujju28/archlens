#!/usr/bin/env python3
"""Natural language → architecture query translator."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

QUERY_PATTERNS = [
    {
        "patterns": [r"what depends on (\w+)", r"who uses (\w+)", r"dependents of (\w+)"],
        "mode": "upstream",
    },
    {
        "patterns": [r"what does (\w+) depend on", r"dependencies of (\w+)"],
        "mode": "downstream",
    },
    {
        "patterns": [r"(?:show|list|find) (?:all )?(\w+)s?\b"],
        "mode": "stereotype",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", choices=["json", "table"], default="table")
    args = parser.parse_args()

    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(args.repo_path)).get_latest_snapshot()
    if not snap:
        print(json.dumps({"error": "No snapshots. Run archlens scan first."}))
        sys.exit(1)

    q = args.query.lower()
    results = []
    query_type = "all"

    for pattern_def in QUERY_PATTERNS:
        for pattern in pattern_def["patterns"]:
            match = re.search(pattern, q)
            if not match:
                continue
            token = match.group(1)
            if pattern_def["mode"] == "stereotype":
                stereo = token.rstrip("s").capitalize()
                results = [
                    {
                        "name": e.name,
                        "stereotype": e.stereotype,
                        "file_path": e.file_path,
                    }
                    for e in snap.elements
                    if e.stereotype.lower() == stereo.lower()
                ]
                query_type = "elements by stereotype"
            else:
                by_id = {e.id: e for e in snap.elements}
                targets = {
                    e.id
                    for e in snap.elements
                    if e.name.lower() == token.lower() or token.lower() in e.id.lower()
                }
                direction = pattern_def["mode"]
                for r in snap.relationships:
                    if direction == "upstream" and r.target_id in targets:
                        src = by_id.get(r.source_id)
                        if src:
                            results.append(
                                {
                                    "name": src.name,
                                    "stereotype": src.stereotype,
                                    "rel_type": r.rel_type,
                                    "file_path": src.file_path,
                                }
                            )
                    if direction == "downstream" and r.source_id in targets:
                        tgt = by_id.get(r.target_id)
                        if tgt:
                            results.append(
                                {
                                    "name": tgt.name,
                                    "stereotype": tgt.stereotype,
                                    "rel_type": r.rel_type,
                                    "file_path": tgt.file_path,
                                }
                            )
                query_type = f"{direction} dependencies"
            break
        if results or query_type != "all":
            break

    if not results and query_type == "all":
        results = [
            {"name": e.name, "stereotype": e.stereotype, "file_path": e.file_path}
            for e in snap.elements
        ]
        query_type = "all elements"

    payload = {"query_type": query_type, "result_count": len(results), "results": results}
    if args.output == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(f"Query: {args.query}")
        print(f"Type: {query_type}")
        print(f"Results: {len(results)}")
        for row in results:
            print(" | ".join(str(v) for v in row.values()))


if __name__ == "__main__":
    main()
