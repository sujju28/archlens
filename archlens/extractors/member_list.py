"""Public method / member lists attached as element metadata (not C4 nodes)."""

from __future__ import annotations

import re

_JAVA_METHOD = re.compile(
    r"(?:public|protected)\s+(?:static\s+|final\s+|synchronized\s+)*"
    r"(?:<[^>]+>\s+)?[\w.<>,\[\]?]+\s+(\w+)\s*\(",
)
_PY_DEF = re.compile(r"^\s+def\s+(\w+)\s*\(", re.MULTILINE)


def java_public_methods(text: str, class_name: str, *, limit: int = 40) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for m in _JAVA_METHOD.finditer(text):
        name = m.group(1)
        if name == class_name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


def python_methods(class_text: str, *, limit: int = 40) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for m in _PY_DEF.finditer(class_text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names
