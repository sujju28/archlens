"""Fine-grain view: paragraphs, PERFORM, methods, BMS fields, COPY usage."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archlens.analysis.source_harvest import harvest_for_elements
from archlens.models import ArchElement, ArchSnapshot, is_code_level


@dataclass
class FineGrainReport:
    capability_id: str = ""
    paragraphs: list[dict[str, Any]] = field(default_factory=list)
    performs: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    copy_usage: list[str] = field(default_factory=list)
    bms_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "paragraphs": self.paragraphs,
            "performs": self.performs,
            "methods": self.methods,
            "copy_usage": self.copy_usage,
            "bms_fields": self.bms_fields,
        }

    def to_markdown(self) -> str:
        lines = ["# Fine grain", ""]
        if self.methods:
            lines += ["## Methods", "", ", ".join(f"`{m}`" for m in self.methods[:30]), ""]
        if self.paragraphs:
            lines += ["## Paragraphs", ""]
            for p in self.paragraphs[:30]:
                lines.append(f"- `{p.get('name')}` in `{p.get('program')}`")
            lines.append("")
        if self.performs:
            lines += ["## PERFORM", ""]
            for p in self.performs[:40]:
                lines.append(f"- {p}")
            lines.append("")
        if self.copy_usage:
            lines += ["## COPY usage", ""]
            for c in self.copy_usage[:20]:
                lines.append(f"- {c}")
            lines.append("")
        if self.bms_fields:
            lines += [
                "## BMS fields",
                "",
                ", ".join(f"`{f}`" for f in self.bms_fields[:40]),
                "",
            ]
        return "\n".join(lines)


def fine_grain_for(
    snapshot: ArchSnapshot,
    seed_elements: list[ArchElement],
    *,
    repo: Path | str | None = None,
    capability_id: str = "",
) -> FineGrainReport:
    root = Path(repo or snapshot.repo_path)
    by_id = {e.id: e for e in snapshot.elements}
    harvest = harvest_for_elements(snapshot, seed_elements, root)

    copy_users: dict[str, list[str]] = defaultdict(list)
    for rel in snapshot.relationships:
        if rel.rel_type != "copies":
            continue
        src, tgt = by_id.get(rel.source_id), by_id.get(rel.target_id)
        if src and tgt and not is_code_level(src):
            copy_users[tgt.name].append(src.name)

    seed_names = {e.name for e in seed_elements}
    seed_ids = {e.id for e in seed_elements}
    copy_lines = []
    for cpy, users in sorted(copy_users.items()):
        if seed_names & set(users) or cpy in harvest.copybooks:
            copy_lines.append(f"`{cpy}` used by " + ", ".join(f"`{u}`" for u in users[:8]))

    performs = []
    for rel in snapshot.relationships:
        if rel.rel_type != "performs":
            continue
        src, tgt = by_id.get(rel.source_id), by_id.get(rel.target_id)
        if not src or not tgt:
            continue
        prog = (src.metadata or {}).get("program")
        if prog in seed_names or src.id in seed_ids or any(
            s.id in (rel.source_id, rel.target_id) or s.name == prog for s in seed_elements
        ):
            performs.append(f"`{src.name}` → `{tgt.name}`")

    paras = []
    for e in snapshot.elements:
        if (e.metadata or {}).get("kind") != "paragraph":
            continue
        prog = (e.metadata or {}).get("program")
        if prog in seed_names or any(s.name == prog for s in seed_elements):
            paras.append({"name": e.name, "program": prog, "id": e.id})

    fields = list(harvest.bms_fields)
    for e in snapshot.elements:
        if (e.metadata or {}).get("kind") != "bms_field":
            continue
        mp = (e.metadata or {}).get("map")
        if any(
            (s.metadata or {}).get("maps") and mp in (s.metadata or {}).get("maps", [])
            for s in seed_elements
        ) or mp in {s.name for s in seed_elements}:
            if e.name not in fields:
                fields.append(e.name)

    return FineGrainReport(
        capability_id=capability_id,
        paragraphs=paras[:40],
        performs=list(dict.fromkeys(performs))[:40],
        methods=harvest.methods,
        copy_usage=copy_lines[:20],
        bms_fields=fields[:40],
    )
