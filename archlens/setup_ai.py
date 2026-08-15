"""Generate platform adapter files for AI coding assistants / IDEs."""

from __future__ import annotations

import json
from pathlib import Path

SHARED_WORKFLOW = """
## Available MCP Tools
- `archlens_scan` — Always run first to ensure a fresh snapshot
- `archlens_query` — Elements & dependencies (NL or structured)
- `archlens_impact` — Blast radius of file/element changes
- `archlens_drift` — Detect architectural drift
- `archlens_diagram` — Mermaid/Structurizr diagrams
- `archlens_report` — Generate ARCHITECTURE.md

## Workflow Guidelines
1. Always scan first if `.archlens/` is missing or stale
2. Impact questions: scan → impact → diagram with highlights
3. Overviews: scan → query (group_by stereotype) → diagram
4. Show dependency chains (WHY, not just WHAT)
5. Be conservative with effort estimates
""".strip()

AGENTS_MD = f"""# ArchLens: Architecture Intelligence

This repository uses ArchLens for automated architecture analysis via MCP.
Supported IDEs/hosts: Claude Code, GitHub Copilot, Cursor, Windsurf, VS Code, Antigravity.

{SHARED_WORKFLOW}
"""

COPILOT_MD = f"""# Architecture Analysis with ArchLens

This project uses ArchLens for architecture intelligence.
Use the ArchLens MCP tools for architecture-related questions.

## When to use ArchLens
- Architecture, structure, or dependency questions
- "What breaks if I change X" / PR blast radius
- Architecture diagrams or documentation freshness

{SHARED_WORKFLOW}
"""

CURSORRULES = f"""# ArchLens Architecture Intelligence

When the user asks about architecture, dependencies, impact of changes,
or code structure, use the ArchLens MCP tools.

{SHARED_WORKFLOW}
"""

WINDSURF_RULES = f"""# ArchLens Architecture Intelligence (Windsurf)

Register and use the ArchLens MCP server for architecture questions.

{SHARED_WORKFLOW}
"""

ANTIGRAVITY_SKILL = f"""---
name: archlens
description: >-
  Architecture intelligence for any codebase. Use when the user asks about
  code architecture, dependencies, impact of changes, effort estimation,
  architecture diagrams, or documentation freshness. Supports Java, TypeScript/React,
  and Python. Works via MCP tools across IDEs.
---

# ArchLens Skill

{SHARED_WORKFLOW}
"""

MCP_SERVER_BLOCK = {
    "archlens": {
        "command": "archlens",
        "args": ["mcp"],
    }
}

MCP_JSON = json.dumps({"mcpServers": MCP_SERVER_BLOCK}, indent=2) + "\n"

VSCODE_MCP_SETTINGS = {
    "github.copilot.chat.mcpServers": MCP_SERVER_BLOCK,
    "mcp": {"servers": MCP_SERVER_BLOCK},
}

ALL_PLATFORMS = {
    "claude",
    "copilot",
    "cursor",
    "windsurf",
    "antigravity",
    "vscode",
}


def _merge_json(path: Path, patch: dict) -> None:
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            existing = {}
    # Deep-ish merge for top-level keys
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            merged = dict(existing[key])
            merged.update(value)
            existing[key] = merged
        else:
            existing[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def generate_adapters(
    repo: Path,
    platforms: list[str],
    *,
    overwrite: bool = False,
) -> list[Path]:
    if "all" in platforms:
        selected = set(ALL_PLATFORMS)
    else:
        selected = set(platforms) & ALL_PLATFORMS

    touched: list[Path] = []

    def write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            return
        path.write_text(content, encoding="utf-8")
        touched.append(path)

    def write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            # Still merge MCP registration into existing JSON configs
            if path.suffix == ".json":
                before = path.read_text(encoding="utf-8")
                _merge_json(path, data)
                after = path.read_text(encoding="utf-8")
                if before != after:
                    touched.append(path)
            return
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        touched.append(path)

    if "claude" in selected:
        write_text(repo / "AGENTS.md", AGENTS_MD)
        write_json(repo / ".claude" / "mcp.json", {"mcpServers": MCP_SERVER_BLOCK})

    if "copilot" in selected:
        write_text(repo / ".github" / "copilot-instructions.md", COPILOT_MD)

    if "cursor" in selected:
        write_text(repo / ".cursorrules", CURSORRULES)
        write_json(repo / ".cursor" / "mcp.json", {"mcpServers": MCP_SERVER_BLOCK})

    if "windsurf" in selected:
        write_text(repo / ".windsurfrules", WINDSURF_RULES)
        write_json(repo / ".windsurf" / "mcp.json", {"mcpServers": MCP_SERVER_BLOCK})

    if "vscode" in selected or "copilot" in selected:
        # Merge MCP registration into VS Code settings without clobbering user settings
        settings_path = repo / ".vscode" / "settings.json"
        before = settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
        _merge_json(settings_path, VSCODE_MCP_SETTINGS)
        after = settings_path.read_text(encoding="utf-8")
        if before != after:
            touched.append(settings_path)
        write_json(repo / ".vscode" / "mcp.json", {"servers": MCP_SERVER_BLOCK})

    if "antigravity" in selected:
        write_text(repo / ".agents" / "skills" / "archlens" / "SKILL.md", ANTIGRAVITY_SKILL)
        write_json(repo / ".agents" / "mcp.json", {"mcpServers": MCP_SERVER_BLOCK})

    return touched
