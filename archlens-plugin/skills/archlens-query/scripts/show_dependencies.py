#!/usr/bin/env python3
"""Show upstream/downstream dependencies for an element."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--element", required=True)
    parser.add_argument("--direction", choices=["upstream", "downstream", "both"], default="both")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--output", choices=["json", "table", "mermaid"], default="table")
    args = parser.parse_args()

    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(args.repo_path)).get_latest_snapshot()
    if not snap:
        print("ERROR: No snapshots", file=sys.stderr)
        sys.exit(1)

    by_id = {e.id: e for e in snap.elements}
    targets = {
        e.id
        for e in snap.elements
        if e.name.lower() == args.element.lower() or args.element.lower() in e.id.lower()
    }
    if not targets:
        print(json.dumps({"error": f"Element not found: {args.element}"}))
        sys.exit(1)

    upstream: dict[str, list[tuple[str, str]]] = {}
    downstream: dict[str, list[tuple[str, str]]] = {}
    for r in snap.relationships:
        upstream.setdefault(r.target_id, []).append((r.source_id, r.rel_type))
        downstream.setdefault(r.source_id, []).append((r.target_id, r.rel_type))

    results = []

    def walk(adj, start_ids, direction):
        visited = set(start_ids)
        q = deque((sid, 0) for sid in start_ids)
        while q:
            cur, depth = q.popleft()
            if depth >= args.depth:
                continue
            for nid, rel in adj.get(cur, []):
                if nid in visited:
                    continue
                visited.add(nid)
                el = by_id.get(nid)
                if not el:
                    continue
                results.append(
                    {
                        "name": el.name,
                        "stereotype": el.stereotype,
                        "rel_type": rel,
                        "direction": direction,
                        "hops": depth + 1,
                        "file_path": el.file_path,
                    }
                )
                q.append((nid, depth + 1))

    if args.direction in ("upstream", "both"):
        walk(upstream, targets, "upstream")
    if args.direction in ("downstream", "both"):
        walk(downstream, targets, "downstream")

    if args.output == "json":
        print(json.dumps({"results": results}, indent=2))
    elif args.output == "mermaid":
        print("graph LR")
        for row in results:
            print(f'  {args.element} -->|{row["rel_type"]}| {row["name"]}')
    else:
        for row in results:
            print(
                f"{row['direction']:10} {row['name']:30} {row['rel_type']:10} hops={row['hops']}"
            )


if __name__ == "__main__":
    main()
