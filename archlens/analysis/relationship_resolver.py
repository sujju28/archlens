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

        from archlens.analysis.data_model import link_entity_foreign_keys
        from archlens.extractors.mainframe_stereotype import infer_mainframe_stereotype

        # Mainframe post-pass: mark LINK/JCL targets and re-infer stereotypes
        linked_targets = {
            r.target_id
            for r in resolved
            if r.rel_type in ("cics_link", "cics_xctl", "cics_start")
        }
        jcl_targets = {
            r.target_id for r in resolved if r.rel_type == "executes"
        }
        for el in elements:
            if el.language not in ("cobol", "jcl"):
                continue
            meta = dict(el.metadata or {})
            analysis = dict(meta.get("analysis") or {})
            if el.id in linked_targets:
                analysis["called_via_cics_link"] = True
                meta["called_via_cics_link"] = True
            if el.id in jcl_targets or meta.get("called_via_jcl_exec_pgm"):
                analysis["called_via_jcl_exec_pgm"] = True
                meta["called_via_jcl_exec_pgm"] = True
            for flag in (
                "is_copybook",
                "has_bms_send_map",
                "has_bms_receive_map",
                "has_exec_sql",
                "has_vsam_read_write",
                "has_mq_operations",
                "is_jcl_job",
            ):
                if flag in meta and flag not in analysis:
                    analysis[flag] = meta[flag]
            if meta.get("kind") == "copybook":
                analysis["is_copybook"] = True
            if meta.get("kind") == "jcl_job":
                analysis["is_jcl_job"] = True

            override = None
            # config is not on resolver — keep behavioral only here; overrides applied at extract
            if analysis:
                meta["analysis"] = analysis
                # Don't downgrade Controllers set via yaml override at extract time unless Component
                if el.stereotype in ("Component", "Batch Job", "Service", "Repository"):
                    el.stereotype = infer_mainframe_stereotype(analysis)
                el.metadata = meta

        return link_entity_foreign_keys(elements, resolved)
