"""SQLite storage for architecture snapshots."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from archlens.models import ArchElement, ArchRelationship, ArchSnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    branch TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    repo_path TEXT NOT NULL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS elements (
    id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    name TEXT NOT NULL,
    stereotype TEXT,
    c4_level TEXT DEFAULT 'Component',
    language TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    annotations_json TEXT,
    extends_id TEXT,
    implements_json TEXT,
    metadata_json TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
    PRIMARY KEY (id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    description TEXT,
    technology TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS change_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_id TEXT NOT NULL,
    from_snapshot TEXT NOT NULL,
    to_snapshot TEXT NOT NULL,
    change_type TEXT NOT NULL,
    diff_summary TEXT,
    FOREIGN KEY (from_snapshot) REFERENCES snapshots(id),
    FOREIGN KEY (to_snapshot) REFERENCES snapshots(id)
);

CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(snapshot_id, source_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(snapshot_id, target_id);
CREATE INDEX IF NOT EXISTS idx_elements_file ON elements(snapshot_id, file_path);
CREATE INDEX IF NOT EXISTS idx_elements_stereotype ON elements(snapshot_id, stereotype);
"""


class SQLiteStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def save_snapshot(self, snapshot: ArchSnapshot) -> str:
        snapshot_id = snapshot.snapshot_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO snapshots
                (id, commit_sha, branch, timestamp, repo_path, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    snapshot.commit_sha,
                    snapshot.branch,
                    snapshot.timestamp.isoformat(),
                    snapshot.repo_path,
                    json.dumps(snapshot.metadata),
                ),
            )
            conn.execute("DELETE FROM elements WHERE snapshot_id = ?", (snapshot_id,))
            conn.execute("DELETE FROM relationships WHERE snapshot_id = ?", (snapshot_id,))

            for el in snapshot.elements:
                conn.execute(
                    """
                    INSERT INTO elements (
                        id, snapshot_id, name, stereotype, c4_level, language,
                        file_path, line_start, line_end, annotations_json,
                        extends_id, implements_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        el.id,
                        snapshot_id,
                        el.name,
                        el.stereotype,
                        el.c4_level,
                        el.language,
                        el.file_path,
                        el.line_start,
                        el.line_end,
                        json.dumps(el.annotations),
                        el.extends,
                        json.dumps(el.implements),
                        json.dumps(el.metadata),
                    ),
                )

            for rel in snapshot.relationships:
                conn.execute(
                    """
                    INSERT INTO relationships
                    (snapshot_id, source_id, target_id, rel_type, description, technology)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        rel.source_id,
                        rel.target_id,
                        rel.rel_type,
                        rel.description,
                        rel.technology,
                    ),
                )
            conn.commit()
        return snapshot_id

    def get_snapshot(self, snapshot_id: str) -> ArchSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_snapshot(conn, row)

    def get_latest_snapshot(self) -> ArchSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return self._row_to_snapshot(conn, row)

    def get_snapshot_by_commit(self, commit_sha: str) -> ArchSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE commit_sha = ? ORDER BY timestamp DESC LIMIT 1",
                (commit_sha,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_snapshot(conn, row)

    def list_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, commit_sha, branch, timestamp, repo_path FROM snapshots "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_change(
        self,
        element_id: str,
        from_snapshot: str,
        to_snapshot: str,
        change_type: str,
        diff_summary: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO change_history
                (element_id, from_snapshot, to_snapshot, change_type, diff_summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (element_id, from_snapshot, to_snapshot, change_type, diff_summary),
            )
            conn.commit()

    def _row_to_snapshot(self, conn: sqlite3.Connection, row: sqlite3.Row) -> ArchSnapshot:
        snapshot_id = row["id"]
        elements = []
        for er in conn.execute(
            "SELECT * FROM elements WHERE snapshot_id = ?", (snapshot_id,)
        ):
            elements.append(
                ArchElement(
                    id=er["id"],
                    name=er["name"],
                    stereotype=er["stereotype"] or "Unknown",
                    c4_level=er["c4_level"] or "Component",
                    language=er["language"],
                    file_path=er["file_path"],
                    line_start=er["line_start"],
                    line_end=er["line_end"],
                    annotations=json.loads(er["annotations_json"] or "[]"),
                    extends=er["extends_id"],
                    implements=json.loads(er["implements_json"] or "[]"),
                    metadata=json.loads(er["metadata_json"] or "{}"),
                )
            )

        relationships = []
        for rr in conn.execute(
            "SELECT * FROM relationships WHERE snapshot_id = ?", (snapshot_id,)
        ):
            relationships.append(
                ArchRelationship(
                    source_id=rr["source_id"],
                    target_id=rr["target_id"],
                    rel_type=rr["rel_type"],
                    description=rr["description"],
                    technology=rr["technology"],
                )
            )

        ts = row["timestamp"]
        if isinstance(ts, str):
            try:
                timestamp = datetime.fromisoformat(ts)
            except ValueError:
                timestamp = datetime.now(UTC)
        else:
            timestamp = datetime.now(UTC)

        return ArchSnapshot(
            snapshot_id=snapshot_id,
            commit_sha=row["commit_sha"],
            timestamp=timestamp,
            branch=row["branch"],
            repo_path=row["repo_path"],
            elements=elements,
            relationships=relationships,
            metadata=json.loads(row["metadata_json"] or "{}"),
        )


def default_db_path(repo_path: Path | str) -> Path:
    return Path(repo_path) / ".archlens" / "archlens.db"
