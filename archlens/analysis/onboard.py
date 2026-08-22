"""First 90 minutes: context diagram → capabilities → one guided change."""

from __future__ import annotations

from pathlib import Path

from archlens.analysis.capabilities import CapabilityCatalog
from archlens.analysis.explain import explain_capability
from archlens.analysis.playbook import build_playbook
from archlens.analysis.reading_priority import reading_priority
from archlens.generators.mermaid import MermaidGenerator
from archlens.models import ArchSnapshot


def onboard_markdown(
    snapshot: ArchSnapshot,
    catalog: CapabilityCatalog,
    *,
    repo: Path | str | None = None,
    capability_id: str | None = None,
) -> str:
    root = Path(repo or snapshot.repo_path)
    project = snapshot.metadata.get("project_name") or "this system"
    caps = sorted(
        catalog.capabilities,
        key=lambda c: (0 if c.status == "approved" else 1, c.missing_in_code, c.title.lower()),
    )[:10]
    pick = None
    if capability_id:
        cid = capability_id.lower()
        pick = next(
            (
                c
                for c in catalog.capabilities
                if c.id.lower() == cid
                or cid in c.title.lower()
                or cid in {e.lower() for e in c.elements}
            ),
            None,
        )
    if pick is None:
        pick = caps[0] if caps else None

    mermaid = MermaidGenerator(max_edges=80).generate(snapshot, level="context")
    prio = reading_priority(snapshot)
    lines = [
        f"# Onboarding: {project} (first 90 minutes)",
        "",
        "1. Skim the **context** diagram.",
        "2. Read the **10 capabilities** (what the system does).",
        "3. Take **one guided change** using the playbook (do not skip blast radius / tests).",
        "",
        "## Minute 0–20 — Context",
        "",
        "```mermaid",
        mermaid,
        "```",
        "",
        f"- **Elements:** {len(snapshot.elements)}  ",
        f"- **Relationships:** {len(snapshot.relationships)}  ",
        "",
        "## Minute 20–50 — Ten capabilities",
        "",
    ]
    if not caps:
        lines.append("_No capabilities. Run `archlens scan` then `archlens capabilities`._")
        lines.append("")
    for i, c in enumerate(caps, 1):
        els = ", ".join(f"`{e}`" for e in c.elements[:4]) or "—"
        lines.append(f"{i}. **{c.title}** (`{c.id}`) — {c.stereotype or 'entry'} — {els}")
    lines.append("")
    lines.extend(["## Learn first vs skip", "", prio.to_markdown().replace("# Reading priority\n\n", ""), ""])
    lines.extend(["## Minute 50–90 — One guided change", ""])
    if pick:
        lines.append(f"Suggested first change: **{pick.title}** (`{pick.id}`).")
        lines.append("")
        expl = explain_capability(snapshot, pick, repo=root, use_llm=False)
        lines.append(expl.narrative)
        lines.append("")
        pb = build_playbook(snapshot, pick, repo=root)
        lines.append(pb.to_markdown().replace("# Playbook:", "### Playbook:", 1))
    else:
        lines.append("No capability to guide a first change.")
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            "archlens capabilities",
            f"archlens explain --capability {pick.id if pick else '<id>'}",
            f"archlens playbook --capability {pick.id if pick else '<id>'}",
            f"archlens strangler --capability {pick.id if pick else '<id>'}",
            "archlens impact --files <your-file>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)
