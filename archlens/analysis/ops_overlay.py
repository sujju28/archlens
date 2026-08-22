"""Ops overlay: JCL job/step names, CICS TRANSID, BMS maps (not APM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archlens.config import ArchLensConfig, load_config
from archlens.models import ArchSnapshot, is_code_level

_CSD_TX = re.compile(
    r"DEFINE\s+TRANSACTION\s*\(\s*([A-Z0-9]+)\s*\).*?PROGRAM\s*\(\s*([A-Z0-9]+)\s*\)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class OpsOverlay:
    jobs: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    transids: list[str] = field(default_factory=list)
    maps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "jobs": self.jobs,
            "steps": self.steps,
            "transids": self.transids,
            "maps": self.maps,
            "notes": self.notes,
        }

    def to_markdown(self) -> str:
        lines = ["# Ops overlay (JCL / CICS / maps)", ""]
        for label, items in (
            ("Jobs", self.jobs),
            ("Steps / PGM", self.steps),
            ("TRANSID", self.transids),
            ("Maps", self.maps),
        ):
            if items:
                lines.append(f"## {label}")
                lines.append("")
                for i in items:
                    lines.append(f"- `{i}`")
                lines.append("")
        for n in self.notes:
            lines.append(f"- {n}")
        return "\n".join(lines) + ("\n" if lines else "")


def ops_overlay(
    snapshot: ArchSnapshot,
    *,
    repo: Path | str | None = None,
    config: ArchLensConfig | None = None,
    seed_names: list[str] | None = None,
) -> OpsOverlay:
    root = Path(repo or snapshot.repo_path)
    cfg = config or (load_config(root) if root.exists() else ArchLensConfig())
    seeds = {n.upper() for n in (seed_names or [])}
    jobs, steps, trans, maps = [], [], [], []

    for e in snapshot.elements:
        if is_code_level(e):
            continue
        meta = e.metadata or {}
        kind = meta.get("kind")
        if kind == "jcl_job":
            jobs.append(e.name)
        if kind == "jcl_step":
            pgm = meta.get("pgm") or meta.get("exec_target")
            steps.append(f"{e.name}" + (f" PGM={pgm}" if pgm else ""))
            if seeds and pgm and pgm.upper() in seeds:
                jobs.append(str(meta.get("job") or ""))
        if kind == "bms_map":
            maps.append(e.name)
        for t in meta.get("cics_starts") or []:
            trans.append(str(t))
        for m in meta.get("maps") or []:
            maps.append(str(m))

    for tx, prog in (cfg.mainframe.transactions or {}).items():
        trans.append(f"{tx} → {prog}")
        if not seeds or prog.upper() in seeds or tx.upper() in seeds:
            continue

    for spec in cfg.mainframe.cics_definitions or []:
        path = root / spec
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _CSD_TX.finditer(text):
            trans.append(f"{m.group(1).upper()} → {m.group(2).upper()}")

    def uniq(xs: list[str]) -> list[str]:
        return [x for x in dict.fromkeys(xs) if x]

    notes = []
    if not jobs and not trans and not maps:
        notes.append("No JCL jobs, TRANSID map, or BMS maps in this snapshot.")
    return OpsOverlay(
        jobs=uniq(jobs)[:20],
        steps=uniq(steps)[:30],
        transids=uniq(trans)[:30],
        maps=uniq(maps)[:20],
        notes=notes,
    )
