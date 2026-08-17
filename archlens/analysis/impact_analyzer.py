"""Impact analysis via dependency graph traversal."""

from __future__ import annotations

from collections import deque

import networkx as nx

from archlens.config import ArchLensConfig
from archlens.models import AffectedElement, ArchSnapshot, ImpactReport

RISK_WEIGHTS = {
    "Controller": 3.0,
    "Gateway": 3.0,
    "Service": 2.0,
    "Repository": 1.5,
    "Configuration": 2.5,
    "Component": 1.0,
    "UI Component": 1.5,
    "Middleware": 2.0,
    "Entity": 1.0,
    "Worker": 2.0,
}


class ImpactAnalyzer:
    def __init__(self, config: ArchLensConfig | None = None):
        self.config = config or ArchLensConfig()

    def analyze(
        self,
        snapshot: ArchSnapshot,
        files: list[str] | None = None,
        elements: list[str] | None = None,
        depth: int | None = None,
    ) -> ImpactReport:
        max_depth = depth or self.config.impact.max_depth
        by_id = {e.id: e for e in snapshot.elements}
        graph = self._build_graph(snapshot)

        changed_ids = self._resolve_changed(by_id, files or [], elements or [])
        if not changed_ids:
            return ImpactReport(
                changed_files=files or [],
                changed_elements=[],
                summary={"warning": "No architectural elements matched."},
            )

        direct: list[AffectedElement] = []
        transitive: list[AffectedElement] = []
        visited = set(changed_ids)
        queue: deque[tuple[str, int, str]] = deque()

        # Upstream = who depends on me (predecessors in digraph where edge A→B means A depends on B)
        # We store edges as source → target meaning source depends on / injects target.
        # Upstream dependents of X are nodes with edge → X, i.e. predecessors.
        for start_id in changed_ids:
            for dep_id in graph.predecessors(start_id):
                if dep_id in visited:
                    continue
                visited.add(dep_id)
                el = by_id.get(dep_id)
                if not el:
                    continue
                rel_type = graph.edges[dep_id, start_id].get("rel_type", "depends")
                reason = f"{rel_type} → {by_id[start_id].name}"
                entry = AffectedElement(
                    id=dep_id,
                    name=el.name,
                    stereotype=el.stereotype,
                    file_path=el.file_path,
                    reason=reason,
                    hops=1,
                    risk=self._risk(el.stereotype),
                )
                direct.append(entry)
                queue.append((dep_id, 1, f"{el.name} → {by_id[start_id].name}"))

        while queue:
            current_id, hops, chain = queue.popleft()
            if hops >= max_depth:
                continue
            for dep_id in graph.predecessors(current_id):
                if dep_id in visited:
                    continue
                visited.add(dep_id)
                el = by_id.get(dep_id)
                if not el:
                    continue
                rel_type = graph.edges[dep_id, current_id].get("rel_type", "depends")
                new_chain = f"{el.name} →({rel_type}) {chain}"
                entry = AffectedElement(
                    id=dep_id,
                    name=el.name,
                    stereotype=el.stereotype,
                    file_path=el.file_path,
                    reason=new_chain,
                    hops=hops + 1,
                    risk=self._risk(el.stereotype),
                )
                transitive.append(entry)
                queue.append((dep_id, hops + 1, new_chain))

        all_affected = direct + transitive
        risk_score = sum(RISK_WEIGHTS.get(a.stereotype, 1.0) for a in all_affected)
        suggestions = self._suggest(changed_ids, by_id, direct)

        return ImpactReport(
            changed_files=files or [],
            changed_elements=[by_id[i].name for i in changed_ids if i in by_id],
            directly_affected=direct,
            transitively_affected=transitive,
            risk_score=round(risk_score, 1),
            suggested_changes=suggestions,
            summary={
                "direct_dependents": len(direct),
                "transitive_dependents": len(transitive),
                "total_affected": len(all_affected),
                "high_risk_count": sum(1 for a in all_affected if a.risk == "HIGH"),
            },
        )

    def _build_graph(self, snapshot: ArchSnapshot) -> nx.DiGraph:
        g = nx.DiGraph()
        for e in snapshot.elements:
            g.add_node(e.id)
        for r in snapshot.relationships:
            g.add_edge(r.source_id, r.target_id, rel_type=r.rel_type)
        return g

    def _resolve_changed(
        self,
        by_id: dict,
        files: list[str],
        element_names: list[str],
    ) -> list[str]:
        changed: list[str] = []
        for eid, el in by_id.items():
            for f in files:
                fp = el.file_path.replace("\\", "/")
                f_norm = f.replace("\\", "/")
                if fp.endswith(f_norm) or f_norm.endswith(fp) or f_norm in fp:
                    changed.append(eid)
                    break
        for name in element_names:
            for eid, el in by_id.items():
                if el.name.lower() == name.lower() or eid.lower() == name.lower():
                    changed.append(eid)
        return list(dict.fromkeys(changed))

    def _risk(self, stereotype: str) -> str:
        weight = RISK_WEIGHTS.get(stereotype, 1.0)
        critical = self.config.impact.critical_stereotypes
        if stereotype in critical or weight >= 2.5:
            return "HIGH"
        if weight >= 1.5:
            return "MEDIUM"
        return "LOW"

    def _suggest(self, changed_ids: list[str], by_id: dict, direct: list[AffectedElement]) -> list[str]:
        suggestions: list[str] = []
        critical = set(self.config.impact.critical_stereotypes)

        for cid in changed_ids:
            el = by_id.get(cid)
            if not el:
                continue
            dependents = [d for d in direct if el.name in d.reason or d.reason.endswith(el.name)]
            if not dependents:
                dependents = [d for d in direct if el.id in d.reason or el.name in d.reason]

            containers = sorted(
                {
                    str((by_id.get(d.id).metadata or {}).get("container"))
                    for d in dependents
                    if by_id.get(d.id) and (by_id[d.id].metadata or {}).get("container")
                }
            )
            owners = sorted(
                {
                    str((by_id.get(d.id).metadata or {}).get("owner"))
                    for d in dependents
                    if by_id.get(d.id) and (by_id[d.id].metadata or {}).get("owner")
                }
            )

            if dependents:
                names = ", ".join(f"`{d.name}` ({d.stereotype})" for d in dependents[:6])
                suggestions.append(
                    f"Blast radius of `{el.name}` ({el.stereotype}): update {names}"
                )
            if containers:
                suggestions.append(
                    f"Notify containers impacted by `{el.name}`: "
                    + ", ".join(f"`{c}`" for c in containers[:6])
                )
            if owners:
                suggestions.append(
                    f"Owners to loop in for `{el.name}`: " + ", ".join(owners[:6])
                )

            high = [d for d in dependents if d.stereotype in critical or d.risk == "HIGH"]
            if high:
                suggestions.append(
                    f"High-risk entry points depending on `{el.name}`: "
                    + ", ".join(f"`{d.name}`" for d in high[:5])
                    + " — verify contracts/tests before merge"
                )

            if el.stereotype == "Entity":
                suggestions.append(
                    f"Entity `{el.name}` changed — check migrations/DDL and "
                    f"repository mappings; run `archlens schema-drift`"
                )
            if el.stereotype == "Service":
                suggestions.append(
                    f"Update unit/integration tests covering `{el.name}` "
                    f"(`{el.file_path}`)"
                )
            if el.stereotype in ("Controller", "Gateway"):
                suggestions.append(
                    f"API surface `{el.name}` changed — review OpenAPI/clients "
                    f"and run `archlens contracts` if multi-repo"
                )
            if (el.metadata or {}).get("critical_paths"):
                paths = ", ".join(
                    f"`{p}`" for p in (el.metadata or {}).get("critical_paths", [])[:4]
                )
                suggestions.append(
                    f"`{el.name}` is on critical path(s) {paths} — treat as release-risk"
                )

        # De-dupe while preserving order
        seen: set[str] = set()
        uniq: list[str] = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        return uniq