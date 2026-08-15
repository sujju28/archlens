"""Configuration loader for .archlens.yaml."""

from __future__ import annotations

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


def default_config_yaml() -> str:
    return """# .archlens.yaml
project_name: "My Application"
languages:
  - java
  - typescript
  - python

# Custom stereotype mappings
stereotypes:
  java: []
  typescript: []
  python: []

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
    # Normalize stereotype mappings from YAML list-of-dicts
    stereotypes_raw = data.get("stereotypes") or {}
    stereotypes: dict[str, list[dict[str, Any]]] = {}
    for lang, items in stereotypes_raw.items():
        stereotypes[lang] = items or []
    data["stereotypes"] = stereotypes
    return ArchLensConfig.model_validate(data)


def write_default_config(repo_path: Path | str) -> Path:
    repo = Path(repo_path)
    path = repo / ".archlens.yaml"
    if not path.exists():
        path.write_text(default_config_yaml(), encoding="utf-8")
    return path
