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


class ImpactConfig(BaseModel):
    max_depth: int = 5
    critical_stereotypes: list[str] = Field(
        default_factory=lambda: ["Controller", "Gateway"]
    )


class ArchLensConfig(BaseModel):
    project_name: str = "My Application"
    languages: list[str] = Field(default_factory=lambda: ["java", "typescript", "python"])
    stereotypes: dict[str, list[StereotypeMapping]] = Field(default_factory=dict)
    containers: list[ContainerMapping] = Field(default_factory=list)
    include: list[str] = Field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    diagrams: DiagramConfig = Field(default_factory=DiagramConfig)
    impact: ImpactConfig = Field(default_factory=ImpactConfig)

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


def default_config_yaml() -> str:
    return """# .archlens.yaml
# Optional & additive. Detection works without this file via multi-signal cascade:
#   1) annotation/decorator  2) inheritance  3) naming  4) directory  5) Component
project_name: "My Application"
languages:
  - java
  - typescript
  - python

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

impact:
  max_depth: 5
  critical_stereotypes:
    - "Controller"
    - "Gateway"
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
    return ArchLensConfig.model_validate(data)


def write_default_config(repo_path: Path | str) -> Path:
    repo = Path(repo_path)
    path = repo / ".archlens.yaml"
    if not path.exists():
        path.write_text(default_config_yaml(), encoding="utf-8")
    return path
