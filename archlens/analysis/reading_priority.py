"""Dead / unreachable vs hotspot reading order."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from archlens.models import ArchSnapshot, is_code_level

ENTRIES = {"Controller", "Gateway", "UI Component", "Batch Job", "Worker"}


@dataclass
class ReadingPriority:
    learn_first: list[str] = field(default_factory=list)
    skip_or_later: list[str] = field(default_factory=list)
    unreachable_from_entries: list[str] = field(default_factory=list)
    hotspots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "learn_first": self.learn_first,
            "skip_or_later": self.skip_or_later,
            "unreachable_from_entries": self.unreachable_from_entries,
            "hotspots": self.hotspots,
        }

    def to_markdown(self) -> str:
        lines = ["# Reading priority", ""]
        if self.learn_first:
            lines += ["## Learn first (hotspots + entries)", ""]
            for x in self.learn_first:
                lines.append(f"- {x}")
            lines.append("")
        if self.skip_or_later:
            lines += ["## Skip or later (no inbound edges)", ""]
            for x in self.skip_or_later:
                lines.append(f"- {x}")
            lines.append("")
        if self.unreachable_from_entries:
            lines += ["## Unreachable from entry points", ""]
            for x in self.unreachable_from_entries[:25]:
                lines.append(f"- {x}")
            lines.append("")
        return "\n".join(lines)


def reading_priority(snapshot: ArchSnapshot, *, seed_names: list[str] | None = None) -> ReadingPriority:
    els = [e for e in snapshot.elements if not is_code_level(e)]
    by_id = {e.id: e for e in els}
    inbound: dict[str, int] = defaultdict(int)
    outbound: dict[str, int] = defaultdict(int)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for r in snapshot.relationships:
        if r.source_id not in by_id or r.target_id not in by_id:
            continue
        inbound[r.target_id] += 1
        outbound[r.source_id] += 1
        outgoing[r.source_id].append(r.target_id)

    degree = {e.id: inbound[e.id] + outbound[e.id] for e in els}
    hot = sorted(els, key=lambda e: -degree[e.id])[:12]
    hotspots = [
        f"`{e.name}` ({e.stereotype}, degree {degree[e.id]})"
        for e in hot
        if degree[e.id] >= 2
    ]

    dead = [
        f"`{e.name}` ({e.stereotype}) — `{e.file_path}`"
        for e in els
        if inbound[e.id] == 0 and outbound[e.id] == 0 and e.stereotype not in ENTRIES
    ]

    entries = [e for e in els if e.stereotype in ENTRIES]
    reachable: set[str] = set()
    stack = [e.id for e in entries]
    while stack:
        eid = stack.pop()
        if eid in reachable:
            continue
        reachable.add(eid)
        stack.extend(outgoing.get(eid, []))

    unreach = [
        f"`{e.name}` ({e.stereotype})"
        for e in els
        if e.id not in reachable and e.stereotype not in ("Entity", "Shared Data", "Configuration")
    ]

    learn = []
    if seed_names:
        learn.extend(f"Start at `{n}`" for n in seed_names[:5])
    learn.extend(hotspots[:8])
    for e in entries[:6]:
        line = f"Entry `{e.name}` ({e.stereotype})"
        if line not in learn:
            learn.append(line)

    skip = dead[:15]
    if seed_names:
        skip = [s for s in skip if not any(n in s for n in seed_names)]

    return ReadingPriority(
        learn_first=learn[:15],
        skip_or_later=skip,
        unreachable_from_entries=unreach[:25],
        hotspots=hotspots,
    )
