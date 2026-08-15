"""Multi-repo architecture aggregation.

Combines exported `architecture.json` snapshots (or live scans) from multiple
repositories into a unified system-level ArchSnapshot.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from archlens.models import ArchElement, ArchRelationship, ArchSnapshot


def load_architecture_json(path: Path | str) -> ArchSnapshot:
    """Load an ArchLens export JSON into an ArchSnapshot."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ArchSnapshot.model_validate(data)


def aggregate_snapshots(
    snapshots: list[ArchSnapshot],
    *,
    system_name: str = "Distributed System",
    prefix_ids: bool = True,
) -> ArchSnapshot:
    """
    Merge multiple repo snapshots into one system view.

    Element/relationship IDs are optionally prefixed with a short repo slug
    to avoid collisions across services.
    """
    if not snapshots:
        raise ValueError("No snapshots to aggregate")

    elements: list[ArchElement] = []
    relationships: list[ArchRelationship] = []
    repo_map: list[dict] = []

    for snap in snapshots:
        slug = _repo_slug(snap)
        repo_map.append(
            {
                "slug": slug,
                "repo_path": snap.repo_path,
                "commit_sha": snap.commit_sha,
                "snapshot_id": snap.snapshot_id,
                "element_count": len(snap.elements),
            }
        )
        id_map: dict[str, str] = {}
        for el in snap.elements:
            new_id = f"{slug}::{el.id}" if prefix_ids else el.id
            id_map[el.id] = new_id
            meta = dict(el.metadata or {})
            meta["source_repo"] = snap.repo_path
            meta["source_slug"] = slug
            if "container" not in meta:
                meta["container"] = slug
            elements.append(
                el.model_copy(
                    update={
                        "id": new_id,
                        "metadata": meta,
                        "c4_level": "Container" if el.c4_level == "Component" else el.c4_level,
                    }
                )
            )
        for rel in snap.relationships:
            src = id_map.get(rel.source_id, rel.source_id)
            tgt = id_map.get(rel.target_id, rel.target_id)
            if prefix_ids:
                if "::" not in src:
                    src = f"{slug}::{src}"
                if "::" not in tgt:
                    tgt = f"{slug}::{tgt}"
            relationships.append(
                ArchRelationship(
                    source_id=src,
                    target_id=tgt,
                    rel_type=rel.rel_type,
                    description=rel.description,
                    technology=rel.technology,
                )
            )

    return ArchSnapshot(
        snapshot_id=str(uuid.uuid4()),
        commit_sha="aggregated",
        timestamp=datetime.now(UTC),
        branch=None,
        repo_path="aggregated",
        elements=elements,
        relationships=relationships,
        metadata={
            "project_name": system_name,
            "aggregated": True,
            "repos": repo_map,
            "archlens_version": "0.1.0",
        },
    )


def aggregate_from_paths(
    paths: list[Path | str],
    *,
    system_name: str = "Distributed System",
) -> ArchSnapshot:
    """Load architecture JSON files and aggregate them."""
    snaps = [load_architecture_json(p) for p in paths]
    return aggregate_snapshots(snaps, system_name=system_name)


def _repo_slug(snap: ArchSnapshot) -> str:
    meta_name = (snap.metadata or {}).get("project_name")
    if meta_name and meta_name not in ("My Application", "Architecture Report"):
        return _slugify(str(meta_name))
    path = Path(snap.repo_path)
    name = path.name if path.name not in ("", ".", "aggregated") else "repo"
    return _slugify(name)


def _slugify(value: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in value.strip().lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "repo"
