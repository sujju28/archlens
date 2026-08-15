"""ArchLens Click CLI."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from archlens import __version__
from archlens.analysis.diff_engine import DiffEngine
from archlens.analysis.impact_analyzer import ImpactAnalyzer
from archlens.config import load_config, write_default_config
from archlens.generators.markdown_report import MarkdownReportGenerator
from archlens.generators.mermaid import MermaidGenerator
from archlens.generators.structurizr import StructurizrExporter
from archlens.scanner import scan_repository
from archlens.storage.sqlite_store import SQLiteStore, default_db_path

console = Console()


def _repo_path(repo: str | None) -> Path:
    return Path(repo).resolve() if repo else Path.cwd().resolve()


def _store(repo: Path) -> SQLiteStore:
    return SQLiteStore(default_db_path(repo))


@click.group()
@click.version_option(__version__, prog_name="archlens")
def cli():
    """ArchLens — living architecture intelligence."""


@cli.command()
@click.option("--repo", default=None, help="Repository root (default: cwd)")
@click.option("--lang", default=None, help="Comma-separated languages (java,typescript,python)")
def init(repo: str | None, lang: str | None):
    """Initialize .archlens/ directory and config in a repo."""
    root = _repo_path(repo)
    arch_dir = root / ".archlens"
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / ".gitkeep").touch()
    cfg_path = write_default_config(root)
    if lang:
        # Update languages in config file lightly
        text = cfg_path.read_text(encoding="utf-8")
        langs = [l.strip() for l in lang.split(",") if l.strip()]
        langs_yaml = "\n".join(f"  - {l}" for l in langs)
        text = re.sub(
            r"languages:\n(?:  - .*\n)+",
            f"languages:\n{langs_yaml}\n",
            text,
            count=1,
        )
        cfg_path.write_text(text, encoding="utf-8")
    # Ensure DB schema exists
    _store(root)
    console.print(f"[green]Initialized ArchLens in[/green] {root}")
    console.print(f"  Config: {cfg_path}")
    console.print(f"  Database: {default_db_path(root)}")


@cli.command()
@click.option("--repo", default=None, help="Repository root")
@click.option("--commit", default=None, help="Commit SHA")
def scan(repo: str | None, commit: str | None):
    """Parse the codebase and create a new snapshot."""
    root = _repo_path(repo)
    with console.status("Scanning..."):
        snapshot = scan_repository(root, commit=commit)
    by_stereo: dict[str, int] = {}
    for e in snapshot.elements:
        by_stereo[e.stereotype] = by_stereo.get(e.stereotype, 0) + 1
    console.print(f"[green]Scan complete[/green] — snapshot [cyan]{snapshot.snapshot_id}[/cyan]")
    console.print(f"  Commit: {snapshot.commit_sha}")
    console.print(f"  Elements: {len(snapshot.elements)} | Relationships: {len(snapshot.relationships)}")
    for s, count in sorted(by_stereo.items(), key=lambda x: -x[1]):
        console.print(f"    {s}: {count}")


@cli.command()
@click.option("--repo", default=None)
@click.option("--from", "from_ref", default=None, help="From snapshot id or commit")
@click.option("--to", "to_ref", default=None, help="To snapshot id or commit (default: latest)")
def diff(repo: str | None, from_ref: str | None, to_ref: str | None):
    """Compare two snapshots (or commits)."""
    root = _repo_path(repo)
    store = _store(root)
    to_snap = _resolve_snapshot(store, to_ref) if to_ref else store.get_latest_snapshot()
    if not to_snap:
        console.print("[red]No target snapshot found. Run archlens scan first.[/red]")
        sys.exit(1)
    if not from_ref:
        snaps = store.list_snapshots(limit=2)
        if len(snaps) < 2:
            console.print("[yellow]Need at least two snapshots to diff. Provide --from.[/yellow]")
            sys.exit(1)
        from_snap = store.get_snapshot(snaps[1]["id"])
    else:
        from_snap = _resolve_snapshot(store, from_ref)
    if not from_snap:
        console.print(f"[red]From snapshot not found: {from_ref}[/red]")
        sys.exit(1)

    result = DiffEngine().compare(from_snap, to_snap)
    summary = DiffEngine().summary(result)
    console.print("[bold]Architecture Diff[/bold]")
    console.print(f"  Added elements: {summary['added_elements']}")
    console.print(f"  Removed elements: {summary['removed_elements']}")
    console.print(f"  Modified elements: {summary['modified_elements']}")
    console.print(f"  Added relationships: {summary['added_relationships']}")
    console.print(f"  Removed relationships: {summary['removed_relationships']}")
    for el in result.added_elements[:10]:
        console.print(f"  [green]+[/green] {el.name} ({el.stereotype})")
    for el in result.removed_elements[:10]:
        console.print(f"  [red]-[/red] {el.name} ({el.stereotype})")
    for ch in result.modified_elements[:10]:
        console.print(f"  [yellow]~[/yellow] {ch.element.name}: {ch.diff_summary}")


@cli.command()
@click.option("--repo", default=None)
@click.option("--files", default=None, help="Comma-separated or space-separated file paths")
@click.option("--elements", default=None, help="Comma-separated element names")
@click.option("--depth", type=int, default=None)
@click.option("--output", default=None, help="Write JSON/Markdown report to file")
def impact(repo: str | None, files: str | None, elements: str | None, depth: int | None, output: str | None):
    """Analyze impact of changed files or elements."""
    root = _repo_path(repo)
    store = _store(root)
    snapshot = store.get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    config = load_config(root)
    file_list = _split_list(files)
    element_list = _split_list(elements)
    report = ImpactAnalyzer(config).analyze(
        snapshot, files=file_list, elements=element_list, depth=depth
    )
    payload = report.model_dump()
    if output:
        out = Path(output)
        if out.suffix.lower() == ".md":
            out.write_text(_impact_markdown(report), encoding="utf-8")
        else:
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"Wrote impact report to {out}")
    else:
        console.print_json(data=payload)


@cli.command()
@click.option("--repo", default=None)
@click.option("--format", "fmt", type=click.Choice(["mermaid", "structurizr"]), default="mermaid")
@click.option("--level", type=click.Choice(["context", "container", "component"]), default="component")
@click.option("--highlight", default=None, help="Comma-separated element names to highlight")
@click.option("--output", default=None)
def diagram(repo: str | None, fmt: str, level: str, highlight: str | None, output: str | None):
    """Generate Mermaid or Structurizr diagrams."""
    root = _repo_path(repo)
    snapshot = _store(root).get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    hl = _split_list(highlight)
    if fmt == "structurizr":
        content = StructurizrExporter().generate(snapshot, level=level)
    else:
        content = MermaidGenerator().generate(snapshot, level=level, highlight=hl)
    if output:
        Path(output).write_text(content, encoding="utf-8")
        console.print(f"Wrote diagram to {output}")
    else:
        click.echo(content)


@cli.command()
@click.option("--repo", default=None)
@click.option("--output", default="docs/ARCHITECTURE.md")
def report(repo: str | None, output: str):
    """Generate full ARCHITECTURE.md report."""
    root = _repo_path(repo)
    snapshot = _store(root).get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    md = MarkdownReportGenerator().generate(snapshot)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    console.print(f"[green]Report written to[/green] {out}")


@cli.command()
@click.option("--repo", default=None)
@click.argument("query_text", required=False)
@click.option("--stereotype", default=None)
@click.option("--element", default=None)
@click.option("--direction", type=click.Choice(["upstream", "downstream", "both"]), default="both")
@click.option("--group-by", "group_by", default=None, type=click.Choice(["stereotype", "layer"]))
@click.option("--json", "as_json", is_flag=True, help="Emit JSON including query tier")
def query(
    repo: str | None,
    query_text: str | None,
    stereotype: str | None,
    element: str | None,
    direction: str,
    group_by: str | None,
    as_json: bool,
):
    """Query the architecture database (NL 3-tier or structured)."""
    from archlens.analysis.nl_query import structured_query

    root = _repo_path(repo)
    snapshot = _store(root).get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)

    payload = structured_query(
        snapshot,
        stereotype=stereotype,
        element=element,
        direction=direction,
        group_by=group_by,
        query=query_text,
    )
    results = payload.get("results") or []
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    if payload.get("tier") == "tier3":
        console.print(f"[yellow]{payload.get('error')}[/yellow]")
        console.print(payload.get("hint", ""))
        return

    title = f"Query results ({payload.get('result_count', len(results))}) [{payload.get('tier', '?')}]"
    table = Table(title=title)
    if results:
        cols = list(results[0].keys())
        for col in cols:
            table.add_column(col)
        for row in results:
            table.add_row(*[str(row.get(c, "")) for c in cols])
        console.print(table)
    else:
        console.print("[yellow]No results.[/yellow]")


@cli.command()
@click.option("--repo", default=None)
@click.option("--fail-on-change", is_flag=True, help="Exit 2 if drift detected")
@click.option("--output", type=click.Choice(["text", "json"]), default="text")
def drift(repo: str | None, fail_on_change: bool, output: str):
    """Check if architecture has changed since last snapshot."""
    root = _repo_path(repo)
    store = _store(root)
    baseline = store.get_latest_snapshot()
    if not baseline:
        console.print("[red]No baseline snapshot. Run archlens scan first.[/red]")
        sys.exit(1)

    from archlens.scanner import git_rev

    current = scan_repository(root, commit=git_rev(root), persist=False)
    current.snapshot_id = "current-working-tree"
    result = DiffEngine().compare(baseline, current)
    summary = DiffEngine().summary(result)
    payload = {
        "status": "drift" if result.has_changes else "no_drift",
        "summary": summary,
        "added_elements": [e.name for e in result.added_elements],
        "removed_elements": [e.name for e in result.removed_elements],
        "modified_elements": [
            {"name": c.element.name, "diff": c.diff_summary} for c in result.modified_elements
        ],
    }
    if output == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        if result.has_changes:
            console.print("[yellow]Architectural drift detected[/yellow]")
            console.print(f"  +{summary['added_elements']} / -{summary['removed_elements']} / ~{summary['modified_elements']}")
        else:
            console.print("[green]No architectural drift[/green]")

    if fail_on_change and result.has_changes:
        sys.exit(2)


@cli.command()
@click.option("--repo", default=None)
@click.option("--format", "fmt", type=click.Choice(["json"]), default="json")
@click.option("--output", default=None)
def export(repo: str | None, fmt: str, output: str | None):
    """Export architecture as JSON."""
    root = _repo_path(repo)
    snapshot = _store(root).get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    data = snapshot.model_dump(mode="json")
    text = json.dumps(data, indent=2)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"Exported to {output}")
    else:
        click.echo(text)


@cli.command("setup-ai")
@click.option("--repo", default=None)
@click.option(
    "--platform",
    "platforms",
    default="all",
    help="claude,copilot,cursor,windsurf,vscode,antigravity,all",
)
@click.option("--overwrite", is_flag=True, help="Overwrite existing adapter files")
def setup_ai(repo: str | None, platforms: str, overwrite: bool):
    """Generate AI/IDE adapter files (Claude, Copilot, Cursor, Windsurf, VS Code, Antigravity)."""
    from archlens.setup_ai import generate_adapters

    root = _repo_path(repo)
    selected = [p.strip() for p in platforms.split(",")] if platforms != "all" else ["all"]
    created = generate_adapters(root, selected, overwrite=overwrite)
    if not created:
        console.print("[yellow]No new adapter files written (already present). Use --overwrite to replace.[/yellow]")
    for path in created:
        console.print(f"  [green]updated[/green] {path}")
    console.print(f"[green]AI adapters ready in[/green] {root}")
    console.print("Then register MCP in your IDE, or rely on generated mcp.json / settings.json entries.")
    console.print("Start server with: [cyan]archlens mcp[/cyan]")


@cli.command()
@click.option("--repo", default=None)
@click.option("--cli", "cli_mode", is_flag=True, help="Force local CLI REPL (no Antigravity SDK)")
def agent(repo: str | None, cli_mode: bool):
    """Start the ArchLens architect agent (Antigravity or CLI fallback)."""
    from archlens.agent.standalone import main as agent_main

    root = str(_repo_path(repo))
    argv = ["--repo", root]
    if cli_mode:
        argv.append("--cli")
    agent_main(argv)


@cli.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio")
@click.option("--port", type=int, default=8080)
def mcp(transport: str, port: int):
    """Start the ArchLens MCP server for AI coding assistants / IDEs."""
    try:
        from archlens.mcp_server import run_mcp
    except ImportError as e:
        console.print(
            "[red]MCP dependencies not installed.[/red] "
            "Reinstall with: pip install archlens  (mcp is a core dependency)"
        )
        console.print(f"Details: {e}")
        sys.exit(1)
    run_mcp(transport=transport, port=port)


def _resolve_snapshot(store: SQLiteStore, ref: str):
    snap = store.get_snapshot(ref)
    if snap:
        return snap
    return store.get_snapshot_by_commit(ref)


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[\s,]+", value.strip())
    return [p for p in parts if p]


def _impact_markdown(report) -> str:
    lines = [
        "# Architecture Impact Report",
        "",
        f"**Risk score:** {report.risk_score}",
        f"**Changed:** {', '.join(report.changed_elements)}",
        "",
        "## Directly Affected",
        "",
    ]
    for a in report.directly_affected:
        lines.append(f"- **{a.name}** ({a.stereotype}, {a.risk}) — {a.reason}")
    lines.extend(["", "## Transitively Affected", ""])
    for a in report.transitively_affected:
        lines.append(f"- **{a.name}** ({a.stereotype}, hops={a.hops}, {a.risk}) — {a.reason}")
    if report.suggested_changes:
        lines.extend(["", "## Suggestions", ""])
        for s in report.suggested_changes:
            lines.append(f"- {s}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    cli()
