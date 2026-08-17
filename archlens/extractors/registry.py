"""Language detection and extractor registry."""

from __future__ import annotations

from pathlib import Path

from archlens.config import ArchLensConfig
from archlens.extractors.base import BaseExtractor
from archlens.extractors.cobol_extractor import CobolExtractor
from archlens.extractors.java_extractor import JavaExtractor
from archlens.extractors.jcl_extractor import JclExtractor
from archlens.extractors.python_extractor import PythonExtractor
from archlens.extractors.ts_extractor import TypeScriptExtractor
from archlens.models import ArchElement, ArchRelationship


FRAMEWORK_MARKERS = {
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "typescript": ["tsconfig.json", "package.json"],
    "python": ["pyproject.toml", "requirements.txt", "setup.py"],
    "cobol": [".cbl", ".cob"],  # detected via extensions below
}


def detect_languages(repo_path: Path) -> list[str]:
    found: list[str] = []
    for lang, markers in FRAMEWORK_MARKERS.items():
        if lang == "cobol":
            continue
        for marker in markers:
            if (repo_path / marker).exists():
                found.append(lang)
                break
    ext_map = {
        "java": {".java"},
        "typescript": {".ts", ".tsx", ".jsx"},
        "python": {".py"},
        "cobol": {".cbl", ".cob", ".cpy", ".dcl"},
        "jcl": {".jcl", ".proc"},
    }
    for lang, exts in ext_map.items():
        label = "cobol" if lang == "jcl" else lang
        if label in found:
            continue
        for p in repo_path.rglob("*"):
            if p.suffix.lower() in exts and ".archlens" not in p.parts:
                found.append(label)
                break
    return found


def _element_richness(el: ArchElement) -> int:
    meta = el.metadata or {}
    score = 0
    if meta.get("kind") == "program_ref":
        score -= 50
    if meta.get("from_jcl"):
        score -= 20
    score += len(meta.get("calls") or [])
    score += len(meta.get("cics_links") or [])
    score += len(meta.get("tables_read") or [])
    score += len(el.annotations or [])
    if el.stereotype not in ("Component", "Unknown", "Batch Job"):
        score += 5
    return score


class ExtractorRegistry:
    def __init__(self, config: ArchLensConfig | None = None, repo_root: Path | None = None):
        self.config = config or ArchLensConfig()
        self.repo_root = repo_root
        self._extractors: list[BaseExtractor] = [
            JavaExtractor(self.config, repo_root),
            TypeScriptExtractor(self.config, repo_root),
            PythonExtractor(self.config, repo_root),
            CobolExtractor(self.config, repo_root),
            JclExtractor(self.config, repo_root),
        ]

    def for_file(self, file_path: Path) -> BaseExtractor | None:
        suffix = file_path.suffix.lower()
        for extractor in self._extractors:
            if suffix in {s.lower() for s in extractor.supported_extensions()}:
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

        by_id: dict[str, ArchElement] = {}
        for e in all_elements:
            existing = by_id.get(e.id)
            if existing is None:
                by_id[e.id] = e
                continue
            if _element_richness(e) > _element_richness(existing):
                # Merge flags from placeholder
                merged_meta = dict(existing.metadata or {})
                merged_meta.update(e.metadata or {})
                e.metadata = merged_meta
                by_id[e.id] = e
            else:
                merged_meta = dict(e.metadata or {})
                merged_meta.update(existing.metadata or {})
                existing.metadata = merged_meta

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
