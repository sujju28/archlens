"""CDM semantic overlays — aliases, ownership, and cross-repo same-as links.

These make a code-inferred CDM closer to a classical canonical model without
replacing extraction: humans declare what “Customer” means across services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SameAsGroup(BaseModel):
    """Tables that represent the same logical/canonical entity."""

    tables: list[str] = Field(default_factory=list)
    canonical: str
    description: str = ""


class CdmSemantics(BaseModel):
    """Explicit semantic layer over inferred tables."""

    # local_or_qualified_name → canonical name
    aliases: dict[str, str] = Field(default_factory=dict)
    # canonical entity → owning team / system
    owners: dict[str, str] = Field(default_factory=dict)
    # merge groups
    same_as: list[SameAsGroup] = Field(default_factory=list)
    # drop noise tables (exact or simple glob with *)
    suppress: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def default_cdm_semantics_path(repo: Path) -> Path:
    return repo / ".archlens" / "cdm.yaml"


def load_cdm_semantics(
    repo: Path | str | None = None,
    path: Path | str | None = None,
) -> CdmSemantics:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    if repo:
        root = Path(repo)
        candidates.extend(
            [
                default_cdm_semantics_path(root),
                root / "cdm.yaml",
                root / ".archlens-cdm.yaml",
            ]
        )
    for p in candidates:
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            # Allow embedding under intents-style `cdm:` key
            if "cdm" in data and isinstance(data["cdm"], dict):
                data = data["cdm"]
            return CdmSemantics.model_validate(data)
    return CdmSemantics()


def write_example_cdm_semantics(repo: Path | str) -> Path:
    root = Path(repo)
    path = default_cdm_semantics_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(
        """# CDM semantics (optional) — human canonical layer over inferred tables
# Applied by `archlens cdm` / aggregate CDM. Keep small and reviewed.

# Map local / physical names → canonical business names
aliases: {}
#   users: Customer
#   C_BPartner: BusinessPartner
#   billing::users: Customer

# Who owns the canonical entity
owners: {}
#   Customer: team-crm
#   Order: team-orders

# Cross-repo / synonym tables that are the same logical entity
same_as: []
#   - canonical: Customer
#     tables: [users, customer, C_BPartner, billing::users]
#     description: Party master across services

# Drop noise from CDM (exact name or prefix*)
suppress: []
#   - SYSDUMMY1
#   - temp_*

notes: []
""",
        encoding="utf-8",
    )
    return path


def resolve_canonical_name(table: str, semantics: CdmSemantics) -> str:
    """Resolve a table name through aliases and same_as groups."""
    if not table:
        return table
    # Direct alias (case-insensitive)
    lower_map = {k.lower(): v for k, v in semantics.aliases.items()}
    if table.lower() in lower_map:
        return lower_map[table.lower()]
    # same_as membership
    for group in semantics.same_as:
        members = {t.lower() for t in group.tables}
        if table.lower() in members or table.lower() == group.canonical.lower():
            return group.canonical
    return table


def is_suppressed(table: str, semantics: CdmSemantics) -> bool:
    import fnmatch

    name = table or ""
    for pattern in semantics.suppress:
        if fnmatch.fnmatch(name.lower(), pattern.lower()) or fnmatch.fnmatch(
            name, pattern
        ):
            return True
    return False


def semantics_to_dict(semantics: CdmSemantics) -> dict[str, Any]:
    return semantics.model_dump()
