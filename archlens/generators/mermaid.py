"""Mermaid.js diagram generator."""

from __future__ import annotations

from archlens.models import ArchSnapshot

LAYER_ORDER = [
    ("Controller", "API Layer"),
    ("Gateway", "API Layer"),
    ("Middleware", "API Layer"),
    ("UI Component", "UI Layer"),
    ("Service", "Service Layer"),
    ("Worker", "Service Layer"),
    ("Repository", "Data Layer"),
    ("Entity", "Data Layer"),
    ("Configuration", "Config Layer"),
    ("Component", "Components"),
]


class MermaidGenerator:
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
        lines = ["graph LR"]
        by_layer: dict[str, list] = {}
        for el in snapshot.elements:
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

        for rel in snapshot.relationships:
            src = self._safe_id(rel.source_id)
            tgt = self._safe_id(rel.target_id)
            lines.append(f"    {src} -->|{rel.rel_type}| {tgt}")

        if highlight:
            lines.append("    classDef highlight fill:#f96,stroke:#333,stroke-width:2px")
        return "\n".join(lines)

    def _container(self, snapshot: ArchSnapshot) -> str:
        # Prefer optional monorepo containers: mapping; else top-level directory
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
        for rel in snapshot.relationships:
            a = pkg_of.get(rel.source_id)
            b = pkg_of.get(rel.target_id)
            if a and b and a != b:
                key = (a, b)
                if key not in seen:
                    seen.add(key)
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
