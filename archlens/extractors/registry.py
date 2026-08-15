"""Language detection and extractor registry."""

from __future__ import annotations

from pathlib import Path

from archlens.config import ArchLensConfig
from archlens.extractors.base import BaseExtractor
from archlens.extractors.java_extractor import JavaExtractor
from archlens.extractors.python_extractor import PythonExtractor
from archlens.extractors.ts_extractor import TypeScriptExtractor
from archlens.models import ArchElement, ArchRelationship


FRAMEWORK_MARKERS = {
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "typescript": ["tsconfig.json", "package.json"],
    "python": ["pyproject.toml", "requirements.txt", "setup.py"],
}


def detect_languages(repo_path: Path) -> list[str]:
    found: list[str] = []
    for lang, markers in FRAMEWORK_MARKERS.items():
        for marker in markers:
            if (repo_path / marker).exists():
                found.append(lang)
                break
    # Also check for source files
    ext_map = {
        "java": {".java"},
        "typescript": {".ts", ".tsx", ".jsx"},
        "python": {".py"},
    }
    for lang, exts in ext_map.items():
        if lang in found:
            continue
        for p in repo_path.rglob("*"):
            if p.suffix in exts and ".archlens" not in p.parts:
                found.append(lang)
                break
    return found


class ExtractorRegistry:
    def __init__(self, config: ArchLensConfig | None = None, repo_root: Path | None = None):
        self.config = config or ArchLensConfig()
        self.repo_root = repo_root
        self._extractors: list[BaseExtractor] = [
            JavaExtractor(self.config, repo_root),
            TypeScriptExtractor(self.config, repo_root),
            PythonExtractor(self.config, repo_root),
        ]

    def for_file(self, file_path: Path) -> BaseExtractor | None:
        suffix = file_path.suffix.lower()
        for extractor in self._extractors:
            if suffix in extractor.supported_extensions():
                # Skip plain .js unless it looks like JSX/React
                if suffix == ".js" and file_path.suffix.lower() == ".js":
                    # still allow
                    pass
                return extractor
        return None

    def scan_files(self, files: list[Path]) -> tuple[list[ArchElement], list[ArchRelationship]]:
        all_elements: list[ArchElement] = []
        for fp in files:
            extractor = self.for_file(fp)
            if not extractor:
                continue
            try:
                all_elements.extend(extractor.extract_elements(fp))
            except Exception:
                continue

        by_id = {e.id: e for e in all_elements}
        # Prefer richer stereotypes if duplicates
        for e in all_elements:
            existing = by_id.get(e.id)
            if existing and existing.stereotype == "Unknown" and e.stereotype != "Unknown":
                by_id[e.id] = e

        all_rels: list[ArchRelationship] = []
        seen_rels: set[tuple[str, str, str]] = set()
        for fp in files:
            extractor = self.for_file(fp)
            if not extractor:
                continue
            try:
                for rel in extractor.extract_relationships(fp, by_id):
                    key = (rel.source_id, rel.target_id, rel.rel_type)
                    if key not in seen_rels:
                        seen_rels.add(key)
                        all_rels.append(rel)
            except Exception:
                continue

        return list(by_id.values()), all_rels
