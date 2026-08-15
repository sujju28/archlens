#!/usr/bin/env python3
"""Suggest changes from an impact JSON report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--impact-json", required=True)
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    data = json.loads(Path(args.impact_json).read_text(encoding="utf-8"))
    lines = ["# Suggested Changes", ""]
    for s in data.get("suggested_changes", []):
        lines.append(f"- {s}")
    for a in data.get("directly_affected", []):
        lines.append(
            f"- Review `{a['name']}` ({a.get('stereotype')}) — {a.get('reason')} "
            f"[risk={a.get('risk')}]"
        )
    for a in data.get("transitively_affected", [])[:10]:
        lines.append(
            f"- Optionally review `{a['name']}` (transitive, hops={a.get('hops')})"
        )

    if args.output == "json":
        print(json.dumps({"suggestions": lines[2:]}, indent=2))
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
