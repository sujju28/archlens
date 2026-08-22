"""COBOL paragraph / PERFORM extraction (procedure division)."""

from __future__ import annotations

import re

_PROC = re.compile(r"PROCEDURE\s+DIVISION", re.IGNORECASE)
_SECTION = re.compile(r"^([A-Z0-9][\w-]*)\s+SECTION\s*\.\s*$", re.IGNORECASE)
_PARA = re.compile(r"^([A-Z0-9][\w-]*)\s*\.\s*$")
_PERFORM = re.compile(
    r"\bPERFORM\s+(?!VARYING\b)(?:UNTIL\s+\S+\s+)?"
    r"([A-Z0-9][\w-]*)(?:\s+THRU\s+([A-Z0-9][\w-]*))?",
    re.IGNORECASE,
)

_RESERVED = {
    "EXIT",
    "EJECT",
    "SKIP1",
    "SKIP2",
    "SKIP3",
    "CONTINUE",
    "GOBACK",
    "STOP",
    "RETURN",
    "GIVING",
    "COPY",
    "EXEC",
    "END-EXEC",
    "END-IF",
    "END-EVALUATE",
    "END-PERFORM",
    "ELSE",
    "WHEN",
    "OTHER",
    "TRUE",
    "FALSE",
    "NOT",
    "AND",
    "OR",
    "IF",
    "EVALUATE",
    "PERFORM",
    "MOVE",
    "DISPLAY",
    "CALL",
    "COMPUTE",
    "OPEN",
    "CLOSE",
    "READ",
    "WRITE",
    "REWRITE",
    "DELETE",
    "START",
    "INITIALIZE",
    "INSPECT",
    "STRING",
    "UNSTRING",
    "ACCEPT",
    "ADD",
    "SUBTRACT",
    "MULTIPLY",
    "DIVIDE",
    "GO",
    "TO",
    "THRU",
    "UNTIL",
    "TIMES",
    "VARYING",
    "WITH",
    "TEST",
    "AFTER",
    "BEFORE",
    "SECTION",
    "DIVISION",
    "PROGRAM",
}


def extract_paragraphs_and_performs(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return paragraph names and (source_para, target_para) PERFORM edges."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if _PROC.search(ln)), None)
    if start is None:
        return [], []
    paras: list[str] = []
    seen: set[str] = set()
    current: str | None = None
    performs: list[tuple[str, str]] = []
    body = "\n".join(lines[start + 1 :])
    for raw in lines[start + 1 :]:
        line = raw.strip()
        if not line:
            continue
        sm = _SECTION.match(line)
        if sm:
            current = None
            continue
        pm = _PARA.match(line)
        if pm:
            name = pm.group(1).upper()
            if name in _RESERVED:
                continue
            # Prefer labeled paras (1000-FOO) or names not COBOL verbs
            if name not in seen:
                seen.add(name)
                paras.append(name)
            current = name
            continue
        if current:
            for m in _PERFORM.finditer(line):
                a = m.group(1).upper()
                b = (m.group(2) or "").upper()
                if a not in _RESERVED:
                    performs.append((current, a))
                if b and b not in _RESERVED:
                    performs.append((current, b))
    # Also catch multi-line PERFORM in collapsed body
    if not performs:
        current_fallback = paras[0] if paras else None
        if current_fallback:
            for m in _PERFORM.finditer(body):
                a = m.group(1).upper()
                b = (m.group(2) or "").upper()
                if a not in _RESERVED:
                    performs.append((current_fallback, a))
                if b and b not in _RESERVED:
                    performs.append((current_fallback, b))
    return paras[:40], performs[:80]


def cobol_remarks(raw: str, *, limit: int = 8) -> list[str]:
    """Fixed-format comment indicator (col 7) and `*>` free-format remarks."""
    out: list[str] = []
    skip = ("copyright", "licensed", "all rights", "spdx")
    for line in raw.splitlines():
        body = ""
        if len(line) > 6 and line[6] in "*C/cDd":
            body = (line[7:72] if len(line) > 7 else line[7:]).strip()
        else:
            m = re.search(r"\*>\s*(.+)$", line)
            if m:
                body = m.group(1).strip()
        if len(body) < 12:
            continue
        low = body.lower()
        if any(s in low for s in skip):
            continue
        out.append(body)
        if len(out) >= limit:
            break
    return out
