#!/usr/bin/env python3
"""Generate a human-readable drift / diff report."""
from __future__ import annotations

import argparse
import json
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--from-snapshot", default=None)
    parser.add_argument("--to-snapshot", default=None)
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    result = subprocess.run(
        ["archlens", "drift", "--repo", args.repo_path, "--output", "json"],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout or "{}")
    if args.output == "json":
        print(json.dumps(data, indent=2))
        return

    summary = data.get("summary", {})
    lines = [
        "## Architecture Drift Report",
        "",
        "### Summary",
        f"- **New elements**: {summary.get('added_elements', 0)} ({', '.join(data.get('added_elements', [])) or '—'})",
        f"- **Removed elements**: {summary.get('removed_elements', 0)} ({', '.join(data.get('removed_elements', [])) or '—'})",
        f"- **Modified elements**: {summary.get('modified_elements', 0)}",
        f"- **New relationships**: {summary.get('added_relationships', 0)}",
        f"- **Broken relationships**: {summary.get('removed_relationships', 0)}",
        "",
    ]
    for m in data.get("modified_elements", []):
        if isinstance(m, dict):
            lines.append(f"- Modified `{m.get('name')}`: {m.get('diff')}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
