"""Standalone ArchLens agent.

Prefers Google Antigravity SDK when available; otherwise runs a local
CLI-backed interactive session usable from any terminal/IDE.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

SYSTEM_PROMPT = """
You are ArchLens Architect, specialized in codebase architecture analysis.

CLI tools:
- archlens scan / query / impact / diff / diagram / drift / report / mcp

Rules:
1. Ensure a fresh snapshot before answering architecture questions
2. Prefer archlens query / impact for structure and change analysis
3. Explain WHY components are affected (dependency chains)
4. Be conservative with effort estimates
""".strip()


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        return err or out or f"command failed: {' '.join(cmd)}"
    return out


def run_cli_session(repo_path: str) -> None:
    """Interactive REPL that maps intents to ArchLens CLI commands."""
    repo = str(Path(repo_path).resolve())
    print("ArchLens Architect (CLI mode)")
    print(f"Repository: {repo}")
    print("Commands: scan | query <text> | impact <files...> | diagram | drift | report | help | exit\n")

    while True:
        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw.lower() in ("exit", "quit"):
            break
        if raw.lower() in ("help", "?"):
            print(SYSTEM_PROMPT)
            continue

        parts = shlex.split(raw)
        head = parts[0].lower()
        if head == "scan":
            print(_run(["archlens", "scan", "--repo", repo]))
        elif head == "query":
            q = " ".join(parts[1:]) or "overview"
            print(_run(["archlens", "query", "--repo", repo, q]))
        elif head == "impact":
            files = parts[1:]
            cmd = ["archlens", "impact", "--repo", repo]
            if files:
                cmd.extend(["--files", ",".join(files)])
            print(_run(cmd))
        elif head == "diagram":
            print(_run(["archlens", "diagram", "--repo", repo, "--format", "mermaid"]))
        elif head == "drift":
            print(_run(["archlens", "drift", "--repo", repo, "--output", "json"]))
        elif head == "report":
            out = str(Path(repo) / "docs" / "ARCHITECTURE.md")
            print(_run(["archlens", "report", "--repo", repo, "--output", out]))
        else:
            # Treat free text as NL query after ensuring scan exists
            db = Path(repo) / ".archlens" / "archlens.db"
            if not db.exists():
                print(_run(["archlens", "scan", "--repo", repo]))
            print(_run(["archlens", "query", "--repo", repo, raw]))


async def run_agent(repo_path: str) -> None:
    """Try Antigravity SDK; fall back to CLI session."""
    try:
        from google.antigravity import Agent, LocalAgentConfig, types  # type: ignore
    except ImportError:
        run_cli_session(repo_path)
        return

    config = LocalAgentConfig(
        system_prompt=SYSTEM_PROMPT + f"\nDB: {repo_path}/.archlens/archlens.db",
        capabilities=types.CapabilitiesConfig(
            enable_shell=True,
            enable_file_read=True,
            enable_file_write=True,
        ),
    )
    async with Agent(config) as agent:
        print("ArchLens Architect Agent initialized (Antigravity).")
        print(f"Repository: {repo_path}")
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in ("exit", "quit"):
                break
            response = await agent.chat(user_input)
            print(f"\nArchLens: {await response.text()}\n")


def main(argv: list[str] | None = None) -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="ArchLens standalone agent")
    parser.add_argument("--repo", required=True, help="Path to repository")
    parser.add_argument("--cli", action="store_true", help="Force CLI REPL mode")
    args = parser.parse_args(argv)
    if args.cli:
        run_cli_session(args.repo)
    else:
        asyncio.run(run_agent(args.repo))


if __name__ == "__main__":
    main()
