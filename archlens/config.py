"""Configuration loader for .archlens.yaml.

`.archlens.yaml` is optional and additive. Stereotype detection works out of
the box via a multi-signal cascade (annotations → inheritance → naming →
directory → Component). Use this file only for custom annotations, path
overrides, include/exclude, or monorepo `containers:` mapping.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


DEFAULT_EXCLUDE = [
    "node_modules/",
    "build/",
    "dist/",
    "target/",
    "__pycache__/",
    ".git/",
    ".archlens/",
    "*.test.*",
    "*.spec.*",
    "venv/",
    ".venv/",
]

DEFAULT_INCLUDE = ["src/", "app/", "lib/", ""]


class StereotypeMapping(BaseModel):
    annotation: str | None = None
    decorator: str | None = None
    convention: str | None = None
    stereotype: str


class ContainerMapping(BaseModel):
    """Map subdirectory globs to C4 Container (service) names — monorepo."""

    path: str  # glob relative to repo root, e.g. "apps/api/**" or "services/billing/"
    name: str  # C4 container / service name


class DiagramConfig(BaseModel):
    default_format: str = "mermaid"
    default_level: str = "component"
    output_dir: str = "docs/architecture/"
    # Stay under Mermaid's secure maxEdges default (500); leave headroom for
    # multiple ```mermaid blocks and host off-by-one checks.
    max_edges: int = 400


class ImpactConfig(BaseModel):
    max_depth: int = 5
    critical_stereotypes: list[str] = Field(
        default_factory=lambda: ["Controller", "Gateway"]
    )


class SchemaConfig(BaseModel):
    """DDL / migration paths for CDM triangulation."""

    globs: list[str] = Field(
        default_factory=lambda: [
            "**/db/migration/**/*.sql",
            "**/db/migrations/**/*.sql",
            "**/flyway/**/*.sql",
            "**/liquibase/**/*.{sql,yaml,yml,xml}",
            "**/changelog/**/*.{sql,yaml,yml,xml}",
            "**/schema/**/*.sql",
            "**/ddl/**/*.sql",
        ]
    )
    fail_on_drift: bool = False


class MainframeStereotypeOverride(BaseModel):
    program: str | None = None
    program_pattern: str | None = None  # glob, e.g. "DB*"
    stereotype: str


class MainframeConfig(BaseModel):
    """COBOL / CICS / DB2 / JCL options (Phase 1.5)."""

    dialect: str = "ibm-enterprise"
    copybook_paths: list[str] = Field(default_factory=list)
    jcl_paths: list[str] = Field(default_factory=list)
    bms_maps_path: str | None = None
    cics_definitions: list[str] = Field(default_factory=list)
    # Inline TRANSID → PROGRAM map
    transactions: dict[str, str] = Field(default_factory=dict)
    stereotypes: list[MainframeStereotypeOverride] = Field(default_factory=list)


class ArchLensConfig(BaseModel):
    project_name: str = "My Application"
    languages: list[str] = Field(
        default_factory=lambda: ["java", "typescript", "python", "cobol"]
    )
    stereotypes: dict[str, list[StereotypeMapping]] = Field(default_factory=dict)
    containers: list[ContainerMapping] = Field(default_factory=list)
    include: list[str] = Field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    diagrams: DiagramConfig = Field(default_factory=DiagramConfig)
    impact: ImpactConfig = Field(default_factory=ImpactConfig)
    ddl: SchemaConfig = Field(default_factory=SchemaConfig)
    mainframe: MainframeConfig = Field(default_factory=MainframeConfig)
    intents_path: str | None = None  # override; default .archlens/intents.yaml

    def custom_stereotype_for(self, language: str, annotation: str) -> str | None:
        mappings = self.stereotypes.get(language, [])
        for m in mappings:
            key = m.annotation or m.decorator
            if key and key.lower() == annotation.lower():
                return m.stereotype
        return None

    def convention_stereotype(self, language: str, file_path: str) -> str | None:
        mappings = self.stereotypes.get(language, [])
        normalized = file_path.replace("\\", "/")
        for m in mappings:
            if m.convention:
                pattern = m.convention.replace("*", "").rstrip("/")
                if pattern in normalized:
                    return m.stereotype
        return None

    def container_for(self, file_path: str) -> str | None:
        """Resolve optional monorepo container name for a file path."""
        if not self.containers:
            return None
        normalized = file_path.replace("\\", "/")
        for mapping in self.containers:
            pattern = mapping.path.replace("\\", "/")
            if fnmatch.fnmatch(normalized, pattern):
                return mapping.name
            # Also allow prefix-style paths without **
            prefix = pattern.rstrip("*").rstrip("/")
            if prefix and (normalized == prefix or normalized.startswith(prefix + "/")):
                return mapping.name
        return None

    def mainframe_stereotype_override(self, program_name: str) -> str | None:
        for rule in self.mainframe.stereotypes:
            if rule.program and rule.program.upper() == program_name.upper():
                return rule.stereotype
            if rule.program_pattern and fnmatch.fnmatch(
                program_name.upper(), rule.program_pattern.upper()
            ):
                return rule.stereotype
        return None


def default_config_yaml() -> str:
    return """# .archlens.yaml
# Optional & additive. Detection works without this file via multi-signal cascade:
#   1) annotation/decorator  2) inheritance  3) naming  4) directory  5) Component
project_name: "My Application"
languages:
  - java
  - typescript
  - python
  - cobol

# Custom stereotype mappings (only for non-standard annotations / path overrides)
stereotypes:
  java: []
  # Example:
  #   - annotation: "BusinessLogic"
  #     stereotype: "Service"
  typescript: []
  python: []
  #   - decorator: "batch_job"
  #     stereotype: "Worker"
  #   - convention: "adapters/"
  #     stereotype: "Gateway"

# Mainframe (COBOL/CICS/DB2/JCL) — optional
mainframe:
  dialect: "ibm-enterprise"
  copybook_paths: []
  jcl_paths: []
  # transactions:
  #   CUST: "CUSTINQ"
  stereotypes: []
  #   - program: "CUSTINQ"
  #     stereotype: "Controller"
  #   - program_pattern: "DB*"
  #     stereotype: "Repository"

# Monorepo: map subdirectory globs → C4 Container (service) names
# Leave empty for single-service repos. Multi-repo cross-links are Phase 3.
containers: []
# Example:
#   - path: "apps/api/**"
#     name: "API Service"
#   - path: "apps/web/**"
#     name: "Web App"
#   - path: "packages/billing/**"
#     name: "Billing Service"

# Directories to scan (empty string = repo root)
include:
  - "src/"
  - "app/"
  - "lib/"
  - "cobol/"
  - "jcl/"
  - ""

# Directories / patterns to ignore
exclude:
  - "node_modules/"
  - "build/"
  - "dist/"
  - "target/"
  - "__pycache__/"
  - ".git/"
  - ".archlens/"
  - "*.test.*"
  - "*.spec.*"
  - "venv/"
  - ".venv/"

diagrams:
  default_format: "mermaid"
  default_level: "component"
  output_dir: "docs/architecture/"
  max_edges: 400

impact:
  max_depth: 5
  critical_stereotypes:
    - "Controller"
    - "Gateway"

# Schema / DDL triangulation (CDM vs Flyway/Liquibase/SQL)
ddl:
  globs:
    - "**/db/migration/**/*.sql"
    - "**/db/migrations/**/*.sql"
    - "**/flyway/**/*.sql"
    - "**/schema/**/*.sql"
  fail_on_drift: false

# Human overlays live in .archlens/intents.yaml (owners, forbidden edges, domains)
"""


def find_config_path(repo_path: Path) -> Path | None:
    candidate = repo_path / ".archlens.yaml"
    if candidate.exists():
        return candidate
    return None


def load_config(repo_path: Path | str) -> ArchLensConfig:
    repo = Path(repo_path)
    path = find_config_path(repo)
    if path is None:
        return ArchLensConfig()
    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    stereotypes_raw = data.get("stereotypes") or {}
    stereotypes: dict[str, list[dict[str, Any]]] = {}
    for lang, items in stereotypes_raw.items():
        stereotypes[lang] = items or []
    data["stereotypes"] = stereotypes
    containers_raw = data.get("containers") or []
    data["containers"] = containers_raw
    # Accept legacy `schema:` key as alias for `ddl:`
    if "ddl" not in data and "schema" in data:
        data["ddl"] = data.pop("schema")
    return ArchLensConfig.model_validate(data)


def write_default_config(repo_path: Path | str) -> Path:
    repo = Path(repo_path)
    path = repo / ".archlens.yaml"
    if not path.exists():
        path.write_text(default_config_yaml(), encoding="utf-8")
    return path
