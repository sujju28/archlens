"""Architecture health scoring: coupling, cycles, layer violations, trends."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from archlens.models import ArchSnapshot, is_code_level
from archlens.storage.sqlite_store import SQLiteStore

LAYER_RANK = {
    "Controller": 1,
    "Gateway": 1,
    "UI Component": 1,
    "Middleware": 2,
    "Service": 3,
    "Worker": 3,
    "Batch Job": 3,
    "Repository": 4,
    "Entity": 4,
    "Shared Data": 4,
    "Configuration": 5,
    "Component": 3,
}


@dataclass
class HealthReport:
    score: float
    grade: str
    metrics: dict[str, Any] = field(default_factory=dict)
    cycles: list[list[str]] = field(default_factory=list)
    layer_violations: list[dict[str, str]] = field(default_factory=list)
    highly_coupled: list[dict[str, Any]] = field(default_factory=list)
    trends: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "grade": self.grade,
            "metrics": self.metrics,
            "cycles": self.cycles,
            "layer_violations": self.layer_violations,
            "highly_coupled": self.highly_coupled,
            "trends": self.trends,
        }


class HealthScorer:
    def analyze(self, snapshot: ArchSnapshot, store: SQLiteStore | None = None) -> HealthReport:
        g = nx.DiGraph()
        by_id = {e.id: e for e in snapshot.elements if not is_code_level(e)}
        for e in snapshot.elements:
            if is_code_level(e):
                continue
            g.add_node(e.id, stereotype=e.stereotype, name=e.name)
        for r in snapshot.relationships:
            if r.source_id in by_id and r.target_id in by_id:
                g.add_edge(r.source_id, r.target_id, rel_type=r.rel_type)

        n_elements = len(snapshot.elements)
        n_rels = g.number_of_edges()
        density = nx.density(g) if n_elements > 1 else 0.0

        # Cycles
        cycles: list[list[str]] = []
        try:
            for cycle in nx.simple_cycles(g):
                if len(cycle) >= 2:
                    names = [by_id[n].name if n in by_id else n for n in cycle]
                    cycles.append(names)
                if len(cycles) >= 20:
                    break
        except nx.NetworkXError:
            pass

        # Layer violations: higher layer depending on lower? Actually violation =
        # lower architectural layer depending upward (Repository → Controller)
        # or Controller depending on Entity skipping Service sometimes —
        # classic: layer A should not depend on layer above it.
        violations = []
        for src, tgt, data in g.edges(data=True):
            s, t = by_id.get(src), by_id.get(tgt)
            if not s or not t:
                continue
            rs = LAYER_RANK.get(s.stereotype, 3)
            rt = LAYER_RANK.get(t.stereotype, 3)
            # Violation: deeper layer (higher rank number) depends on shallower (lower number)
            if rs > rt:
                violations.append(
                    {
                        "from": s.name,
                        "from_stereotype": s.stereotype,
                        "to": t.name,
                        "to_stereotype": t.stereotype,
                        "rel_type": data.get("rel_type", ""),
                        "reason": f"{s.stereotype} should not depend on {t.stereotype}",
                    }
                )

        # Coupling: fan-in / fan-out
        coupled = []
        for nid in g.nodes:
            fan_in = g.in_degree(nid)
            fan_out = g.out_degree(nid)
            score = fan_in + fan_out
            if score >= 3:
                el = by_id.get(nid)
                coupled.append(
                    {
                        "name": el.name if el else nid,
                        "stereotype": el.stereotype if el else "Unknown",
                        "fan_in": fan_in,
                        "fan_out": fan_out,
                        "coupling": score,
                    }
                )
        coupled.sort(key=lambda x: -x["coupling"])

        # Score 0-100
        score = 100.0
        score -= min(40.0, len(cycles) * 8.0)
        score -= min(30.0, len(violations) * 3.0)
        score -= min(20.0, density * 100.0)
        if n_elements == 0:
            score = 0.0
        score = max(0.0, round(score, 1))
        grade = (
            "A" if score >= 90 else
            "B" if score >= 75 else
            "C" if score >= 60 else
            "D" if score >= 40 else
            "F"
        )

        trends = []
        if store:
            trends = self._trends(store, score)

        return HealthReport(
            score=score,
            grade=grade,
            metrics={
                "elements": n_elements,
                "relationships": n_rels,
                "density": round(density, 4),
                "cycle_count": len(cycles),
                "layer_violation_count": len(violations),
                "avg_coupling": round(
                    sum(c["coupling"] for c in coupled) / len(coupled), 2
                )
                if coupled
                else 0.0,
            },
            cycles=cycles[:10],
            layer_violations=violations[:25],
            highly_coupled=coupled[:15],
            trends=trends,
        )

    def _trends(self, store: SQLiteStore, current_score: float) -> list[dict[str, Any]]:
        snaps = store.list_snapshots(limit=10)
        trends = []
        for meta in reversed(snaps):
            snap = store.get_snapshot(meta["id"])
            if not snap:
                continue
            # Avoid infinite recursion — compute lightweight metrics only
            report = HealthScorer().analyze(snap, store=None)
            trends.append(
                {
                    "snapshot_id": snap.snapshot_id,
                    "commit_sha": snap.commit_sha,
                    "timestamp": str(snap.timestamp),
                    "score": report.score,
                    "grade": report.grade,
                    "cycle_count": report.metrics.get("cycle_count"),
                    "layer_violation_count": report.metrics.get("layer_violation_count"),
                }
            )
        if trends:
            trends[-1]["score"] = current_score  # align last with full analysis
        return trends
