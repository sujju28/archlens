"""Java / Spring Boot extractor using tree-sitter."""

from __future__ import annotations

import re
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_java as tsjava

from archlens.extractors.base import (
    JAVA_STEREOTYPE_MAP,
    BaseExtractor,
)
from archlens.extractors.entity_metadata import parse_entity_metadata
from archlens.models import ArchElement, ArchRelationship, RelType


class JavaExtractor(BaseExtractor):
    language = "java"

    def __init__(self, config=None, repo_root: Path | None = None):
        super().__init__(config, repo_root)
        self._language = Language(tsjava.language())
        self._parser = Parser(self._language)

    def supported_extensions(self) -> set[str]:
        return {".java"}

    def _parse(self, source: bytes):
        return self._parser.parse(source)

    def extract_elements(self, file_path: Path) -> list[ArchElement]:
        source = file_path.read_bytes()
        tree = self._parse(source)
        text = source.decode("utf-8", errors="replace")
        package = self._find_package(text)
        elements: list[ArchElement] = []

        types = self._extract_types(tree.root_node, source, package, file_path, text)
        if types:
            elements.extend(types)
        else:
            elements.extend(self._regex_fallback(text, package, file_path))
        return elements

    def extract_relationships(
        self, file_path: Path, elements: dict[str, ArchElement]
    ) -> list[ArchRelationship]:
        source = file_path.read_bytes()
        text = source.decode("utf-8", errors="replace")
        rels: list[ArchRelationship] = []
        file_elements = [e for e in elements.values() if e.file_path == self.relative_path(file_path)]

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
            for iface in el.implements:
                target = self._resolve_name(iface, elements)
                if target:
                    rels.append(
                        ArchRelationship(
                            source_id=el.id,
                            target_id=target,
                            rel_type=RelType.IMPLEMENTS.value,
                            description=f"implements {iface}",
                        )
                    )

        for match in re.finditer(
            r"@(?:Autowired|Inject|Resource)\s+(?:private|protected|public)?\s*"
            r"(?:final\s+)?(\w+)\s+(\w+)\s*;",
            text,
        ):
            type_name = match.group(1)
            for el in file_elements:
                target = self._resolve_name(type_name, elements)
                if target:
                    rels.append(
                        ArchRelationship(
                            source_id=el.id,
                            target_id=target,
                            rel_type=RelType.INJECTS.value,
                            description=f"injects {type_name}",
                            technology="Spring DI",
                        )
                    )

        for el in file_elements:
            ctor = re.search(
                rf"(?:public|protected)\s+{re.escape(el.name)}\s*\(([^)]*)\)",
                text,
            )
            if ctor:
                params = ctor.group(1)
                for pm in re.finditer(r"(?:final\s+)?(\w+)\s+\w+", params):
                    type_name = pm.group(1)
                    if type_name in ("String", "int", "long", "boolean", "Integer", "Long", "Boolean"):
                        continue
                    target = self._resolve_name(type_name, elements)
                    if target:
                        rels.append(
                            ArchRelationship(
                                source_id=el.id,
                                target_id=target,
                                rel_type=RelType.INJECTS.value,
                                description=f"constructor injects {type_name}",
                                technology="Spring DI",
                            )
                        )

        for imp in re.finditer(r"import\s+([\w.]+)\s*;", text):
            import_path = imp.group(1)
            short = import_path.split(".")[-1]
            target = self._resolve_name(short, elements) or self._resolve_name(import_path, elements)
            for el in file_elements:
                if target and target != el.id:
                    rels.append(
                        ArchRelationship(
                            source_id=el.id,
                            target_id=target,
                            rel_type=RelType.IMPORTS.value,
                            description=f"imports {import_path}",
                        )
                    )
        return rels

    def _extract_types(
        self, root, source: bytes, package: str | None, file_path: Path, text: str
    ) -> list[ArchElement]:
        elements = []
        for node in self._walk(root):
            if node.type not in ("class_declaration", "interface_declaration"):
                continue
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
            annotations = self._type_annotations(node, source)
            extends = None
            implements: list[str] = []

            if node.type == "class_declaration":
                sc = node.child_by_field_name("superclass")
                if sc:
                    extends = (
                        source[sc.start_byte : sc.end_byte]
                        .decode("utf-8")
                        .replace("extends", "")
                        .strip()
                    )
                ifaces = node.child_by_field_name("interfaces")
                if ifaces:
                    raw = source[ifaces.start_byte : ifaces.end_byte].decode("utf-8")
                    implements = [
                        x.strip()
                        for x in re.sub(r"^implements\s+", "", raw).split(",")
                        if x.strip()
                    ]
            else:
                # interface extends OtherIface, ...
                ifaces = node.child_by_field_name("interfaces") or node.child_by_field_name(
                    "extends"
                )
                # tree-sitter-java: interfaces field on interface_declaration
                for child in node.children:
                    if child.type == "extends_interfaces":
                        raw = source[child.start_byte : child.end_byte].decode("utf-8")
                        implements = [
                            x.strip()
                            for x in re.sub(r"^extends\s+", "", raw).split(",")
                            if x.strip()
                        ]
                        break

            stereotype = self.resolve_element_stereotype(
                name=name,
                file_path=file_path,
                annotations=annotations,
                extends=extends,
                implements=implements,
                builtin_map=JAVA_STEREOTYPE_MAP,
            )

            # Slice of this type's source for metadata (cheap: use whole file)
            metadata = {}
            if stereotype == "Entity" or re.match(r"^[IX]_", name):
                stereotype = "Entity"
                metadata = parse_entity_metadata(name, text, annotations, language="java")

            eid = f"{package}.{name}" if package else self.make_id(name, file_path)
            elements.append(
                ArchElement(
                    id=eid,
                    name=name,
                    stereotype=stereotype,
                    language="java",
                    file_path=self.relative_path(file_path),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    annotations=annotations,
                    extends=extends,
                    implements=implements,
                    metadata=metadata,
                )
            )
        return elements

    def _type_annotations(self, type_node, source: bytes) -> list[str]:
        annotations = []
        for child in type_node.children:
            if child.type == "modifiers":
                for m in child.children:
                    if m.type in ("marker_annotation", "annotation"):
                        name_node = m.child_by_field_name("name")
                        if name_node:
                            annotations.append(
                                source[name_node.start_byte : name_node.end_byte].decode("utf-8")
                            )
        return annotations

    def _regex_fallback(self, text: str, package: str | None, file_path: Path) -> list[ArchElement]:
        elements = []
        patterns = [
            (
                r"((?:@\w+(?:\([^)]*\))?\s*)*)"
                r"(?:public\s+|protected\s+|private\s+)?(?:abstract\s+|final\s+)?class\s+(\w+)"
                r"(?:\s+extends\s+([\w.]+))?(?:\s+implements\s+([\w.\s,]+))?",
                "class",
            ),
            (
                r"((?:@\w+(?:\([^)]*\))?\s*)*)"
                r"(?:public\s+|protected\s+|private\s+)?interface\s+(\w+)"
                r"(?:\s+extends\s+([\w.\s,]+))?",
                "interface",
            ),
        ]
        for pattern, kind in patterns:
            for m in re.finditer(pattern, text):
                if kind == "class":
                    ann_block, name, extends, implements_raw = m.groups()
                    implements = [x.strip() for x in (implements_raw or "").split(",") if x.strip()]
                else:
                    ann_block, name, extends_raw = m.groups()
                    extends = None
                    implements = [x.strip() for x in (extends_raw or "").split(",") if x.strip()]
                annotations = re.findall(r"@(\w+)", ann_block or "")
                stereotype = self.resolve_element_stereotype(
                    name=name,
                    file_path=file_path,
                    annotations=annotations,
                    extends=extends,
                    implements=implements,
                    builtin_map=JAVA_STEREOTYPE_MAP,
                )
                metadata = {}
                if stereotype == "Entity" or re.match(r"^[IX]_", name):
                    stereotype = "Entity"
                    metadata = parse_entity_metadata(name, text, annotations, language="java")
                eid = f"{package}.{name}" if package else self.make_id(name, file_path)
                elements.append(
                    ArchElement(
                        id=eid,
                        name=name,
                        stereotype=stereotype,
                        language="java",
                        file_path=self.relative_path(file_path),
                        line_start=text[: m.start()].count("\n") + 1,
                        annotations=annotations,
                        extends=extends,
                        implements=implements,
                        metadata=metadata,
                    )
                )
        return elements

    def _find_package(self, text: str) -> str | None:
        m = re.search(r"package\s+([\w.]+)\s*;", text)
        return m.group(1) if m else None

    def _resolve_name(self, name: str, elements: dict[str, ArchElement]) -> str | None:
        short = name.split(".")[-1]
        if name in elements:
            return name
        if short in elements:
            return short
        for eid, el in elements.items():
            if el.name == short or eid.endswith(f".{short}"):
                return eid
        return None

    def _walk(self, node):
        yield node
        for child in node.children:
            yield from self._walk(child)
