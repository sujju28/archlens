"""ArchLens MCP Server — Universal AI Agent Interface."""

from __future__ import annotations

import json
import subprocess
from collections import deque
from pathlib import Path

RISK_WEIGHTS = {
    "Controller": 3.0,
    "Gateway": 3.0,
    "Service": 2.0,
    "Repository": 1.5,
    "Configuration": 2.5,
    "Component": 1.0,
    "UI Component": 1.5,
    "Middleware": 2.0,
}


def run_mcp(transport: str = "stdio", port: int = 8080) -> None:
    """Start MCP server. Requires optional dependency: mcp."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("archlens")

    @mcp.tool()
    def archlens_scan(repo_path: str, commit: str | None = None) -> str:
        """Scan a codebase to extract its architecture model."""
        from archlens.scanner import scan_repository
        from archlens.storage.sqlite_store import SQLiteStore, default_db_path

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

    @mcp.tool()
    def archlens_query(
        repo_path: str,
        query: str | None = None,
        stereotype: str | None = None,
        element: str | None = None,
        direction: str = "both",
        group_by: str | None = None,
    ) -> str:
        """Query the architecture database."""
        from archlens.storage.sqlite_store import SQLiteStore, default_db_path

        store = SQLiteStore(default_db_path(repo_path))
        snap = store.get_latest_snapshot()
        if not snap:
            return json.dumps({"error": "No snapshots found. Run archlens_scan first."})

        results = []
        if stereotype:
            results = [
                {
                    "name": e.name,
                    "stereotype": e.stereotype,
                    "language": e.language,
                    "file_path": e.file_path,
                }
                for e in snap.elements
                if e.stereotype.lower() == stereotype.lower()
            ]
        elif element:
            by_id = {e.id: e for e in snap.elements}
            target_ids = {
                e.id
                for e in snap.elements
                if e.name.lower() == element.lower() or element.lower() in e.id.lower()
            }
            if direction in ("upstream", "both"):
                for r in snap.relationships:
                    if r.target_id in target_ids:
                        src = by_id.get(r.source_id)
                        if src:
                            results.append(
                                {
                                    "name": src.name,
                                    "stereotype": src.stereotype,
                                    "file_path": src.file_path,
                                    "rel_type": r.rel_type,
                                    "direction": "upstream",
                                }
                            )
            if direction in ("downstream", "both"):
                for r in snap.relationships:
                    if r.source_id in target_ids:
                        tgt = by_id.get(r.target_id)
                        if tgt:
                            results.append(
                                {
                                    "name": tgt.name,
                                    "stereotype": tgt.stereotype,
                                    "file_path": tgt.file_path,
                                    "rel_type": r.rel_type,
                                    "direction": "downstream",
                                }
                            )
        elif group_by in ("stereotype", "layer"):
            counts: dict[str, int] = {}
            for e in snap.elements:
                counts[e.stereotype] = counts.get(e.stereotype, 0) + 1
            results = [{"stereotype": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
        else:
            results = [
                {
                    "name": e.name,
                    "stereotype": e.stereotype,
                    "language": e.language,
                    "file_path": e.file_path,
                }
                for e in snap.elements
            ]

        return json.dumps({"result_count": len(results), "results": results}, indent=2)

    @mcp.tool()
    def archlens_impact(
        repo_path: str,
        files: list[str] | None = None,
        elements: list[str] | None = None,
        depth: int = 5,
    ) -> str:
        """Analyze the architectural impact of code changes."""
        from archlens.analysis.impact_analyzer import ImpactAnalyzer
        from archlens.config import load_config
        from archlens.storage.sqlite_store import SQLiteStore, default_db_path

        store = SQLiteStore(default_db_path(repo_path))
        snap = store.get_latest_snapshot()
        if not snap:
            return json.dumps({"error": "No architecture database. Run archlens_scan first."})
        report = ImpactAnalyzer(load_config(repo_path)).analyze(
            snap, files=files, elements=elements, depth=depth
        )
        return json.dumps(report.model_dump(), indent=2)

    @mcp.tool()
    def archlens_drift(repo_path: str) -> str:
        """Detect architectural drift between current codebase and last snapshot."""
        result = subprocess.run(
            ["archlens", "drift", "--repo", repo_path, "--output", "json"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout or json.dumps({"status": "no_drift"})
        if result.returncode == 2:
            return result.stdout
        return json.dumps({"error": result.stderr or "drift check failed"})

    @mcp.tool()
    def archlens_diagram(
        repo_path: str,
        level: str = "component",
        format: str = "mermaid",
        highlight: list[str] | None = None,
    ) -> str:
        """Generate an architecture diagram from the latest snapshot."""
        from archlens.generators.mermaid import MermaidGenerator
        from archlens.generators.structurizr import StructurizrExporter
        from archlens.storage.sqlite_store import SQLiteStore, default_db_path

        snap = SQLiteStore(default_db_path(repo_path)).get_latest_snapshot()
        if not snap:
            return json.dumps({"error": "No snapshot. Run archlens_scan first."})
        if format == "structurizr":
            return StructurizrExporter().generate(snap, level=level)
        return MermaidGenerator().generate(snap, level=level, highlight=highlight)

    @mcp.tool()
    def archlens_report(repo_path: str, output_path: str | None = None) -> str:
        """Generate a full ARCHITECTURE.md report."""
        out = output_path or str(Path(repo_path) / "docs" / "ARCHITECTURE.md")
        result = subprocess.run(
            ["archlens", "report", "--repo", repo_path, "--output", out],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return json.dumps({"error": result.stderr})
        return json.dumps({"status": "success", "report_path": out, "summary": result.stdout.strip()})

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # SSE / HTTP transport when supported by FastMCP
        try:
            mcp.run(transport="sse")
        except Exception:
            # Fallback note
            raise SystemExit(
                f"SSE transport unavailable in this mcp version. "
                f"Use --transport stdio. (requested port={port})"
            )
