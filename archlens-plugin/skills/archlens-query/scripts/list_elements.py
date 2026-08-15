#!/usr/bin/env python3
"""List architecture elements with optional filters."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--stereotype", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("--group-by", default=None)
    parser.add_argument("--file-pattern", default=None)
    parser.add_argument("--output", choices=["json", "table", "mermaid"], default="table")
    args = parser.parse_args()

    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(args.repo_path)).get_latest_snapshot()
    if not snap:
        print("ERROR: No snapshots", file=sys.stderr)
        sys.exit(1)

    elements = snap.elements
    if args.stereotype:
        elements = [e for e in elements if e.stereotype.lower() == args.stereotype.lower()]
    if args.language:
        elements = [e for e in elements if e.language.lower() == args.language.lower()]
    if args.file_pattern:
        import fnmatch

        elements = [e for e in elements if fnmatch.fnmatch(e.file_path, args.file_pattern)]

    if args.group_by in ("layer", "stereotype"):
        groups: dict[str, int] = defaultdict(int)
        for e in elements:
            groups[e.stereotype] += 1
        data = [{"stereotype": k, "count": v} for k, v in sorted(groups.items(), key=lambda x: -x[1])]
    else:
        data = [
            {
                "name": e.name,
                "stereotype": e.stereotype,
                "language": e.language,
                "file_path": e.file_path,
            }
            for e in elements
        ]

    if args.output == "json":
        print(json.dumps(data, indent=2))
    elif args.output == "mermaid":
        print("graph LR")
        for e in elements:
            print(f'  {e.name}["{e.name}<br/>«{e.stereotype}»"]')
    else:
        for row in data:
            print(" | ".join(str(v) for v in row.values()))


if __name__ == "__main__":
    main()
