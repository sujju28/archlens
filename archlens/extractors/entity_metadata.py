"""Extract data-model metadata across Java, TypeScript, Python, and COBOL/DCLGEN."""

from __future__ import annotations

import re
from typing import Any

# --- Java / Adempiere / JPA ---
_TABLE_NAME = re.compile(
    r"""(?:public\s+|static\s+|final\s+)*String\s+Table_Name\s*=\s*["']([^"']+)["']"""
)
_COLUMNNAME = re.compile(
    r"""(?:public\s+|static\s+|final\s+)*String\s+COLUMNNAME_(\w+)\s*=\s*["']([^"']+)["']"""
)
_JPA_TABLE = re.compile(
    r"""@Table\s*\([^)]*name\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_JPA_FIELD = re.compile(
    r"(?:private|protected|public)\s+(?:static\s+)?(?:final\s+)?"
    r"([\w.<>,\s\[\]]+?)\s+(\w+)\s*;"
)

# --- TypeScript / TypeORM / Nest ---
_TS_ENTITY_TABLE = re.compile(
    r"""@Entity\s*\(\s*(?:\{[^}]*name\s*:\s*['"]([^'"]+)['"]|['"]([^'"]+)['"])""",
    re.IGNORECASE,
)
_TS_COLUMN = re.compile(
    r"""@(?:Column|PrimaryColumn|PrimaryGeneratedColumn|CreateDateColumn|UpdateDateColumn)"""
    r"""(?:\([^)]*\))?\s*(?:public\s+|private\s+|readonly\s+|protected\s+)*(\w+)\s*!?\s*[:=]""",
    re.IGNORECASE,
)
_TS_PROP = re.compile(
    r"""(?:public\s+|private\s+|readonly\s+|protected\s+)?(\w+)\s*!\s*:\s*([\w.<>,\s\[\]]+)""",
)
_TS_JOIN = re.compile(
    r"""@JoinColumn\s*\(\s*\{[^}]*name\s*:\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
_TS_MANY_TO_ONE = re.compile(
    r"""@(?:ManyToOne|OneToOne)\s*\(\s*\(\)\s*=>\s*(\w+)""",
    re.IGNORECASE,
)

# --- Python / SQLAlchemy / Pydantic / dataclass ---
_PY_TABLENAME = re.compile(
    r"""__tablename__\s*=\s*['"]([^'"]+)['"]"""
)
_PY_COLUMN = re.compile(
    r"""^(\s*)(\w+)\s*=\s*Column\s*\(""",
    re.MULTILINE,
)
_PY_DATACLASS_FIELD = re.compile(
    r"""^(\s*)(\w+)\s*:\s*([^\n=]+)(?:\s*=\s*.+)?\s*$""",
    re.MULTILINE,
)
_PY_SA_FK = re.compile(
    r"""ForeignKey\s*\(\s*['"]([\w.]+)['"]""",
)

# --- COBOL DCLGEN / copybook ---
_DCLGEN_TABLE = re.compile(
    r"""(?:EXEC\s+SQL\s+)?(?:DECLARE|declare)\s+(\w+)\s+TABLE""",
    re.IGNORECASE,
)
_DCLGEN_SQL_COLS = re.compile(
    r"""DECLARE\s+\w+\s+TABLE\s*\((.*?)\)\s*END-EXEC""",
    re.IGNORECASE | re.DOTALL,
)
_DCL_SQL_COL = re.compile(
    r"""^\s*(\w+)\s+(?:CHAR|VARCHAR|INTEGER|SMALLINT|BIGINT|DECIMAL|NUMERIC|DATE|TIME|TIMESTAMP|FLOAT|REAL|DOUBLE|BLOB|CLOB)\b""",
    re.IGNORECASE | re.MULTILINE,
)
_DCL_LEVEL = re.compile(
    r"""^\s*(\d{1,2})\s+([\w-]+)(?:\s+PIC|\s+USAGE|\s+\.|$)""",
    re.IGNORECASE | re.MULTILINE,
)

_SKIP_FIELDS = {
    "serialVersionUID",
    "logger",
    "log",
    "constructor",
    "prototype",
    "length",
}


def parse_entity_metadata(
    name: str,
    text: str,
    annotations: list[str] | None = None,
    *,
    language: str = "java",
) -> dict[str, Any]:
    """Return table/column/FK metadata for Entity-like types."""
    lang = (language or "java").lower()
    if lang in ("typescript", "javascript", "ts", "js"):
        return parse_typescript_entity_metadata(name, text, annotations)
    if lang in ("python", "py"):
        return parse_python_entity_metadata(name, text, annotations)
    if lang in ("cobol", "cpy", "dclgen"):
        return parse_cobol_data_metadata(name, text)
    return parse_java_entity_metadata(name, text, annotations)


def parse_java_entity_metadata(
    name: str, text: str, annotations: list[str] | None = None
) -> dict[str, Any]:
    annotations = annotations or []
    meta: dict[str, Any] = {}

    table = None
    m = _TABLE_NAME.search(text)
    if m:
        table = m.group(1)
        meta["kind"] = "po"
    else:
        jm = _JPA_TABLE.search(text)
        if jm:
            table = jm.group(1)
            meta["kind"] = "jpa"
        elif "Entity" in annotations or name.endswith("Entity"):
            meta["kind"] = "jpa"
            table = _guess_table_from_name(name)
        elif re.match(r"^[IX]_", name):
            meta["kind"] = "po"
            table = name[2:]
        elif name.endswith("Model"):
            meta["kind"] = "model"
            table = _guess_table_from_name(name)

    if table:
        meta["table_name"] = table

    columns: list[str] = []
    for cm in _COLUMNNAME.finditer(text):
        columns.append(cm.group(2))

    if not columns and meta.get("kind") in ("jpa", "model", None):
        if meta.get("kind") == "jpa" or "Entity" in annotations:
            for fm in _JPA_FIELD.finditer(text):
                fname = fm.group(2)
                if fname in _SKIP_FIELDS or fname.startswith("_"):
                    continue
                columns.append(fname)

    return _finalize(meta, columns, table or name, language="java")


def parse_typescript_entity_metadata(
    name: str, text: str, annotations: list[str] | None = None
) -> dict[str, Any]:
    annotations = annotations or []
    meta: dict[str, Any] = {"kind": "typeorm"}
    table = None
    tm = _TS_ENTITY_TABLE.search(text)
    if tm:
        table = tm.group(1) or tm.group(2)
    if not table and ("Entity" in annotations or name.endswith("Entity") or name.endswith("Model")):
        table = _guess_table_from_name(name)
    if table:
        meta["table_name"] = table

    columns: list[str] = []
    for cm in _TS_COLUMN.finditer(text):
        columns.append(cm.group(1))
    # JoinColumn explicit FK names
    fk_cols = [m.group(1) for m in _TS_JOIN.finditer(text)]
    for fk in fk_cols:
        if fk not in columns:
            columns.append(fk)

    # Relation targets → synthetic FK column names (Order → orderId)
    for rm in _TS_MANY_TO_ONE.finditer(text):
        target = rm.group(1)
        if not target:
            continue
        synth = target[:1].lower() + target[1:] + "Id"
        if synth not in columns:
            columns.append(synth)
        if synth not in fk_cols:
            fk_cols.append(synth)

    # Class property fields (TypeORM definite assignment)
    if "Entity" in annotations or "@Entity" in text or name.endswith("Entity"):
        for pm in _TS_PROP.finditer(text):
            fname = pm.group(1)
            if fname in _SKIP_FIELDS or fname.startswith("_"):
                continue
            if fname not in columns:
                columns.append(fname)

    meta = _finalize(meta, columns, table or name, language="typescript")
    # Prefer explicit JoinColumn FKs
    existing = list(meta.get("fk_columns") or [])
    for fk in fk_cols:
        if fk not in existing:
            existing.append(fk)
    if existing:
        meta["fk_columns"] = existing
    return meta


def parse_python_entity_metadata(
    name: str, text: str, annotations: list[str] | None = None
) -> dict[str, Any]:
    annotations = annotations or []
    meta: dict[str, Any] = {}
    table = None
    tm = _PY_TABLENAME.search(text)
    if tm:
        table = tm.group(1)
        meta["kind"] = "sqlalchemy"
    elif "dataclass" in annotations or name.endswith("Model") or name.endswith("Entity"):
        meta["kind"] = "dataclass" if "dataclass" in annotations else "model"
        table = _guess_table_from_name(name)
    elif any("BaseModel" in a or a == "BaseModel" for a in annotations) or "BaseModel" in text[:500]:
        meta["kind"] = "pydantic"
        table = _guess_table_from_name(name)
    else:
        meta["kind"] = "model"
        table = _guess_table_from_name(name)

    if table:
        meta["table_name"] = table

    columns: list[str] = []
    for cm in _PY_COLUMN.finditer(text):
        columns.append(cm.group(2))

    fk_cols: list[str] = []
    for fm in _PY_SA_FK.finditer(text):
        ref = fm.group(1)  # users.id or order.id
        # Use table_id style
        ref_table = ref.split(".")[0]
        fk_cols.append(f"{ref_table}_id")

    if not columns:
        # dataclass / pydantic annotated fields inside class
        class_m = re.search(rf"class\s+{re.escape(name)}\b[\s\S]*?(?=\nclass\s+|\Z)", text)
        body = class_m.group(0) if class_m else text
        for dm in _PY_DATACLASS_FIELD.finditer(body):
            indent, fname, _ftype = dm.groups()
            if not indent or fname.startswith("_") or fname in ("self", "cls"):
                continue
            if fname in ("Config", "Meta", "model_config"):
                continue
            columns.append(fname)

    meta = _finalize(meta, columns, table or name, language="python")
    existing = list(meta.get("fk_columns") or [])
    for fk in fk_cols:
        if fk not in existing:
            existing.append(fk)
    # Also treat *Id / *_id fields as FKs
    for col in meta.get("columns") or []:
        if (col.endswith("_id") or col.endswith("Id")) and col not in existing:
            if col.lower() not in (f"{(table or name).lower()}_id", "id"):
                existing.append(col)
    if existing:
        meta["fk_columns"] = existing
    return meta


def parse_cobol_data_metadata(name: str, text: str) -> dict[str, Any]:
    """Parse DCLGEN / copybook-style layouts into table + columns."""
    meta: dict[str, Any] = {"kind": "dclgen"}
    table = None
    tm = _DCLGEN_TABLE.search(text)
    if tm:
        table = tm.group(1).upper()
    elif name.upper().startswith("DCL"):
        table = name.upper()[3:]
        meta["kind"] = "dclgen"
    else:
        table = name.upper()
        meta["kind"] = "copybook"

    columns: list[str] = []
    # Prefer DECLARE TABLE SQL column list (canonical DB2 names)
    sm = _DCLGEN_SQL_COLS.search(text)
    if sm:
        for cm in _DCL_SQL_COL.finditer(sm.group(1)):
            columns.append(cm.group(1).upper())
    for lm in _DCL_LEVEL.finditer(text):
        level, field = int(lm.group(1)), lm.group(2).upper().replace("-", "_")
        if level in (1, 77):
            continue
        if field in ("FILLER", "SQLCA"):
            continue
        if level <= 49 and field not in columns:
            columns.append(field)

    if table:
        meta["table_name"] = table
    return _finalize(meta, columns, table or name, language="cobol")


def merge_entity_metadata(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Merge two metadata dicts preferring non-empty columns/fks/table."""
    out = dict(base or {})
    for k, v in (extra or {}).items():
        if k in ("columns", "fk_columns") and isinstance(v, list):
            existing = list(out.get(k) or [])
            for item in v:
                if item not in existing:
                    existing.append(item)
            out[k] = existing
        elif k == "table_name" and v and not out.get("table_name"):
            out[k] = v
        elif k not in out or out[k] in (None, "", [], {}):
            out[k] = v
    return out


def _finalize(
    meta: dict[str, Any],
    columns: list[str],
    own_table: str,
    *,
    language: str,
) -> dict[str, Any]:
    seen: set[str] = set()
    uniq: list[str] = []
    for c in columns:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    if uniq:
        meta["columns"] = uniq
    fk_cols = _infer_fk_columns(uniq, own_table)
    if fk_cols:
        meta["fk_columns"] = fk_cols
    meta["language"] = language
    return meta


def _guess_table_from_name(name: str) -> str:
    for prefix in ("I_", "X_", "DCL"):
        if name.upper().startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix) :]
    for suffix in ("Entity", "Model", "PO", "DTO", "Record"):
        if name.endswith(suffix) and name != suffix:
            return name[: -len(suffix)]
    return name


def _infer_fk_columns(columns: list[str], own_table: str) -> list[str]:
    own_pk_variants = {
        f"{own_table}_ID",
        f"{own_table}_id",
        f"{own_table}Id",
        "id",
        "ID",
    }
    fks: list[str] = []
    for col in columns:
        if col in own_pk_variants:
            continue
        if col.endswith("_ID") or col.endswith("_id") or (col.endswith("Id") and col != "Id"):
            fks.append(col)
    return fks


def fk_target_table(fk_column: str) -> str:
    """Map FK column name to likely table/entity name."""
    col = fk_column
    if col.endswith("_ID"):
        return col[:-3]
    if col.endswith("_id"):
        return col[:-3]
    if col.endswith("Id") and len(col) > 2:
        base = col[:-2]
        # OrderId → Order; userId → user (keep casing)
        return base
    return col
