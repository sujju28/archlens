"""Behavioral / process traces: API → service → repo → table and CICS chains."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from archlens.models import ArchSnapshot

ENTRY_STEREOTYPES = {"Controller", "Gateway", "UI Component", "Batch Job"}
DATA_STEREOTYPES = {"Entity", "Repository", "Shared Data"}
HOP_RELS = {
    "calls",
    "injects",
    "routes_to",
    "implements",
    "references",
    "accesses_table",
    "writes_table",
    "cics_link",
    "cics_xctl",
    "cics_start",
    "executes",
    "reads_dataset",
    "writes_dataset",
    "copies",
    "uses_map",
}


@dataclass
class ProcessTrace:
    entry: str
    entry_stereotype: str
    path: list[str]
    terminal: str
    terminal_stereotype: str
    kind: str = "request"  # request | cics | batch | data

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "entry_stereotype": self.entry_stereotype,
            "path": self.path,
            "terminal": self.terminal,
            "terminal_stereotype": self.terminal_stereotype,
            "kind": self.kind,
        }


@dataclass
class ProcessTraceReport:
    traces: list[ProcessTrace] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "traces": [t.to_dict() for t in self.traces],
            "stats": self.stats,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Process / behavioral traces",
            "",
            f"- **Traces:** {len(self.traces)}",
            f"- **Entries covered:** {self.stats.get('entries', 0)}",
            "",
        ]
        by_kind: dict[str, list[ProcessTrace]] = defaultdict(list)
        for t in self.traces:
            by_kind[t.kind].append(t)
        for kind, items in sorted(by_kind.items()):
            lines.append(f"## {kind.title()}")
            lines.append("")
            for t in items[:40]:
                lines.append(f"- `{' → '.join(t.path)}`")
            if len(items) > 40:
                lines.append(f"- _…and {len(items) - 40} more_")
            lines.append("")
        return "\n".join(lines)


def build_process_traces(
    snapshot: ArchSnapshot,
    *,
    max_depth: int = 6,
    max_traces: int = 200,
) -> ProcessTraceReport:
    by_id = {e.id: e for e in snapshot.elements}
    outgoing: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in snapshot.relationships:
        if r.rel_type in HOP_RELS:
            outgoing[r.source_id].append((r.target_id, r.rel_type))

    entries = [e for e in snapshot.elements if e.stereotype in ENTRY_STEREOTYPES]
    traces: list[ProcessTrace] = []
    seen_paths: set[tuple[str, ...]] = set()

    for entry in entries:
        if len(traces) >= max_traces:
            break
        # BFS paths to data terminals
        queue: deque[tuple[str, list[str], int]] = deque([(entry.id, [entry.name], 0)])
        visited_local: set[str] = {entry.id}
        while queue and len(traces) < max_traces:
            current, path, depth = queue.popleft()
            el = by_id.get(current)
            if not el:
                continue
            is_terminal = el.stereotype in DATA_STEREOTYPES or (
                el.language in ("db2",) and el.stereotype == "Entity"
            )
            if is_terminal and len(path) > 1:
                key = tuple(path)
                if key not in seen_paths:
                    seen_paths.add(key)
                    kind = _kind_for(entry)
                    traces.append(
                        ProcessTrace(
                            entry=entry.name,
                            entry_stereotype=entry.stereotype,
                            path=list(path),
                            terminal=el.name,
                            terminal_stereotype=el.stereotype,
                            kind=kind,
                        )
                    )
                continue
            if depth >= max_depth:
                continue
            for tgt, _rel in outgoing.get(current, []):
                nxt = by_id.get(tgt)
                if not nxt:
                    continue
                if tgt in visited_local and nxt.stereotype not in DATA_STEREOTYPES:
                    continue
                visited_local.add(tgt)
                queue.append((tgt, path + [nxt.name], depth + 1))

    # Also short CICS LINK/XCTL chains even without Entity terminal
    for r in snapshot.relationships:
        if r.rel_type not in ("cics_link", "cics_xctl", "cics_start"):
            continue
        src, tgt = by_id.get(r.source_id), by_id.get(r.target_id)
        if not src or not tgt:
            continue
        key = (src.name, tgt.name)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        traces.append(
            ProcessTrace(
                entry=src.name,
                entry_stereotype=src.stereotype,
                path=[src.name, tgt.name],
                terminal=tgt.name,
                terminal_stereotype=tgt.stereotype,
                kind="cics",
            )
        )
        if len(traces) >= max_traces:
            break

    # Fix kinds for request paths
    for t in traces:
        if t.kind == "request" and t.entry_stereotype == "Batch Job":
            t.kind = "batch"
        if t.entry_stereotype in ("Controller", "Gateway") and t.terminal_stereotype in DATA_STEREOTYPES:
            t.kind = "request"

    return ProcessTraceReport(
        traces=traces,
        stats={
            "entries": len(entries),
            "trace_count": len(traces),
            "kinds": dict(
                (k, sum(1 for t in traces if t.kind == k))
                for k in sorted({t.kind for t in traces})
            ),
        },
    )


def _kind_for(entry) -> str:
    if entry.stereotype == "Batch Job":
        return "batch"
    if entry.language in ("cobol", "jcl", "bms"):
        return "cics"
    return "request"
