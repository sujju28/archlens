"""Core scanning orchestration."""

from __future__ import annotations

import fnmatch
import subprocess
import uuid
from pathlib import Path

from archlens.analysis.relationship_resolver import RelationshipResolver
from archlens.config import ArchLensConfig, load_config
from archlens.extractors.registry import ExtractorRegistry, detect_languages
from archlens.models import ArchSnapshot
from archlens.storage.sqlite_store import SQLiteStore, default_db_path


def git_rev(repo: Path, ref: str = "HEAD") -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", ref],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def git_branch(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def should_exclude(path: Path, repo: Path, exclude: list[str]) -> bool:
    try:
        rel = str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(path)
    for pattern in exclude:
        pat = pattern.rstrip("/")
        if not pat:
            continue
        if pat in rel.split("/"):
            return True
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern):
            return True
        if any(fnmatch.fnmatch(part, pat) for part in rel.split("/")):
            return True
    return False


def collect_files(repo: Path, config: ArchLensConfig) -> list[Path]:
    include = [i for i in config.include if i is not None]
    files: list[Path] = []
    roots: list[Path] = []
    for inc in include:
        if inc == "" or inc == ".":
            roots.append(repo)
        else:
            candidate = repo / inc
            if candidate.exists():
                roots.append(candidate)
    if not roots:
        roots = [repo]

    extensions = {
        ".java",
        ".ts",
        ".tsx",
        ".jsx",
        ".js",
        ".py",
        ".cbl",
        ".cob",
        ".cpy",
        ".jcl",
        ".proc",
        ".bms",
    }
    seen: set[Path] = set()
    for root in roots:
        if root.is_file():
            candidates = [root]
        else:
            candidates = root.rglob("*")
        for path in candidates:
            if not path.is_file():
                continue
            if path.suffix.lower() not in extensions:
                continue
            if should_exclude(path, repo, config.exclude):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return files


def scan_repository(
    repo_path: Path | str,
    commit: str | None = None,
    config: ArchLensConfig | None = None,
    store: SQLiteStore | None = None,
    persist: bool = True,
) -> ArchSnapshot:
    repo = Path(repo_path).resolve()
    config = config or load_config(repo)

    files = collect_files(repo, config)
    registry = ExtractorRegistry(config, repo)
    elements, relationships = registry.scan_files(files)
    relationships = RelationshipResolver().resolve(elements, relationships)

    # Attach optional monorepo container names (C4 Container mapping)
    for el in elements:
        container = config.container_for(el.file_path)
        if container:
            el.metadata["container"] = container

    commit_sha = commit or git_rev(repo)
    snapshot = ArchSnapshot(
        snapshot_id=str(uuid.uuid4()),
        commit_sha=commit_sha,
        branch=git_branch(repo),
        repo_path=str(repo),
        elements=elements,
        relationships=relationships,
        metadata={
            "project_name": config.project_name,
            "languages": detect_languages(repo) or config.languages,
            "file_count": len(files),
            "archlens_version": "0.1.0",
            "containers": [
                {"path": c.path, "name": c.name} for c in config.containers
            ],
        },
    )

    # Human intent overlays (stereotype/owners/domains/critical paths)
    from archlens.analysis.intents import apply_intents, intent_relationships, load_intents

    intents = load_intents(repo)
    apply_intents(snapshot, intents=intents)
    for rel in intent_relationships(intents, snapshot):
        snapshot.relationships.append(rel)

    if persist:
        store = store or SQLiteStore(default_db_path(repo))
        store.save_snapshot(snapshot)
    return snapshot
