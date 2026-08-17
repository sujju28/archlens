"""Domain / bounded-context slicing from packages, containers, FKs, and intents."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from archlens.models import ArchSnapshot


@dataclass
class DomainSlice:
    name: str
    elements: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    stereotypes: dict[str, int] = field(default_factory=dict)
    signal: str = "package"  # package | container | intent | fk_cluster

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "elements": self.elements,
            "tables": self.tables,
            "stereotypes": self.stereotypes,
            "signal": self.signal,
            "size": len(self.elements),
        }


@dataclass
class DomainReport:
    domains: list[DomainSlice] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": [d.to_dict() for d in self.domains],
            "unassigned": self.unassigned,
            "stats": self.stats,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Domain / bounded-context slices",
            "",
            f"- **Domains:** {len(self.domains)}",
            f"- **Unassigned elements:** {len(self.unassigned)}",
            "",
        ]
        for d in self.domains:
            lines.append(f"## {d.name}")
            lines.append("")
            lines.append(f"- **Signal:** {d.signal}")
            lines.append(f"- **Size:** {len(d.elements)}")
            if d.stereotypes:
                lines.append(
                    "- **Stereotypes:** "
                    + ", ".join(f"{k}: {v}" for k, v in sorted(d.stereotypes.items()))
                )
            if d.tables:
                lines.append(
                    "- **Tables:** " + ", ".join(f"`{t}`" for t in d.tables[:12])
                )
            sample = ", ".join(f"`{n}`" for n in d.elements[:12])
            lines.append(f"- **Sample:** {sample}")
            lines.append("")
        return "\n".join(lines)


def slice_domains(snapshot: ArchSnapshot, *, min_size: int = 2) -> DomainReport:
    """Cluster elements into domains using intents → container → package heuristics."""
    buckets: dict[str, list] = defaultdict(list)
    signals: dict[str, str] = {}

    for el in snapshot.elements:
        domains_meta = (el.metadata or {}).get("domains") or []
        if domains_meta:
            name = str(domains_meta[0])
            buckets[name].append(el)
            signals[name] = "intent"
            continue
        container = (el.metadata or {}).get("container")
        if container:
            buckets[str(container)].append(el)
            signals[str(container)] = "container"
            continue
        pkg = _package_token(el.file_path, el.language)
        if pkg:
            buckets[pkg].append(el)
            signals[pkg] = "package"
            continue
        buckets["_unassigned"].append(el)

    # Merge tiny package buckets into parent-ish names when possible
    domains: list[DomainSlice] = []
    unassigned: list[str] = []
    for name, els in sorted(buckets.items(), key=lambda x: (-len(x[1]), x[0])):
        if name == "_unassigned":
            unassigned = [e.name for e in els]
            continue
        if len(els) < min_size and signals.get(name) == "package":
            unassigned.extend(e.name for e in els)
            continue
        stereo = Counter(e.stereotype for e in els)
        tables = [
            str((e.metadata or {}).get("table_name") or e.name)
            for e in els
            if e.stereotype == "Entity"
        ]
        domains.append(
            DomainSlice(
                name=name,
                elements=[e.name for e in els],
                tables=sorted(set(tables))[:40],
                stereotypes=dict(stereo),
                signal=signals.get(name, "package"),
            )
        )

    # Optional: attach FK-linked orphan entities into largest related domain
    domains = _attach_fk_orphans(snapshot, domains)

    return DomainReport(
        domains=domains,
        unassigned=unassigned[:100],
        stats={
            "domain_count": len(domains),
            "unassigned_count": len(unassigned),
            "largest": domains[0].name if domains else None,
        },
    )


def _package_token(file_path: str, language: str) -> str | None:
    path = file_path.replace("\\", "/")
    parts = [p for p in path.split("/") if p and p not in (".", "src", "main", "java", "app", "lib")]
    # Prefer .../domain/foo or .../modules/billing
    for i, part in enumerate(parts):
        if part.lower() in ("domain", "domains", "modules", "services", "packages", "apps"):
            if i + 1 < len(parts):
                return parts[i + 1].replace("-", "_")
    # Java package-ish: com/company/billing/...
    if language == "java":
        m = re.search(r"/(?:com|org|net)/[\w]+/([\w]+)/", "/" + path)
        if m:
            return m.group(1)
    # Fallback: second-level directory
    if len(parts) >= 2:
        return parts[0] if parts[0] not in ("test", "tests") else parts[1]
    return parts[0] if parts else None


def _attach_fk_orphans(snapshot: ArchSnapshot, domains: list[DomainSlice]) -> list[DomainSlice]:
    """Light FK clustering signal: mark entities that only appear via references."""
    # Already have domains; annotate signal for domains dominated by Entity FKs
    name_to_domain = {}
    for d in domains:
        for n in d.elements:
            name_to_domain[n] = d.name
    # No structural change required for MVP — return as-is
    return domains
