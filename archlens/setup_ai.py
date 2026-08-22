"""Generate platform adapter files for AI coding assistants / IDEs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

SKILLS_SOURCE = Path(__file__).resolve().parent / "skills"

SHARED_WORKFLOW = """
## ArchLens (do not free-prompt the architecture)

Use **MCP tools** named `archlens_*`, or the `archlens` CLI. Cite tool output.
Do not invent owners, business rules, runtime behavior, or graph edges.

### Always
- Stale or missing snapshot → `archlens_scan` (init first if `.archlens/` is missing)
- New developer / "how does this system work" → `archlens_onboard`
- Change a feature → `archlens_playbook` then `archlens_explain` (`no_llm` unless asked) then `archlens_impact`
- What breaks → `archlens_impact` (optional `archlens_strangler`)
- Tables / CDM → `archlens_cdm` / `archlens_schema_drift`
- COBOL / CICS / JCL → `archlens_grain` + `archlens_ops` + `archlens_rules`

### MCP tools (subset)
`archlens_scan`, `archlens_query`, `archlens_impact`, `archlens_playbook`, `archlens_explain`,
`archlens_onboard`, `archlens_capabilities`, `archlens_strangler`, `archlens_grain`,
`archlens_rules`, `archlens_ops`, `archlens_reading_priority`, `archlens_cdm`,
`archlens_schema_drift`, `archlens_drift`, `archlens_intents`, `archlens_traces`,
`archlens_domains`, `archlens_timeline`, `archlens_health`, `archlens_diagram`, `archlens_report`
""".strip()

AGENTS_MD = f"""# ArchLens: Architecture Intelligence

This repository uses ArchLens for living architecture analysis (MCP + project skills).

Project skills (Cursor/Claude/Antigravity): `.cursor/skills/archlens-*`, same files under `.claude/skills/` and `.agents/skills/`.
Prefer those skills over ad-hoc prompts. Architect entry: skill `archlens-architect`.

{SHARED_WORKFLOW}
"""

COPILOT_MD = f"""# Architecture Analysis with ArchLens

This project uses ArchLens. Use ArchLens MCP tools for architecture questions; follow the workflows below instead of inventing a prompt.

## When to use ArchLens
- Onboarding / what to read first
- "What breaks if I change X" / PR blast radius
- Data model, COBOL/CICS, drift, diagrams

{SHARED_WORKFLOW}
"""

CURSORRULES = f"""# ArchLens Architecture Intelligence

When the user asks about architecture, onboarding, dependencies, impact, COBOL/CICS, or data model, use ArchLens MCP tools and the project skills under `.cursor/skills/archlens-*`.

{SHARED_WORKFLOW}
"""

CURSOR_RULE_MDC = f"""---
description: ArchLens living architecture — MCP tools and project skills
alwaysApply: true
---

{CURSORRULES}
"""

WINDSURF_RULES = f"""# ArchLens Architecture Intelligence (Windsurf)

Register and use the ArchLens MCP server. Follow project skills if present under `.cursor/skills/`.

{SHARED_WORKFLOW}
"""

ANTIGRAVITY_SKILL = f"""---
name: archlens
description: >-
  Architecture intelligence via ArchLens MCP. Use for onboarding, change
  playbooks, impact, CDM, COBOL/CICS, drift, and diagrams. Never invent
  architecture that is not in the snapshot.
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

SKILL_INSTALL_DIRS = (
    Path(".cursor") / "skills",
    Path(".claude") / "skills",
    Path(".agents") / "skills",
)


def _merge_json(path: Path, patch: dict) -> None:
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            existing = {}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            merged = dict(existing[key])
            merged.update(value)
            existing[key] = merged
        else:
            existing[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def packaged_skill_dirs() -> list[Path]:
    if not SKILLS_SOURCE.is_dir():
        return []
    dirs = sorted(p for p in SKILLS_SOURCE.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
    return dirs


def install_skills(repo: Path, *, overwrite: bool = False) -> list[Path]:
    """Copy packaged ArchLens skills into IDE project skill folders."""
    touched: list[Path] = []
    shared = SKILLS_SOURCE / "_shared.md"
    skill_dirs = packaged_skill_dirs()
    if not skill_dirs:
        return touched

    for rel_root in SKILL_INSTALL_DIRS:
        dest_root = repo / rel_root
        dest_root.mkdir(parents=True, exist_ok=True)
        if shared.is_file():
            dest_shared = dest_root / "_shared.md"
            if overwrite or not dest_shared.exists():
                shutil.copy2(shared, dest_shared)
                touched.append(dest_shared)
        for src in skill_dirs:
            dest = dest_root / src.name
            dest.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                if not item.is_file():
                    continue
                target = dest / item.name
                if target.exists() and not overwrite:
                    continue
                shutil.copy2(item, target)
                touched.append(target)
    return touched


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
            if path.suffix == ".json":
                before = path.read_text(encoding="utf-8")
                _merge_json(path, data)
                after = path.read_text(encoding="utf-8")
                if before != after:
                    touched.append(path)
            return
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        touched.append(path)

    # Skills are the product UX — install for every setup-ai / init, all IDEs.
    touched.extend(install_skills(repo, overwrite=overwrite))

    if "claude" in selected:
        write_text(repo / "AGENTS.md", AGENTS_MD)
        write_json(repo / ".claude" / "mcp.json", {"mcpServers": MCP_SERVER_BLOCK})

    if "copilot" in selected:
        write_text(repo / ".github" / "copilot-instructions.md", COPILOT_MD)

    if "cursor" in selected:
        write_text(repo / ".cursorrules", CURSORRULES)
        write_text(repo / ".cursor" / "rules" / "archlens.mdc", CURSOR_RULE_MDC)
        write_json(repo / ".cursor" / "mcp.json", {"mcpServers": MCP_SERVER_BLOCK})

    if "windsurf" in selected:
        write_text(repo / ".windsurfrules", WINDSURF_RULES)
        write_json(repo / ".windsurf" / "mcp.json", {"mcpServers": MCP_SERVER_BLOCK})

    if "vscode" in selected or "copilot" in selected:
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
