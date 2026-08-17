"""Canonical data model Markdown + Mermaid ER diagram generator."""

from __future__ import annotations

from datetime import UTC, datetime

from archlens.analysis.data_model import CanonicalDataModel, build_canonical_data_model
from archlens.models import ArchSnapshot

# Mermaid erDiagram edge budget (preview hosts ~500)
DEFAULT_MAX_ER_EDGES = 400


class CdmReportGenerator:
    def __init__(self, max_er_edges: int = DEFAULT_MAX_ER_EDGES, max_entities: int = 80):
        self.max_er_edges = max_er_edges
        self.max_entities = max_entities

    def generate(self, snapshot: ArchSnapshot, cdm: CanonicalDataModel | None = None) -> str:
        cdm = cdm or build_canonical_data_model(snapshot)
        project = snapshot.metadata.get("project_name", "Canonical Data Model")
        lines = [
            f"# {project} — Canonical Data Model",
            "",
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Commit: `{snapshot.commit_sha}` | Snapshot: `{snapshot.snapshot_id}`",
            "",
            "## How to read this",
            "",
            "This CDM is **inferred from code** (JPA `@Entity` / Adempiere-metasfresh "
            "`I_*` / `X_*` persistent models). It is a logical view of tables, columns, "
            "and FK-style associations — not a substitute for the AD dictionary or DDL.",
            "",
            "## Summary",
            "",
            f"- **Entities (tables):** {cdm.stats.get('entity_count', 0)}",
            f"- **Associations (FKs):** {cdm.stats.get('association_count', 0)}",
            f"- **Columns captured:** {cdm.stats.get('columns_total', 0)}",
            f"- **Kinds:** {cdm.stats.get('kinds', {})}",
            "",
        ]

        if not cdm.entities:
            lines.extend(
                [
                    "_No Entity stereotypes with table metadata were found._",
                    "",
                    "Tips: include generated model sources (e.g. `**/java-gen/**` or "
                    "`I_*.java`), then re-run `archlens scan` and `archlens cdm`.",
                    "",
                ]
            )
            return "\n".join(lines)

        lines.extend(
            [
                "## Entity-relationship diagram",
                "",
            ]
        )
        er = self._er_diagram(cdm)
        if er:
            lines.extend(["```mermaid", er, "```", ""])

        lines.extend(["## Entities", ""])
        # Rank: most FKs / columns first for readability
        ranked = sorted(
            cdm.entities,
            key=lambda e: (-len(e.fk_columns), -len(e.columns), e.table_name.lower()),
        )
        for ent in ranked[: self.max_entities]:
            lines.append(f"### `{ent.table_name}`")
            lines.append("")
            lines.append(f"- **Type:** `{ent.name}` ({ent.kind})")
            if ent.container:
                lines.append(f"- **Container:** {ent.container}")
            lines.append(f"- **Source:** `{ent.file_path}`")
            if ent.columns:
                shown = ", ".join(f"`{c}`" for c in ent.columns[:24])
                if len(ent.columns) > 24:
                    shown += f", … (+{len(ent.columns) - 24})"
                lines.append(f"- **Columns ({len(ent.columns)}):** {shown}")
            if ent.fk_columns:
                lines.append(
                    "- **FK columns:** "
                    + ", ".join(f"`{c}`" for c in ent.fk_columns[:20])
                )
            lines.append("")

        if len(ranked) > self.max_entities:
            lines.append(f"_…and {len(ranked) - self.max_entities} more entities._")
            lines.append("")

        lines.extend(
            [
                "## Associations",
                "",
                "| From | FK | To |",
                "|------|----|----|",
            ]
        )
        for a in sorted(cdm.associations, key=lambda x: (x.source_table, x.fk_column))[
            :200
        ]:
            lines.append(
                f"| `{a.source_table}` | `{a.fk_column}` | `{a.target_table}` |"
            )
        if len(cdm.associations) > 200:
            lines.append(f"| … | _{len(cdm.associations) - 200} more_ | |")
        lines.append("")
        return "\n".join(lines)

    def _er_diagram(self, cdm: CanonicalDataModel) -> str:
        # Pick entities that participate in associations, then fill to max_entities
        connected: set[str] = set()
        for a in cdm.associations:
            connected.add(a.source_table)
            connected.add(a.target_table)

        by_table = {e.table_name: e for e in cdm.entities}
        chosen_tables = sorted(connected)[: self.max_entities]
        if len(chosen_tables) < min(40, len(cdm.entities)):
            for e in sorted(cdm.entities, key=lambda x: -len(x.columns)):
                if e.table_name not in chosen_tables:
                    chosen_tables.append(e.table_name)
                if len(chosen_tables) >= min(40, self.max_entities):
                    break

        lines = ["erDiagram"]
        for table in chosen_tables:
            ent = by_table.get(table)
            if not ent:
                continue
            safe = _safe_er_id(table)
            cols = ent.columns[:8] or ["id"]
            lines.append(f"    {safe} {{")
            for col in cols:
                ctype = "int" if col.endswith("_ID") else "string"
                lines.append(f"        {ctype} {_safe_er_id(col)}")
            lines.append("    }")

        edge_count = 0
        for a in cdm.associations:
            if a.source_table not in chosen_tables or a.target_table not in chosen_tables:
                continue
            if edge_count >= self.max_er_edges:
                break
            lines.append(
                f"    {_safe_er_id(a.source_table)} }}o--|| {_safe_er_id(a.target_table)} : "
                f'"{a.fk_column}"'
            )
            edge_count += 1
        return "\n".join(lines)


def _safe_er_id(value: str) -> str:
    return (
        value.replace("-", "_")
        .replace(".", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )
