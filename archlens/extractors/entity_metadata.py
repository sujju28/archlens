"""Extract data-model metadata from Java entity / PO / JPA sources."""

from __future__ import annotations

import re
from typing import Any

# Adempiere / metasfresh: String Table_Name = "C_Order";
_TABLE_NAME = re.compile(
    r"""(?:public\s+|static\s+|final\s+)*String\s+Table_Name\s*=\s*["']([^"']+)["']"""
)
# String COLUMNNAME_Foo = "Foo";
_COLUMNNAME = re.compile(
    r"""(?:public\s+|static\s+|final\s+)*String\s+COLUMNNAME_(\w+)\s*=\s*["']([^"']+)["']"""
)
# JPA @Table(name = "orders")
_JPA_TABLE = re.compile(
    r"""@Table\s*\([^)]*name\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
# JPA field: private Type name;
_JPA_FIELD = re.compile(
    r"(?:private|protected|public)\s+(?:static\s+)?(?:final\s+)?"
    r"([\w.<>,\s\[\]]+?)\s+(\w+)\s*;"
)
_SKIP_FIELDS = {"serialVersionUID", "logger", "log"}


def parse_entity_metadata(name: str, text: str, annotations: list[str] | None = None) -> dict[str, Any]:
    """Return table/column/FK metadata for Entity-like types."""
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
            table = name[2:]  # I_C_Order → C_Order
        elif name.endswith("Model"):
            meta["kind"] = "model"
            table = _guess_table_from_name(name)

    if table:
        meta["table_name"] = table

    columns: list[str] = []
    for cm in _COLUMNNAME.finditer(text):
        columns.append(cm.group(2))

    if not columns and meta.get("kind") == "jpa":
        for fm in _JPA_FIELD.finditer(text):
            fname = fm.group(2)
            if fname in _SKIP_FIELDS or fname.startswith("_"):
                continue
            columns.append(fname)

    # Deduplicate preserving order
    seen: set[str] = set()
    uniq_cols: list[str] = []
    for c in columns:
        if c not in seen:
            seen.add(c)
            uniq_cols.append(c)
    if uniq_cols:
        meta["columns"] = uniq_cols

    fk_cols = _infer_fk_columns(uniq_cols, table or name)
    if fk_cols:
        meta["fk_columns"] = fk_cols

    return meta


def _guess_table_from_name(name: str) -> str:
    for prefix in ("I_", "X_"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    for suffix in ("Entity", "Model", "PO"):
        if name.endswith(suffix) and name != suffix:
            return name[: -len(suffix)]
    return name


def _infer_fk_columns(columns: list[str], own_table: str) -> list[str]:
    """Columns ending in _ID that likely reference another table."""
    own_pk = f"{own_table}_ID" if own_table else ""
    fks: list[str] = []
    for col in columns:
        if not col.endswith("_ID"):
            continue
        if col == own_pk:
            continue
        # Skip common non-FK technical IDs? Keep AD_Client_ID / AD_Org_ID as soft FKs.
        fks.append(col)
    return fks


def fk_target_table(fk_column: str) -> str:
    """C_BPartner_ID → C_BPartner; AD_User_ID → AD_User."""
    if fk_column.endswith("_ID"):
        return fk_column[:-3]
    return fk_column
