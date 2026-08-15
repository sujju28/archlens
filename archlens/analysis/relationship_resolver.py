"""Cross-file relationship resolution."""

from __future__ import annotations

from archlens.models import ArchElement, ArchRelationship, RelType


class RelationshipResolver:
    """Resolves and enriches cross-file relationships after extraction."""

    def resolve(
        self,
        elements: list[ArchElement],
        relationships: list[ArchRelationship],
    ) -> list[ArchRelationship]:
        by_id = {e.id: e for e in elements}
        by_name: dict[str, list[str]] = {}
        for e in elements:
            by_name.setdefault(e.name, []).append(e.id)

        resolved: list[ArchRelationship] = []
        seen: set[tuple[str, str, str]] = set()

        def add(rel: ArchRelationship) -> None:
            key = (rel.source_id, rel.target_id, rel.rel_type)
            if key in seen:
                return
            if rel.source_id not in by_id or rel.target_id not in by_id:
                # Keep unresolved imports only if both ends exist
                return
            if rel.source_id == rel.target_id:
                return
            seen.add(key)
            resolved.append(rel)

        for rel in relationships:
            # Try to remap target if it's a short name
            target = rel.target_id
            if target not in by_id:
                candidates = by_name.get(target.split(".")[-1], [])
                if len(candidates) == 1:
                    target = candidates[0]
                elif candidates:
                    # Prefer same-language match
                    src = by_id.get(rel.source_id)
                    lang_matches = [
                        c for c in candidates if src and by_id[c].language == src.language
                    ]
                    target = lang_matches[0] if lang_matches else candidates[0]
            add(
                ArchRelationship(
                    source_id=rel.source_id,
                    target_id=target,
                    rel_type=rel.rel_type,
                    description=rel.description,
                    technology=rel.technology,
                )
            )

        # Infer Controller → Service by naming convention
        services = [e for e in elements if e.stereotype == "Service"]
        controllers = [e for e in elements if e.stereotype == "Controller"]
        for ctrl in controllers:
            base = ctrl.name.replace("Controller", "").replace("Router", "").replace("Resource", "")
            for svc in services:
                svc_base = svc.name.replace("Service", "")
                if base and svc_base and base == svc_base:
                    add(
                        ArchRelationship(
                            source_id=ctrl.id,
                            target_id=svc.id,
                            rel_type=RelType.INJECTS.value,
                            description=f"inferred {ctrl.name} → {svc.name}",
                            technology="naming convention",
                        )
                    )

        # Infer Service → Repository
        repos = [e for e in elements if e.stereotype in ("Repository", "Entity")]
        for svc in services:
            base = svc.name.replace("Service", "")
            for repo in repos:
                repo_base = (
                    repo.name.replace("Repository", "")
                    .replace("Repo", "")
                    .replace("Entity", "")
                    .replace("Model", "")
                )
                if base and repo_base and base == repo_base:
                    add(
                        ArchRelationship(
                            source_id=svc.id,
                            target_id=repo.id,
                            rel_type=RelType.INJECTS.value,
                            description=f"inferred {svc.name} → {repo.name}",
                            technology="naming convention",
                        )
                    )

        return resolved
