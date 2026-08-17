"""Canonical data model (CDM) construction from Entity stereotypes."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from archlens.extractors.entity_metadata import fk_target_table
from archlens.models import ArchElement, ArchRelationship, ArchSnapshot, RelType


@dataclass
class DataEntity:
    id: str
    name: str
    table_name: str
    columns: list[str] = field(default_factory=list)
    fk_columns: list[str] = field(default_factory=list)
    file_path: str = ""
    kind: str = "entity"
    container: str | None = None


@dataclass
class DataAssociation:
    source_table: str
    target_table: str
    fk_column: str
    source_id: str
    target_id: str


@dataclass
class CanonicalDataModel:
    entities: list[DataEntity]
    associations: list[DataAssociation]
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "table_name": e.table_name,
                    "columns": e.columns,
                    "fk_columns": e.fk_columns,
                    "file_path": e.file_path,
                    "kind": e.kind,
                    "container": e.container,
                }
                for e in self.entities
            ],
            "associations": [
                {
                    "source_table": a.source_table,
                    "target_table": a.target_table,
                    "fk_column": a.fk_column,
                    "source_id": a.source_id,
                    "target_id": a.target_id,
                }
                for a in self.associations
            ],
            "stats": self.stats,
        }


def link_entity_foreign_keys(
    elements: list[ArchElement],
    relationships: list[ArchRelationship],
) -> list[ArchRelationship]:
    """Add REFERENCES relationships from Entity fk_columns → target Entity."""
    entities = [e for e in elements if e.stereotype == "Entity"]
    by_table: dict[str, ArchElement] = {}
    for e in entities:
        table = (e.metadata or {}).get("table_name") or _table_from_name(e.name)
        if table and table not in by_table:
            by_table[table] = e
        # Also index I_C_Order / X_C_Order → C_Order
        if e.name.startswith(("I_", "X_")) and len(e.name) > 2:
            by_table.setdefault(e.name[2:], e)

    existing = {(r.source_id, r.target_id, r.rel_type) for r in relationships}
    added: list[ArchRelationship] = []

    for e in entities:
        meta = e.metadata or {}
        for fk in meta.get("fk_columns") or []:
            target_table = fk_target_table(fk)
            target = by_table.get(target_table)
            if not target or target.id == e.id:
                continue
            key = (e.id, target.id, RelType.REFERENCES.value)
            if key in existing:
                continue
            existing.add(key)
            added.append(
                ArchRelationship(
                    source_id=e.id,
                    target_id=target.id,
                    rel_type=RelType.REFERENCES.value,
                    description=f"FK {fk} → {target_table}",
                    technology="data model",
                )
            )
    return relationships + added


def build_canonical_data_model(snapshot: ArchSnapshot) -> CanonicalDataModel:
    """Build a CDM view from Entity elements in a snapshot."""
    # Prefer I_* over X_* for the same table (interfaces carry the contract)
    by_table: dict[str, ArchElement] = {}
    for e in snapshot.elements:
        if e.stereotype != "Entity":
            continue
        table = (e.metadata or {}).get("table_name") or _table_from_name(e.name)
        if not table:
            continue
        existing = by_table.get(table)
        if existing is None:
            by_table[table] = e
            continue
        # Prefer richer column metadata / I_ over X_
        score_new = _entity_score(e)
        score_old = _entity_score(existing)
        if score_new > score_old:
            by_table[table] = e

    entities: list[DataEntity] = []
    for table, e in sorted(by_table.items(), key=lambda x: x[0].lower()):
        meta = e.metadata or {}
        entities.append(
            DataEntity(
                id=e.id,
                name=e.name,
                table_name=table,
                columns=list(meta.get("columns") or []),
                fk_columns=list(meta.get("fk_columns") or []),
                file_path=e.file_path,
                kind=str(meta.get("kind") or "entity"),
                container=(meta.get("container") if isinstance(meta.get("container"), str) else None)
                or (e.metadata.get("container") if e.metadata else None),
            )
        )

    table_ids = {e.table_name: e.id for e in entities}
    associations: list[DataAssociation] = []
    seen: set[tuple[str, str, str]] = set()
    for e in entities:
        for fk in e.fk_columns:
            tgt = fk_target_table(fk)
            if tgt not in table_ids or tgt == e.table_name:
                continue
            key = (e.table_name, tgt, fk)
            if key in seen:
                continue
            seen.add(key)
            associations.append(
                DataAssociation(
                    source_table=e.table_name,
                    target_table=tgt,
                    fk_column=fk,
                    source_id=e.id,
                    target_id=table_ids[tgt],
                )
            )

    # Also harvest REFERENCES from snapshot relationships
    id_to_table = {e.id: e.table_name for e in entities}
    for rel in snapshot.relationships:
        if rel.rel_type != RelType.REFERENCES.value:
            continue
        st = id_to_table.get(rel.source_id)
        tt = id_to_table.get(rel.target_id)
        if not st or not tt:
            continue
        fk = (rel.description or "").replace("FK ", "").split(" →")[0].strip() or "FK"
        key = (st, tt, fk)
        if key in seen:
            continue
        seen.add(key)
        associations.append(
            DataAssociation(
                source_table=st,
                target_table=tt,
                fk_column=fk,
                source_id=rel.source_id,
                target_id=rel.target_id,
            )
        )

    kinds = Counter(e.kind for e in entities)
    return CanonicalDataModel(
        entities=entities,
        associations=associations,
        stats={
            "entity_count": len(entities),
            "association_count": len(associations),
            "kinds": dict(kinds),
            "columns_total": sum(len(e.columns) for e in entities),
        },
    )


def _table_from_name(name: str) -> str:
    if name.startswith(("I_", "X_")) and len(name) > 2:
        return name[2:]
    for suffix in ("Entity", "Model", "PO"):
        if name.endswith(suffix) and name != suffix:
            return name[: -len(suffix)]
    return name


def _entity_score(e: ArchElement) -> int:
    meta = e.metadata or {}
    score = len(meta.get("columns") or [])
    if e.name.startswith("I_"):
        score += 1000
    if meta.get("table_name"):
        score += 50
    return score
