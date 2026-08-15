#!/usr/bin/env python3
"""Estimate effort from an impact JSON report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

LOC_BY_STEREOTYPE = {
    "Controller": 25,
    "Service": 40,
    "Repository": 20,
    "UI Component": 30,
    "Configuration": 15,
    "Gateway": 35,
    "Middleware": 25,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--impact-json", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.impact_json).read_text(encoding="utf-8"))
    affected = data.get("directly_affected", []) + data.get("transitively_affected", [])
    breakdown = []
    total = 0
    for a in affected:
        loc = LOC_BY_STEREOTYPE.get(a.get("stereotype", ""), 20)
        # Transitive gets half weight
        if a.get("hops", 1) > 1:
            loc = max(10, loc // 2)
        total += loc
        breakdown.append(
            {
                "element": a.get("name"),
                "estimated_lines": loc,
                "type": "interface_update" if a.get("hops", 1) == 1 else "potential_update",
            }
        )

    # Changed elements themselves
    for name in data.get("changed_elements", []):
        total += 30
        breakdown.append({"element": name, "estimated_lines": 30, "type": "direct_change"})

    complexity = "LOW" if total < 80 else "MEDIUM" if total < 200 else "HIGH"
    print(
        json.dumps(
            {
                "total_files_affected": len({a.get("name") for a in affected}) + len(data.get("changed_elements", [])),
                "estimated_lines_changed": total,
                "complexity": complexity,
                "breakdown": breakdown,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
