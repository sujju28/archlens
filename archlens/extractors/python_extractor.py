"""Python / FastAPI / Flask extractor using tree-sitter with ast fallback."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

from archlens.extractors.base import (
    PYTHON_ROUTE_METHODS,
    PYTHON_STEREOTYPE_MAP,
    BaseExtractor,
)
from archlens.extractors.entity_metadata import parse_entity_metadata
from archlens.extractors.member_list import python_methods
from archlens.models import ArchElement, ArchRelationship, RelType


class PythonExtractor(BaseExtractor):
    language = "python"

    def __init__(self, config=None, repo_root: Path | None = None):
        super().__init__(config, repo_root)
        self._language = Language(tspython.language())
        self._parser = Parser(self._language)

    def supported_extensions(self) -> set[str]:
        return {".py"}

    def extract_elements(self, file_path: Path) -> list[ArchElement]:
        source = file_path.read_bytes()
        text = source.decode("utf-8", errors="replace")
        try:
            tree = self._parser.parse(source)
            elements = self._extract_via_tree_sitter(tree.root_node, source, text, file_path)
            if elements:
                return elements
        except Exception:
            pass
        return self._extract_via_ast(text, file_path)

    def extract_relationships(
        self, file_path: Path, elements: dict[str, ArchElement]
    ) -> list[ArchRelationship]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        rels: list[ArchRelationship] = []
        rel_path = self.relative_path(file_path)
        file_elements = [e for e in elements.values() if e.file_path == rel_path]

        # Inheritance
        for el in file_elements:
            if el.extends:
                target = self._resolve_name(el.extends, elements)
                if target:
                    rels.append(
                        ArchRelationship(
                            source_id=el.id,
                            target_id=target,
                            rel_type=RelType.INHERITS.value,
                            description=f"extends {el.extends}",
                        )
                    )

        # Imports
        for m in re.finditer(
            r"from\s+([\w.]+)\s+import\s+(.+)",
            text,
        ):
            module, names = m.groups()
            for part in names.split(","):
                part = part.strip().split(" as ")[0].strip()
                if not part or part == "*":
                    continue
                target = self._resolve_name(part, elements)
                for el in file_elements:
                    if target and target != el.id:
                        rels.append(
                            ArchRelationship(
                                source_id=el.id,
                                target_id=target,
                                rel_type=RelType.IMPORTS.value,
                                description=f"from {module} import {part}",
                            )
                        )

        # Type hints / constructor injection heuristics
        for el in file_elements:
            # def __init__(self, svc: UserService)
            init = re.search(
                rf"class\s+{re.escape(el.name)}\b[\s\S]*?def\s+__init__\s*\(([^)]*)\)",
                text,
            )
            if init:
                for pm in re.finditer(r"(\w+)\s*:\s*([A-Z]\w+)", init.group(1)):
                    type_name = pm.group(2)
                    target = self._resolve_name(type_name, elements)
                    if target:
                        rels.append(
                            ArchRelationship(
                                source_id=el.id,
                                target_id=target,
                                rel_type=RelType.INJECTS.value,
                                description=f"depends on {type_name}",
                            )
                        )

        # Route relationships: FastAPI route handlers are Controllers
        for el in file_elements:
            if el.stereotype == "Controller":
                # Look for Depends(SomeService)
                for m in re.finditer(r"Depends\((\w+)\)", text):
                    target = self._resolve_name(m.group(1), elements)
                    if target:
                        rels.append(
                            ArchRelationship(
                                source_id=el.id,
                                target_id=target,
                                rel_type=RelType.INJECTS.value,
                                description=f"Depends({m.group(1)})",
                                technology="FastAPI",
                            )
                        )
        return rels

    def _extract_via_tree_sitter(
        self, root, source: bytes, text: str, file_path: Path
    ) -> list[ArchElement]:
        elements: list[ArchElement] = []
        for node in self._walk(root):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if not name_node:
                    continue
                name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
                decorators = self._preceding_decorators(node, source)
                extends = self._superclasses(node, source)
                stereotype = self.resolve_element_stereotype(
                    name=name,
                    file_path=file_path,
                    annotations=decorators,
                    extends=extends[0] if extends else None,
                    implements=extends[1:] if len(extends) > 1 else [],
                    builtin_map=PYTHON_STEREOTYPE_MAP,
                )
                class_text = source[node.start_byte : node.end_byte].decode(
                    "utf-8", errors="replace"
                )
                metadata: dict = {}
                if (
                    stereotype == "Entity"
                    or "dataclass" in decorators
                    or any("BaseModel" in d for d in decorators)
                    or "__tablename__" in class_text
                    or name.endswith(("Entity", "Model"))
                ):
                    # SQLAlchemy / dataclass / pydantic → Entity for data model
                    if stereotype in ("Component", "Unknown", "Entity") or name.endswith(
                        ("Entity", "Model")
                    ):
                        if "__tablename__" in class_text or "Column(" in class_text:
                            stereotype = "Entity"
                        elif "dataclass" in decorators or any(
                            "BaseModel" in d for d in decorators
                        ):
                            stereotype = "Entity"
                    if stereotype == "Entity":
                        metadata = parse_entity_metadata(
                            name, class_text, decorators, language="python"
                        )
                methods = python_methods(class_text)
                if methods:
                    metadata = dict(metadata)
                    metadata["methods"] = methods
                elements.append(
                    ArchElement(
                        id=self.make_id(name, file_path),
                        name=name,
                        stereotype=stereotype,
                        language="python",
                        file_path=self.relative_path(file_path),
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        annotations=decorators,
                        extends=extends[0] if extends else None,
                        implements=extends[1:] if len(extends) > 1 else [],
                        metadata=metadata,
                    )
                )
            elif node.type == "decorated_definition":
                # Route handlers etc.
                el = self._decorated_function(node, source, file_path)
                if el:
                    elements.append(el)
        return elements

    def _decorated_function(self, node, source: bytes, file_path: Path) -> ArchElement | None:
        decorators = []
        is_route = False
        for child in node.children:
            if child.type == "decorator":
                text = source[child.start_byte : child.end_byte].decode("utf-8")
                decorators.append(text.lstrip("@"))
                # @app.get / @router.post
                m = re.search(r"(\w+)\.(\w+)\s*\(", text)
                if m and m.group(2).lower() in PYTHON_ROUTE_METHODS:
                    is_route = True
                    decorators.append(m.group(2))
                m2 = re.search(r"@(\w+)\b", text)
                if m2:
                    decorators.append(m2.group(1))

        func = None
        for child in node.children:
            if child.type == "function_definition":
                func = child
                break
        if not func:
            return None
        name_node = func.child_by_field_name("name")
        if not name_node:
            return None
        name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
        if name.startswith("_") and not is_route:
            return None

        if is_route:
            stereotype = "Controller"
        else:
            stereotype = self.resolve_element_stereotype(
                name=name,
                file_path=file_path,
                annotations=[d.split("(")[0].split(".")[-1] for d in decorators],
                builtin_map=PYTHON_STEREOTYPE_MAP,
            )
            if stereotype == "Component" and not decorators:
                return None

        return ArchElement(
            id=self.make_id(name, file_path),
            name=name,
            stereotype=stereotype,
            language="python",
            file_path=self.relative_path(file_path),
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            annotations=list(dict.fromkeys(decorators)),
        )

    def _extract_via_ast(self, text: str, file_path: Path) -> list[ArchElement]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        elements: list[ArchElement] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                decorators = [self._decorator_name(d) for d in node.decorator_list]
                decorators = [d for d in decorators if d]
                bases = [self._expr_name(b) for b in node.bases]
                bases = [b for b in bases if b]
                stereotype = self.resolve_element_stereotype(
                    name=node.name,
                    file_path=file_path,
                    annotations=decorators,
                    extends=bases[0] if bases else None,
                    implements=bases[1:],
                    builtin_map=PYTHON_STEREOTYPE_MAP,
                )
                # Reconstruct class source slice by line range
                lines = text.splitlines()
                start = (getattr(node, "lineno", 1) or 1) - 1
                end = getattr(node, "end_lineno", None) or (start + 1)
                class_text = "\n".join(lines[start:end])
                metadata: dict = {}
                if (
                    stereotype == "Entity"
                    or "dataclass" in decorators
                    or any("BaseModel" in (d or "") for d in decorators)
                    or "__tablename__" in class_text
                    or node.name.endswith(("Entity", "Model"))
                ):
                    if "__tablename__" in class_text or "Column(" in class_text:
                        stereotype = "Entity"
                    elif "dataclass" in decorators or any(
                        "BaseModel" in (d or "") for d in decorators
                    ):
                        stereotype = "Entity"
                    if stereotype == "Entity":
                        metadata = parse_entity_metadata(
                            node.name, class_text, decorators, language="python"
                        )
                methods = python_methods(class_text)
                if methods:
                    metadata = dict(metadata)
                    metadata["methods"] = methods
                elements.append(
                    ArchElement(
                        id=self.make_id(node.name, file_path),
                        name=node.name,
                        stereotype=stereotype,
                        language="python",
                        file_path=self.relative_path(file_path),
                        line_start=getattr(node, "lineno", None),
                        line_end=getattr(node, "end_lineno", None),
                        annotations=decorators,
                        extends=bases[0] if bases else None,
                        implements=bases[1:],
                        metadata=metadata,
                    )
                )
            elif isinstance(node, ast.FunctionDef):
                decorators = [self._decorator_name(d) for d in node.decorator_list]
                decorators = [d for d in decorators if d]
                is_route = any(
                    any(m in d.lower() for m in PYTHON_ROUTE_METHODS)
                    for d in decorators
                )
                if not decorators and not is_route:
                    continue
                if is_route:
                    stereotype = "Controller"
                else:
                    stereotype = self.resolve_element_stereotype(
                        name=node.name,
                        file_path=file_path,
                        annotations=[d.split(".")[-1] for d in decorators],
                        builtin_map=PYTHON_STEREOTYPE_MAP,
                    )
                elements.append(
                    ArchElement(
                        id=self.make_id(node.name, file_path),
                        name=node.name,
                        stereotype=stereotype,
                        language="python",
                        file_path=self.relative_path(file_path),
                        line_start=getattr(node, "lineno", None),
                        line_end=getattr(node, "end_lineno", None),
                        annotations=decorators,
                    )
                )
        return elements

    def _preceding_decorators(self, class_node, source: bytes) -> list[str]:
        # In tree-sitter Python, decorators wrap via decorated_definition parent
        parent = class_node.parent
        if parent and parent.type == "decorated_definition":
            return self._decorator_list(parent, source)
        return []

    def _decorator_list(self, node, source: bytes) -> list[str]:
        out = []
        for child in node.children:
            if child.type == "decorator":
                text = source[child.start_byte : child.end_byte].decode("utf-8").lstrip("@")
                out.append(text.split("(")[0].strip())
        return out

    def _superclasses(self, class_node, source: bytes) -> list[str]:
        args = class_node.child_by_field_name("superclasses")
        if not args:
            return []
        text = source[args.start_byte : args.end_byte].decode("utf-8").strip("()")
        return [p.strip() for p in text.split(",") if p.strip()]

    def _decorator_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._decorator_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        if isinstance(node, ast.Call):
            return self._decorator_name(node.func)
        return None

    def _expr_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._expr_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def _resolve_name(self, name: str, elements: dict[str, ArchElement]) -> str | None:
        if name in elements:
            return name
        for eid, el in elements.items():
            if el.name == name or eid.endswith(f".{name}"):
                return eid
        return None

    def _walk(self, node):
        yield node
        for child in node.children:
            yield from self._walk(child)
