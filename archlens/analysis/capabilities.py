"""Capability catalog — auto-seeded on scan, human-refined in YAML.

Scan discovers technical entry points (controllers, CICS screens, batch jobs,
gateways) as candidate capabilities. Humans can rename, describe, own, and
approve them. Subsequent scans refresh technical links without wiping curated
fields.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from archlens.models import ArchElement, ArchSnapshot

ENTRY_STEREOTYPES = ("Controller", "Gateway", "UI Component", "Batch Job", "Worker")

_STRIP_SUFFIXES = (
    "RestController",
    "Controller",
    "Resource",
    "Router",
    "Handler",
    "Gateway",
    "Job",
    "Worker",
    "Batch",
)


class Capability(BaseModel):
    id: str
    source: str = "auto"  # auto | curated
    status: str = "candidate"  # candidate | approved | deprecated
    title: str = ""
    description: str = ""
    owner: str = ""
    stereotype: str = ""
    elements: list[str] = Field(default_factory=list)
    file_path: str = ""
    related_tables: list[str] = Field(default_factory=list)
    missing_in_code: bool = False
    notes: str = ""

    def to_yaml_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "status": self.status,
            "title": self.title,
            "stereotype": self.stereotype,
            "elements": list(self.elements),
            "file_path": self.file_path,
        }
        if self.description:
            data["description"] = self.description
        if self.owner:
            data["owner"] = self.owner
        if self.related_tables:
            data["related_tables"] = list(self.related_tables)
        if self.missing_in_code:
            data["missing_in_code"] = True
        if self.notes:
            data["notes"] = self.notes
        return data


class CapabilityCatalog(BaseModel):
    capabilities: list[Capability] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for c in self.capabilities:
            by_status[c.status] = by_status.get(c.status, 0) + 1
        return {
            "capability_count": len(self.capabilities),
            "by_status": by_status,
            "missing_in_code": sum(1 for c in self.capabilities if c.missing_in_code),
            "capabilities": [c.model_dump() for c in self.capabilities],
        }

    def to_markdown(self, *, title: str = "Capabilities") -> str:
        lines = [
            f"# {title}",
            "",
            "Technical entry points discovered from code, optionally labeled as "
            "business capabilities in `.archlens/capabilities.yaml`. "
            "Scan refreshes links; curated titles/owners are preserved.",
            "",
            f"- **Capabilities:** {len(self.capabilities)}",
        ]
        by_status: dict[str, int] = {}
        by_stereo: dict[str, int] = {}
        for c in self.capabilities:
            by_status[c.status] = by_status.get(c.status, 0) + 1
            by_stereo[c.stereotype or "?"] = by_stereo.get(c.stereotype or "?", 0) + 1
        if by_status:
            lines.append(
                "- **By status:** "
                + ", ".join(f"{k}: {v}" for k, v in sorted(by_status.items()))
            )
        if by_stereo:
            lines.append(
                "- **By kind:** "
                + ", ".join(f"{k}: {v}" for k, v in sorted(by_stereo.items()))
            )
        missing = [c for c in self.capabilities if c.missing_in_code]
        if missing:
            lines.append(f"- **Missing in code:** {len(missing)}")
        lines.extend(["", "## Catalog", ""])
        ranked = sorted(
            self.capabilities,
            key=lambda c: (0 if c.status == "approved" else 1, c.title.lower()),
        )
        for cap in ranked[:80]:
            flag = " ⚠ missing" if cap.missing_in_code else ""
            lines.append(f"### {cap.title or cap.id}{flag}")
            lines.append("")
            lines.append(f"- **Id:** `{cap.id}` ({cap.status}, {cap.source})")
            if cap.stereotype:
                lines.append(f"- **Kind:** {cap.stereotype}")
            if cap.owner:
                lines.append(f"- **Owner:** {cap.owner}")
            if cap.description:
                lines.append(f"- **Description:** {cap.description}")
            if cap.elements:
                lines.append(
                    "- **Elements:** " + ", ".join(f"`{n}`" for n in cap.elements[:8])
                )
            if cap.file_path:
                lines.append(f"- **Source:** `{cap.file_path}`")
            if cap.related_tables:
                lines.append(
                    "- **Related data:** "
                    + ", ".join(f"`{t}`" for t in cap.related_tables[:8])
                )
            lines.append("")
        if len(ranked) > 80:
            lines.append(f"_…and {len(ranked) - 80} more._")
            lines.append("")
        return "\n".join(lines)


def default_capabilities_path(repo: Path) -> Path:
    return repo / ".archlens" / "capabilities.yaml"


def load_catalog(repo: Path | str, path: Path | str | None = None) -> CapabilityCatalog:
    p = Path(path) if path else default_capabilities_path(Path(repo))
    if not p.exists():
        return CapabilityCatalog()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    items = data.get("capabilities") if isinstance(data, dict) else data
    if not items:
        return CapabilityCatalog()
    caps = [Capability.model_validate(x) for x in items]
    return CapabilityCatalog(capabilities=caps)


def save_catalog(repo: Path | str, catalog: CapabilityCatalog) -> Path:
    path = default_capabilities_path(Path(repo))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "note": (
            "Auto-seeded on scan. Edit title/description/owner/status; "
            "those fields are preserved. Technical links are refreshed."
        ),
        "capabilities": [c.to_yaml_dict() for c in catalog.capabilities],
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def write_example_capabilities(repo: Path | str) -> Path:
    """Create an empty catalog file only if missing (scan will fill it)."""
    path = default_capabilities_path(Path(repo))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(
        """# Capabilities catalog (hybrid)
# Scan auto-seeds candidates from Controllers / CICS screens / batch jobs / gateways.
# Curate title, description, owner, status — those fields are never overwritten.
#
# status: candidate | approved | deprecated
# source: auto | curated

version: 1
capabilities: []
""",
        encoding="utf-8",
    )
    return path


def capability_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "capability"


def guess_title(name: str, stereotype: str) -> str:
    base = name
    for suf in _STRIP_SUFFIXES:
        if base.endswith(suf) and len(base) > len(suf):
            base = base[: -len(suf)]
            break
    # COBOL-ish all-caps identifiers
    if base.isupper() and len(base) >= 4:
        return base
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", base)
    spaced = re.sub(r"[_-]+", " ", spaced).strip()
    if not spaced:
        return name
    title = spaced[0].upper() + spaced[1:]
    if stereotype == "Batch Job" and "job" not in title.lower():
        return f"{title} batch"
    if stereotype == "Gateway" and "gateway" not in title.lower():
        return f"{title} gateway"
    return title


def discover_capabilities(snapshot: ArchSnapshot) -> list[Capability]:
    """Build candidate capabilities from entry-point elements."""
    tables_by_entry = _related_tables(snapshot)
    found: list[Capability] = []
    seen: set[str] = set()
    for el in snapshot.elements:
        if el.stereotype not in ENTRY_STEREOTYPES:
            continue
        cid = capability_id(el.name)
        if cid in seen:
            cid = capability_id(f"{el.name}-{el.stereotype}")
        seen.add(cid)
        found.append(
            Capability(
                id=cid,
                source="auto",
                status="candidate",
                title=guess_title(el.name, el.stereotype),
                stereotype=el.stereotype,
                elements=[el.name],
                file_path=el.file_path,
                related_tables=tables_by_entry.get(el.name, []),
            )
        )
    return found


def merge_catalog(
    existing: CapabilityCatalog,
    discovered: list[Capability],
) -> CapabilityCatalog:
    """Refresh technical fields; preserve human-curated text."""
    by_id = {c.id: c for c in existing.capabilities}
    by_element: dict[str, Capability] = {}
    for c in existing.capabilities:
        for n in c.elements:
            by_element.setdefault(n, c)

    live_ids: set[str] = set()
    merged: list[Capability] = []

    for disc in discovered:
        prior = by_id.get(disc.id)
        if prior is None and disc.elements:
            prior = by_element.get(disc.elements[0])
        if prior is None:
            merged.append(disc)
            live_ids.add(disc.id)
            continue
        live_ids.add(prior.id)
        merged.append(_merge_one(prior, disc))

    # Keep curated/approved records even if code disappeared
    for old in existing.capabilities:
        if old.id in live_ids:
            continue
        kept = old.model_copy(update={"missing_in_code": True})
        if kept.status == "candidate" and kept.source == "auto" and not _is_curated(kept):
            # Auto candidate vanished — keep but flag; user can delete later
            merged.append(kept)
        else:
            merged.append(kept)

    merged.sort(key=lambda c: (c.status != "approved", c.title.lower(), c.id))
    # De-dupe by id (first wins)
    uniq: list[Capability] = []
    seen: set[str] = set()
    for c in merged:
        if c.id in seen:
            continue
        seen.add(c.id)
        uniq.append(c)
    return CapabilityCatalog(capabilities=uniq)


def sync_capabilities(
    snapshot: ArchSnapshot,
    repo: Path | str,
    *,
    persist: bool = True,
) -> CapabilityCatalog:
    """Discover, merge with YAML, optionally write back."""
    root = Path(repo)
    existing = load_catalog(root)
    discovered = discover_capabilities(snapshot)
    catalog = merge_catalog(existing, discovered)
    snapshot.metadata["capabilities"] = {
        "count": len(catalog.capabilities),
        "approved": sum(1 for c in catalog.capabilities if c.status == "approved"),
        "candidates": sum(1 for c in catalog.capabilities if c.status == "candidate"),
        "missing_in_code": sum(1 for c in catalog.capabilities if c.missing_in_code),
    }
    if persist:
        save_catalog(root, catalog)
    return catalog


def _is_curated(cap: Capability) -> bool:
    return cap.source == "curated" or cap.status in ("approved", "deprecated") or bool(
        cap.description or cap.owner or cap.notes
    )


def _merge_one(prior: Capability, disc: Capability) -> Capability:
    updates: dict[str, Any] = {
        "stereotype": disc.stereotype or prior.stereotype,
        "elements": disc.elements or prior.elements,
        "file_path": disc.file_path or prior.file_path,
        "related_tables": disc.related_tables or prior.related_tables,
        "missing_in_code": False,
    }
    # Preserve human fields
    if prior.title:
        updates["title"] = prior.title
    else:
        updates["title"] = disc.title
    if prior.description:
        updates["description"] = prior.description
    if prior.owner:
        updates["owner"] = prior.owner
    if prior.notes:
        updates["notes"] = prior.notes
    if prior.status and prior.status != "candidate":
        updates["status"] = prior.status
    elif prior.status:
        updates["status"] = prior.status
    if prior.source == "curated":
        updates["source"] = "curated"
    return prior.model_copy(update=updates)


def _related_tables(snapshot: ArchSnapshot) -> dict[str, list[str]]:
    """Map entry element name → nearby Entity/dataset names via relationships."""
    by_id = {e.id: e for e in snapshot.elements}
    outgoing: dict[str, list[str]] = {}
    for r in snapshot.relationships:
        outgoing.setdefault(r.source_id, []).append(r.target_id)

    result: dict[str, list[str]] = {}
    for el in snapshot.elements:
        if el.stereotype not in ENTRY_STEREOTYPES:
            continue
        tables: list[str] = []
        seen = {el.id}
        queue = list(outgoing.get(el.id, []))
        hops = 0
        while queue and hops < 4 and len(tables) < 8:
            nxt_ids = queue
            queue = []
            hops += 1
            for nid in nxt_ids:
                if nid in seen:
                    continue
                seen.add(nid)
                tgt = by_id.get(nid)
                if not tgt:
                    continue
                if tgt.stereotype == "Entity" or tgt.language in ("db2", "dataset"):
                    tname = str((tgt.metadata or {}).get("table_name") or tgt.name)
                    if tname not in tables:
                        tables.append(tname)
                queue.extend(outgoing.get(nid, []))
        if tables:
            result[el.name] = tables
    return result
