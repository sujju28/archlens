"""ArchLens MCP tool implementations (IDE-agnostic).

These functions are the shared backend for FastMCP tools and unit tests.
Any IDE that speaks MCP (Claude Code, Copilot, Cursor, Windsurf, Antigravity,
VS Code MCP hosts) can call them via `archlens mcp`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def tool_scan(repo_path: str, commit: str | None = None) -> str:
    from archlens.scanner import scan_repository
    from archlens.storage.sqlite_store import default_db_path

    snap = scan_repository(repo_path, commit=commit)
    stereotypes: dict[str, int] = {}
    for el in snap.elements:
        stereotypes[el.stereotype] = stereotypes.get(el.stereotype, 0) + 1
    return json.dumps(
        {
            "status": "success",
            "snapshot_id": snap.snapshot_id,
            "commit": snap.commit_sha,
            "total_elements": len(snap.elements),
            "total_relationships": len(snap.relationships),
            "elements_by_stereotype": stereotypes,
            "db_path": str(default_db_path(repo_path)),
        },
        indent=2,
    )


def tool_query(
    repo_path: str,
    query: str | None = None,
    stereotype: str | None = None,
    element: str | None = None,
    direction: str = "both",
    group_by: str | None = None,
) -> str:
    from archlens.analysis.nl_query import structured_query
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshots found. Run archlens_scan first."})
    return json.dumps(
        structured_query(
            snap,
            stereotype=stereotype,
            element=element,
            direction=direction,
            group_by=group_by,
            query=query,
        ),
        indent=2,
    )


def tool_impact(
    repo_path: str,
    files: list[str] | None = None,
    elements: list[str] | None = None,
    depth: int = 5,
) -> str:
    from archlens.analysis.impact_analyzer import ImpactAnalyzer
    from archlens.config import load_config
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No architecture database. Run archlens_scan first."})
    report = ImpactAnalyzer(load_config(repo_path)).analyze(
        snap, files=files, elements=elements, depth=depth
    )
    return json.dumps(report.model_dump(), indent=2)


def tool_drift(repo_path: str) -> str:
    result = subprocess.run(
        ["archlens", "drift", "--repo", repo_path, "--output", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode in (0, 2) and result.stdout.strip():
        return result.stdout
    if result.returncode == 0:
        return json.dumps({"status": "no_drift"})
    return json.dumps({"error": result.stderr or "drift check failed", "code": result.returncode})


def tool_diagram(
    repo_path: str,
    level: str = "component",
    format: str = "mermaid",
    highlight: list[str] | None = None,
) -> str:
    from archlens.config import load_config
    from archlens.generators.mermaid import MermaidGenerator
    from archlens.generators.structurizr import StructurizrExporter
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    if format == "structurizr":
        return StructurizrExporter().generate(snap, level=level)
    max_edges = load_config(repo_path).diagrams.max_edges
    return MermaidGenerator(max_edges=max_edges).generate(
        snap, level=level, highlight=highlight
    )


def tool_report(repo_path: str, output_path: str | None = None) -> str:
    from archlens.config import load_config
    from archlens.generators.markdown_report import MarkdownReportGenerator
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    out = Path(output_path) if output_path else Path(repo_path) / "docs" / "ARCHITECTURE.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    max_edges = load_config(repo_path).diagrams.max_edges
    component_mmd = out.parent / "architecture" / "components.mmd"
    rel_link = f"{component_mmd.parent.name}/{component_mmd.name}"
    from archlens.analysis.health import HealthScorer

    store = SQLiteStore(default_db_path(repo_path))
    health = HealthScorer().analyze(snap, store=store)
    md = MarkdownReportGenerator(max_edges=max_edges).generate(
        snap,
        health=health,
        component_diagram_path=component_mmd,
        component_diagram_relpath=rel_link,
    )
    out.write_text(md, encoding="utf-8")
    return json.dumps(
        {
            "status": "success",
            "report_path": str(out),
            "component_diagram_path": str(component_mmd) if component_mmd.exists() else None,
            "elements": len(snap.elements),
            "relationships": len(snap.relationships),
        },
        indent=2,
    )


def tool_aggregate(architecture_json_paths: list[str], system_name: str = "Distributed System") -> str:
    from archlens.distributed.aggregator import aggregate_from_paths

    snap = aggregate_from_paths(architecture_json_paths, system_name=system_name)
    return json.dumps(
        {
            "status": "success",
            "snapshot_id": snap.snapshot_id,
            "total_elements": len(snap.elements),
            "total_relationships": len(snap.relationships),
            "repos": snap.metadata.get("repos", []),
            "snapshot": snap.model_dump(mode="json"),
        },
        indent=2,
    )


def tool_events(repo_path: str) -> str:
    from archlens.config import load_config
    from archlens.distributed.events import EventFlowTracer
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    report = EventFlowTracer(load_config(repo_path)).scan_repo(repo_path, snapshot=snap)
    return json.dumps(report.to_dict(), indent=2)


def tool_contracts(repo_paths: list[str]) -> str:
    from archlens.distributed.openapi_linker import OpenAPIContractLinker

    report = OpenAPIContractLinker().analyze_repos(repo_paths)
    return json.dumps(report.to_dict(), indent=2)


def tool_health(repo_path: str, trends: bool = True) -> str:
    from archlens.analysis.health import HealthScorer
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    store = SQLiteStore(default_db_path(repo_path))
    snap = store.get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    report = HealthScorer().analyze(snap, store=store if trends else None)
    return json.dumps(report.to_dict(), indent=2)


def tool_cdm(repo_path: str, output_path: str | None = None) -> str:
    from archlens.analysis.data_model import build_canonical_data_model
    from archlens.generators.cdm_report import CdmReportGenerator
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    cdm = build_canonical_data_model(snap)
    out = Path(output_path) if output_path else Path(repo_path) / "docs" / "CANONICAL_DATA_MODEL.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(CdmReportGenerator().generate(snap, cdm), encoding="utf-8")
    return json.dumps(
        {
            "status": "success",
            "report_path": str(out),
            **cdm.stats,
        },
        indent=2,
    )


def tool_schema_drift(repo_path: str, output_path: str | None = None) -> str:
    from archlens.analysis.schema_drift import analyze_schema_drift
    from archlens.config import load_config
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    cfg = load_config(repo_path)
    report = analyze_schema_drift(snap, repo_path, globs=cfg.ddl.globs)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.to_markdown(), encoding="utf-8")
    return json.dumps(report.to_dict(), indent=2)


def tool_intents(repo_path: str, validate: bool = True) -> str:
    from archlens.analysis.intents import load_intents, validate_intents
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    intents = load_intents(repo_path)
    payload: dict[str, Any] = intents.model_dump()
    if validate:
        snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
        if snap:
            payload["validation"] = validate_intents(snap, intents=intents)
    return json.dumps(payload, indent=2)


def tool_traces(repo_path: str) -> str:
    from archlens.analysis.process_traces import build_process_traces
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    return json.dumps(build_process_traces(snap).to_dict(), indent=2)


def tool_domains(repo_path: str) -> str:
    from archlens.analysis.domains import slice_domains
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
    if not snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    return json.dumps(slice_domains(snap).to_dict(), indent=2)


def tool_timeline(
    repo_path: str, from_ref: str | None = None, to_ref: str | None = None
) -> str:
    from archlens.analysis.narrative_diff import narrative_diff
    from archlens.storage.sqlite_store import SQLiteStore, default_db_path

    store = SQLiteStore(default_db_path(repo_path))
    to_snap = store.get_snapshot(to_ref) if to_ref else store.get_latest_snapshot()
    if to_ref and not to_snap:
        to_snap = store.get_snapshot_by_commit(to_ref)
    if not to_snap:
        return json.dumps({"error": "No snapshot. Run archlens_scan first."})
    if from_ref:
        from_snap = store.get_snapshot(from_ref) or store.get_snapshot_by_commit(from_ref)
    else:
        snaps = store.list_snapshots(limit=2)
        from_snap = store.get_snapshot(snaps[1]["id"]) if len(snaps) >= 2 else None
    if not from_snap:
        return json.dumps({"error": "Need a prior snapshot for timeline."})
    return json.dumps(narrative_diff(from_snap, to_snap), indent=2)


def tool_federate(url: str) -> str:
    from archlens.distributed.federation import fetch_remote_architecture

    data = fetch_remote_architecture(url)
    return json.dumps(
        {
            "status": "success",
            "url": url,
            "total_elements": len(data.get("elements", [])),
            "total_relationships": len(data.get("relationships", [])),
            "architecture": data,
        },
        indent=2,
    )


TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "archlens_scan", "description": "Scan a codebase and create an architecture snapshot."},
    {"name": "archlens_query", "description": "Query architecture elements and dependencies (NL or structured)."},
    {"name": "archlens_impact", "description": "Analyze blast radius of changed files or elements."},
    {"name": "archlens_drift", "description": "Detect architectural drift vs the latest snapshot."},
    {"name": "archlens_diagram", "description": "Generate Mermaid or Structurizr architecture diagrams."},
    {"name": "archlens_report", "description": "Generate ARCHITECTURE.md from the latest snapshot."},
    {"name": "archlens_aggregate", "description": "Aggregate architecture.json exports from multiple repos."},
    {"name": "archlens_events", "description": "Detect Kafka/RabbitMQ/SQS event producers and consumers."},
    {"name": "archlens_contracts", "description": "Link services via OpenAPI specs and HTTP call sites."},
    {"name": "archlens_health", "description": "Score architecture health (cycles, coupling, layer violations)."},
    {"name": "archlens_cdm", "description": "Generate a canonical data model from Entity/PO/JPA types."},
    {"name": "archlens_schema_drift", "description": "Compare CDM vs Flyway/Liquibase/DDL schema."},
    {"name": "archlens_intents", "description": "Load/validate human architecture intent overlays."},
    {"name": "archlens_traces", "description": "Build API→data and CICS process traces."},
    {"name": "archlens_domains", "description": "Slice architecture into domain/bounded contexts."},
    {"name": "archlens_timeline", "description": "Narrative time-travel diff between snapshots."},
    {"name": "archlens_federate", "description": "Fetch architecture JSON from a remote ArchLens/HTTP URL."},
]
