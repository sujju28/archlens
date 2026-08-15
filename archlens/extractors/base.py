"""Abstract base extractor and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from archlens.config import ArchLensConfig
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
        # Prefer ending with class/function name
        if not base.endswith(name):
            return f"{base}.{name}" if base else name
        return base


JAVA_STEREOTYPE_MAP = {
    "RestController": "Controller",
    "Controller": "Controller",
    "Service": "Service",
    "Repository": "Repository",
    "Entity": "Entity",
    "Component": "Component",
    "Configuration": "Configuration",
    "Bean": "Configuration",
    "FeignClient": "Gateway",
    "Aspect": "Middleware",
    "ControllerAdvice": "Middleware",
}

TS_STEREOTYPE_MAP = {
    "Controller": "Controller",
    "Injectable": "Service",
    "Entity": "Entity",
    "Component": "UI Component",
    "Module": "Configuration",
    "NgModule": "Configuration",
    "Middleware": "Middleware",
    "Guard": "Middleware",
    "Interceptor": "Middleware",
    "Pipe": "Component",
}

PYTHON_STEREOTYPE_MAP = {
    "dataclass": "Entity",
    "service": "Service",
    "repository": "Repository",
    "component": "Component",
    "route": "Controller",
    "router": "Controller",
}

PYTHON_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route"}

CONVENTION_DIRS = {
    "controllers": "Controller",
    "controller": "Controller",
    "services": "Service",
    "service": "Service",
    "repositories": "Repository",
    "repository": "Repository",
    "repos": "Repository",
    "models": "Entity",
    "entities": "Entity",
    "middleware": "Middleware",
    "adapters": "Gateway",
    "clients": "Gateway",
    "gateways": "Gateway",
    "config": "Configuration",
    "configs": "Configuration",
    "components": "UI Component",
}


def stereotype_from_annotations(
    annotations: list[str],
    language: str,
    mapping: dict[str, str],
    config: ArchLensConfig | None = None,
) -> str:
    for ann in annotations:
        if config:
            custom = config.custom_stereotype_for(language, ann)
            if custom:
                return custom
        if ann in mapping:
            return mapping[ann]
    return "Unknown"


def stereotype_from_path(file_path: str, config: ArchLensConfig | None = None, language: str = "python") -> str | None:
    if config:
        custom = config.convention_stereotype(language, file_path)
        if custom:
            return custom
    parts = Path(file_path).parts
    for part in parts:
        lower = part.lower()
        if lower in CONVENTION_DIRS:
            return CONVENTION_DIRS[lower]
    return None


def load_query_file(name: str) -> str:
    query_path = Path(__file__).resolve().parent.parent / "queries" / name
    return query_path.read_text(encoding="utf-8")
