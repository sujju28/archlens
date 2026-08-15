"""Compare architecture snapshots for drift."""

from __future__ import annotations

from archlens.models import ArchDiff, ArchElement, ArchRelationship, ArchSnapshot, ElementChange


class DiffEngine:
    def compare(self, from_snap: ArchSnapshot, to_snap: ArchSnapshot) -> ArchDiff:
        from_els = {e.id: e for e in from_snap.elements}
        to_els = {e.id: e for e in to_snap.elements}

        added = [to_els[i] for i in to_els if i not in from_els]
        removed = [from_els[i] for i in from_els if i not in to_els]
        modified: list[ElementChange] = []

        for eid in set(from_els) & set(to_els):
            a, b = from_els[eid], to_els[eid]
            changes = []
            if a.stereotype != b.stereotype:
                changes.append(f"stereotype: {a.stereotype} → {b.stereotype}")
            if a.file_path != b.file_path:
                changes.append(f"moved: {a.file_path} → {b.file_path}")
            if set(a.annotations) != set(b.annotations):
                changes.append("annotations changed")
            if a.extends != b.extends:
                changes.append(f"extends: {a.extends} → {b.extends}")
            if changes:
                modified.append(
                    ElementChange(
                        element=b,
                        change_type="modified",
                        diff_summary="; ".join(changes),
                    )
                )

        from_rels = self._rel_keys(from_snap.relationships)
        to_rels = self._rel_keys(to_snap.relationships)
        added_rels = [r for k, r in to_rels.items() if k not in from_rels]
        removed_rels = [r for k, r in from_rels.items() if k not in to_rels]

        return ArchDiff(
            from_snapshot_id=from_snap.snapshot_id,
            to_snapshot_id=to_snap.snapshot_id,
            added_elements=added,
            removed_elements=removed,
            modified_elements=modified,
            added_relationships=added_rels,
            removed_relationships=removed_rels,
        )

    def _rel_keys(
        self, relationships: list[ArchRelationship]
    ) -> dict[tuple[str, str, str], ArchRelationship]:
        return {(r.source_id, r.target_id, r.rel_type): r for r in relationships}

    def summary(self, diff: ArchDiff) -> dict:
        return {
            "added_elements": len(diff.added_elements),
            "removed_elements": len(diff.removed_elements),
            "modified_elements": len(diff.modified_elements),
            "added_relationships": len(diff.added_relationships),
            "removed_relationships": len(diff.removed_relationships),
            "has_changes": diff.has_changes,
        }
