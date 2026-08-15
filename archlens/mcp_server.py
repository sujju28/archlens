"""ArchLens MCP Server — Universal AI Agent Interface for all IDEs.

Supports:
  - stdio transport (Claude Code, Cursor, Windsurf, Copilot, Antigravity, VS Code)
  - SSE / HTTP transport (web and remote hosts)

Usage:
    archlens mcp
    archlens mcp --transport sse --port 8080
"""

from __future__ import annotations

from archlens.mcp_tools import (
    tool_diagram,
    tool_drift,
    tool_impact,
    tool_query,
    tool_report,
    tool_scan,
)


def run_mcp(transport: str = "stdio", port: int = 8080) -> None:
    """Start MCP server. Requires the mcp package (installed by default with archlens)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise SystemExit(
            "MCP SDK not installed. Reinstall with: pip install 'archlens' (mcp is a core dependency)"
        ) from e

    mcp = FastMCP("archlens")

    @mcp.tool(name="archlens_scan")
    def archlens_scan(repo_path: str, commit: str | None = None) -> str:
        """Scan a codebase to extract its architecture model and store a snapshot."""
        return tool_scan(repo_path, commit=commit)

    @mcp.tool(name="archlens_query")
    def archlens_query(
        repo_path: str,
        query: str | None = None,
        stereotype: str | None = None,
        element: str | None = None,
        direction: str = "both",
        group_by: str | None = None,
    ) -> str:
        """Query the architecture database (natural language or structured filters)."""
        return tool_query(
            repo_path,
            query=query,
            stereotype=stereotype,
            element=element,
            direction=direction,
            group_by=group_by,
        )

    @mcp.tool(name="archlens_impact")
    def archlens_impact(
        repo_path: str,
        files: list[str] | None = None,
        elements: list[str] | None = None,
        depth: int = 5,
    ) -> str:
        """Analyze architectural impact of changed files or elements."""
        return tool_impact(repo_path, files=files, elements=elements, depth=depth)

    @mcp.tool(name="archlens_drift")
    def archlens_drift(repo_path: str) -> str:
        """Detect architectural drift between current code and last snapshot."""
        return tool_drift(repo_path)

    @mcp.tool(name="archlens_diagram")
    def archlens_diagram(
        repo_path: str,
        level: str = "component",
        format: str = "mermaid",
        highlight: list[str] | None = None,
    ) -> str:
        """Generate Mermaid or Structurizr diagrams from the latest snapshot."""
        return tool_diagram(repo_path, level=level, format=format, highlight=highlight)

    @mcp.tool(name="archlens_report")
    def archlens_report(repo_path: str, output_path: str | None = None) -> str:
        """Generate a full ARCHITECTURE.md report."""
        return tool_report(repo_path, output_path=output_path)

    if transport == "stdio":
        mcp.run(transport="stdio")
        return

    # SSE / streamable HTTP — API varies by mcp SDK version
    for kwargs in (
        {"transport": "sse"},
        {"transport": "streamable-http"},
    ):
        try:
            # Some versions accept host/port via settings; try run with transport only
            if hasattr(mcp, "settings"):
                try:
                    mcp.settings.port = port
                except Exception:
                    pass
            mcp.run(**kwargs)
            return
        except (TypeError, ValueError, Exception):
            continue

    raise SystemExit(
        f"SSE/HTTP transport is not available in this mcp SDK version "
        f"(requested port={port}). Use: archlens mcp --transport stdio"
    )
