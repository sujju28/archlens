"""Abstract base extractor and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from archlens.config import ArchLensConfig
from archlens.extractors.stereotype import (  # noqa: F401 — re-export
    CONVENTION_DIRS,
    JAVA_STEREOTYPE_MAP,
    PYTHON_ROUTE_METHODS,
    PYTHON_STEREOTYPE_MAP,
    TS_STEREOTYPE_MAP,
    load_query_file,
    resolve_stereotype,
    stereotype_from_annotations,
    stereotype_from_name,
    stereotype_from_path,
)
from archlens.models import ArchElement, ArchRelationship


class BaseExtractor(ABC):
    language: str = "unknown"

    def __init__(self, config: ArchLensConfig | None = None, repo_root: Path | None = None):
        self.config = config or ArchLensConfig()
        self.repo_root = repo_root

    @abstractmethod
    def extract_elements(self, file_path: Path) -> list[ArchElement]:
        ...

    @abstractmethod
    def extract_relationships(
        self, file_path: Path, elements: dict[str, ArchElement]
    ) -> list[ArchRelationship]:
        ...

    @abstractmethod
    def supported_extensions(self) -> set[str]:
        ...

    def relative_path(self, file_path: Path) -> str:
        if self.repo_root:
            try:
                return str(file_path.resolve().relative_to(self.repo_root.resolve()))
            except ValueError:
                pass
        return str(file_path)

    def make_id(self, name: str, file_path: Path, qualifier: str | None = None) -> str:
        rel = self.relative_path(file_path).replace("/", ".").replace("\\", ".")
        for ext in self.supported_extensions():
            if rel.endswith(ext):
                rel = rel[: -len(ext)]
                break
        parts = [p for p in rel.split(".") if p and p != "__init__"]
        base = ".".join(parts) if parts else name
        if qualifier:
            return f"{base}.{qualifier}"
        if not base.endswith(name):
            return f"{base}.{name}" if base else name
        return base

    def resolve_element_stereotype(
        self,
        name: str,
        file_path: Path | str,
        annotations: list[str] | None = None,
        extends: str | None = None,
        implements: list[str] | None = None,
        builtin_map: dict[str, str] | None = None,
    ) -> str:
        return resolve_stereotype(
            language=self.language,
            name=name,
            file_path=str(file_path),
            annotations=annotations,
            extends=extends,
            implements=implements,
            config=self.config,
            builtin_map=builtin_map,
        )
