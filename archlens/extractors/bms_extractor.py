"""BMS map source (DFHMDI / DFHMDF) — fields on CICS screens."""

from __future__ import annotations

import re
from pathlib import Path

from archlens.extractors.base import BaseExtractor
from archlens.models import ArchElement, ArchRelationship, RelType, C4Level

_MAP = re.compile(r"(\w+)\s+DFHMDI\b", re.IGNORECASE)
_FIELD = re.compile(r"(\w+)\s+DFHMDF\b", re.IGNORECASE)


class BmsExtractor(BaseExtractor):
    language = "bms"

    def supported_extensions(self) -> set[str]:
        return {".bms"}

    def extract_elements(self, file_path: Path) -> list[ArchElement]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        rel = self.relative_path(file_path)
        maps = [m.group(1).upper() for m in _MAP.finditer(text)]
        if not maps:
            maps = [file_path.stem.upper()]
        fields = [m.group(1).upper() for m in _FIELD.finditer(text)]
        elements: list[ArchElement] = []
        for map_name in maps:
            elements.append(
                ArchElement(
                    id=f"bms.{map_name}",
                    name=map_name,
                    stereotype="UI Component",
                    language="bms",
                    file_path=rel,
                    metadata={"kind": "bms_map", "fields": fields[:80]},
                )
            )
            for fld in fields[:40]:
                elements.append(
                    ArchElement(
                        id=f"bms.{map_name}.field.{fld}",
                        name=fld,
                        stereotype="UI Component",
                        c4_level=C4Level.CODE.value,
                        language="bms",
                        file_path=rel,
                        metadata={"kind": "bms_field", "map": map_name},
                    )
                )
        return elements

    def extract_relationships(
        self, file_path: Path, elements: dict[str, ArchElement]
    ) -> list[ArchRelationship]:
        rel = self.relative_path(file_path)
        maps = [e for e in elements.values() if e.file_path == rel and e.metadata.get("kind") == "bms_map"]
        rels: list[ArchRelationship] = []
        for mp in maps:
            for fld in (mp.metadata or {}).get("fields") or []:
                tgt = f"bms.{mp.name}.field.{fld}"
                if tgt not in elements:
                    continue
                rels.append(
                    ArchRelationship(
                        source_id=mp.id,
                        target_id=tgt,
                        rel_type=RelType.COMPOSES.value,
                        description=f"BMS field {fld}",
                        technology="BMS",
                    )
                )
        return rels
