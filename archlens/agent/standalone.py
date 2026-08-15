"""Standalone ArchLens agent stub (optional Antigravity SDK).

This module documents the intended standalone agent interface.
The Antigravity SDK is optional; when unavailable, prefer `archlens mcp`.
"""

from __future__ import annotations

SYSTEM_PROMPT = """
You are ArchLens Architect, an AI agent specialized in codebase architecture analysis.

You have the following CLI tools available:
- `archlens scan` — Scan a repository and create an architecture snapshot
- `archlens query` — Query the architecture database
- `archlens impact` — Analyze impact of changes
- `archlens diff` — Compare two architecture snapshots
- `archlens diagram` — Generate Mermaid diagrams
- `archlens drift` — Check for architectural drift
- `archlens report` — Generate ARCHITECTURE.md

Your workflow:
1. When the user asks about architecture, ensure a fresh snapshot exists first
2. Use `archlens query` for questions about structure and dependencies
3. Use `archlens impact` for questions about change impact
4. Use `archlens diagram` to generate visual context
5. Always explain WHY components are affected, not just WHAT
6. Present Mermaid diagrams inline when they add clarity
7. Be conservative with effort estimates

The architecture database is at: {repo_path}/.archlens/archlens.db
"""


async def run_agent(repo_path: str) -> None:
    """Interactive agent session. Requires google.antigravity SDK."""
    try:
        from google.antigravity import Agent, LocalAgentConfig, types
    except ImportError as e:
        raise SystemExit(
            "google.antigravity SDK not installed. "
            "Use `archlens mcp` for the universal agent interface instead."
        ) from e

    config = LocalAgentConfig(
        system_prompt=SYSTEM_PROMPT.format(repo_path=repo_path),
        capabilities=types.CapabilitiesConfig(
            enable_shell=True,
            enable_file_read=True,
            enable_file_write=True,
        ),
    )

    async with Agent(config) as agent:
        print("ArchLens Architect Agent initialized.")
        print(f"Repository: {repo_path}")
        print("Type architecture questions. Type 'exit' to quit.\n")
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in ("exit", "quit"):
                break
            response = await agent.chat(user_input)
            print(f"\nArchLens: {await response.text()}\n")


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    asyncio.run(run_agent(args.repo))
