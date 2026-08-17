"""Human intent overlays — versioned architecture intent that extractors cannot know."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from archlens.models import ArchElement, ArchRelationship, ArchSnapshot, RelType


class ForbiddenEdge(BaseModel):
    source: str  # element name, stereotype, or container
    target: str
    reason: str = ""


class CriticalPath(BaseModel):
    name: str
    elements: list[str] = Field(default_factory=list)
    description: str = ""


class Boundary(BaseModel):
    name: str
    include: list[str] = Field(default_factory=list)  # path globs
    exclude: list[str] = Field(default_factory=list)


class ArchitectureIntents(BaseModel):
    """Declarative overlays applied after extraction."""

    stereotype_overrides: dict[str, str] = Field(default_factory=dict)
    owners: dict[str, str] = Field(default_factory=dict)
    forbidden_edges: list[ForbiddenEdge] = Field(default_factory=list)
    critical_paths: list[CriticalPath] = Field(default_factory=list)
    boundaries: list[Boundary] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def default_intents_path(repo: Path) -> Path:
    return repo / ".archlens" / "intents.yaml"


def load_intents(repo: Path | str) -> ArchitectureIntents:
    root = Path(repo)
    candidates = [
        default_intents_path(root),
        root / "intents.yaml",
        root / ".archlens-intents.yaml",
    ]
    for path in candidates:
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return ArchitectureIntents.model_validate(data)
    return ArchitectureIntents()


def write_example_intents(repo: Path | str) -> Path:
    root = Path(repo)
    path = default_intents_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(
        """# Architecture intents (human overlay — optional)
# Applied after code extraction. Keep this file small and reviewed.

stereotype_overrides: {}
#   LegacyBatchRunner: Worker

owners: {}
#   UserService: team-identity

forbidden_edges: []
#   - source: "UI Component"
#     target: "Repository"
#     reason: "UI must not talk to persistence directly"

critical_paths: []
#   - name: Checkout
#     elements: [OrderController, OrderService, OrderRepository]
#     description: Money path

boundaries: []
#   - name: Billing
#     include: ["**/billing/**", "**/payment/**"]

notes: []
""",
        encoding="utf-8",
    )
    return path


def apply_intents(
    snapshot: ArchSnapshot,
    intents: ArchitectureIntents | None = None,
    repo: Path | str | None = None,
) -> ArchSnapshot:
    """Mutate snapshot elements/relationships with intent overlays; return same snapshot."""
    intents = intents or (load_intents(repo) if repo else ArchitectureIntents())
    if not any(
        [
            intents.stereotype_overrides,
            intents.owners,
            intents.forbidden_edges,
            intents.critical_paths,
            intents.boundaries,
        ]
    ):
        return snapshot

    by_name = {e.name: e for e in snapshot.elements}
    for name, stereo in intents.stereotype_overrides.items():
        el = by_name.get(name)
        if el:
            el.stereotype = stereo
            el.metadata["intent_stereotype"] = stereo

    for name, owner in intents.owners.items():
        el = by_name.get(name)
        if el:
            el.metadata["owner"] = owner

    # Boundary tags on elements
    for boundary in intents.boundaries:
        for el in snapshot.elements:
            path = el.file_path.replace("\\", "/")
            if boundary.exclude and any(
                fnmatch.fnmatch(path, p) for p in boundary.exclude
            ):
                continue
            if not boundary.include or any(
                fnmatch.fnmatch(path, p) for p in boundary.include
            ):
                el.metadata.setdefault("domains", [])
                if isinstance(el.metadata["domains"], list) and boundary.name not in el.metadata["domains"]:
                    el.metadata["domains"].append(boundary.name)

    # Critical path membership
    for path in intents.critical_paths:
        for ename in path.elements:
            el = by_name.get(ename)
            if el:
                el.metadata.setdefault("critical_paths", [])
                if path.name not in el.metadata["critical_paths"]:
                    el.metadata["critical_paths"].append(path.name)

    snapshot.metadata["intents"] = {
        "overrides": len(intents.stereotype_overrides),
        "owners": len(intents.owners),
        "forbidden_edges": len(intents.forbidden_edges),
        "critical_paths": len(intents.critical_paths),
        "boundaries": len(intents.boundaries),
    }
    return snapshot


def validate_intents(
    snapshot: ArchSnapshot,
    intents: ArchitectureIntents | None = None,
    repo: Path | str | None = None,
) -> dict[str, Any]:
    """Check forbidden edges and missing critical-path elements."""
    intents = intents or (load_intents(repo) if repo else ArchitectureIntents())
    by_id = {e.id: e for e in snapshot.elements}
    by_name = {e.name.lower(): e for e in snapshot.elements}
    violations: list[dict[str, Any]] = []

    def matches(selector: str, el: ArchElement) -> bool:
        s = selector.strip()
        if not s:
            return False
        if el.name.lower() == s.lower():
            return True
        if el.stereotype.lower() == s.lower():
            return True
        container = (el.metadata or {}).get("container")
        if container and str(container).lower() == s.lower():
            return True
        domains = (el.metadata or {}).get("domains") or []
        return any(str(d).lower() == s.lower() for d in domains)

    for rule in intents.forbidden_edges:
        for rel in snapshot.relationships:
            src = by_id.get(rel.source_id)
            tgt = by_id.get(rel.target_id)
            if not src or not tgt:
                continue
            if matches(rule.source, src) and matches(rule.target, tgt):
                violations.append(
                    {
                        "type": "forbidden_edge",
                        "source": src.name,
                        "target": tgt.name,
                        "rel_type": rel.rel_type,
                        "reason": rule.reason or f"{rule.source} ↛ {rule.target}",
                    }
                )

    missing_critical: list[dict[str, Any]] = []
    for path in intents.critical_paths:
        missing = [n for n in path.elements if n.lower() not in by_name]
        if missing:
            missing_critical.append({"path": path.name, "missing": missing})

    return {
        "violation_count": len(violations),
        "violations": violations[:100],
        "missing_critical_paths": missing_critical,
        "ok": not violations and not missing_critical,
    }


def intent_relationships(intents: ArchitectureIntents, snapshot: ArchSnapshot) -> list[ArchRelationship]:
    """Optional synthetic COMPOSES edges along declared critical paths."""
    by_name = {e.name: e for e in snapshot.elements}
    rels: list[ArchRelationship] = []
    for path in intents.critical_paths:
        ids = [by_name[n].id for n in path.elements if n in by_name]
        for a, b in zip(ids, ids[1:]):
            rels.append(
                ArchRelationship(
                    source_id=a,
                    target_id=b,
                    rel_type=RelType.COMPOSES.value,
                    description=f"critical path: {path.name}",
                    technology="intent",
                )
            )
    return rels
