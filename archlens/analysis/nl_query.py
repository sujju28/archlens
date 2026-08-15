"""Natural language architecture query engine (3-tier resolution)."""

from __future__ import annotations

import re
from typing import Any

from archlens.models import ArchSnapshot

QUERY_PATTERNS: list[dict[str, Any]] = [
    {
        "patterns": [
            r"what depends on (\w+)",
            r"who uses (\w+)",
            r"dependents of (\w+)",
            r"who calls (\w+)",
        ],
        "mode": "upstream",
        "description": "upstream dependencies",
    },
    {
        "patterns": [
            r"what does (\w+) depend on",
            r"dependencies of (\w+)",
            r"what does (\w+) use",
            r"what does (\w+) call",
        ],
        "mode": "downstream",
        "description": "downstream dependencies",
    },
    {
        "patterns": [
            r"(?:show|list|find) (?:all )?([\w ]+?)s?(?:\s|$)",
            r"how many ([\w ]+?)s?\b",
        ],
        "mode": "stereotype",
        "description": "elements by stereotype",
    },
    {
        "patterns": [
            r"how is (?:the )?(?:project|system|architecture) structured",
            r"group by (?:stereotype|layer)",
            r"\boverview\b",
            r"\bsummary\b",
        ],
        "mode": "group_stereotype",
        "description": "stereotype counts",
    },
]

STEREOTYPE_ALIASES = {
    "controller": "Controller",
    "controllers": "Controller",
    "service": "Service",
    "services": "Service",
    "repository": "Repository",
    "repositories": "Repository",
    "repo": "Repository",
    "repos": "Repository",
    "component": "Component",
    "components": "Component",
    "ui": "UI Component",
    "ui component": "UI Component",
    "ui components": "UI Component",
    "middleware": "Middleware",
    "config": "Configuration",
    "configuration": "Configuration",
    "gateway": "Gateway",
    "gateways": "Gateway",
    "entity": "Entity",
    "entities": "Entity",
    "worker": "Worker",
    "workers": "Worker",
}


def run_nl_query(snapshot: ArchSnapshot, nl_query: str) -> dict[str, Any]:
    """
    Three-tier NL query resolution:
      1. Pattern matching → structured filter
      2. Entity extraction from element names
      3. Schema/agent fallback for complex questions
    """
    q = (nl_query or "").strip()
    if not q:
        return _all_elements(snapshot, "empty query → all elements")

    for pattern_def in QUERY_PATTERNS:
        for pattern in pattern_def["patterns"]:
            match = re.search(pattern, q.lower())
            if not match:
                continue
            mode = pattern_def["mode"]
            if mode == "group_stereotype":
                return _group_by_stereotype(snapshot, pattern_def["description"], "tier1")
            if mode == "stereotype":
                token = match.group(1).strip()
                stereo = _normalize_stereotype(token)
                # Only accept tier-1 stereotype hits for known taxonomy aliases
                if stereo and token.strip().lower() in STEREOTYPE_ALIASES:
                    results = [
                        _el_dict(e)
                        for e in snapshot.elements
                        if e.stereotype.lower() == stereo.lower()
                    ]
                    return {
                        "tier": "tier1",
                        "query_type": pattern_def["description"],
                        "matched_pattern": pattern,
                        "stereotype": stereo,
                        "result_count": len(results),
                        "results": results,
                    }
                continue
            if mode in ("upstream", "downstream"):
                element = match.group(1)
                results = _deps(snapshot, element, mode)
                return {
                    "tier": "tier1",
                    "query_type": pattern_def["description"],
                    "matched_pattern": pattern,
                    "element": element,
                    "direction": mode,
                    "result_count": len(results),
                    "results": results,
                }

    entities = _extract_entities(snapshot, q)
    if entities:
        if re.search(r"depend|uses|calls|import", q.lower()):
            direction = "upstream"
            if re.search(r"what does|dependencies of|depends on what", q.lower()):
                direction = "downstream"
            results: list[dict[str, Any]] = []
            for ent in entities[:3]:
                results.extend(_deps(snapshot, ent, direction))
            seen: set[tuple] = set()
            unique = []
            for r in results:
                key = (r.get("name"), r.get("direction"), r.get("rel_type"))
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            return {
                "tier": "tier2",
                "query_type": "entity dependency lookup",
                "entities": entities,
                "result_count": len(unique),
                "results": unique,
            }

        matched = [
            _el_dict(e)
            for e in snapshot.elements
            if e.name.lower() in {x.lower() for x in entities}
            or any(x.lower() in e.id.lower() for x in entities)
        ]
        return {
            "tier": "tier2",
            "query_type": "entity name match",
            "entities": entities,
            "result_count": len(matched),
            "results": matched,
        }

    return {
        "tier": "tier3",
        "query_type": "agent_fallback",
        "error": "Could not parse query with pattern/entity matching. Use SQL or structured filters.",
        "hint": (
            "Try: stereotype filter, element+direction, or phrases like "
            "'what depends on UserService', 'list all controllers'."
        ),
        "available_tables": ["elements", "relationships", "snapshots", "change_history"],
        "snapshot_id": snapshot.snapshot_id,
        "schema": {
            "elements": ["id", "name", "stereotype", "language", "file_path", "annotations"],
            "relationships": ["source_id", "target_id", "rel_type", "description"],
        },
        "sample_elements": [_el_dict(e) for e in snapshot.elements[:10]],
        "result_count": 0,
        "results": [],
    }


def structured_query(
    snapshot: ArchSnapshot,
    *,
    stereotype: str | None = None,
    element: str | None = None,
    direction: str = "both",
    group_by: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Structured + optional NL entry point used by CLI and MCP."""
    if query and not stereotype and not element and not group_by:
        return run_nl_query(snapshot, query)
    if group_by in ("stereotype", "layer"):
        return _group_by_stereotype(snapshot, "stereotype counts", "structured")
    if stereotype:
        results = [
            _el_dict(e)
            for e in snapshot.elements
            if e.stereotype.lower() == stereotype.lower()
        ]
        return {
            "tier": "structured",
            "query_type": "stereotype filter",
            "result_count": len(results),
            "results": results,
        }
    if element:
        results = _deps(snapshot, element, direction)
        return {
            "tier": "structured",
            "query_type": f"{direction} dependencies",
            "element": element,
            "result_count": len(results),
            "results": results,
        }
    return _all_elements(snapshot, "all elements")


def _normalize_stereotype(token: str) -> str | None:
    key = token.strip().lower()
    if key in STEREOTYPE_ALIASES:
        return STEREOTYPE_ALIASES[key]
    if re.fullmatch(r"[a-zA-Z][\w\s-]{0,40}", token.strip()):
        return token.strip().title()
    return None


def _extract_entities(snapshot: ArchSnapshot, query: str) -> list[str]:
    names = sorted({e.name for e in snapshot.elements}, key=len, reverse=True)
    found: list[str] = []
    q_lower = query.lower()
    for name in names:
        if name.lower() in q_lower:
            found.append(name)
    for token in re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b", query):
        for e in snapshot.elements:
            if e.name.lower() == token.lower() and e.name not in found:
                found.append(e.name)
    return found


def _deps(snapshot: ArchSnapshot, element: str, direction: str) -> list[dict[str, Any]]:
    by_id = {e.id: e for e in snapshot.elements}
    target_ids = {
        e.id
        for e in snapshot.elements
        if e.name.lower() == element.lower() or element.lower() in e.id.lower()
    }
    results: list[dict[str, Any]] = []
    if direction in ("upstream", "both"):
        for r in snapshot.relationships:
            if r.target_id in target_ids or element.lower() in r.target_id.lower():
                src = by_id.get(r.source_id)
                if src:
                    results.append({**_el_dict(src), "rel_type": r.rel_type, "direction": "upstream"})
    if direction in ("downstream", "both"):
        for r in snapshot.relationships:
            if r.source_id in target_ids or element.lower() in r.source_id.lower():
                tgt = by_id.get(r.target_id)
                if tgt:
                    results.append({**_el_dict(tgt), "rel_type": r.rel_type, "direction": "downstream"})
    return results


def _group_by_stereotype(snapshot: ArchSnapshot, query_type: str, tier: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for e in snapshot.elements:
        counts[e.stereotype] = counts.get(e.stereotype, 0) + 1
    results = [
        {"stereotype": k, "count": v}
        for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    return {
        "tier": tier,
        "query_type": query_type,
        "result_count": len(results),
        "results": results,
    }


def _all_elements(snapshot: ArchSnapshot, query_type: str) -> dict[str, Any]:
    results = [_el_dict(e) for e in snapshot.elements]
    return {
        "tier": "structured",
        "query_type": query_type,
        "result_count": len(results),
        "results": results,
    }


def _el_dict(e) -> dict[str, Any]:
    return {
        "name": e.name,
        "stereotype": e.stereotype,
        "language": e.language,
        "file_path": e.file_path,
        "id": e.id,
    }
