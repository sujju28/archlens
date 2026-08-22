"""Human-readable ARCHITECTURE.md report generator."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from archlens.analysis.data_model import basic_data_model_summary
from archlens.analysis.health import HealthReport, HealthScorer
from archlens.generators.mermaid import DEFAULT_MAX_EDGES, MermaidGenerator
from archlens.models import ArchElement, ArchSnapshot, ImpactReport

_ENTRY_STEREOTYPES = ("Controller", "Gateway")
_ARCH_STEREOTYPES = (
    "Controller",
    "Gateway",
    "Service",
    "Repository",
    "Worker",
    "Middleware",
    "Configuration",
    "Entity",
    "UI Component",
)


class MarkdownReportGenerator:
    def __init__(self, max_edges: int = DEFAULT_MAX_EDGES):
        self.max_edges = max_edges
        self.mermaid = MermaidGenerator(max_edges=max_edges)

    def generate(
        self,
        snapshot: ArchSnapshot,
        impact: ImpactReport | None = None,
        health: HealthReport | None = None,
        *,
        component_diagram_path: Path | str | None = None,
        component_diagram_relpath: str | None = None,
    ) -> str:
        """Build a narrative ARCHITECTURE.md from a snapshot."""
        if health is None:
            health = HealthScorer().analyze(snapshot)

        project = snapshot.metadata.get("project_name", "Architecture Report")
        containers = self._containers(snapshot)
        name_of = {e.id: e.name for e in snapshot.elements}
        by_id = {e.id: e for e in snapshot.elements}

        lines: list[str] = [
            f"# {project}",
            "",
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Commit: `{snapshot.commit_sha}` | Snapshot: `{snapshot.snapshot_id}`",
            "",
            "## How to read this",
            "",
            "ArchLens extracts a C4-style model from source: **containers** "
            "(modules/services), **components** (classes with stereotypes), and "
            "**relationships** (calls, imports, injection). This report summarizes "
            "the scanned scope — not necessarily every file in the monorepo.",
            "",
            "## System Context",
            "",
            "```mermaid",
            self.mermaid.generate(snapshot, level="context"),
            "```",
            "",
            self._narrative_overview(snapshot, containers, health),
            "",
            "## Stereotype Summary",
            "",
            "| Stereotype | Count | Role |",
            "|------------|-------|------|",
        ]

        role_hint = {
            "Controller": "HTTP/API entry points",
            "Gateway": "External/system boundaries",
            "Service": "Business / application logic",
            "Repository": "Persistence / data access",
            "Worker": "Background / async work",
            "Middleware": "Cross-cutting interceptors",
            "Configuration": "Wiring / config",
            "Entity": "Domain data models",
            "UI Component": "Presentation",
            "Component": "General / unclassified types",
        }
        counts = Counter(e.stereotype for e in snapshot.elements)
        for stereo, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"| {stereo} | {count} | {role_hint.get(stereo, '—')} |")

        lines.extend(
            [
                "",
                f"**Total elements:** {len(snapshot.elements)} | "
                f"**Relationships:** {len(snapshot.relationships)} | "
                f"**Containers:** {len(containers)}",
                "",
                "## Container Diagram",
                "",
                "```mermaid",
                self.mermaid.generate(snapshot, level="container"),
                "```",
                "",
                "## Containers (modules)",
                "",
                "Each container is a mapped directory/module and the stereotypes "
                "found inside it.",
                "",
            ]
        )
        lines.extend(self._container_sections(snapshot, containers))

        lines.extend(
            [
                "## Container dependency matrix",
                "",
                "Edges are collapsed from component relationships across container "
                "boundaries (A → B means something in A depends on something in B).",
                "",
            ]
        )
        lines.extend(self._container_matrix(snapshot, containers))

        lines.extend(
            [
                "",
                "## Basic data model",
                "",
            ]
        )
        lines.extend(self._basic_data_model_section(snapshot))

        lines.extend(
            [
                "## API & entry points",
                "",
            ]
        )
        lines.extend(self._entry_points(snapshot, containers))

        lines.extend(
            [
                "",
                "## Capabilities",
                "",
            ]
        )
        lines.extend(self._capabilities_section(snapshot))

        lines.extend(
            [
                "",
                "## Coupling hotspots",
                "",
                "Types with the highest fan-in + fan-out — often shared kernels or "
                "god classes.",
                "",
            ]
        )
        lines.extend(self._hotspots(snapshot, health, containers, by_id))

        lines.extend(
            [
                "",
                "## Architecture health",
                "",
                f"**Score:** {health.score:.1f} (**{health.grade}**) — "
                f"{health.metrics.get('cycle_count', 0)} cycles, "
                f"{health.metrics.get('layer_violation_count', 0)} layer violations, "
                f"avg coupling {health.metrics.get('avg_coupling', 0)}.",
                "",
            ]
        )
        if health.cycles:
            lines.append("### Sample dependency cycles")
            lines.append("")
            for cycle in health.cycles[:5]:
                lines.append(f"- {' → '.join(cycle[:8])}{' → …' if len(cycle) > 8 else ''}")
            lines.append("")

        lines.extend(self._component_diagram_section(snapshot, component_diagram_path, component_diagram_relpath))

        lines.extend(
            [
                "## Key component dependencies",
                "",
                "Top architectural types (controllers/services/repos) and what they "
                "depend on.",
                "",
            ]
        )
        lines.extend(self._arch_dependency_table(snapshot, name_of))

        if impact and (impact.directly_affected or impact.changed_elements):
            lines.extend(
                [
                    "",
                    "## Impact Summary",
                    "",
                    f"- **Changed:** {', '.join(impact.changed_elements) or '—'}",
                    f"- **Direct dependents:** {len(impact.directly_affected)}",
                    f"- **Transitive dependents:** {len(impact.transitively_affected)}",
                    f"- **Risk score:** {impact.risk_score}",
                    "",
                ]
            )
            if impact.suggested_changes:
                lines.append("### Suggested Changes")
                lines.append("")
                for s in impact.suggested_changes:
                    lines.append(f"- {s}")

        lines.append("")
        return "\n".join(lines)

    def _container_name(self, el: ArchElement) -> str:
        if el.metadata and el.metadata.get("container"):
            return str(el.metadata["container"])
        parts = el.file_path.replace("\\", "/").split("/")
        return parts[0] if parts else "root"

    def _containers(self, snapshot: ArchSnapshot) -> dict[str, list[ArchElement]]:
        packages: dict[str, list[ArchElement]] = defaultdict(list)
        for el in snapshot.elements:
            packages[self._container_name(el)].append(el)
        return dict(sorted(packages.items(), key=lambda x: (-len(x[1]), x[0])))

    def _narrative_overview(
        self,
        snapshot: ArchSnapshot,
        containers: dict[str, list[ArchElement]],
        health: HealthReport,
    ) -> str:
        n_ctrl = sum(1 for e in snapshot.elements if e.stereotype == "Controller")
        n_svc = sum(1 for e in snapshot.elements if e.stereotype == "Service")
        n_repo = sum(1 for e in snapshot.elements if e.stereotype == "Repository")
        names = list(containers.keys())
        hub = names[0] if names else "—"
        # Find most depended-upon container
        pkg_of = {e.id: self._container_name(e) for e in snapshot.elements}
        inbound: Counter[str] = Counter()
        for rel in snapshot.relationships:
            a, b = pkg_of.get(rel.source_id), pkg_of.get(rel.target_id)
            if a and b and a != b:
                inbound[b] += 1
        shared = inbound.most_common(1)[0][0] if inbound else hub

        return (
            "## Solution shape\n\n"
            f"This scan covers **{len(containers)} containers** with "
            f"**{n_ctrl} controllers**, **{n_svc} services**, and "
            f"**{n_repo} repositories**. "
            f"Largest module by type count: **{hub}** ({len(containers.get(hub, []))} elements). "
            f"Most depended-on module: **{shared}**. "
            f"Health grade **{health.grade}** "
            f"({health.metrics.get('cycle_count', 0)} cycles, "
            f"{health.metrics.get('layer_violation_count', 0)} layer violations) — "
            "useful as a coupling signal, not a product quality verdict.\n"
        )

    def _container_sections(
        self,
        snapshot: ArchSnapshot,
        containers: dict[str, list[ArchElement]],
    ) -> list[str]:
        lines: list[str] = []
        for name, els in containers.items():
            stereo = Counter(e.stereotype for e in els)
            stereo_s = ", ".join(f"{s} {c}" for s, c in stereo.most_common())
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"**{len(els)}** types — {stereo_s}")
            lines.append("")
            for kind in _ENTRY_STEREOTYPES + ("Service", "Repository"):
                picks = sorted(e.name for e in els if e.stereotype == kind)
                if not picks:
                    continue
                shown = ", ".join(f"`{n}`" for n in picks[:12])
                if len(picks) > 12:
                    shown += f", … (+{len(picks) - 12})"
                lines.append(f"- **{kind}s:** {shown}")
            lines.append("")
        return lines

    def _container_matrix(
        self,
        snapshot: ArchSnapshot,
        containers: dict[str, list[ArchElement]],
    ) -> list[str]:
        names = list(containers.keys())
        pkg_of = {e.id: self._container_name(e) for e in snapshot.elements}
        edges: Counter[tuple[str, str]] = Counter()
        for rel in snapshot.relationships:
            a, b = pkg_of.get(rel.source_id), pkg_of.get(rel.target_id)
            if a and b and a != b:
                edges[(a, b)] += 1

        if not names:
            return ["_No containers detected._", ""]

        # Keep matrix readable
        names = names[:12]
        header = "| From \\ To | " + " | ".join(names) + " |"
        sep = "|---|" + "|".join(["---"] * len(names)) + "|"
        lines = [header, sep]
        for src in names:
            cells = []
            for tgt in names:
                if src == tgt:
                    cells.append("—")
                else:
                    n = edges.get((src, tgt), 0)
                    cells.append(str(n) if n else "")
            lines.append(f"| {src} | " + " | ".join(cells) + " |")
        lines.append("")
        if edges:
            lines.append("**Strongest cross-module edges:**")
            lines.append("")
            for (a, b), n in edges.most_common(10):
                lines.append(f"- `{a}` → `{b}` ({n} relationships)")
            lines.append("")
        return lines

    def _basic_data_model_section(self, snapshot: ArchSnapshot) -> list[str]:
        summary = basic_data_model_summary(snapshot)
        lines = [
            "Inventory of data-facing types extracted across stacks "
            "(Java/TS/Python entities, DB2 tables, JCL datasets). "
            "For columns/FKs and ER diagrams, run `archlens cdm`.",
            "",
            f"- **Entities:** {summary['entity_count']} "
            f"({summary['entities_with_columns']} with columns)",
            f"- **Repositories:** {summary['repository_count']}",
            f"- **Shared data / datasets:** "
            f"{summary['shared_data_count']} / {summary['dataset_count']}",
            f"- **Data relationships:** {summary['data_relationships']}",
        ]
        if summary.get("entities_by_language"):
            langs = ", ".join(
                f"{k}: {v}" for k, v in sorted(summary["entities_by_language"].items())
            )
            lines.append(f"- **Entities by language:** {langs}")
        if summary.get("sample_entities"):
            lines.append(
                "- **Sample entities:** "
                + ", ".join(f"`{n}`" for n in summary["sample_entities"][:12])
            )
        if summary.get("sample_tables"):
            shown = []
            for row in summary["sample_tables"][:10]:
                label = f"`{row['table']}` ({row['columns']} cols"
                if row.get("language"):
                    label += f", {row['language']}"
                label += ")"
                shown.append(label)
            lines.append("- **Sample tables:** " + ", ".join(shown))
        if summary.get("sample_repositories"):
            lines.append(
                "- **Sample repositories:** "
                + ", ".join(f"`{n}`" for n in summary["sample_repositories"][:10])
            )
        lines.append("")
        return lines

    def _capabilities_section(self, snapshot: ArchSnapshot) -> list[str]:
        from archlens.analysis.capabilities import (
            discover_capabilities,
            load_catalog,
            merge_catalog,
        )

        catalog = None
        repo = snapshot.repo_path
        if repo and Path(repo).exists():
            catalog = load_catalog(repo)
        if not catalog or not catalog.capabilities:
            from archlens.analysis.capabilities import CapabilityCatalog

            catalog = merge_catalog(
                catalog or CapabilityCatalog(),
                discover_capabilities(snapshot),
            )
        if not catalog.capabilities:
            return [
                "_No Controller/Gateway/UI/Batch entry points found to seed capabilities._",
                "",
            ]
        approved = [c for c in catalog.capabilities if c.status == "approved"]
        shown = (approved or catalog.capabilities)[:15]
        lines = [
            "Entry points mapped to capabilities (auto-seeded on scan; "
            "curate titles in `.archlens/capabilities.yaml`). "
            "Full catalog: `archlens capabilities`.",
            "",
            f"- **Total:** {len(catalog.capabilities)} "
            f"({sum(1 for c in catalog.capabilities if c.status == 'approved')} approved, "
            f"{sum(1 for c in catalog.capabilities if c.status == 'candidate')} candidates)",
            "",
        ]
        for cap in shown:
            extra = f" — {cap.description}" if cap.description else ""
            lines.append(
                f"- **{cap.title}** (`{cap.stereotype}`) "
                + ", ".join(f"`{n}`" for n in cap.elements[:4])
                + extra
            )
        if len(catalog.capabilities) > len(shown):
            lines.append(f"- _…and {len(catalog.capabilities) - len(shown)} more_")
        lines.append("")
        return lines

    def _entry_points(
        self,
        snapshot: ArchSnapshot,
        containers: dict[str, list[ArchElement]],
    ) -> list[str]:
        entries = [e for e in snapshot.elements if e.stereotype in _ENTRY_STEREOTYPES]
        if not entries:
            return ["_No Controller/Gateway stereotypes detected in this scan._", ""]

        lines = [
            f"Found **{len(entries)}** API/gateway entry points across the scan.",
            "",
            "| Container | Entry point | Stereotype | File |",
            "|-----------|-------------|------------|------|",
        ]
        # Prefer RestController-ish names first
        def sort_key(e: ArchElement) -> tuple:
            return (0 if "Rest" in e.name or "Controller" in e.name else 1, e.name)

        for e in sorted(entries, key=sort_key)[:40]:
            c = self._container_name(e)
            lines.append(f"| {c} | `{e.name}` | {e.stereotype} | `{e.file_path}` |")
        if len(entries) > 40:
            lines.append(f"| … | _{len(entries) - 40} more_ | | |")
        lines.append("")
        return lines

    def _hotspots(
        self,
        snapshot: ArchSnapshot,
        health: HealthReport,
        containers: dict[str, list[ArchElement]],
        by_id: dict[str, ArchElement],
    ) -> list[str]:
        lines = [
            "| Element | Stereotype | Container | Coupling |",
            "|---------|------------|-----------|----------|",
        ]
        if health.highly_coupled:
            for item in health.highly_coupled[:15]:
                name = item.get("name", "?")
                stereo = item.get("stereotype", "?")
                fan_in = item.get("fan_in", 0)
                fan_out = item.get("fan_out", 0)
                coupling = item.get("coupling", fan_in + fan_out)
                # Resolve container by name (first match)
                el = next((e for e in snapshot.elements if e.name == name), None)
                container = self._container_name(el) if el else "—"
                lines.append(
                    f"| `{name}` | {stereo} | {container} | "
                    f"{coupling} (in {fan_in} / out {fan_out}) |"
                )
        else:
            # Fallback: degree from relationships
            degree: Counter[str] = Counter()
            for rel in snapshot.relationships:
                degree[rel.source_id] += 1
                degree[rel.target_id] += 1
            for eid, deg in degree.most_common(15):
                el = by_id.get(eid)
                if not el:
                    continue
                lines.append(
                    f"| `{el.name}` | {el.stereotype} | {self._container_name(el)} | {deg} |"
                )
        lines.append("")
        return lines

    def _arch_dependency_table(
        self,
        snapshot: ArchSnapshot,
        name_of: dict[str, str],
    ) -> list[str]:
        arch = [e for e in snapshot.elements if e.stereotype in _ARCH_STEREOTYPES]
        arch = sorted(arch, key=lambda e: (e.stereotype, e.name))[:30]
        deps: dict[str, set[str]] = {e.name: set() for e in arch}
        arch_ids = {e.id for e in arch}
        for rel in snapshot.relationships:
            if rel.source_id not in arch_ids:
                continue
            src = name_of.get(rel.source_id)
            tgt = name_of.get(rel.target_id)
            if src in deps and tgt:
                deps[src].add(tgt)

        lines = [
            "| Component | Stereotype | Depends on |",
            "|-----------|------------|------------|",
        ]
        for e in arch:
            targets = ", ".join(f"`{t}`" for t in sorted(deps[e.name])[:8]) or "—"
            if len(deps[e.name]) > 8:
                targets += ", …"
            lines.append(f"| `{e.name}` | {e.stereotype} | {targets} |")
        lines.append("")
        return lines

    def _component_diagram_section(
        self,
        snapshot: ArchSnapshot,
        component_diagram_path: Path | str | None,
        component_diagram_relpath: str | None,
    ) -> list[str]:
        total_rels = len(snapshot.relationships)
        lines = ["## Component Diagram", ""]
        if total_rels <= self.max_edges:
            lines.extend(
                [
                    "```mermaid",
                    self.mermaid.generate(snapshot, level="component"),
                    "```",
                    "",
                ]
            )
            return lines

        link = component_diagram_relpath or "docs/architecture/components.mmd"
        if component_diagram_path is not None:
            written = Path(component_diagram_path)
            written.parent.mkdir(parents=True, exist_ok=True)
            full = MermaidGenerator(max_edges=0).generate(snapshot, level="component")
            written.write_text(full, encoding="utf-8")
            lines.extend(
                [
                    f"_Not embedded: {total_rels} relationships exceed Mermaid's "
                    f"~500-edge preview limit._",
                    "",
                    f"Full component graph: [`{link}`]({link}) — open in "
                    "[mermaid.live](https://mermaid.live) with "
                    '`"maxEdges": 5000`.',
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"_Not embedded: {total_rels} relationships exceed preview limit._",
                    "",
                    "```bash",
                    "archlens diagram --level component --output docs/architecture/components.mmd",
                    "```",
                    "",
                ]
            )
        return lines
