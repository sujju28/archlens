"""COBOL / CICS / DB2 extractor (regex-based; tree-sitter-cobol optional later).

Handles fixed-format IBM COBOL (cols 8–72) and free-format source.
"""

from __future__ import annotations

import re
from pathlib import Path

from archlens.extractors.base import BaseExtractor
from archlens.extractors.mainframe_stereotype import infer_mainframe_stereotype
from archlens.models import ArchElement, ArchRelationship, RelType

_PROGRAM_ID = re.compile(
    r"PROGRAM-ID\s*\.\s*([A-Z0-9][\w-]*)\s*\.?",
    re.IGNORECASE,
)
_CALL_STATIC = re.compile(
    r"\bCALL\s+['\"]([A-Z0-9][\w-]*)['\"]",
    re.IGNORECASE,
)
_CALL_DYNAMIC = re.compile(
    r"\bCALL\s+([A-Z][\w-]*)\b",
    re.IGNORECASE,
)
_CICS_LINK = re.compile(
    r"EXEC\s+CICS\s+LINK\s+.*?PROGRAM\s*\(\s*['\"]?([A-Z0-9][\w-]*)['\"]?\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_CICS_XCTL = re.compile(
    r"EXEC\s+CICS\s+XCTL\s+.*?PROGRAM\s*\(\s*['\"]?([A-Z0-9][\w-]*)['\"]?\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_CICS_START = re.compile(
    r"EXEC\s+CICS\s+START\s+.*?TRANSID\s*\(\s*['\"]?([A-Z0-9][\w-]*)['\"]?\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_CICS_SEND_MAP = re.compile(
    r"EXEC\s+CICS\s+SEND\s+MAP\s*\(\s*['\"]?([A-Z0-9][\w-]*)['\"]?\s*\)",
    re.IGNORECASE,
)
_CICS_RECV_MAP = re.compile(
    r"EXEC\s+CICS\s+RECEIVE\s+MAP\s*\(\s*['\"]?([A-Z0-9][\w-]*)['\"]?\s*\)",
    re.IGNORECASE,
)
_COPY = re.compile(
    r"\bCOPY\s+([A-Z0-9][\w-]*)\s*\.?",
    re.IGNORECASE,
)
_SQL_FROM = re.compile(
    r"EXEC\s+SQL\b.*?FROM\s+([A-Z][\w.]*)",
    re.IGNORECASE | re.DOTALL,
)
_SQL_INTO = re.compile(
    r"EXEC\s+SQL\b.*?(?:INSERT\s+INTO|UPDATE)\s+([A-Z][\w.]*)",
    re.IGNORECASE | re.DOTALL,
)
_SQL_ANY = re.compile(r"EXEC\s+SQL\b", re.IGNORECASE)
_VSAM = re.compile(
    r"\b(?:READ|WRITE|REWRITE|DELETE|START)\s+(?:FILE\s+)?([A-Z][\w-]*)",
    re.IGNORECASE,
)
_MQ = re.compile(r"\bMQ(?:PUT|GET|OPEN|CLOSE)\b", re.IGNORECASE)
_COBOL_RESERVED_CALL = {
    "USING",
    "BY",
    "CONTENT",
    "REFERENCE",
    "VALUE",
    "RETURNING",
    "END-CALL",
}


class CobolExtractor(BaseExtractor):
    language = "cobol"

    def supported_extensions(self) -> set[str]:
        return {".cbl", ".cob", ".cpy"}

    def extract_elements(self, file_path: Path) -> list[ArchElement]:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        text = normalize_cobol_source(raw)
        rel = self.relative_path(file_path)
        is_copybook = file_path.suffix.lower() == ".cpy"

        program_name = None
        m = _PROGRAM_ID.search(text)
        if m:
            program_name = m.group(1).upper()
        elif is_copybook:
            program_name = file_path.stem.upper()
        else:
            program_name = file_path.stem.upper()

        analysis = self._analyze(text, is_copybook=is_copybook)
        override = self.config.mainframe_stereotype_override(program_name)
        stereotype = infer_mainframe_stereotype(analysis, override=override)

        eid = f"cobol.{program_name}"
        metadata = {
            "kind": "copybook" if is_copybook else "program",
            "analysis": {k: v for k, v in analysis.items() if not isinstance(v, list)},
            "calls": analysis.get("calls", []),
            "cics_links": analysis.get("cics_links", []),
            "cics_xctls": analysis.get("cics_xctls", []),
            "copies": analysis.get("copies", []),
            "tables_read": analysis.get("tables_read", []),
            "tables_written": analysis.get("tables_written", []),
            "maps": analysis.get("maps", []),
        }

        elements = [
            ArchElement(
                id=eid,
                name=program_name,
                stereotype=stereotype,
                language="cobol",
                file_path=rel,
                metadata=metadata,
            )
        ]

        # Synthetic DB2 table entities
        for table in sorted(set(analysis.get("tables_read", []) + analysis.get("tables_written", []))):
            tid = f"db2.{table}"
            elements.append(
                ArchElement(
                    id=tid,
                    name=table,
                    stereotype="Entity",
                    language="db2",
                    file_path=rel,
                    metadata={"kind": "db2_table", "table_name": table},
                )
            )

        # Synthetic BMS map elements
        for map_name in analysis.get("maps", []):
            mid = f"bms.{map_name}"
            elements.append(
                ArchElement(
                    id=mid,
                    name=map_name,
                    stereotype="UI Component",
                    language="bms",
                    file_path=rel,
                    metadata={"kind": "bms_map"},
                )
            )

        return elements

    def extract_relationships(
        self, file_path: Path, elements: dict[str, ArchElement]
    ) -> list[ArchRelationship]:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
        text = normalize_cobol_source(raw)
        rel_path = self.relative_path(file_path)
        file_els = [e for e in elements.values() if e.file_path == rel_path and e.language == "cobol"]
        if not file_els:
            # resolve by PROGRAM-ID
            m = _PROGRAM_ID.search(text)
            name = (m.group(1) if m else file_path.stem).upper()
            src_id = f"cobol.{name}"
        else:
            src_id = file_els[0].id

        analysis = self._analyze(text, is_copybook=file_path.suffix.lower() == ".cpy")
        rels: list[ArchRelationship] = []

        def add(tgt_id: str, rel_type: str, desc: str, tech: str | None = None) -> None:
            if tgt_id == src_id:
                return
            # Allow forward refs — resolver keeps only existing targets
            rels.append(
                ArchRelationship(
                    source_id=src_id,
                    target_id=tgt_id,
                    rel_type=rel_type,
                    description=desc,
                    technology=tech,
                )
            )

        for prog in analysis.get("calls", []):
            add(f"cobol.{prog}", RelType.CALLS.value, f"CALL '{prog}'", "COBOL")
        for prog in analysis.get("dynamic_calls", []):
            add(
                f"cobol.{prog}",
                RelType.CALLS.value,
                f"CALL {prog} (dynamic)",
                "COBOL dynamic",
            )
        for prog in analysis.get("cics_links", []):
            add(f"cobol.{prog}", RelType.CICS_LINK.value, f"EXEC CICS LINK PROGRAM('{prog}')", "CICS")
        for prog in analysis.get("cics_xctls", []):
            add(f"cobol.{prog}", RelType.CICS_XCTL.value, f"EXEC CICS XCTL PROGRAM('{prog}')", "CICS")
        for trans in analysis.get("cics_starts", []):
            # Map TRANSID → program via config when available
            prog = self.config.mainframe.transactions.get(trans, trans)
            add(f"cobol.{prog.upper()}", RelType.CICS_START.value, f"EXEC CICS START TRANSID('{trans}')", "CICS")
        for cpy in analysis.get("copies", []):
            add(f"cobol.{cpy}", RelType.COPIES.value, f"COPY {cpy}", "COPY")
            add(f"cobol.{cpy}", RelType.IMPORTS.value, f"COPY {cpy}", "COPY")
        for table in analysis.get("tables_read", []):
            add(f"db2.{table}", RelType.ACCESSES_TABLE.value, f"EXEC SQL FROM {table}", "DB2")
        for table in analysis.get("tables_written", []):
            add(f"db2.{table}", RelType.WRITES_TABLE.value, f"EXEC SQL WRITE {table}", "DB2")
        for map_name in analysis.get("maps", []):
            add(f"bms.{map_name}", RelType.USES_MAP.value, f"CICS MAP {map_name}", "BMS")

        return rels

    def _analyze(self, text: str, *, is_copybook: bool) -> dict:
        calls = [m.group(1).upper() for m in _CALL_STATIC.finditer(text)]
        dynamic: list[str] = []
        for m in _CALL_DYNAMIC.finditer(text):
            name = m.group(1).upper()
            if name in _COBOL_RESERVED_CALL or name in calls:
                continue
            # Skip if looks like a literal already captured
            if f"'{name}'" in text.upper() or f'"{name}"' in text.upper():
                continue
            dynamic.append(name)

        cics_links = [m.group(1).upper() for m in _CICS_LINK.finditer(text)]
        cics_xctls = [m.group(1).upper() for m in _CICS_XCTL.finditer(text)]
        cics_starts = [m.group(1).upper() for m in _CICS_START.finditer(text)]
        send_maps = [m.group(1).upper() for m in _CICS_SEND_MAP.finditer(text)]
        recv_maps = [m.group(1).upper() for m in _CICS_RECV_MAP.finditer(text)]
        copies = [m.group(1).upper() for m in _COPY.finditer(text)]
        tables_read = [m.group(1).upper().split(".")[-1] for m in _SQL_FROM.finditer(text)]
        tables_written = [m.group(1).upper().split(".")[-1] for m in _SQL_INTO.finditer(text)]

        return {
            "is_copybook": is_copybook,
            "has_bms_send_map": bool(send_maps),
            "has_bms_receive_map": bool(recv_maps),
            "has_exec_sql": bool(_SQL_ANY.search(text)),
            "has_vsam_read_write": bool(_VSAM.search(text)),
            "has_mq_operations": bool(_MQ.search(text)),
            "called_via_cics_link": False,  # filled by resolver post-pass
            "called_via_jcl_exec_pgm": False,
            "calls": sorted(set(calls)),
            "dynamic_calls": sorted(set(dynamic)),
            "cics_links": sorted(set(cics_links)),
            "cics_xctls": sorted(set(cics_xctls)),
            "cics_starts": sorted(set(cics_starts)),
            "copies": sorted(set(copies)),
            "tables_read": sorted(set(tables_read)),
            "tables_written": sorted(set(tables_written)),
            "maps": sorted(set(send_maps + recv_maps)),
        }


def normalize_cobol_source(raw: str) -> str:
    """Strip sequence numbers / indicator area; keep Area A/B (cols 8–72)."""
    lines_out: list[str] = []
    for line in raw.splitlines():
        # Free format if short or no classic padding
        if len(line) < 7:
            lines_out.append(line)
            continue
        # Comment indicator in column 7 (1-based) → index 6
        indicator = line[6] if len(line) > 6 else " "
        if indicator in ("*", "/", "C", "c", "D", "d"):
            continue
        # Fixed format: cols 8–72 (indices 7:72)
        if len(line) >= 72 or (len(line) > 6 and line[:6].strip().isdigit()):
            code = line[7:72] if len(line) > 7 else line[7:]
            lines_out.append(code)
        else:
            lines_out.append(line)
    # Collapse EXEC blocks to single-line-friendly text
    return "\n".join(lines_out)
