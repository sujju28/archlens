"""Comments, Javadoc, COBOL remarks, and candidate business rules from source."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archlens.extractors.cobol_paragraphs import cobol_remarks
from archlens.models import ArchElement, ArchSnapshot, is_code_level

_JAVADOC = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)
_LINE_DOC = re.compile(r"^\s*///\s?(.*)$", re.MULTILINE)
_PY_DOC = re.compile(r'^\s*("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', re.MULTILINE)
_IF_COB = re.compile(r"\bIF\s+(.{8,90}?)(?:\s+THEN)?\s*$", re.IGNORECASE | re.MULTILINE)
_EVAL = re.compile(r"\bEVALUATE\s+(.{3,70})", re.IGNORECASE)
_WHEN = re.compile(r"\bWHEN\s+(.{3,70})", re.IGNORECASE)
_IF_JAVA = re.compile(r"\bif\s*\((.{8,90})\)", re.IGNORECASE)
_VALID = re.compile(
    r"@(?:Valid|NotNull|NotBlank|Size|Pattern|AssertTrue|Min|Max)\b"
    r"|validate[A-Z]\w*|\.validate\s*\(",
)
_LICENSE = ("licensed under", "copyright", "all rights reserved", "apache license", "spdx")


@dataclass
class DocNote:
    kind: str
    text: str
    citation: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "citation": self.citation}


@dataclass
class CandidateRule:
    kind: str
    text: str
    citation: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "citation": self.citation}


@dataclass
class Harvest:
    comments: list[DocNote] = field(default_factory=list)
    rules: list[CandidateRule] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    copybooks: list[str] = field(default_factory=list)
    bms_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "comments": [c.to_dict() for c in self.comments],
            "rules": [r.to_dict() for r in self.rules],
            "methods": self.methods,
            "paragraphs": self.paragraphs,
            "copybooks": self.copybooks,
            "bms_fields": self.bms_fields,
        }


def harvest_for_elements(
    snapshot: ArchSnapshot,
    elements: list[ArchElement],
    repo: Path,
    *,
    max_comments: int = 12,
    max_rules: int = 20,
) -> Harvest:
    h = Harvest()
    seen_c: set[str] = set()
    seen_r: set[str] = set()
    for el in elements:
        if is_code_level(el):
            if (el.metadata or {}).get("kind") == "paragraph":
                h.paragraphs.append(el.name)
            if (el.metadata or {}).get("kind") == "bms_field":
                h.bms_fields.append(el.name)
            continue
        meta = el.metadata or {}
        for m in meta.get("methods") or []:
            if m not in h.methods:
                h.methods.append(str(m))
        for p in meta.get("paragraphs") or []:
            if p not in h.paragraphs:
                h.paragraphs.append(str(p))
        for c in meta.get("copies") or []:
            if c not in h.copybooks:
                h.copybooks.append(str(c))
        for fld in meta.get("fields") or []:
            if (meta.get("kind") == "bms_map") and fld not in h.bms_fields:
                h.bms_fields.append(str(fld))
        for remark in meta.get("remarks") or []:
            key = remark[:80]
            if key not in seen_c:
                seen_c.add(key)
                h.comments.append(
                    DocNote("remark", remark[:240], f"{el.file_path}#{el.name}")
                )
        path = repo / el.file_path if el.file_path else None
        if not path or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for note in _docs_from_text(text, el):
            key = note.text[:80]
            if key in seen_c:
                continue
            seen_c.add(key)
            h.comments.append(note)
            if len(h.comments) >= max_comments:
                break
        for rule in _rules_from_text(text, el):
            key = rule.text[:80]
            if key in seen_r:
                continue
            seen_r.add(key)
            h.rules.append(rule)
            if len(h.rules) >= max_rules:
                break
        if el.language == "cobol" and not meta.get("remarks"):
            for remark in cobol_remarks(text):
                key = remark[:80]
                if key in seen_c:
                    continue
                seen_c.add(key)
                h.comments.append(
                    DocNote("remark", remark[:240], f"{el.file_path}#{el.name}")
                )
    h.comments = h.comments[:max_comments]
    h.rules = h.rules[:max_rules]
    h.methods = h.methods[:40]
    h.paragraphs = h.paragraphs[:40]
    h.copybooks = h.copybooks[:20]
    h.bms_fields = h.bms_fields[:40]
    return h


def _docs_from_text(text: str, el: ArchElement) -> list[DocNote]:
    notes: list[DocNote] = []
    cite = f"{el.file_path}#{el.name}"
    if el.language == "java":
        for m in _JAVADOC.finditer(text):
            body = _clean_comment(m.group(1))
            if body:
                notes.append(DocNote("javadoc", body[:280], cite))
            if len(notes) >= 4:
                break
    elif el.language in ("typescript", "javascript"):
        for m in _JAVADOC.finditer(text):
            body = _clean_comment(m.group(1))
            if body:
                notes.append(DocNote("jsdoc", body[:280], cite))
        for line in _LINE_DOC.findall(text)[:6]:
            if line.strip():
                notes.append(DocNote("comment", line.strip()[:280], cite))
    elif el.language == "python":
        m = _PY_DOC.search(text)
        if m:
            body = m.group(1).strip("'\" \n")
            body = _clean_comment(body)
            if body:
                notes.append(DocNote("docstring", body[:280], cite))
    return notes


def _rules_from_text(text: str, el: ArchElement) -> list[CandidateRule]:
    cite = f"{el.file_path}#{el.name}"
    rules: list[CandidateRule] = []
    if el.language == "cobol":
        for m in _IF_COB.finditer(text):
            cond = " ".join(m.group(1).split())
            rules.append(CandidateRule("IF", cond[:160], cite))
        for m in _EVAL.finditer(text):
            rules.append(CandidateRule("EVALUATE", " ".join(m.group(1).split())[:160], cite))
        for m in _WHEN.finditer(text):
            w = " ".join(m.group(1).split())
            if w.upper() in ("OTHER", "TRUE", "FALSE"):
                continue
            rules.append(CandidateRule("WHEN", w[:160], cite))
    else:
        for m in _IF_JAVA.finditer(text):
            cond = " ".join(m.group(1).split())
            if any(x in cond for x in ("null", "isEmpty", "status", "valid", "amount", "==", "!=")):
                rules.append(CandidateRule("if", cond[:160], cite))
        if _VALID.search(text):
            rules.append(
                CandidateRule(
                    "validator",
                    "Bean validation / validate*() present",
                    cite,
                )
            )
    return rules[:12]


def _clean_comment(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*\*\s?", "", line).strip()
        if not line:
            continue
        low = line.lower()
        if any(h in low for h in _LICENSE):
            continue
        if line.startswith(("@param", "@return", "@throws", ":param", ":return")):
            continue
        lines.append(line)
        if len(lines) >= 4:
            break
    return " ".join(lines).strip()
