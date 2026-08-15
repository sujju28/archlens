#!/usr/bin/env python3
"""Generate ARCHITECTURE.md report."""
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--output", default="docs/ARCHITECTURE.md")
    args = parser.parse_args()

    result = subprocess.run(
        ["archlens", "report", "--repo", args.repo_path, "--output", args.output],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    print(result.stdout or f"Report written to {args.output}")


if __name__ == "__main__":
    main()
