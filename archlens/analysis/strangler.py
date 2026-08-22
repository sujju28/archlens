"""Strangler-fig extract slice: programs + tables + jobs + maps for one capability."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from archlens.models import ArchSnapshot, is_code_level

DOWNSTREAM = {
    "calls",
    "injects",
    "routes_to",
    "implements",
    "copies",
    "imports",
    "references",
    "accesses_table",
    "writes_table",
    "cics_link",
    "cics_xctl",
    "cics_start",
    "executes",
    "reads_dataset",
    "writes_dataset",
    "uses_map",
    "composes",
}


@dataclass
class StranglerSlice:
    capability_id: str
    title: str
    programs: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    jobs: list[str] = field(default_factory=list)
    maps: list[str] = field(default_factory=list)
    copybooks: list[str] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "title": self.title,
            "programs": self.programs,
            "tables": self.tables,
            "jobs": self.jobs,
            "maps": self.maps,
            "copybooks": self.copybooks,
            "datasets": self.datasets,
            "files": self.files,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Strangler slice: {self.title}",
            "",
            "Programs, tables, jobs, and maps that move together if you extract this capability.",
            "",
        ]
        for label, items in (
            ("Programs / classes", self.programs),
            ("Tables", self.tables),
            ("Batch jobs", self.jobs),
            ("BMS maps", self.maps),
            ("COPY books", self.copybooks),
            ("Datasets", self.datasets),
            ("Files", self.files),
        ):
            if items:
                lines.append(f"## {label}")
                lines.append("")
                for i in items[:40]:
                    lines.append(f"- `{i}`")
                lines.append("")
        return "\n".join(lines)


def strangler_slice(
    snapshot: ArchSnapshot,
    *,
    capability_id: str,
    title: str,
    seed_names: list[str],
    related_tables: list[str] | None = None,
    depth: int = 4,
) -> StranglerSlice:
    by_name = {e.name: e for e in snapshot.elements if not is_code_level(e)}
    by_id = {e.id: e for e in snapshot.elements}
    seeds = [by_name[n] for n in seed_names if n in by_name]
    outgoing: dict[str, list[str]] = {}
    for r in snapshot.relationships:
        if r.rel_type not in DOWNSTREAM:
            continue
        if r.source_id not in by_id or r.target_id not in by_id:
            continue
        if is_code_level(by_id[r.source_id]) or is_code_level(by_id[r.target_id]):
            if r.rel_type not in ("uses_map", "copies", "executes"):
                continue
        outgoing.setdefault(r.source_id, []).append(r.target_id)

    seen: set[str] = set()
    stack = [e.id for e in seeds]
    while stack:
        eid = stack.pop()
        if eid in seen:
            continue
        seen.add(eid)
        if len(seen) > 80:
            break
        for t in outgoing.get(eid, []):
            if t not in seen:
                stack.append(t)

    programs, tables, jobs, maps, copies, datasets, files = [], [], [], [], [], [], []
    for eid in seen:
        el = by_id.get(eid)
        if not el or is_code_level(el):
            continue
        files.append(el.file_path)
        kind = (el.metadata or {}).get("kind")
        if el.stereotype == "Entity" or kind in ("db2_table",):
            tables.append(el.name)
        elif el.stereotype == "Batch Job" or kind in ("jcl_job", "jcl_step"):
            jobs.append(el.name)
        elif kind == "bms_map" or el.language == "bms":
            maps.append(el.name)
        elif kind in ("copybook", "dclgen") or el.stereotype == "Shared Data":
            if kind == "dataset":
                datasets.append(el.name)
            else:
                copies.append(el.name)
        elif kind == "dataset":
            datasets.append(el.name)
        else:
            programs.append(el.name)
    for t in related_tables or []:
        if t not in tables:
            tables.append(t)

    def uniq(xs: list[str]) -> list[str]:
        return list(dict.fromkeys(x for x in xs if x))

    return StranglerSlice(
        capability_id=capability_id,
        title=title,
        programs=uniq(programs)[:40],
        tables=uniq(tables)[:40],
        jobs=uniq(jobs)[:20],
        maps=uniq(maps)[:20],
        copybooks=uniq(copies)[:20],
        datasets=uniq(datasets)[:20],
        files=uniq(files)[:40],
    )
