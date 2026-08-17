"""TypeScript / React / NestJS extractor using tree-sitter."""

from __future__ import annotations

import re
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_typescript as tstypescript

from archlens.extractors.base import (
    TS_STEREOTYPE_MAP,
    BaseExtractor,
)
from archlens.extractors.entity_metadata import parse_entity_metadata
from archlens.models import ArchElement, ArchRelationship, RelType


class TypeScriptExtractor(BaseExtractor):
    language = "typescript"

    def __init__(self, config=None, repo_root: Path | None = None):
        super().__init__(config, repo_root)
        # Prefer TSX so JSX is supported
        try:
            self._language = Language(tstypescript.language_tsx())
        except Exception:
            self._language = Language(tstypescript.language_typescript())
        self._parser = Parser(self._language)

    def supported_extensions(self) -> set[str]:
        return {".ts", ".tsx", ".jsx", ".js"}

    def extract_elements(self, file_path: Path) -> list[ArchElement]:
        source = file_path.read_bytes()
        tree = self._parser.parse(source)
        text = source.decode("utf-8", errors="replace")
        elements: list[ArchElement] = []

        elements.extend(self._extract_classes(tree.root_node, source, file_path))
        elements.extend(self._extract_react_components(tree.root_node, source, text, file_path))

        # Deduplicate by id
        seen: set[str] = set()
        unique = []
        for el in elements:
            if el.id not in seen:
                seen.add(el.id)
                unique.append(el)
        return unique

    def extract_relationships(
        self, file_path: Path, elements: dict[str, ArchElement]
    ) -> list[ArchRelationship]:
        source = file_path.read_bytes()
        text = source.decode("utf-8", errors="replace")
        rels: list[ArchRelationship] = []
        rel_path = self.relative_path(file_path)
        file_elements = [e for e in elements.values() if e.file_path == rel_path]

        # Imports
        for m in re.finditer(
            r"import\s+(?:type\s+)?(?:\{([^}]+)\}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]",
            text,
        ):
            named, default, _source = m.groups()
            names = []
            if default:
                names.append(default)
            if named:
                for part in named.split(","):
                    part = part.strip()
                    if not part or part.startswith("type "):
                        continue
                    names.append(part.split(" as ")[0].strip())
            for name in names:
                target = self._resolve_name(name, elements)
                for el in file_elements:
                    if target and target != el.id:
                        rels.append(
                            ArchRelationship(
                                source_id=el.id,
                                target_id=target,
                                rel_type=RelType.IMPORTS.value,
                                description=f"imports {name}",
                            )
                        )

        # Constructor DI (NestJS)
        for el in file_elements:
            ctor = re.search(
                rf"constructor\s*\(([^)]*)\)",
                text,
            )
            if ctor and el.name in text[max(0, ctor.start() - 200) : ctor.start() + 1]:
                for pm in re.finditer(r"(?:private|protected|public|readonly)?\s*(?:readonly\s+)?(\w+)\s*:\s*(\w+)", ctor.group(1)):
                    type_name = pm.group(2)
                    target = self._resolve_name(type_name, elements)
                    if target:
                        rels.append(
                            ArchRelationship(
                                source_id=el.id,
                                target_id=target,
                                rel_type=RelType.INJECTS.value,
                                description=f"injects {type_name}",
                                technology="NestJS DI",
                            )
                        )

        # JSX composition
        for m in re.finditer(r"<([A-Z]\w+)\b", text):
            comp = m.group(1)
            target = self._resolve_name(comp, elements)
            for el in file_elements:
                if target and target != el.id and el.stereotype == "UI Component":
                    rels.append(
                        ArchRelationship(
                            source_id=el.id,
                            target_id=target,
                            rel_type=RelType.COMPOSES.value,
                            description=f"renders <{comp}>",
                        )
                    )

        # extends
        for el in file_elements:
            if el.extends:
                target = self._resolve_name(el.extends.split(".")[-1], elements)
                if target:
                    rels.append(
                        ArchRelationship(
                            source_id=el.id,
                            target_id=target,
                            rel_type=RelType.INHERITS.value,
                            description=f"extends {el.extends}",
                        )
                    )
        return rels

    def _extract_classes(self, root, source: bytes, file_path: Path) -> list[ArchElement]:
        elements = []
        for node in self._walk(root):
            if node.type != "class_declaration":
                continue
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
            decorators = self._decorators(node, source)
            extends = self._heritage(node, source)

            stereotype = self.resolve_element_stereotype(
                name=name,
                file_path=file_path,
                annotations=decorators,
                extends=extends,
                builtin_map=TS_STEREOTYPE_MAP,
            )
            # Include preceding decorators — @Entity('users') sits outside class node
            start = node.start_byte
            if node.parent:
                start = min(start, node.parent.start_byte)
            class_text = source[start : node.end_byte].decode("utf-8", errors="replace")
            metadata: dict = {}
            if stereotype == "Entity" or "Entity" in decorators or name.endswith(
                ("Entity", "Model")
            ):
                stereotype = "Entity"
                metadata = parse_entity_metadata(
                    name, class_text, decorators, language="typescript"
                )
            elements.append(
                ArchElement(
                    id=self.make_id(name, file_path),
                    name=name,
                    stereotype=stereotype,
                    language="typescript",
                    file_path=self.relative_path(file_path),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    annotations=decorators,
                    extends=extends,
                    metadata=metadata,
                )
            )
        return elements

    def _extract_react_components(
        self, root, source: bytes, text: str, file_path: Path
    ) -> list[ArchElement]:
        """Detect React functional components via heuristic: exported fn returning JSX."""
        elements = []
        # function Component() { return <... }
        for m in re.finditer(
            r"(?:export\s+(?:default\s+)?)?(?:function|const)\s+([A-Z]\w*)\s*"
            r"(?:=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?=>|(\([^)]*\)|\(\)))",
            text,
        ):
            name = m.group(1)
            # Look ahead for JSX return
            window = text[m.start() : m.start() + 800]
            if not re.search(r"return\s*\(?\s*<[A-Za-z]|=>\s*\(?\s*<[A-Za-z]|<[A-Z]", window):
                continue
            elements.append(
                ArchElement(
                    id=self.make_id(name, file_path),
                    name=name,
                    stereotype="UI Component",
                    language="typescript",
                    file_path=self.relative_path(file_path),
                    line_start=text[: m.start()].count("\n") + 1,
                    annotations=["ReactFC"],
                )
            )

        # Also walk AST for function_declaration returning jsx
        for node in self._walk(root):
            if node.type not in ("function_declaration", "arrow_function"):
                continue
            name_node = node.child_by_field_name("name") if node.type == "function_declaration" else None
            name = None
            if name_node:
                name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
            if not name or not name[0].isupper():
                continue
            snippet = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
            if "<" not in snippet:
                continue
            eid = self.make_id(name, file_path)
            if any(e.id == eid for e in elements):
                continue
            elements.append(
                ArchElement(
                    id=eid,
                    name=name,
                    stereotype="UI Component",
                    language="typescript",
                    file_path=self.relative_path(file_path),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    annotations=["ReactFC"],
                )
            )
        return elements

    def _decorators(self, class_node, source: bytes) -> list[str]:
        decorators = []
        # Decorators may be siblings on export_statement / ambient_declaration
        nodes = [class_node]
        if class_node.parent:
            nodes.append(class_node.parent)
        for node in nodes:
            for child in node.children:
                if child.type == "decorator":
                    text = source[child.start_byte : child.end_byte].decode("utf-8")
                    m = re.search(r"@(\w+)", text)
                    if m:
                        decorators.append(m.group(1))
        return list(dict.fromkeys(decorators))

    def _heritage(self, class_node, source: bytes) -> str | None:
        for child in class_node.children:
            if child.type == "class_heritage":
                text = source[child.start_byte : child.end_byte].decode("utf-8")
                m = re.search(r"extends\s+([\w.]+)", text)
                if m:
                    return m.group(1)
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
