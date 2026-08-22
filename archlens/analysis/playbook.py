"""Onboarding reading paths and change playbooks per capability.

Grounded in the architecture graph (no free-form LLM). Each playbook lists
what to read first, citations from those files, blast radius, tests, and
data/COPY dependencies so a new developer can take a change safely.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archlens.analysis.capabilities import (
    Capability,
    CapabilityCatalog,
    load_catalog,
    sync_capabilities,
)
from archlens.analysis.impact_analyzer import ImpactAnalyzer
from archlens.config import load_config
from archlens.models import ArchElement, ArchSnapshot, is_code_level

DOWNSTREAM_RELS = {
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
    "executes",
    "reads_dataset",
    "writes_dataset",
    "uses_map",
    "composes",
    "performs",
}

_READ_ORDER = {
    "Controller": 0,
    "Gateway": 0,
    "UI Component": 0,
    "Batch Job": 0,
    "Worker": 1,
    "Service": 2,
    "Middleware": 3,
    "Repository": 4,
    "Entity": 5,
    "Shared Data": 6,
    "Configuration": 7,
    "Component": 8,
}

_LICENSE_HINTS = (
    "licensed under",
    "copyright",
    "all rights reserved",
    "apache license",
    "spdx-license",
)


@dataclass
class ReadingStep:
    order: int
    name: str
    stereotype: str
    file_path: str
    why: str
    excerpt: str = ""
    citation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "name": self.name,
            "stereotype": self.stereotype,
            "file_path": self.file_path,
            "why": self.why,
            "excerpt": self.excerpt,
            "citation": self.citation,
        }


@dataclass
class ChangePlaybook:
    capability_id: str
    title: str
    owner: str = ""
    stereotype: str = ""
    summary: str = ""
    reading_path: list[ReadingStep] = field(default_factory=list)
    blast_radius: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    copybooks: list[str] = field(default_factory=list)
    dont_skip: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    bms_fields: list[str] = field(default_factory=list)
    strangler: list[str] = field(default_factory=list)
    ops: list[str] = field(default_factory=list)
    learn_first: list[str] = field(default_factory=list)
    skip_or_later: list[str] = field(default_factory=list)
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "title": self.title,
            "owner": self.owner,
            "stereotype": self.stereotype,
            "summary": self.summary,
            "reading_path": [s.to_dict() for s in self.reading_path],
            "blast_radius": self.blast_radius,
            "tests": self.tests,
            "tables": self.tables,
            "copybooks": self.copybooks,
            "dont_skip": self.dont_skip,
            "suggestions": self.suggestions,
            "comments": self.comments,
            "rules": self.rules,
            "methods": self.methods,
            "paragraphs": self.paragraphs,
            "bms_fields": self.bms_fields,
            "strangler": self.strangler,
            "ops": self.ops,
            "learn_first": self.learn_first,
            "skip_or_later": self.skip_or_later,
            "risk_score": self.risk_score,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Playbook: {self.title}",
            "",
            f"**Capability:** `{self.capability_id}` ({self.stereotype or 'entry'})  ",
        ]
        if self.owner:
            lines.append(f"**Owner:** {self.owner}  ")
        lines.append(f"**Risk if changed:** {self.risk_score}")
        lines.append("")
        if self.summary:
            lines.extend([self.summary, ""])
        lines.extend(
            [
                "This is a **reading path + change recipe** from the architecture graph, "
                "not a substitute for reading the programs.",
                "",
                "## Start here (reading path)",
                "",
            ]
        )
        for step in self.reading_path:
            lines.append(
                f"{step.order}. **{step.name}** ({step.stereotype}) — {step.why}  "
            )
            lines.append(f"   `{step.citation or step.file_path}`")
            if step.excerpt:
                excerpt = step.excerpt.replace("\n", " ").strip()
                lines.append(f"   > {excerpt}")
            lines.append("")
        if self.tables:
            lines.extend(
                [
                    "## Data to know",
                    "",
                    ", ".join(f"`{t}`" for t in self.tables[:20]),
                    "",
                ]
            )
        if self.copybooks:
            lines.extend(
                [
                    "## COPY / shared layouts",
                    "",
                    ", ".join(f"`{c}`" for c in self.copybooks[:20]),
                    "",
                ]
            )
        if self.blast_radius:
            lines.extend(["## Blast radius (who depends on this)", ""])
            for b in self.blast_radius[:15]:
                lines.append(f"- {b}")
            lines.append("")
        if self.tests:
            lines.extend(["## Tests likely covering this", ""])
            for t in self.tests[:12]:
                lines.append(f"- `{t}`")
            lines.append("")
        if self.dont_skip:
            lines.extend(["## Don't skip", ""])
            for d in self.dont_skip[:10]:
                lines.append(f"- {d}")
            lines.append("")
        if self.suggestions:
            lines.extend(["## Suggested next actions", ""])
            for s in self.suggestions[:10]:
                lines.append(f"- {s}")
            lines.append("")
        if self.comments:
            lines.extend(["## Comments / remarks (as documentation)", ""])
            for c in self.comments[:10]:
                lines.append(f"- {c}")
            lines.append("")
        if self.rules:
            lines.extend(["## Candidate business rules (from code)", ""])
            for r in self.rules[:12]:
                lines.append(f"- {r}")
            lines.append("")
        if self.methods or self.paragraphs or self.bms_fields:
            lines.extend(["## Fine grain", ""])
            if self.methods:
                lines.append("Methods: " + ", ".join(f"`{m}`" for m in self.methods[:20]))
            if self.paragraphs:
                lines.append("Paragraphs: " + ", ".join(f"`{p}`" for p in self.paragraphs[:20]))
            if self.bms_fields:
                lines.append("BMS fields: " + ", ".join(f"`{f}`" for f in self.bms_fields[:20]))
            lines.append("")
        if self.strangler:
            lines.extend(["## Strangler slice", ""])
            for s in self.strangler:
                lines.append(f"- {s}")
            lines.append("")
        if self.ops:
            lines.extend(["## Ops overlay", ""])
            for o in self.ops:
                lines.append(f"- {o}")
            lines.append("")
        if self.learn_first or self.skip_or_later:
            lines.extend(["## Reading order (hotspots vs skip)", ""])
            for x in self.learn_first[:8]:
                lines.append(f"- Learn: {x}")
            for x in self.skip_or_later[:6]:
                lines.append(f"- Later: {x}")
            lines.append("")
        return "\n".join(lines)


def build_playbook(
    snapshot: ArchSnapshot,
    capability: Capability,
    *,
    repo: Path | str | None = None,
) -> ChangePlaybook:
    root = Path(repo or snapshot.repo_path)
    by_name = {e.name: e for e in snapshot.elements}
    entries = [by_name[n] for n in capability.elements if n in by_name]
    if not entries and capability.file_path:
        entries = [
            e
            for e in snapshot.elements
            if e.file_path.replace("\\", "/") == capability.file_path.replace("\\", "/")
        ]

    reading = _reading_path(snapshot, entries, root)
    copybooks = [
        s.name
        for s in reading
        if s.stereotype == "Shared Data" or "copy" in s.why.lower()
    ]
    tables = list(capability.related_tables)
    for s in reading:
        if s.stereotype == "Entity":
            if s.name not in tables:
                tables.append(s.name)

    impact = ImpactAnalyzer(load_config(root) if root.exists() else None).analyze(
        snapshot, elements=capability.elements, depth=4
    )
    blast = [
        f"`{a.name}` ({a.stereotype}, {a.risk}) — {a.reason}"
        for a in impact.directly_affected[:12]
    ]
    tests = _find_tests(root, snapshot, entries)
    dont_skip = _dont_skip(entries, impact, snapshot)
    suggestions = list(impact.suggested_changes[:8])
    if not suggestions:
        suggestions.append(
            f"Read the files in order, then change `{capability.elements[0] if capability.elements else capability.id}` "
            "and re-run `archlens impact` on that file."
        )
    if tests:
        suggestions.insert(0, "Run the listed tests after your change.")
    summary = capability.description or (
        f"Start at {entries[0].name} ({entries[0].stereotype}) and follow "
        f"{len(reading)} linked files before editing."
        if entries
        else "Entry elements were not found in the latest snapshot."
    )

    pb = ChangePlaybook(
        capability_id=capability.id,
        title=capability.title or capability.id,
        owner=capability.owner,
        stereotype=capability.stereotype,
        summary=summary,
        reading_path=reading,
        blast_radius=blast,
        tests=tests,
        tables=tables[:20],
        copybooks=copybooks[:20],
        dont_skip=dont_skip,
        suggestions=suggestions,
        risk_score=impact.risk_score,
    )
    from archlens.analysis.explain import enrich_playbook_extras

    return enrich_playbook_extras(snapshot, capability, pb, repo=root)


def playbooks_for_catalog(
    snapshot: ArchSnapshot,
    catalog: CapabilityCatalog,
    *,
    repo: Path | str | None = None,
    limit: int = 20,
    capability_id: str | None = None,
) -> list[ChangePlaybook]:
    caps = catalog.capabilities
    if capability_id:
        cid = capability_id.lower()
        caps = [
            c
            for c in caps
            if c.id.lower() == cid or cid in c.title.lower() or cid in {e.lower() for e in c.elements}
        ]
    # Prefer approved, then ones with files
    caps = sorted(
        caps,
        key=lambda c: (0 if c.status == "approved" else 1, c.missing_in_code, c.title.lower()),
    )
    return [build_playbook(snapshot, c, repo=repo) for c in caps[:limit]]


def playbooks_markdown(playbooks: list[ChangePlaybook], *, project: str = "Playbooks") -> str:
    lines = [
        f"# {project} — Reading paths & change playbooks",
        "",
        "For each capability: **what to read first**, citations from those files, "
        "blast radius, tests, and data. Generated from the architecture graph.",
        "",
        f"- **Playbooks:** {len(playbooks)}",
        "",
    ]
    for pb in playbooks:
        lines.append(pb.to_markdown().replace("# Playbook:", "## Playbook:", 1))
        lines.append("")
    return "\n".join(lines)


def resolve_catalog(snapshot: ArchSnapshot, repo: Path | str) -> CapabilityCatalog:
    catalog = load_catalog(repo)
    if not catalog.capabilities:
        catalog = sync_capabilities(snapshot, repo, persist=False)
    return catalog


def match_capability(catalog: CapabilityCatalog, capability_id: str):
    cid = capability_id.lower()
    for c in catalog.capabilities:
        if c.id.lower() == cid or cid in c.title.lower() or cid in {e.lower() for e in c.elements}:
            return c
    return None


def _reading_path(
    snapshot: ArchSnapshot,
    entries: list[ArchElement],
    root: Path,
    *,
    max_steps: int = 12,
) -> list[ReadingStep]:
    by_id = {e.id: e for e in snapshot.elements}
    outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in snapshot.relationships:
        if r.rel_type in DOWNSTREAM_RELS:
            outgoing[r.source_id].append((r.target_id, r.rel_type))

    ordered: list[tuple[ArchElement, str]] = []
    seen: set[str] = set()
    queue: deque[tuple[str, str, int]] = deque()
    for el in entries:
        queue.append((el.id, "entry point", 0))
        seen.add(el.id)

    while queue and len(ordered) < max_steps:
        eid, why, depth = queue.popleft()
        el = by_id.get(eid)
        if not el:
            continue
        if is_code_level(el):
            continue
        ordered.append((el, why))
        if depth >= 5:
            continue
        hops = outgoing.get(eid, [])
        hops.sort(key=lambda h: _READ_ORDER.get(by_id[h[0]].stereotype, 9) if h[0] in by_id else 9)
        for tgt, rel in hops:
            if tgt in seen:
                continue
            seen.add(tgt)
            nxt = by_id.get(tgt)
            if not nxt:
                continue
            queue.append((tgt, f"{rel} from {el.name}", depth + 1))

    steps: list[ReadingStep] = []
    for i, (el, why) in enumerate(ordered, start=1):
        excerpt = _file_excerpt(root, el.file_path)
        steps.append(
            ReadingStep(
                order=i,
                name=el.name,
                stereotype=el.stereotype,
                file_path=el.file_path,
                why=why,
                excerpt=excerpt,
                citation=f"{el.file_path}#{el.name}",
            )
        )
    return steps


def _file_excerpt(root: Path, rel_path: str, *, max_chars: int = 280) -> str:
    if not rel_path:
        return ""
    path = root / rel_path
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(h in low for h in _LICENSE_HINTS):
            continue
        # COBOL comment / program header
        body = stripped.lstrip("/*#-;")
        body = re.sub(r"^\*\s?", "", body)
        if re.match(r"^\d{6}", body):
            body = body[6:].lstrip()
        if re.match(r"^(package |import |from |using )", body, re.I):
            continue
        if re.match(r"^(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION", body, re.I):
            continue
        if len(body) < 8:
            continue
        if re.match(r"^[{}();]+$", body):
            continue
        lines.append(body)
        if len(lines) >= 4:
            break
    blob = " ".join(lines).strip()
    if len(blob) > max_chars:
        blob = blob[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return blob


def _find_tests(root: Path, snapshot: ArchSnapshot, entries: list[ArchElement]) -> list[str]:
    names = {e.name.lower() for e in entries}
    stems = {Path(e.file_path).stem.lower() for e in entries if e.file_path}
    tests: list[str] = []
    for e in snapshot.elements:
        fp = e.file_path.replace("\\", "/")
        low = fp.lower()
        is_test = any(p in low for p in ("/test/", "/tests/", ".test.", ".spec.", "test_"))
        if not is_test:
            continue
        blob = f"{e.name} {fp}".lower()
        if any(n in blob for n in names) or any(s and s in blob for s in stems):
            if fp not in tests:
                tests.append(fp)
    # Also glob the repo for test files mentioning the name
    if root.is_dir() and entries:
        needles = {entries[0].name}
        base = guess_base(entries[0].name)
        if base:
            needles.add(base)
        for pattern in ("**/*test*", "**/*spec*", "**/test_*.py"):
            for path in list(root.glob(pattern))[:80]:
                if not path.is_file():
                    continue
                rel = str(path.relative_to(root)).replace("\\", "/")
                if rel in tests:
                    continue
                try:
                    sample = path.read_text(encoding="utf-8", errors="replace")[:4000]
                except OSError:
                    continue
                blob = f"{rel}\n{sample}".lower()
                if any(n.lower() in blob for n in needles):
                    tests.append(rel)
                if len(tests) >= 12:
                    break
            if len(tests) >= 12:
                break
    return tests[:12]


def guess_base(name: str) -> str:
    for suf in ("Controller", "Service", "Resource", "Router"):
        if name.endswith(suf) and len(name) > len(suf):
            return name[: -len(suf)]
    return name


def _dont_skip(entries: list[ArchElement], impact, snapshot: ArchSnapshot) -> list[str]:
    notes: list[str] = []
    for el in entries:
        paths = (el.metadata or {}).get("critical_paths") or []
        if paths:
            notes.append(
                f"`{el.name}` is on critical path(s) {', '.join(str(p) for p in paths[:3])}"
            )
        owner = (el.metadata or {}).get("owner")
        if owner:
            notes.append(f"Owner of `{el.name}`: {owner}")
    high = [a for a in impact.directly_affected if a.risk == "HIGH"]
    if high:
        notes.append(
            "High-risk dependents: " + ", ".join(f"`{a.name}`" for a in high[:5])
        )
    if any(e.stereotype in ("Controller", "Gateway", "UI Component") for e in entries):
        notes.append("This is an entry point — contract/UI callers may break.")
    if any(e.stereotype == "Batch Job" for e in entries):
        notes.append("Batch/JCL — check datasets, restart, and downstream jobs.")
    if not notes:
        notes.append("Re-scan after the change (`archlens scan` + `archlens impact`).")
    return notes
