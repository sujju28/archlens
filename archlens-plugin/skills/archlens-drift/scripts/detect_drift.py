#!/usr/bin/env python3
"""Detect architectural drift."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    cmd = ["archlens", "drift", "--repo", args.repo_path, "--output", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    else:
        print(json.dumps({"error": result.stderr}))
    if result.returncode == 2:
        sys.exit(2)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
