"""Canonical data model (CDM) construction from Entity stereotypes."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archlens.analysis.cdm_semantics import (
    CdmSemantics,
    is_suppressed,
    load_cdm_semantics,
    resolve_canonical_name,
)
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
    language: str = ""
    container: str | None = None
    owner: str | None = None
    canonical_name: str | None = None
    aliases: list[str] = field(default_factory=list)
    source_repos: list[str] = field(default_factory=list)


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
                    "language": e.language,
                    "container": e.container,
                    "owner": e.owner,
                    "canonical_name": e.canonical_name,
                    "aliases": e.aliases,
                    "source_repos": e.source_repos,
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
    by_table_ci: dict[str, ArchElement] = {}
    by_name_ci: dict[str, ArchElement] = {}
    for e in entities:
        table = (e.metadata or {}).get("table_name") or _table_from_name(e.name)
        if table:
            by_table_ci.setdefault(str(table).lower(), e)
        by_name_ci.setdefault(e.name.lower(), e)
        if e.name.startswith(("I_", "X_", "DCL")) and len(e.name) > 2:
            prefix_len = 3 if e.name.upper().startswith("DCL") else 2
            by_table_ci.setdefault(e.name[prefix_len:].lower(), e)

    existing = {(r.source_id, r.target_id, r.rel_type) for r in relationships}
    added: list[ArchRelationship] = []

    for e in entities:
        meta = e.metadata or {}
        for fk in meta.get("fk_columns") or []:
            target_table = fk_target_table(fk)
            target = by_table_ci.get(target_table.lower()) or by_name_ci.get(
                target_table.lower()
            )
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


def basic_data_model_summary(snapshot: ArchSnapshot) -> dict[str, Any]:
    """Lightweight cross-stack data-model inventory (entities, repos, datasets)."""
    entities = [e for e in snapshot.elements if e.stereotype == "Entity"]
    repos = [e for e in snapshot.elements if e.stereotype == "Repository"]
    shared = [e for e in snapshot.elements if e.stereotype == "Shared Data"]
    datasets = [
        e
        for e in snapshot.elements
        if (e.metadata or {}).get("kind") == "dataset" or e.language == "dataset"
    ]
    with_columns = sum(1 for e in entities if (e.metadata or {}).get("columns"))
    by_lang: Counter[str] = Counter()
    tables: list[tuple[str, int, str]] = []
    for e in entities:
        by_lang[e.language or (e.metadata or {}).get("language") or "unknown"] += 1
        table = (e.metadata or {}).get("table_name") or e.name
        cols = (e.metadata or {}).get("columns") or []
        tables.append((str(table), len(cols), e.language or ""))

    access_rels = [
        r
        for r in snapshot.relationships
        if r.rel_type
        in (
            "accesses_table",
            "writes_table",
            "references",
            "reads_dataset",
            "writes_dataset",
        )
    ]
    sample_tables = [
        {"table": t, "columns": n, "language": lang}
        for t, n, lang in sorted(tables, key=lambda x: (-x[1], x[0].lower()))[:15]
    ]
    by_repo: Counter[str] = Counter()
    for e in entities:
        slug = (e.metadata or {}).get("source_slug") or (e.metadata or {}).get(
            "source_repo"
        )
        if slug:
            by_repo[str(slug)] += 1
    return {
        "entity_count": len(entities),
        "entities_with_columns": with_columns,
        "repository_count": len(repos),
        "shared_data_count": len(shared),
        "dataset_count": len(datasets),
        "data_relationships": len(access_rels),
        "entities_by_language": dict(by_lang),
        "entities_by_repo": dict(by_repo),
        "sample_entities": sorted({e.name for e in entities})[:20],
        "sample_repositories": sorted({e.name for e in repos})[:15],
        "sample_tables": sample_tables,
        "aggregated": bool((snapshot.metadata or {}).get("aggregated")),
    }


def basic_data_model_markdown(snapshot: ArchSnapshot, *, title: str | None = None) -> str:
    """Standalone basic data-model inventory report."""
    summary = basic_data_model_summary(snapshot)
    project = title or snapshot.metadata.get("project_name") or "Data model"
    lines = [
        f"# {project} — Basic data model",
        "",
        "Inventory of data-facing types extracted from code "
        "(entities, repositories, shared data / datasets). "
        "For columns, FKs, and ER diagrams with optional semantic overlays, "
        "run `archlens cdm`.",
        "",
        f"- **Entities:** {summary['entity_count']} "
        f"({summary['entities_with_columns']} with columns)",
        f"- **Repositories:** {summary['repository_count']}",
        f"- **Shared data / datasets:** "
        f"{summary['shared_data_count']} / {summary['dataset_count']}",
        f"- **Data relationships:** {summary['data_relationships']}",
    ]
    if summary.get("aggregated"):
        lines.append("- **Scope:** aggregated multi-repo snapshot")
    if summary.get("entities_by_language"):
        langs = ", ".join(
            f"{k}: {v}" for k, v in sorted(summary["entities_by_language"].items())
        )
        lines.append(f"- **Entities by language:** {langs}")
    if summary.get("entities_by_repo"):
        repos = ", ".join(
            f"{k}: {v}" for k, v in sorted(summary["entities_by_repo"].items())
        )
        lines.append(f"- **Entities by source repo:** {repos}")
    if summary.get("sample_tables"):
        shown = []
        for row in summary["sample_tables"][:12]:
            label = f"`{row['table']}` ({row['columns']} cols"
            if row.get("language"):
                label += f", {row['language']}"
            label += ")"
            shown.append(label)
        lines.append("- **Sample tables:** " + ", ".join(shown))
    if summary.get("sample_entities"):
        lines.append(
            "- **Sample entities:** "
            + ", ".join(f"`{n}`" for n in summary["sample_entities"][:12])
        )
    if summary.get("sample_repositories"):
        lines.append(
            "- **Sample repositories:** "
            + ", ".join(f"`{n}`" for n in summary["sample_repositories"][:10])
        )
    lines.append("")
    return "\n".join(lines)


def build_canonical_data_model(
    snapshot: ArchSnapshot,
    *,
    semantics: CdmSemantics | None = None,
    semantics_path: Path | str | None = None,
    repo: Path | str | None = None,
) -> CanonicalDataModel:
    """Build a CDM view from Entity elements; optionally apply semantic overlays."""
    sem = semantics or load_cdm_semantics(repo=repo, path=semantics_path)

    # physical_key → list of contributing elements (for multi-repo merge)
    physical: dict[str, list[ArchElement]] = defaultdict(list)
    physical_display: dict[str, str] = {}
    for e in snapshot.elements:
        if e.stereotype != "Entity":
            continue
        table = (e.metadata or {}).get("table_name") or _table_from_name(e.name)
        if not table:
            continue
        key = str(table).lower()
        if is_suppressed(str(table), sem) or is_suppressed(key, sem):
            continue
        physical[key].append(e)
        if key not in physical_display or (e.metadata or {}).get("table_name"):
            physical_display[key] = str(
                (e.metadata or {}).get("table_name") or physical_display.get(key) or table
            )

    # Map physical → canonical and merge
    canonical_buckets: dict[str, list[tuple[str, ArchElement]]] = defaultdict(list)
    for pkey, els in physical.items():
        display = physical_display.get(pkey, pkey)
        # Prefer slug-qualified alias lookup for aggregated snaps
        for e in els:
            slug = (e.metadata or {}).get("source_slug")
            candidates = [display, pkey]
            if slug:
                candidates.extend([f"{slug}::{display}", f"{slug}::{pkey}"])
            canon = display
            for c in candidates:
                resolved = resolve_canonical_name(str(c), sem)
                if resolved != c:
                    canon = resolved
                    break
            else:
                canon = resolve_canonical_name(display, sem)
            if is_suppressed(canon, sem):
                continue
            canonical_buckets[canon.lower()].append((display, e))

    entities: list[DataEntity] = []
    for ckey, members in sorted(canonical_buckets.items(), key=lambda x: x[0]):
        # Pick richest element as primary
        best_el = max((m[1] for m in members), key=_entity_score)
        alias_names = sorted({m[0] for m in members if m[0].lower() != ckey})
        # Also include other physical names
        for m in members:
            if m[0] not in alias_names and m[0].lower() != ckey:
                alias_names.append(m[0])
        alias_names = sorted(set(alias_names), key=str.lower)

        columns: list[str] = []
        fks: list[str] = []
        source_repos: list[str] = []
        for _disp, el in members:
            meta = el.metadata or {}
            for col in meta.get("columns") or []:
                if col not in columns:
                    columns.append(col)
            for fk in meta.get("fk_columns") or []:
                if fk not in fks:
                    fks.append(fk)
            slug = meta.get("source_slug") or meta.get("source_repo")
            if slug and str(slug) not in source_repos:
                source_repos.append(str(slug))

        # Canonical display name: prefer semantics owners key / same_as canonical casing
        canon_display = _canonical_display(ckey, members[0][0], sem)
        owner = None
        owner_map = {k.lower(): v for k, v in sem.owners.items()}
        owner = owner_map.get(canon_display.lower()) or owner_map.get(ckey)

        meta = best_el.metadata or {}
        container = meta.get("container") if isinstance(meta.get("container"), str) else None
        entities.append(
            DataEntity(
                id=best_el.id,
                name=best_el.name,
                table_name=canon_display,
                columns=columns,
                fk_columns=fks,
                file_path=best_el.file_path,
                kind=str(meta.get("kind") or "entity"),
                language=best_el.language or str(meta.get("language") or ""),
                container=container,
                owner=owner,
                canonical_name=canon_display,
                aliases=alias_names,
                source_repos=source_repos,
            )
        )

    table_ids = {e.table_name: e.id for e in entities}
    table_ids_ci = {e.table_name.lower(): e.table_name for e in entities}
    # Allow FKs to resolve via aliases too
    for e in entities:
        for a in e.aliases:
            table_ids_ci.setdefault(a.lower(), e.table_name)

    associations: list[DataAssociation] = []
    seen: set[tuple[str, str, str]] = set()
    for e in entities:
        for fk in e.fk_columns:
            tgt_raw = fk_target_table(fk)
            tgt_canon = resolve_canonical_name(tgt_raw, sem)
            tgt = table_ids_ci.get(tgt_canon.lower()) or table_ids_ci.get(tgt_raw.lower())
            if not tgt or tgt == e.table_name:
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
    lang_counts: Counter[str] = Counter((e.language or "unknown") for e in entities)
    owned = sum(1 for e in entities if e.owner)
    return CanonicalDataModel(
        entities=entities,
        associations=associations,
        stats={
            "entity_count": len(entities),
            "association_count": len(associations),
            "kinds": dict(kinds),
            "columns_total": sum(len(e.columns) for e in entities),
            "languages": dict(lang_counts),
            "owned_entities": owned,
            "aliases_applied": sum(1 for e in entities if e.aliases),
            "aggregated": bool((snapshot.metadata or {}).get("aggregated")),
            "semantics": {
                "alias_rules": len(sem.aliases),
                "same_as_groups": len(sem.same_as),
                "owners": len(sem.owners),
                "suppress": len(sem.suppress),
            },
            "basic": basic_data_model_summary(snapshot),
        },
    )


def build_cdm_from_exports(
    paths: list[Path | str],
    *,
    system_name: str = "Distributed System",
    semantics: CdmSemantics | None = None,
    semantics_path: Path | str | None = None,
) -> tuple[ArchSnapshot, CanonicalDataModel]:
    """Aggregate architecture JSON exports then build a semantic CDM."""
    from archlens.distributed.aggregator import aggregate_from_paths

    snap = aggregate_from_paths(list(paths), system_name=system_name)
    cdm = build_canonical_data_model(
        snap, semantics=semantics, semantics_path=semantics_path
    )
    return snap, cdm


def _canonical_display(ckey: str, fallback: str, sem: CdmSemantics) -> str:
    for group in sem.same_as:
        if group.canonical.lower() == ckey:
            return group.canonical
    for _alias, canon in sem.aliases.items():
        if canon.lower() == ckey:
            return canon
    # Preserve original casing when no overlay
    if fallback.lower() == ckey:
        return fallback
    return fallback if fallback else ckey


def _table_from_name(name: str) -> str:
    if name.startswith(("I_", "X_")) and len(name) > 2:
        return name[2:]
    if name.upper().startswith("DCL") and len(name) > 3:
        return name[3:]
    for suffix in ("Entity", "Model", "PO", "Record"):
        if name.endswith(suffix) and name != suffix:
            return name[: -len(suffix)]
    return name


def _entity_score(e: ArchElement) -> int:
    meta = e.metadata or {}
    score = len(meta.get("columns") or []) * 2 + len(meta.get("fk_columns") or [])
    if e.name.startswith("I_"):
        score += 1000
    if meta.get("table_name"):
        score += 50
    if meta.get("kind") in ("db2_table", "po", "jpa", "typeorm", "sqlalchemy", "dclgen"):
        score += 25
    return score
