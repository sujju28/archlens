"""Generate platform adapter files for AI coding assistants."""

from __future__ import annotations

from pathlib import Path

AGENTS_MD = """# ArchLens: Architecture Intelligence

This repository uses ArchLens for automated architecture analysis.
The ArchLens MCP server is available with the following tools.

## Available Tools (via MCP)

### `archlens_scan` — Always run this first
Scans the codebase and creates an architecture snapshot.
Run this before answering any architecture questions.

### `archlens_query` — Answer structure questions
Query the architecture database. Supports:
- `stereotype`: Filter by "Controller", "Service", "Repository", etc.
- `element` + `direction`: Find who depends on or what an element depends on
- `group_by`: "stereotype" or "layer" for overview

### `archlens_impact` — Analyze change impact
Given `files` (changed file paths) or `elements` (component names),
traces the full dependency graph and returns directly/transitively affected
components with risk scores. Always show the dependency chain (WHY, not just WHAT).

### `archlens_drift` — Check for architectural drift
Compares current codebase against last snapshot.

### `archlens_diagram` — Generate Mermaid diagrams
Levels: "context", "container", "component"

### `archlens_report` — Generate ARCHITECTURE.md
Creates a full architecture report with diagrams and dependency matrix.

## Workflow Guidelines
1. **Always scan first** if the `.archlens/` database doesn't exist or is stale
2. **For impact questions**: scan → impact → diagram with highlights
3. **For architecture overviews**: scan → query (group by stereotype) → diagram
4. **Be conservative** with effort estimates
5. **Show dependency chains** — explain WHY something is affected
"""

COPILOT_MD = """# Architecture Analysis with ArchLens

This project uses ArchLens for architecture intelligence.
Use the ArchLens MCP tools for architecture-related questions.

## When to use ArchLens
- User asks about code architecture, structure, or dependencies
- User asks "what breaks if I change X" or "what's the impact of this change"
- User asks for an architecture diagram or documentation
- User wants to understand how components are connected

## Tools
- `archlens_scan`: Parse the codebase (always run first)
- `archlens_query`: Find components and dependencies
- `archlens_impact`: Analyze blast radius of changes
- `archlens_drift`: Check if architecture docs are stale
- `archlens_diagram`: Generate Mermaid diagrams
- `archlens_report`: Generate full ARCHITECTURE.md

## Guidelines
- Always ensure a fresh scan exists before querying
- For impact analysis, show the WHY (dependency chain), not just the WHAT
- Use Mermaid diagrams to visualize results when helpful
- Be conservative with effort estimates — overestimate rather than underestimate
"""

CURSORRULES = """# ArchLens Architecture Intelligence

This project has an ArchLens MCP server registered for architecture analysis.

When the user asks about architecture, dependencies, impact of changes,
or code structure, use the ArchLens MCP tools:

1. `archlens_scan` — Always run first to ensure fresh data
2. `archlens_query` — Find components by stereotype or trace dependencies
3. `archlens_impact` — Analyze what breaks when files change
4. `archlens_diagram` — Generate Mermaid component diagrams
5. `archlens_report` — Generate full ARCHITECTURE.md

Always show dependency chains for impact analysis. Be conservative with estimates.
"""

ANTIGRAVITY_SKILL = """---
name: archlens
description: >-
  Architecture intelligence for any codebase. Use when the user asks about
  code architecture, dependencies, impact of changes, effort estimation,
  architecture diagrams, or documentation freshness. Supports Java, TypeScript/React,
  and Python codebases. Works via MCP tools.
---

# ArchLens Skill

## Overview
ArchLens scans codebases using tree-sitter AST parsing to extract architectural
elements and relationships, stores them in SQLite, and provides querying, impact
analysis, drift detection, and diagram generation via MCP tools.

## MCP Tools Available

| Tool | When to Use |
|------|-------------|
| `archlens_scan` | First action — always scan before querying |
| `archlens_query` | "What depends on X?", "Show all services", structure questions |
| `archlens_impact` | "What breaks if I change X?", "Estimate effort for this feature" |
| `archlens_drift` | "Is the architecture doc up to date?" |
| `archlens_diagram` | "Show me the component diagram" |
| `archlens_report` | "Generate ARCHITECTURE.md" |

## Important Rules
- **Always scan first** — never answer architecture questions without a fresh snapshot
- **Show dependency chains** — explain WHY something is affected, not just WHAT
- **Distinguish direct vs. transitive** — direct is certain, transitive is potential
- **Be conservative** — overestimate effort rather than underestimate
"""

MCP_JSON = """{
  "mcpServers": {
    "archlens": {
      "command": "archlens",
      "args": ["mcp"]
    }
  }
}
"""


def generate_adapters(repo: Path, platforms: list[str]) -> list[Path]:
    all_platforms = {"claude", "copilot", "cursor", "antigravity"}
    if "all" in platforms:
        selected = all_platforms
    else:
        selected = set(platforms) & all_platforms

    created: list[Path] = []

    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(path)

    if "claude" in selected:
        write(repo / "AGENTS.md", AGENTS_MD)
        write(repo / ".claude" / "mcp.json", MCP_JSON)

    if "copilot" in selected:
        write(repo / ".github" / "copilot-instructions.md", COPILOT_MD)

    if "cursor" in selected:
        write(repo / ".cursorrules", CURSORRULES)
        write(repo / ".cursor" / "mcp.json", MCP_JSON)

    if "antigravity" in selected:
        write(repo / ".agents" / "skills" / "archlens" / "SKILL.md", ANTIGRAVITY_SKILL)

    return created
