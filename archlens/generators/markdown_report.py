"""Human-readable ARCHITECTURE.md report generator."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from archlens.generators.mermaid import MermaidGenerator
from archlens.models import ArchSnapshot, ImpactReport


class MarkdownReportGenerator:
    def __init__(self):
        self.mermaid = MermaidGenerator()

    def generate(
        self,
        snapshot: ArchSnapshot,
        impact: ImpactReport | None = None,
    ) -> str:
        counts = Counter(e.stereotype for e in snapshot.elements)
        project = snapshot.metadata.get("project_name", "Architecture Report")
        lines = [
            f"# {project}",
            "",
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Commit: `{snapshot.commit_sha}` | Snapshot: `{snapshot.snapshot_id}`",
            "",
            "## System Overview",
            "",
            "| Stereotype | Count | Elements |",
            "|------------|-------|----------|",
        ]
        by_stereo: dict[str, list[str]] = {}
        for e in snapshot.elements:
            by_stereo.setdefault(e.stereotype, []).append(e.name)

        for stereo, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            names = ", ".join(sorted(by_stereo[stereo])[:8])
            if len(by_stereo[stereo]) > 8:
                names += ", ..."
            lines.append(f"| {stereo} | {count} | {names} |")

        lines.extend(
            [
                "",
                f"**Total elements:** {len(snapshot.elements)} | "
                f"**Relationships:** {len(snapshot.relationships)}",
                "",
                "## Component Diagram",
                "",
                "```mermaid",
                self.mermaid.generate(snapshot, level="component"),
                "```",
                "",
                "## Dependency Matrix",
                "",
            ]
        )

        # Simple dependency matrix for top elements
        names = sorted({e.name for e in snapshot.elements})[:20]
        name_of = {e.id: e.name for e in snapshot.elements}
        deps: dict[str, set[str]] = {n: set() for n in names}
        for rel in snapshot.relationships:
            src = name_of.get(rel.source_id)
            tgt = name_of.get(rel.target_id)
            if src in deps and tgt:
                deps[src].add(tgt)

        if names:
            header = "| Component | Depends on |"
            sep = "|-----------|------------|"
            lines.extend([header, sep])
            for n in names:
                targets = ", ".join(sorted(deps[n])[:10]) or "—"
                lines.append(f"| {n} | {targets} |")

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
