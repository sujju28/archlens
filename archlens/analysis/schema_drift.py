"""Triangulate inferred CDM against Flyway / Liquibase / raw DDL."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archlens.analysis.data_model import CanonicalDataModel, build_canonical_data_model
from archlens.models import ArchSnapshot

_CREATE_TABLE = re.compile(
    r"""CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:["`]?(\w+)["`]?\.)?["`]?(\w+)["`]?\s*\((.*?)\)""",
    re.IGNORECASE | re.DOTALL,
)
_COL_LINE = re.compile(
    r"""^\s*["`]?(\w+)["`]?\s+""",
    re.MULTILINE,
)
_LIQUIBASE_TABLE = re.compile(
    r"""(?:tableName|tableName:)\s*["']?(\w+)["']?""",
    re.IGNORECASE,
)
_LIQUIBASE_COL = re.compile(
    r"""(?:columnName|name:)\s*["']?(\w+)["']?""",
    re.IGNORECASE,
)
_SKIP_SQL_TOKENS = {
    "CONSTRAINT",
    "PRIMARY",
    "UNIQUE",
    "FOREIGN",
    "CHECK",
    "INDEX",
    "KEY",
    "REFERENCES",
}


@dataclass
class SchemaTable:
    name: str
    columns: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class SchemaDriftReport:
    schema_tables: list[SchemaTable]
    cdm_tables: list[str]
    only_in_schema: list[str]
    only_in_cdm: list[str]
    column_mismatches: list[dict[str, Any]]
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def has_drift(self) -> bool:
        return bool(self.only_in_schema or self.only_in_cdm or self.column_mismatches)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_tables": [
                {"name": t.name, "columns": t.columns, "source": t.source}
                for t in self.schema_tables
            ],
            "cdm_tables": self.cdm_tables,
            "only_in_schema": self.only_in_schema,
            "only_in_cdm": self.only_in_cdm,
            "column_mismatches": self.column_mismatches,
            "stats": self.stats,
            "has_drift": self.has_drift,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Schema ↔ CDM Drift",
            "",
            f"- **Schema tables:** {self.stats.get('schema_table_count', 0)}",
            f"- **CDM tables:** {self.stats.get('cdm_table_count', 0)}",
            f"- **Only in schema (DDL):** {len(self.only_in_schema)}",
            f"- **Only in CDM (code):** {len(self.only_in_cdm)}",
            f"- **Column mismatches:** {len(self.column_mismatches)}",
            "",
        ]
        if not self.has_drift:
            lines.append("_No schema↔CDM drift detected._")
            lines.append("")
            return "\n".join(lines)

        if self.only_in_schema:
            lines.extend(["## Tables only in schema/DDL", ""])
            for t in self.only_in_schema[:50]:
                lines.append(f"- `{t}`")
            lines.append("")
        if self.only_in_cdm:
            lines.extend(["## Tables only in code CDM", ""])
            for t in self.only_in_cdm[:50]:
                lines.append(f"- `{t}`")
            lines.append("")
        if self.column_mismatches:
            lines.extend(
                [
                    "## Column mismatches",
                    "",
                    "| Table | Only in schema | Only in CDM |",
                    "|-------|----------------|-------------|",
                ]
            )
            for m in self.column_mismatches[:80]:
                lines.append(
                    f"| `{m['table']}` | "
                    f"{', '.join(f'`{c}`' for c in m.get('only_in_schema', [])[:8]) or '—'} | "
                    f"{', '.join(f'`{c}`' for c in m.get('only_in_cdm', [])[:8]) or '—'} |"
                )
            lines.append("")
        return "\n".join(lines)


DEFAULT_SCHEMA_GLOBS = [
    "**/db/migration/**/*.sql",
    "**/db/migrations/**/*.sql",
    "**/flyway/**/*.sql",
    "**/liquibase/**/*.{sql,yaml,yml,xml}",
    "**/changelog/**/*.{sql,yaml,yml,xml}",
    "**/schema/**/*.sql",
    "**/ddl/**/*.sql",
    "**/ddl/**/*.ddl",
    "**/sql/**/*.sql",
]


def discover_schema_files(repo: Path, globs: list[str] | None = None) -> list[Path]:
    patterns = globs or DEFAULT_SCHEMA_GLOBS
    found: set[Path] = set()
    for pattern in patterns:
        expanded = _expand_brace_glob(pattern)
        for pat in expanded:
            for path in repo.glob(pat):
                if path.is_file():
                    found.add(path.resolve())
    return sorted(found)


def _expand_brace_glob(pattern: str) -> list[str]:
    """Expand simple `{a,b}` suffixes for pathlib (no full brace engine)."""
    if "{" not in pattern or "}" not in pattern:
        return [pattern]
    start = pattern.index("{")
    end = pattern.index("}", start)
    options = pattern[start + 1 : end].split(",")
    prefix, suffix = pattern[:start], pattern[end + 1 :]
    return [f"{prefix}{opt.strip()}{suffix}" for opt in options if opt.strip()]


def parse_schema_files(files: list[Path]) -> list[SchemaTable]:
    by_name: dict[str, SchemaTable] = {}
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path)
        for table in _parse_sql(text, rel) + _parse_liquibaseish(text, rel):
            key = table.name.lower()
            existing = by_name.get(key)
            if existing is None:
                by_name[key] = table
                continue
            for col in table.columns:
                if col not in existing.columns:
                    existing.columns.append(col)
            if table.source and table.source not in existing.source:
                existing.source = f"{existing.source}; {table.source}"
    return sorted(by_name.values(), key=lambda t: t.name.lower())


def compare_schema_to_cdm(
    schema_tables: list[SchemaTable],
    cdm: CanonicalDataModel,
) -> SchemaDriftReport:
    schema_map = {t.name.lower(): t for t in schema_tables}
    cdm_map = {e.table_name.lower(): e for e in cdm.entities}
    only_schema = sorted(schema_map.keys() - cdm_map.keys())
    only_cdm = sorted(cdm_map.keys() - schema_map.keys())
    mismatches: list[dict[str, Any]] = []
    for key in sorted(schema_map.keys() & cdm_map.keys()):
        s_cols = {c.lower() for c in schema_map[key].columns}
        c_cols = {c.lower() for c in (cdm_map[key].columns or [])}
        if not s_cols or not c_cols:
            continue
        only_s = sorted(s_cols - c_cols)
        only_c = sorted(c_cols - s_cols)
        if only_s or only_c:
            mismatches.append(
                {
                    "table": cdm_map[key].table_name,
                    "only_in_schema": only_s,
                    "only_in_cdm": only_c,
                }
            )
    return SchemaDriftReport(
        schema_tables=schema_tables,
        cdm_tables=[e.table_name for e in cdm.entities],
        only_in_schema=[schema_map[k].name for k in only_schema],
        only_in_cdm=[cdm_map[k].table_name for k in only_cdm],
        column_mismatches=mismatches,
        stats={
            "schema_table_count": len(schema_tables),
            "cdm_table_count": len(cdm.entities),
            "schema_files": len({t.source.split(";")[0] for t in schema_tables if t.source}),
        },
    )


def analyze_schema_drift(
    snapshot: ArchSnapshot,
    repo: Path | str,
    *,
    globs: list[str] | None = None,
    cdm: CanonicalDataModel | None = None,
) -> SchemaDriftReport:
    root = Path(repo)
    files = discover_schema_files(root, globs)
    tables = parse_schema_files(files)
    model = cdm or build_canonical_data_model(snapshot)
    report = compare_schema_to_cdm(tables, model)
    report.stats["schema_files"] = len(files)
    return report


def _parse_sql(text: str, source: str) -> list[SchemaTable]:
    tables: list[SchemaTable] = []
    for m in _CREATE_TABLE.finditer(text):
        name = (m.group(2) or m.group(1) or "").strip()
        if not name:
            continue
        body = m.group(3) or ""
        cols: list[str] = []
        for cm in _COL_LINE.finditer(body):
            col = cm.group(1)
            if col.upper() in _SKIP_SQL_TOKENS:
                continue
            if col not in cols:
                cols.append(col)
        tables.append(SchemaTable(name=name, columns=cols, source=source))
    return tables


def _parse_liquibaseish(text: str, source: str) -> list[SchemaTable]:
    """Best-effort Liquibase YAML/XML createTable extraction."""
    lower = text.lower()
    if "createtable" not in lower and "tablename" not in lower and "table_name" not in lower:
        return []
    tables: list[SchemaTable] = []
    chunks = re.split(r"createTable", text, flags=re.IGNORECASE)
    for chunk in chunks[1:]:
        tm = _LIQUIBASE_TABLE.search(chunk)
        if not tm:
            continue
        name = tm.group(1)
        cols: list[str] = []
        for cm in _LIQUIBASE_COL.finditer(chunk[:2000]):
            col = cm.group(1)
            if col.lower() in ("tablename", "schemaname"):
                continue
            if col not in cols:
                cols.append(col)
        tables.append(SchemaTable(name=name, columns=cols, source=source))
    return tables
