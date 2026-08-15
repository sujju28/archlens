#!/usr/bin/env python3
"""Check whether the latest snapshot matches current HEAD."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    args = parser.parse_args()
    db = Path(args.repo_path) / ".archlens" / "archlens.db"
    if not db.exists():
        print("STALE (no database)")
        sys.exit(0)

    head = subprocess.run(
        ["git", "-C", args.repo_path, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    commit = head.stdout.strip() if head.returncode == 0 else None

    try:
        from archlens.storage.sqlite_store import SQLiteStore

        snap = SQLiteStore(db).get_latest_snapshot()
        if not snap:
            print("STALE (no snapshots)")
        elif commit and snap.commit_sha == commit:
            print(f"FRESH (commit={commit}, snapshot={snap.snapshot_id})")
        else:
            print(
                f"STALE (snapshot_commit={snap.commit_sha if snap else None}, head={commit})"
            )
    except Exception as e:
        print(f"STALE ({e})")


if __name__ == "__main__":
    main()
