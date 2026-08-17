"""Narrative time-travel diffs between architecture snapshots."""

from __future__ import annotations

from collections import Counter
from typing import Any

from archlens.analysis.diff_engine import DiffEngine
from archlens.models import ArchDiff, ArchSnapshot


def narrative_diff(
    from_snap: ArchSnapshot,
    to_snap: ArchSnapshot,
    *,
    diff: ArchDiff | None = None,
) -> dict[str, Any]:
    """Human-readable architectural change narrative."""
    engine = DiffEngine()
    d = diff or engine.compare(from_snap, to_snap)
    summary = engine.summary(d)

    added_by = Counter(e.stereotype for e in d.added_elements)
    removed_by = Counter(e.stereotype for e in d.removed_elements)
    modified_by = Counter(c.element.stereotype for c in d.modified_elements)

    headlines: list[str] = []
    if not d.has_changes:
        headlines.append("No architectural changes between these snapshots.")
    else:
        if d.added_elements:
            top = ", ".join(f"{n} {s}" for s, n in added_by.most_common(3))
            headlines.append(f"Added {len(d.added_elements)} element(s) ({top}).")
        if d.removed_elements:
            top = ", ".join(f"{n} {s}" for s, n in removed_by.most_common(3))
            headlines.append(f"Removed {len(d.removed_elements)} element(s) ({top}).")
        if d.modified_elements:
            headlines.append(
                f"Modified {len(d.modified_elements)} element(s) "
                f"(stereotype/path/annotation shifts)."
            )
        if d.added_relationships or d.removed_relationships:
            headlines.append(
                f"Dependency graph shifted: +{len(d.added_relationships)} / "
                f"-{len(d.removed_relationships)} relationships."
            )

    notable: list[str] = []
    for e in d.added_elements[:8]:
        notable.append(f"New {e.stereotype} `{e.name}` in `{e.file_path}`")
    for e in d.removed_elements[:8]:
        notable.append(f"Removed {e.stereotype} `{e.name}` (was `{e.file_path}`)")
    for c in d.modified_elements[:8]:
        notable.append(f"Changed `{c.element.name}`: {c.diff_summary}")

    # Controllers / Entities callouts
    hot = [
        e.name
        for e in d.added_elements + d.removed_elements
        if e.stereotype in ("Controller", "Gateway", "Entity", "Service")
    ][:10]

    paragraphs = [
        f"Comparing `{from_snap.snapshot_id[:8]}` ({from_snap.commit_sha[:8]}) → "
        f"`{to_snap.snapshot_id[:8]}` ({to_snap.commit_sha[:8]}).",
        " ".join(headlines),
    ]
    if hot:
        paragraphs.append("Hotspots: " + ", ".join(f"`{h}`" for h in hot) + ".")

    return {
        "from_snapshot_id": d.from_snapshot_id,
        "to_snapshot_id": d.to_snapshot_id,
        "from_commit": from_snap.commit_sha,
        "to_commit": to_snap.commit_sha,
        "summary": summary,
        "headlines": headlines,
        "notable": notable,
        "added_by_stereotype": dict(added_by),
        "removed_by_stereotype": dict(removed_by),
        "modified_by_stereotype": dict(modified_by),
        "narrative": " ".join(paragraphs),
        "markdown": _to_markdown(paragraphs, notable, summary),
    }


def _to_markdown(paragraphs: list[str], notable: list[str], summary: dict) -> str:
    lines = [
        "# Architecture timeline",
        "",
        paragraphs[0] if paragraphs else "",
        "",
        paragraphs[1] if len(paragraphs) > 1 else "",
        "",
        "## Counts",
        "",
        f"- Added elements: {summary.get('added_elements', 0)}",
        f"- Removed elements: {summary.get('removed_elements', 0)}",
        f"- Modified elements: {summary.get('modified_elements', 0)}",
        f"- Added relationships: {summary.get('added_relationships', 0)}",
        f"- Removed relationships: {summary.get('removed_relationships', 0)}",
        "",
    ]
    if len(paragraphs) > 2:
        lines.extend(["## Hotspots", "", paragraphs[2], ""])
    if notable:
        lines.extend(["## Notable changes", ""])
        for n in notable:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)
