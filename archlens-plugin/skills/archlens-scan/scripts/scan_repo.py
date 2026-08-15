#!/usr/bin/env python3
"""Scan a repository and create an architecture snapshot."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan repo architecture")
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    commit = args.commit
    if not commit:
        result = subprocess.run(
            ["git", "-C", args.repo_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        commit = result.stdout.strip() if result.returncode == 0 else "unknown"

    scan = subprocess.run(
        ["archlens", "scan", "--repo", args.repo_path, "--commit", commit],
        capture_output=True,
        text=True,
    )
    if scan.returncode != 0:
        print(f"ERROR: Scan failed: {scan.stderr}", file=sys.stderr)
        sys.exit(1)

    export = subprocess.run(
        ["archlens", "export", "--repo", args.repo_path, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(export.stdout)
        print(f"Scan complete. Results written to {args.output}")
    else:
        data = json.loads(export.stdout)
        elements = data.get("elements", [])
        relationships = data.get("relationships", [])
        stereotypes: dict[str, int] = {}
        for el in elements:
            s = el.get("stereotype", "Unknown")
            stereotypes[s] = stereotypes.get(s, 0) + 1
        print(f"Scan complete: {len(elements)} elements, {len(relationships)} relationships")
        for s, count in sorted(stereotypes.items()):
            print(f"  {s}: {count}")


if __name__ == "__main__":
    main()
