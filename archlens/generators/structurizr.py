"""Structurizr DSL exporter."""

from __future__ import annotations

from archlens.models import ArchSnapshot


class StructurizrExporter:
    def generate(self, snapshot: ArchSnapshot, level: str = "component") -> str:
        project = snapshot.metadata.get("project_name", "System")
        lines = [
            "workspace {",
            f'    model {{',
            f'        softwareSystem "{project}" {{',
        ]

        # Group by stereotype as containers-ish
        by_stereo: dict[str, list] = {}
        for el in snapshot.elements:
            by_stereo.setdefault(el.stereotype, []).append(el)

        for stereo, els in by_stereo.items():
            container_id = self._safe(stereo)
            lines.append(f'            {container_id} = container "{stereo}s" {{')
            for el in els:
                cid = self._safe(el.id)
                lines.append(
                    f'                {cid} = component "{el.name}" "{el.stereotype}"'
                )
            lines.append("            }")

        # Relationships
        for rel in snapshot.relationships:
            src = self._safe(rel.source_id)
            tgt = self._safe(rel.target_id)
            lines.append(f'            {src} -> {tgt} "{rel.rel_type}"')

        lines.extend(
            [
                "        }",
                "    }",
                "    views {",
                f'        component "{project}" {{',
                "            include *",
                "            autoLayout",
                "        }",
                "    }",
                "}",
            ]
        )
        return "\n".join(lines)

    def _safe(self, value: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in value)
