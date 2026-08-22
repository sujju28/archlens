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
    tool_aggregate,
    tool_cdm,
    tool_capabilities,
    tool_contracts,
    tool_data_model,
    tool_diagram,
    tool_domains,
    tool_drift,
    tool_events,
    tool_explain,
    tool_federate,
    tool_grain,
    tool_health,
    tool_impact,
    tool_intents,
    tool_onboard,
    tool_ops,
    tool_playbook,
    tool_query,
    tool_reading_priority,
    tool_report,
    tool_rules,
    tool_scan,
    tool_schema_drift,
    tool_strangler,
    tool_timeline,
    tool_traces,
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

    @mcp.tool(name="archlens_aggregate")
    def archlens_aggregate(
        architecture_json_paths: list[str],
        system_name: str = "Distributed System",
    ) -> str:
        """Aggregate architecture.json exports from multiple repositories."""
        return tool_aggregate(architecture_json_paths, system_name=system_name)

    @mcp.tool(name="archlens_events")
    def archlens_events(repo_path: str) -> str:
        """Detect Kafka/RabbitMQ/SQS event producers and consumers."""
        return tool_events(repo_path)

    @mcp.tool(name="archlens_contracts")
    def archlens_contracts(repo_paths: list[str]) -> str:
        """Link services via OpenAPI specs and HTTP call-site matching."""
        return tool_contracts(repo_paths)

    @mcp.tool(name="archlens_health")
    def archlens_health(repo_path: str, trends: bool = True) -> str:
        """Score architecture health (cycles, coupling, layer violations)."""
        return tool_health(repo_path, trends=trends)

    @mcp.tool(name="archlens_cdm")
    def archlens_cdm(
        repo_path: str,
        output_path: str | None = None,
        architecture_json_paths: list[str] | None = None,
        system_name: str = "Distributed System",
        semantics_path: str | None = None,
    ) -> str:
        """Generate a canonical data model (single repo or multi-repo exports + semantics)."""
        return tool_cdm(
            repo_path,
            output_path=output_path,
            architecture_json_paths=architecture_json_paths,
            system_name=system_name,
            semantics_path=semantics_path,
        )

    @mcp.tool(name="archlens_data_model")
    def archlens_data_model(
        repo_path: str,
        output_path: str | None = None,
        architecture_json_paths: list[str] | None = None,
        system_name: str = "Distributed System",
    ) -> str:
        """Generate a standalone basic data-model inventory (not full CDM/ER)."""
        return tool_data_model(
            repo_path,
            output_path=output_path,
            architecture_json_paths=architecture_json_paths,
            system_name=system_name,
        )

    @mcp.tool(name="archlens_capabilities")
    def archlens_capabilities(
        repo_path: str, output_path: str | None = None, refresh: bool = True
    ) -> str:
        """List and refresh the hybrid capability catalog from entry points."""
        return tool_capabilities(repo_path, output_path=output_path, refresh=refresh)

    @mcp.tool(name="archlens_playbook")
    def archlens_playbook(
        repo_path: str,
        capability: str | None = None,
        output_path: str | None = None,
        limit: int = 8,
    ) -> str:
        """Reading path + change playbook for a capability (files to read, blast radius, tests)."""
        return tool_playbook(
            repo_path, capability=capability, output_path=output_path, limit=limit
        )

    @mcp.tool(name="archlens_explain")
    def archlens_explain(repo_path: str, capability: str, no_llm: bool = False) -> str:
        """Grounded capability explanation from citations (optional LLM)."""
        return tool_explain(repo_path, capability, no_llm=no_llm)

    @mcp.tool(name="archlens_strangler")
    def archlens_strangler(repo_path: str, capability: str) -> str:
        """Strangler extract slice: programs, tables, jobs, maps."""
        return tool_strangler(repo_path, capability)

    @mcp.tool(name="archlens_grain")
    def archlens_grain(repo_path: str, capability: str) -> str:
        """Paragraph, PERFORM, method, BMS field, and COPY grain."""
        return tool_grain(repo_path, capability)

    @mcp.tool(name="archlens_onboard")
    def archlens_onboard(repo_path: str, capability: str | None = None) -> str:
        """90-minute onboarding: context, capabilities, one guided change."""
        return tool_onboard(repo_path, capability=capability)

    @mcp.tool(name="archlens_rules")
    def archlens_rules(repo_path: str, capability: str) -> str:
        """Candidate business rules and source comments for a capability."""
        return tool_rules(repo_path, capability)

    @mcp.tool(name="archlens_ops")
    def archlens_ops(repo_path: str, capability: str | None = None) -> str:
        """JCL / CICS TRANSID / BMS ops overlay."""
        return tool_ops(repo_path, capability=capability)

    @mcp.tool(name="archlens_reading_priority")
    def archlens_reading_priority(repo_path: str) -> str:
        """Hotspot vs unreachable reading order."""
        return tool_reading_priority(repo_path)

    @mcp.tool(name="archlens_schema_drift")
    def archlens_schema_drift(repo_path: str, output_path: str | None = None) -> str:
        """Compare inferred CDM against Flyway/Liquibase/DDL schema files."""
        return tool_schema_drift(repo_path, output_path=output_path)

    @mcp.tool(name="archlens_intents")
    def archlens_intents(repo_path: str, validate: bool = True) -> str:
        """Load and validate human architecture intent overlays."""
        return tool_intents(repo_path, validate=validate)

    @mcp.tool(name="archlens_traces")
    def archlens_traces(repo_path: str) -> str:
        """Build behavioral process traces (API→data, CICS chains)."""
        return tool_traces(repo_path)

    @mcp.tool(name="archlens_domains")
    def archlens_domains(repo_path: str) -> str:
        """Slice architecture into domain / bounded-context clusters."""
        return tool_domains(repo_path)

    @mcp.tool(name="archlens_timeline")
    def archlens_timeline(
        repo_path: str, from_ref: str | None = None, to_ref: str | None = None
    ) -> str:
        """Narrative time-travel diff between two snapshots."""
        return tool_timeline(repo_path, from_ref=from_ref, to_ref=to_ref)

    @mcp.tool(name="archlens_federate")
    def archlens_federate(url: str) -> str:
        """Fetch architecture JSON from a remote ArchLens export or HTTP endpoint."""
        return tool_federate(url)

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
