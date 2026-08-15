"""Link services via OpenAPI / HTTP contract matching."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from archlens.models import ArchRelationship


@dataclass
class ApiOperation:
    method: str
    path: str
    operation_id: str | None = None
    source_file: str | None = None
    service: str | None = None


@dataclass
class ApiCallSite:
    method: str
    path_or_url: str
    file_path: str
    element_hint: str | None = None
    service: str | None = None


@dataclass
class ContractLinkReport:
    operations: list[ApiOperation] = field(default_factory=list)
    call_sites: list[ApiCallSite] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[ArchRelationship] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "operations": [o.__dict__ for o in self.operations],
            "call_sites": [c.__dict__ for c in self.call_sites],
            "links": self.links,
            "relationships": [r.model_dump() for r in self.relationships],
            "link_count": len(self.links),
        }


OPENAPI_NAMES = {
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
    "api.yaml",
    "api.yml",
    "api.json",
}

HTTP_CALL_PATTERNS = [
    # fetch('/api/users')
    (re.compile(r"""fetch\(\s*[`'\"]([A-Za-z0-9_/:\-\{\}]+)[`'\"]""", re.I), "GET"),
    # axios.get('/users')
    (re.compile(r"""axios\.(get|post|put|patch|delete)\(\s*[`'\"]([A-Za-z0-9_/:\-\{\}]+)[`'\"]""", re.I), None),
    # httpx.get("http://...")
    (re.compile(r"""httpx\.(get|post|put|patch|delete)\(\s*[`'\"]([A-Za-z0-9_/:\-\{\}.]+)[`'\"]""", re.I), None),
    # requests.get(...)
    (re.compile(r"""requests\.(get|post|put|patch|delete)\(\s*[`'\"]([A-Za-z0-9_/:\-\{\}.]+)[`'\"]""", re.I), None),
    # RestTemplate / WebClient
    (re.compile(r"""(?:getForObject|postForObject|exchange)\(\s*[`'\"]([A-Za-z0-9_/:\-\{\}.]+)[`'\"]""", re.I), "GET"),
    (re.compile(r"""WebClient\.create\([^)]*\)\.[a-zA-Z]+\(\)\.[a-zA-Z]+\(\s*[`'\"]([A-Za-z0-9_/:\-\{\}.]+)[`'\"]""", re.I), "GET"),
    # @FeignClient path usage often in interfaces — MatchMapping style on client
    (re.compile(r"""@(Get|Post|Put|Patch|Delete)Mapping\(\s*[`'\"]([A-Za-z0-9_/:\-\{\}]+)[`'\"]""", re.I), None),
]


class OpenAPIContractLinker:
    def discover_specs(self, repo_path: Path | str) -> list[Path]:
        repo = Path(repo_path)
        found: list[Path] = []
        for path in repo.rglob("*"):
            if not path.is_file():
                continue
            if path.name.lower() in OPENAPI_NAMES or path.name.lower().endswith(".openapi.json"):
                if any(p in path.parts for p in ("node_modules", ".git", "dist", "build", ".venv")):
                    continue
                found.append(path)
        return found

    def parse_spec(self, path: Path, service: str | None = None) -> list[ApiOperation]:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            if path.suffix.lower() in (".yaml", ".yml"):
                data = yaml.safe_load(text)
            else:
                data = json.loads(text)
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        ops: list[ApiOperation] = []
        paths = data.get("paths") or {}
        for api_path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, body in methods.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                op_id = None
                if isinstance(body, dict):
                    op_id = body.get("operationId")
                ops.append(
                    ApiOperation(
                        method=method.upper(),
                        path=api_path,
                        operation_id=op_id,
                        source_file=str(path),
                        service=service or path.parent.name,
                    )
                )
        return ops

    def find_call_sites(self, repo_path: Path | str, service: str | None = None) -> list[ApiCallSite]:
        repo = Path(repo_path)
        sites: list[ApiCallSite] = []
        exts = {".java", ".ts", ".tsx", ".js", ".jsx", ".py"}
        for path in repo.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in exts:
                continue
            if any(p in path.parts for p in ("node_modules", ".git", "dist", "build", ".venv", "__pycache__")):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path)
            for pattern, default_method in HTTP_CALL_PATTERNS:
                for m in pattern.finditer(text):
                    if default_method is None and m.lastindex and m.lastindex >= 2:
                        method = m.group(1).upper()
                        url = m.group(2)
                        if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                            pass
                        else:
                            # Feign-style @GetMapping → group1 is Get
                            method = method.replace("MAPPING", "")
                            if len(method) <= 6:
                                method = method.upper()
                            url = m.group(2) if m.lastindex >= 2 else m.group(1)
                    elif default_method is None:
                        method = m.group(1).upper() if m.lastindex else "GET"
                        url = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
                    else:
                        method = default_method
                        url = m.group(1)
                    # Normalize Feign @GetMapping groups
                    if method.lower() in {"get", "post", "put", "patch", "delete"}:
                        method = method.upper()
                    elif m.re.pattern.startswith("@(Get"):
                        method = m.group(1).upper()
                        url = m.group(2)
                    sites.append(
                        ApiCallSite(
                            method=method,
                            path_or_url=url,
                            file_path=rel,
                            service=service or repo.name,
                        )
                    )
        return sites

    def link(
        self,
        operations: list[ApiOperation],
        call_sites: list[ApiCallSite],
    ) -> ContractLinkReport:
        links = []
        relationships: list[ArchRelationship] = []
        for call in call_sites:
            call_path = self._normalize_path(call.path_or_url)
            for op in operations:
                # Don't link a service to its own OpenAPI as a client dependency
                if call.service and op.service and call.service == op.service:
                    # Still allow if paths suggest external host
                    if not call.path_or_url.startswith("http"):
                        continue
                if call.method.upper() != op.method.upper():
                    continue
                if self._paths_match(call_path, self._normalize_path(op.path)):
                    link = {
                        "from_service": call.service,
                        "from_file": call.file_path,
                        "to_service": op.service,
                        "method": op.method,
                        "path": op.path,
                        "operation_id": op.operation_id,
                        "spec": op.source_file,
                    }
                    links.append(link)
                    relationships.append(
                        ArchRelationship(
                            source_id=f"service:{call.service or call.file_path}",
                            target_id=f"service:{op.service or 'api'}",
                            rel_type="routes_to",
                            description=f"{op.method} {op.path}",
                            technology="HTTP/OpenAPI",
                        )
                    )
        # Dedupe relationships
        seen = set()
        unique_rels = []
        for r in relationships:
            key = (r.source_id, r.target_id, r.rel_type, r.description)
            if key not in seen:
                seen.add(key)
                unique_rels.append(r)
        return ContractLinkReport(
            operations=operations,
            call_sites=call_sites,
            links=links,
            relationships=unique_rels,
        )

    def analyze_repos(self, repo_paths: list[Path | str]) -> ContractLinkReport:
        operations: list[ApiOperation] = []
        calls: list[ApiCallSite] = []
        for repo in repo_paths:
            repo = Path(repo)
            service = repo.name
            for spec in self.discover_specs(repo):
                operations.extend(self.parse_spec(spec, service=service))
            calls.extend(self.find_call_sites(repo, service=service))
        return self.link(operations, calls)

    def _normalize_path(self, path: str) -> str:
        # Strip scheme/host
        path = re.sub(r"^https?://[^/]+", "", path)
        if not path.startswith("/"):
            path = "/" + path
        # Drop query
        path = path.split("?", 1)[0]
        return path.rstrip("/") or "/"

    def _paths_match(self, call_path: str, op_path: str) -> bool:
        if call_path == op_path:
            return True
        # Convert OpenAPI {id} and :id to regex
        pattern = re.sub(r"\{[^}]+\}", r"[^/]+", op_path)
        pattern = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", r"[^/]+", pattern)
        pattern = "^" + pattern + "$"
        # Also allow call paths with template vars
        call_norm = re.sub(r"\{[^}]+\}", "X", call_path)
        call_norm = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "X", call_norm)
        op_as_x = re.sub(r"\{[^}]+\}", "X", op_path)
        if call_norm == op_as_x:
            return True
        return re.match(pattern, call_path) is not None
