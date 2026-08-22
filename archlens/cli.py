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
    from archlens.analysis.intents import write_example_intents
    from archlens.analysis.cdm_semantics import write_example_cdm_semantics
    from archlens.analysis.capabilities import write_example_capabilities

    intents_path = write_example_intents(root)
    cdm_sem_path = write_example_cdm_semantics(root)
    caps_path = write_example_capabilities(root)
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
    console.print(f"  Intents: {intents_path}")
    console.print(f"  CDM semantics: {cdm_sem_path}")
    console.print(f"  Capabilities: {caps_path}")
    console.print(f"  Database: {default_db_path(root)}")
    from archlens.setup_ai import generate_adapters

    ai_files = generate_adapters(root, ["cursor"], overwrite=False)
    if ai_files:
        console.print("  Cursor MCP + ArchLens skills installed (more IDEs: archlens setup-ai)")


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
    caps_meta = (snapshot.metadata or {}).get("capabilities") or {}
    if caps_meta:
        console.print(
            f"  Capabilities: {caps_meta.get('count', 0)} "
            f"(approved {caps_meta.get('approved', 0)}, "
            f"candidates {caps_meta.get('candidates', 0)})"
        )


@cli.command()
@click.option("--repo", default=None)
@click.option("--from", "from_ref", default=None, help="From snapshot id or commit")
@click.option("--to", "to_ref", default=None, help="To snapshot id or commit (default: latest)")
@click.option("--narrative/--no-narrative", default=False, help="Print time-travel narrative")
@click.option("--output", default=None, help="Write narrative markdown")
def diff(
    repo: str | None,
    from_ref: str | None,
    to_ref: str | None,
    narrative: bool,
    output: str | None,
):
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

    if narrative or output:
        from archlens.analysis.narrative_diff import narrative_diff

        narr = narrative_diff(from_snap, to_snap, diff=result)
        console.print("")
        console.print(narr["narrative"])
        if output:
            out = Path(output)
            if not out.is_absolute():
                out = root / out
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(narr["markdown"], encoding="utf-8")
            console.print(f"[green]Narrative written to[/green] {out}")


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
    cfg = load_config(root)
    if fmt == "structurizr":
        content = StructurizrExporter().generate(snapshot, level=level)
    else:
        content = MermaidGenerator(max_edges=cfg.diagrams.max_edges).generate(
            snapshot, level=level, highlight=hl
        )
    if output:
        out = Path(output)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        console.print(f"Wrote diagram to {out}")
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
    cfg = load_config(root)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    diagram_dir = out.parent / "architecture"
    component_mmd = diagram_dir / "components.mmd"
    rel_link = f"{diagram_dir.name}/{component_mmd.name}"

    from archlens.analysis.health import HealthScorer

    health = HealthScorer().analyze(snapshot, store=_store(root))
    md = MarkdownReportGenerator(max_edges=cfg.diagrams.max_edges).generate(
        snapshot,
        health=health,
        component_diagram_path=component_mmd,
        component_diagram_relpath=rel_link,
    )
    out.write_text(md, encoding="utf-8")
    console.print(f"[green]Report written to[/green] {out}")
    if component_mmd.exists():
        console.print(f"[green]Component diagram written to[/green] {component_mmd}")


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


@cli.command("aggregate")
@click.option("--input", "inputs", multiple=True, required=True, help="architecture.json paths (repeatable)")
@click.option("--name", default="Distributed System", help="System name")
@click.option("--output", default=None, help="Write aggregated JSON")
@click.option("--store-repo", default=None, help="Also save into this repo's .archlens DB")
def aggregate(inputs: tuple[str, ...], name: str, output: str | None, store_repo: str | None):
    """Aggregate architecture.json exports from multiple repos into one system view."""
    from archlens.distributed.aggregator import aggregate_from_paths

    snap = aggregate_from_paths(list(inputs), system_name=name)
    console.print(
        f"[green]Aggregated[/green] {len(inputs)} repos → "
        f"{len(snap.elements)} elements, {len(snap.relationships)} relationships"
    )
    text = json.dumps(snap.model_dump(mode="json"), indent=2)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"Wrote {output}")
    else:
        click.echo(text)
    if store_repo:
        store = _store(_repo_path(store_repo))
        store.save_snapshot(snap)
        console.print(f"Saved snapshot {snap.snapshot_id} to {store_repo}")


@cli.command("events")
@click.option("--repo", default=None)
@click.option("--output", default=None, help="Write JSON report")
def events_cmd(repo: str | None, output: str | None):
    """Detect Kafka/RabbitMQ/SQS producers and consumers."""
    from archlens.config import load_config
    from archlens.distributed.events import EventFlowTracer

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    report = EventFlowTracer(load_config(root)).scan_repo(root, snapshot=snap)
    payload = report.to_dict()
    if output:
        Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"Wrote {output}")
    else:
        console.print_json(data=payload)
    console.print(
        f"Topics: {len(payload['topics'])} | Endpoints: {payload['endpoint_count']} | "
        f"Event edges: {len(payload['relationships'])}"
    )


@cli.command("contracts")
@click.option("--repo", default=None, help="Single repo (or use --repos)")
@click.option("--repos", default=None, help="Comma-separated repo paths for cross-repo linking")
@click.option("--output", default=None)
def contracts_cmd(repo: str | None, repos: str | None, output: str | None):
    """Link services via OpenAPI specs and HTTP call-site matching."""
    from archlens.distributed.openapi_linker import OpenAPIContractLinker

    paths: list[str]
    if repos:
        paths = [p.strip() for p in repos.split(",") if p.strip()]
    else:
        paths = [str(_repo_path(repo))]
    report = OpenAPIContractLinker().analyze_repos(paths)
    payload = report.to_dict()
    if output:
        Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"Wrote {output}")
    else:
        console.print_json(data=payload)
    console.print(
        f"Operations: {len(report.operations)} | Call sites: {len(report.call_sites)} | "
        f"Links: {report.to_dict()['link_count']}"
    )


@cli.command("cdm")
@click.option("--repo", default=None)
@click.option("--input", "inputs", multiple=True, help="architecture.json paths for multi-repo CDM")
@click.option("--name", default="Distributed System", help="System name when using --input")
@click.option("--semantics", "semantics_path", default=None, help="Path to .archlens/cdm.yaml")
@click.option("--output", default="docs/CANONICAL_DATA_MODEL.md")
@click.option("--json-output", default=None, help="Also write machine-readable CDM JSON")
def cdm_cmd(
    repo: str | None,
    inputs: tuple[str, ...],
    name: str,
    semantics_path: str | None,
    output: str,
    json_output: str | None,
):
    """Generate a canonical data model (single repo or aggregated exports)."""
    from archlens.analysis.cdm_semantics import load_cdm_semantics, write_example_cdm_semantics
    from archlens.analysis.data_model import (
        build_canonical_data_model,
        build_cdm_from_exports,
    )
    from archlens.generators.cdm_report import CdmReportGenerator

    root = _repo_path(repo)
    sem_path = Path(semantics_path) if semantics_path else None
    # Ensure example semantics file exists for discoverability
    write_example_cdm_semantics(root)
    semantics = load_cdm_semantics(repo=root, path=sem_path)

    if inputs:
        snapshot, cdm = build_cdm_from_exports(
            list(inputs), system_name=name, semantics=semantics
        )
        console.print(f"[green]Aggregated CDM from[/green] {len(inputs)} exports")
    else:
        snapshot = _store(root).get_latest_snapshot()
        if not snapshot:
            console.print("[red]No snapshot. Run archlens scan first (or pass --input).[/red]")
            sys.exit(1)
        cdm = build_canonical_data_model(
            snapshot, semantics=semantics, repo=root, semantics_path=sem_path
        )

    md = CdmReportGenerator().generate(snapshot, cdm)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    console.print(f"[green]CDM written to[/green] {out}")
    console.print(
        f"  entities={cdm.stats.get('entity_count')} "
        f"associations={cdm.stats.get('association_count')} "
        f"columns={cdm.stats.get('columns_total')} "
        f"owned={cdm.stats.get('owned_entities')}"
    )
    if json_output:
        jout = Path(json_output)
        if not jout.is_absolute():
            jout = root / jout
        jout.parent.mkdir(parents=True, exist_ok=True)
        jout.write_text(json.dumps(cdm.to_dict(), indent=2), encoding="utf-8")
        console.print(f"[green]CDM JSON written to[/green] {jout}")


@cli.command("data-model")
@click.option("--repo", default=None)
@click.option("--input", "inputs", multiple=True, help="architecture.json paths (optional aggregate)")
@click.option("--name", default="Distributed System")
@click.option("--output", default="docs/BASIC_DATA_MODEL.md")
def data_model_cmd(repo: str | None, inputs: tuple[str, ...], name: str, output: str):
    """Write a standalone basic data-model inventory (not full CDM/ER)."""
    from archlens.analysis.data_model import basic_data_model_markdown
    from archlens.distributed.aggregator import aggregate_from_paths

    root = _repo_path(repo)
    if inputs:
        snapshot = aggregate_from_paths(list(inputs), system_name=name)
    else:
        snapshot = _store(root).get_latest_snapshot()
        if not snapshot:
            console.print("[red]No snapshot. Run archlens scan first.[/red]")
            sys.exit(1)
    md = basic_data_model_markdown(snapshot)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    console.print(f"[green]Basic data model written to[/green] {out}")


@cli.command("capabilities")
@click.option("--repo", default=None)
@click.option("--refresh/--no-refresh", default=True, help="Re-merge from latest snapshot")
@click.option("--output", default="docs/CAPABILITIES.md")
def capabilities_cmd(repo: str | None, refresh: bool, output: str):
    """Show / refresh the hybrid capability catalog (auto-seed + curated labels)."""
    from archlens.analysis.capabilities import (
        load_catalog,
        save_catalog,
        sync_capabilities,
    )

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    if refresh:
        if not snap:
            console.print("[red]No snapshot. Run archlens scan first.[/red]")
            sys.exit(1)
        catalog = sync_capabilities(snap, root, persist=True)
    else:
        catalog = load_catalog(root)
        if not catalog.capabilities and snap:
            catalog = sync_capabilities(snap, root, persist=True)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    project = (snap.metadata.get("project_name") if snap else None) or "Capabilities"
    out.write_text(catalog.to_markdown(title=f"{project} — Capabilities"), encoding="utf-8")
    save_catalog(root, catalog)
    approved = sum(1 for c in catalog.capabilities if c.status == "approved")
    console.print(f"[green]Capabilities written to[/green] {out}")
    console.print(
        f"  total={len(catalog.capabilities)} approved={approved} "
        f"missing={sum(1 for c in catalog.capabilities if c.missing_in_code)}"
    )
    yaml_path = root / ".archlens" / "capabilities.yaml"
    console.print(f"  catalog: {yaml_path}")


@cli.command("playbook")
@click.option("--repo", default=None)
@click.option("--capability", "capability_id", default=None, help="Capability id, title, or element name")
@click.option("--limit", default=12, help="Max playbooks when listing all")
@click.option("--output", default="docs/PLAYBOOKS.md")
def playbook_cmd(repo: str | None, capability_id: str | None, limit: int, output: str):
    """Reading path + change recipe for a capability (onboarding / first change)."""
    from archlens.analysis.playbook import (
        playbooks_for_catalog,
        playbooks_markdown,
        resolve_catalog,
    )

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    if not snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    catalog = resolve_catalog(snap, root)
    books = playbooks_for_catalog(
        snap, catalog, repo=root, limit=1 if capability_id else limit, capability_id=capability_id
    )
    if not books:
        console.print("[yellow]No matching capability. Run archlens scan / capabilities first.[/yellow]")
        sys.exit(1)
    project = snap.metadata.get("project_name") or "Architecture"
    md = books[0].to_markdown() if capability_id and len(books) == 1 else playbooks_markdown(
        books, project=project
    )
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    console.print(f"[green]Playbook written to[/green] {out}")
    for pb in books[:5]:
        console.print(f"  - {pb.title} ({len(pb.reading_path)} files, risk {pb.risk_score})")


@cli.command("explain")
@click.option("--repo", default=None)
@click.option("--capability", "capability_id", required=True, help="Capability id, title, or element name")
@click.option("--output", default=None)
@click.option("--no-llm", is_flag=True, default=False, help="Skip optional LLM; citations-only template")
def explain_cmd(repo: str | None, capability_id: str, output: str | None, no_llm: bool):
    """Grounded explanation from file citations (optional LLM, never unsourced)."""
    from archlens.analysis.explain import explain_capability
    from archlens.analysis.playbook import match_capability, resolve_catalog

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    if not snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    cap = match_capability(resolve_catalog(snap, root), capability_id)
    if not cap:
        console.print(f"[yellow]No capability matching `{capability_id}`.[/yellow]")
        sys.exit(1)
    expl = explain_capability(snap, cap, repo=root, use_llm=not no_llm)
    md = expl.to_markdown()
    if output:
        _write_md(root, output, md)
        console.print(f"[green]Wrote[/green] {output if Path(output).is_absolute() else root / output}")
        console.print(f"  llm_used={expl.llm_used} citations={len(expl.citations)}")
    else:
        console.print(md)


@cli.command("strangler")
@click.option("--repo", default=None)
@click.option("--capability", "capability_id", required=True)
@click.option("--output", default="docs/STRANGLER.md")
def strangler_cmd(repo: str | None, capability_id: str, output: str):
    """Programs + tables + jobs to extract for one capability (strangler slice)."""
    from archlens.analysis.playbook import match_capability, resolve_catalog
    from archlens.analysis.strangler import strangler_slice

    root, snap, cap = _cap_or_exit(repo, capability_id)
    slice_ = strangler_slice(
        snap,
        capability_id=cap.id,
        title=cap.title or cap.id,
        seed_names=list(cap.elements),
        related_tables=list(cap.related_tables),
    )
    out = _write_md(root, output, slice_.to_markdown())
    console.print(f"[green]Strangler slice[/green] {out}")
    console.print(f"  programs={len(slice_.programs)} tables={len(slice_.tables)} jobs={len(slice_.jobs)}")


@cli.command("grain")
@click.option("--repo", default=None)
@click.option("--capability", "capability_id", required=True)
@click.option("--output", default="docs/FINE_GRAIN.md")
def grain_cmd(repo: str | None, capability_id: str, output: str):
    """Paragraph / PERFORM / method / BMS field / COPY grain for a capability."""
    from archlens.analysis.fine_grain import fine_grain_for
    from archlens.models import is_code_level

    root, snap, cap = _cap_or_exit(repo, capability_id)
    by_name = {e.name: e for e in snap.elements if not is_code_level(e)}
    seeds = [by_name[n] for n in cap.elements if n in by_name]
    report = fine_grain_for(snap, seeds, repo=root, capability_id=cap.id)
    out = _write_md(root, output, report.to_markdown())
    console.print(f"[green]Fine grain[/green] {out}")


@cli.command("onboard")
@click.option("--repo", default=None)
@click.option("--capability", "capability_id", default=None, help="Guided first change (default: top capability)")
@click.option("--output", default="docs/ONBOARDING.md")
def onboard_cmd(repo: str | None, capability_id: str | None, output: str):
    """First 90 minutes: context diagram, 10 capabilities, one guided change."""
    from archlens.analysis.onboard import onboard_markdown
    from archlens.analysis.playbook import resolve_catalog

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    if not snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    md = onboard_markdown(snap, resolve_catalog(snap, root), repo=root, capability_id=capability_id)
    out = _write_md(root, output, md)
    console.print(f"[green]Onboarding guide[/green] {out}")


@cli.command("rules")
@click.option("--repo", default=None)
@click.option("--capability", "capability_id", required=True)
@click.option("--output", default="docs/RULES.md")
def rules_cmd(repo: str | None, capability_id: str, output: str):
    """Candidate IF/EVALUATE/validator rules under a capability (not a BRD)."""
    from archlens.analysis.source_harvest import harvest_for_elements
    from archlens.models import is_code_level

    root, snap, cap = _cap_or_exit(repo, capability_id)
    by_name = {e.name: e for e in snap.elements if not is_code_level(e)}
    seeds = [by_name[n] for n in cap.elements if n in by_name]
    h = harvest_for_elements(snap, seeds, root)
    lines = [f"# Candidate rules: {cap.title}", "", "Human-named checklist of logic that exists in code.", ""]
    for r in h.rules:
        lines.append(f"- **{r.kind}** `{r.text}` — `{r.citation}`")
    if h.comments:
        lines.extend(["", "## Comments / remarks", ""])
        for c in h.comments:
            lines.append(f"- [{c.kind}] {c.text} (`{c.citation}`)")
    if not h.rules and not h.comments:
        lines.append("_None harvested._")
    out = _write_md(root, output, "\n".join(lines) + "\n")
    console.print(f"[green]Rules[/green] {out} ({len(h.rules)} candidates)")


@cli.command("ops")
@click.option("--repo", default=None)
@click.option("--capability", "capability_id", default=None)
@click.option("--output", default="docs/OPS_OVERLAY.md")
def ops_cmd(repo: str | None, capability_id: str | None, output: str):
    """JCL job names, CICS TRANSID, BMS maps (ops overlay, not APM)."""
    from archlens.analysis.ops_overlay import ops_overlay
    from archlens.analysis.playbook import match_capability, resolve_catalog

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    if not snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    seeds = None
    if capability_id:
        cap = match_capability(resolve_catalog(snap, root), capability_id)
        if cap:
            seeds = list(cap.elements)
    overlay = ops_overlay(snap, repo=root, seed_names=seeds)
    out = _write_md(root, output, overlay.to_markdown())
    console.print(f"[green]Ops overlay[/green] {out}")


@cli.command("reading-priority")
@click.option("--repo", default=None)
@click.option("--output", default="docs/READING_PRIORITY.md")
def reading_priority_cmd(repo: str | None, output: str):
    """Hotspots to learn first vs unreachable / isolated code to skip."""
    from archlens.analysis.reading_priority import reading_priority

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    if not snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    out = _write_md(root, output, reading_priority(snap).to_markdown())
    console.print(f"[green]Reading priority[/green] {out}")


@cli.command("schema-drift")
@click.option("--repo", default=None)
@click.option("--output", default="docs/SCHEMA_CDM_DRIFT.md")
@click.option("--fail-on-drift", is_flag=True, default=False)
def schema_drift_cmd(repo: str | None, output: str, fail_on_drift: bool):
    """Compare inferred CDM against Flyway/Liquibase/DDL schema files."""
    from archlens.analysis.schema_drift import analyze_schema_drift

    root = _repo_path(repo)
    cfg = load_config(root)
    snapshot = _store(root).get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    report = analyze_schema_drift(snapshot, root, globs=cfg.ddl.globs)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8")
    console.print(f"[green]Schema drift report[/green] {out}")
    console.print(
        f"  schema_tables={report.stats.get('schema_table_count')} "
        f"only_schema={len(report.only_in_schema)} "
        f"only_cdm={len(report.only_in_cdm)} "
        f"col_mismatches={len(report.column_mismatches)}"
    )
    if (fail_on_drift or cfg.ddl.fail_on_drift) and report.has_drift:
        sys.exit(2)


@cli.command("intents")
@click.option("--repo", default=None)
@click.option("--validate/--no-validate", default=True)
@click.option("--init-file", is_flag=True, help="Create example .archlens/intents.yaml")
def intents_cmd(repo: str | None, validate: bool, init_file: bool):
    """Show / validate human architecture intent overlays."""
    from archlens.analysis.intents import load_intents, validate_intents, write_example_intents

    root = _repo_path(repo)
    if init_file:
        path = write_example_intents(root)
        console.print(f"[green]Wrote[/green] {path}")
        return
    intents = load_intents(root)
    console.print(
        f"Intents: overrides={len(intents.stereotype_overrides)} "
        f"owners={len(intents.owners)} "
        f"forbidden={len(intents.forbidden_edges)} "
        f"critical_paths={len(intents.critical_paths)} "
        f"boundaries={len(intents.boundaries)}"
    )
    if validate:
        snap = _store(root).get_latest_snapshot()
        if not snap:
            console.print("[yellow]No snapshot — skip validation.[/yellow]")
            return
        result = validate_intents(snap, intents=intents)
        if result["ok"]:
            console.print("[green]Intent validation OK[/green]")
        else:
            console.print(f"[red]Violations:[/red] {result['violation_count']}")
            for v in result["violations"][:20]:
                console.print(f"  - {v}")
            if result["missing_critical_paths"]:
                console.print(f"  missing critical: {result['missing_critical_paths']}")
            sys.exit(2)


@cli.command("traces")
@click.option("--repo", default=None)
@click.option("--output", default="docs/PROCESS_TRACES.md")
def traces_cmd(repo: str | None, output: str):
    """Build behavioral process traces (API→data, CICS chains)."""
    from archlens.analysis.process_traces import build_process_traces

    root = _repo_path(repo)
    snapshot = _store(root).get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    report = build_process_traces(snapshot)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8")
    console.print(f"[green]Traces written to[/green] {out}")
    console.print(f"  traces={report.stats.get('trace_count')} kinds={report.stats.get('kinds')}")


@cli.command("domains")
@click.option("--repo", default=None)
@click.option("--output", default="docs/DOMAINS.md")
def domains_cmd(repo: str | None, output: str):
    """Slice the architecture into domain / bounded-context clusters."""
    from archlens.analysis.domains import slice_domains

    root = _repo_path(repo)
    snapshot = _store(root).get_latest_snapshot()
    if not snapshot:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    report = slice_domains(snapshot)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8")
    console.print(f"[green]Domains written to[/green] {out}")
    console.print(
        f"  domains={report.stats.get('domain_count')} "
        f"unassigned={report.stats.get('unassigned_count')}"
    )


@cli.command("timeline")
@click.option("--repo", default=None)
@click.option("--from", "from_ref", default=None)
@click.option("--to", "to_ref", default=None)
@click.option("--output", default="docs/ARCHITECTURE_TIMELINE.md")
def timeline_cmd(repo: str | None, from_ref: str | None, to_ref: str | None, output: str):
    """Narrative time-travel diff between two snapshots."""
    from archlens.analysis.narrative_diff import narrative_diff

    root = _repo_path(repo)
    store = _store(root)
    to_snap = _resolve_snapshot(store, to_ref) if to_ref else store.get_latest_snapshot()
    if not to_snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    if from_ref:
        from_snap = _resolve_snapshot(store, from_ref)
    else:
        snaps = store.list_snapshots(limit=2)
        from_snap = store.get_snapshot(snaps[1]["id"]) if len(snaps) >= 2 else None
    if not from_snap:
        console.print("[red]Need a prior snapshot (--from) for timeline.[/red]")
        sys.exit(1)
    narr = narrative_diff(from_snap, to_snap)
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(narr["markdown"], encoding="utf-8")
    console.print(narr["narrative"])
    console.print(f"[green]Timeline written to[/green] {out}")


@cli.command("health")
@click.option("--repo", default=None)
@click.option("--output", default=None)
@click.option("--trends/--no-trends", default=True, help="Include historical scores from DB")
def health_cmd(repo: str | None, output: str | None, trends: bool):
    """Score architecture health (coupling, cycles, layer violations)."""
    from archlens.analysis.health import HealthScorer

    root = _repo_path(repo)
    store = _store(root)
    snap = store.get_latest_snapshot()
    if not snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    report = HealthScorer().analyze(snap, store=store if trends else None)
    payload = report.to_dict()
    if output:
        Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"Wrote {output}")
    console.print(f"Health score: [bold]{report.score}[/bold] (grade {report.grade})")
    console.print(
        f"  cycles={report.metrics.get('cycle_count')} "
        f"layer_violations={report.metrics.get('layer_violation_count')} "
        f"density={report.metrics.get('density')}"
    )
    if not output:
        console.print_json(data=payload)


@cli.command("federate")
@click.option("--url", required=True, help="Remote architecture.json or ArchLens HTTP base URL")
@click.option("--output", default=None, help="Save fetched JSON")
def federate_cmd(url: str, output: str | None):
    """Fetch architecture from a remote ArchLens export / HTTP endpoint."""
    from archlens.distributed.federation import fetch_remote_architecture

    data = fetch_remote_architecture(url)
    text = json.dumps(data, indent=2)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"Wrote {output}")
    else:
        click.echo(text)
    console.print(
        f"Remote elements: {len(data.get('elements', []))} | "
        f"relationships: {len(data.get('relationships', []))}"
    )


def _write_md(root: Path, output: str, text: str) -> Path:
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def _cap_or_exit(repo: str | None, capability_id: str):
    from archlens.analysis.playbook import match_capability, resolve_catalog

    root = _repo_path(repo)
    snap = _store(root).get_latest_snapshot()
    if not snap:
        console.print("[red]No snapshot. Run archlens scan first.[/red]")
        sys.exit(1)
    cap = match_capability(resolve_catalog(snap, root), capability_id)
    if not cap:
        console.print(f"[yellow]No capability matching `{capability_id}`.[/yellow]")
        sys.exit(1)
    return root, snap, cap


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
