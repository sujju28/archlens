"""Mermaid.js diagram generator."""

from __future__ import annotations

from archlens.models import ArchElement, ArchRelationship, ArchSnapshot, is_code_level

# Stay well under Mermaid's secure default (500). Preview hosts often fail at
# edges.length === maxEdges when adding the next edge, and some VS Code
# previews accumulate edges across multiple ```mermaid blocks on one page.
DEFAULT_MAX_EDGES = 400

LAYER_ORDER = [
    ("Controller", "API Layer"),
    ("Gateway", "API Layer"),
    ("Middleware", "API Layer"),
    ("UI Component", "UI Layer"),
    ("Service", "Service Layer"),
    ("Worker", "Service Layer"),
    ("Batch Job", "Batch Layer"),
    ("Repository", "Data Layer"),
    ("Entity", "Data Layer"),
    ("Shared Data", "Data Layer"),
    ("Configuration", "Config Layer"),
    ("Component", "Components"),
]

_STEREOTYPE_PRIORITY = {
    "Controller": 100,
    "Gateway": 95,
    "Middleware": 90,
    "Service": 80,
    "Worker": 75,
    "Batch Job": 72,
    "Repository": 70,
    "Entity": 60,
    "Shared Data": 58,
    "Configuration": 55,
    "UI Component": 50,
    "Component": 10,
}


class MermaidGenerator:
    def __init__(self, max_edges: int = DEFAULT_MAX_EDGES):
        # max_edges <= 0 means no cap (for .mmd export / mermaid.live).
        self.max_edges = max_edges if max_edges <= 0 else max(1, max_edges)

    def generate(
        self,
        snapshot: ArchSnapshot,
        level: str = "component",
        highlight: list[str] | None = None,
    ) -> str:
        highlight = set(highlight or [])
        if level == "context":
            return self._context(snapshot)
        if level == "container":
            return self._container(snapshot)
        return self._component(snapshot, highlight)

    def _component(self, snapshot: ArchSnapshot, highlight: set[str]) -> str:
        by_id = {e.id: e for e in snapshot.elements if not is_code_level(e)}
        component_rels = [
            r
            for r in snapshot.relationships
            if r.source_id in by_id and r.target_id in by_id
        ]
        selected = self._select_relationships(component_rels, by_id)
        kept_ids = {r.source_id for r in selected} | {r.target_id for r in selected}
        for el in snapshot.elements:
            if el.name in highlight or el.id in highlight:
                kept_ids.add(el.id)

        lines = ["graph LR"]
        by_layer: dict[str, list[ArchElement]] = {}
        for el in snapshot.elements:
            if el.id not in kept_ids:
                continue
            layer = self._layer_for(el.stereotype)
            by_layer.setdefault(layer, []).append(el)

        for layer, els in by_layer.items():
            safe_layer = self._safe_id(layer)
            lines.append(f'    subgraph {safe_layer}["{layer}"]')
            for el in els:
                node_id = self._safe_id(el.id)
                label = f"{el.name}<br/>«{el.stereotype}»"
                if el.name in highlight or el.id in highlight:
                    lines.append(f'        {node_id}["{label}"]:::highlight')
                else:
                    lines.append(f'        {node_id}["{label}"]')
            lines.append("    end")

        for rel in selected:
            src = self._safe_id(rel.source_id)
            tgt = self._safe_id(rel.target_id)
            # Avoid labeled edges: some Mermaid hosts mis-count `|label|` links.
            lines.append(f"    {src} --> {tgt}")

        if highlight:
            lines.append("    classDef highlight fill:#f96,stroke:#333,stroke-width:2px")

        truncated = len(snapshot.relationships) - len(selected)
        if truncated > 0:
            lines.append(
                f"    %% truncated {truncated} of {len(snapshot.relationships)} "
                f"edges (maxEdges={self.max_edges})"
            )
        return "\n".join(lines)

    def _select_relationships(
        self,
        relationships: list[ArchRelationship],
        by_id: dict[str, ArchElement],
    ) -> list[ArchRelationship]:
        if self.max_edges <= 0 or len(relationships) <= self.max_edges:
            return list(relationships)

        def score(rel: ArchRelationship) -> tuple[int, str, str]:
            src = by_id.get(rel.source_id)
            tgt = by_id.get(rel.target_id)
            s = _STEREOTYPE_PRIORITY.get(src.stereotype if src else "", 0)
            t = _STEREOTYPE_PRIORITY.get(tgt.stereotype if tgt else "", 0)
            return (max(s, t) * 2 + min(s, t), rel.source_id, rel.target_id)

        ranked = sorted(relationships, key=score, reverse=True)
        return ranked[: self.max_edges]

    def _container(self, snapshot: ArchSnapshot) -> str:
        lines = ["graph TB"]
        packages: dict[str, list] = {}
        for el in snapshot.elements:
            pkg = el.metadata.get("container") if el.metadata else None
            if not pkg:
                parts = el.file_path.replace("\\", "/").split("/")
                pkg = parts[0] if parts else "root"
            packages.setdefault(pkg, []).append(el)

        for pkg, els in packages.items():
            safe = self._safe_id(pkg)
            stereotypes = sorted({e.stereotype for e in els})
            label = f"{pkg}<br/>{', '.join(stereotypes[:4])}"
            lines.append(f'    {safe}["{label}"]')

        pkg_of = {}
        for el in snapshot.elements:
            pkg = el.metadata.get("container") if el.metadata else None
            if not pkg:
                parts = el.file_path.replace("\\", "/").split("/")
                pkg = parts[0] if parts else "root"
            pkg_of[el.id] = pkg

        seen = set()
        edges: list[tuple[str, str]] = []
        for rel in snapshot.relationships:
            a = pkg_of.get(rel.source_id)
            b = pkg_of.get(rel.target_id)
            if a and b and a != b:
                key = (a, b)
                if key not in seen:
                    seen.add(key)
                    edges.append(key)

        for a, b in (edges if self.max_edges <= 0 else edges[: self.max_edges]):
            lines.append(f"    {self._safe_id(a)} --> {self._safe_id(b)}")
        return "\n".join(lines)

    def _context(self, snapshot: ArchSnapshot) -> str:
        name = snapshot.metadata.get("project_name", "System")
        langs = sorted({e.language for e in snapshot.elements})
        lines = [
            "graph TB",
            f'    System["{name}<br/>«software system»"]',
            '    User["Users"] -->|uses| System',
        ]
        for lang in langs:
            lines.append(f'    System --> {self._safe_id(lang)}["{lang} components"]')
        return "\n".join(lines)

    def _layer_for(self, stereotype: str) -> str:
        for stereo, layer in LAYER_ORDER:
            if stereotype == stereo:
                return layer
        return "Other"

    def _safe_id(self, value: str) -> str:
        return (
            value.replace(".", "_")
            .replace("/", "_")
            .replace("-", "_")
            .replace(" ", "_")
            .replace("«", "")
            .replace("»", "")
        )
