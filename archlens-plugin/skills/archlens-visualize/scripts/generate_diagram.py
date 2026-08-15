#!/usr/bin/env python3
"""Generate architecture diagrams."""
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--level", default="component")
    parser.add_argument("--format", default="mermaid")
    parser.add_argument("--highlight", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    cmd = [
        "archlens",
        "diagram",
        "--repo",
        args.repo_path,
        "--level",
        args.level,
        "--format",
        args.format,
    ]
    if args.highlight:
        cmd.extend(["--highlight", args.highlight])
    if args.output:
        cmd.extend(["--output", args.output])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    print(result.stdout)


if __name__ == "__main__":
    main()
