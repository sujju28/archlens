"""Stereotype resolution via multi-signal cascade.

Priority (highest → lowest):
  1. Annotation / decorator (built-in taxonomy + .archlens.yaml)
  2. Type / inheritance (e.g. JpaRepository, React.Component)
  3. Naming convention (UserServiceImpl, OrderController, …)
  4. Directory convention (services/, controllers/, …)
  5. Fallback → Component

`.archlens.yaml` is optional and additive — custom mappings override/extend
built-ins; they are never required for standard Spring/Nest/FastAPI/React.
"""

from __future__ import annotations

import re
from pathlib import Path

from archlens.config import ArchLensConfig

JAVA_STEREOTYPE_MAP = {
    "RestController": "Controller",
    "Controller": "Controller",
    "Service": "Service",
    "Repository": "Repository",
    "Entity": "Entity",
    "Component": "Component",
    "Configuration": "Configuration",
    "Bean": "Configuration",
    "FeignClient": "Gateway",
    "Aspect": "Middleware",
    "ControllerAdvice": "Middleware",
}

TS_STEREOTYPE_MAP = {
    "Controller": "Controller",
    "Injectable": "Service",
    "Entity": "Entity",
    "Component": "UI Component",
    "Module": "Configuration",
    "NgModule": "Configuration",
    "Middleware": "Middleware",
    "Guard": "Middleware",
    "Interceptor": "Middleware",
    "Pipe": "Component",
}

PYTHON_STEREOTYPE_MAP = {
    "dataclass": "Entity",
    "service": "Service",
    "repository": "Repository",
    "component": "Component",
    "route": "Controller",
    "router": "Controller",
}

PYTHON_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route"}

CONVENTION_DIRS = {
    "controllers": "Controller",
    "controller": "Controller",
    "services": "Service",
    "service": "Service",
    "repositories": "Repository",
    "repository": "Repository",
    "repos": "Repository",
    "models": "Entity",
    "entities": "Entity",
    "middleware": "Middleware",
    "adapters": "Gateway",
    "clients": "Gateway",
    "gateways": "Gateway",
    "config": "Configuration",
    "configs": "Configuration",
    "components": "UI Component",
}

# Suffix → stereotype (checked longest-first)
NAME_SUFFIXES: list[tuple[str, str]] = [
    ("ServiceImpl", "Service"),
    ("Controller", "Controller"),
    ("RestController", "Controller"),
    ("Repository", "Repository"),
    ("Repo", "Repository"),
    ("Service", "Service"),
    ("Gateway", "Gateway"),
    ("Client", "Gateway"),
    ("Middleware", "Middleware"),
    ("Interceptor", "Middleware"),
    ("Filter", "Middleware"),
    ("Config", "Configuration"),
    ("Configuration", "Configuration"),
    ("Entity", "Entity"),
    ("Model", "Entity"),
    ("Worker", "Worker"),
    ("Handler", "Controller"),
    ("Router", "Controller"),
    ("Component", "UI Component"),
]

# Adempiere / metasfresh persistent object interfaces & generated classes
_PO_NAME = re.compile(r"^[IX]_([A-Z][\w]*)$")

INHERITANCE_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(JpaRepository|CrudRepository|PagingAndSortingRepository|MongoRepository)\b"), "Repository"),
    (re.compile(r"\bRepository\b"), "Repository"),
    (re.compile(r"(React\.)?(Pure)?Component\b"), "UI Component"),
    (re.compile(r"\b(APIView|ViewSet|GenericAPIView)\b"), "Controller"),
    (re.compile(r"\b(BaseHTTPMiddleware|MiddlewareMixin)\b"), "Middleware"),
    (re.compile(r"\b(BaseModel|Model)\b"), "Entity"),
    (re.compile(r"\bPO\b"), "Entity"),  # Adempiere Persistent Object
    (re.compile(r"\bI_Persistent\b"), "Entity"),
]


def resolve_stereotype(
    *,
    language: str,
    name: str,
    file_path: str,
    annotations: list[str] | None = None,
    extends: str | None = None,
    implements: list[str] | None = None,
    config: ArchLensConfig | None = None,
    builtin_map: dict[str, str] | None = None,
) -> str:
    """Resolve stereotype using the documented multi-signal cascade."""
    annotations = annotations or []
    implements = implements or []
    config = config or ArchLensConfig()
    builtin_map = builtin_map or _builtin_map_for(language)

    # 1. Annotation / decorator (custom yaml first, then built-in)
    for ann in annotations:
        short = ann.split("(")[0].split(".")[-1].lstrip("@")
        custom = config.custom_stereotype_for(language, short)
        if custom:
            return custom
        if short in builtin_map:
            return builtin_map[short]
        if ann in builtin_map:
            return builtin_map[ann]

    # 2. Type / inheritance
    bases = [extends] if extends else []
    bases.extend(implements)
    for base in bases:
        if not base:
            continue
        for pattern, stereo in INHERITANCE_SIGNALS:
            if pattern.search(base):
                return stereo
        # Interface named *Repository
        if re.search(r"Repository$", base):
            return "Repository"
        # Implements I_C_Order / org.compiere.model.I_* → Entity
        short_base = base.split(".")[-1]
        if _PO_NAME.match(short_base) or short_base.startswith("I_"):
            return "Entity"

    # 3. Naming convention (includes I_/X_ table models)
    named = stereotype_from_name(name)
    if named:
        return named

    # 4. Directory convention (yaml convention overrides first)
    path_stereo = stereotype_from_path(file_path, config, language)
    if path_stereo:
        return path_stereo

    # 5. Fallback
    return "Component"


def stereotype_from_name(name: str) -> str | None:
    if _PO_NAME.match(name):
        return "Entity"
    for suffix, stereo in NAME_SUFFIXES:
        if name.endswith(suffix) and name != suffix:
            return stereo
    return None


def stereotype_from_annotations(
    annotations: list[str],
    language: str,
    mapping: dict[str, str],
    config: ArchLensConfig | None = None,
) -> str:
    """Legacy helper — prefer resolve_stereotype for full cascade."""
    result = resolve_stereotype(
        language=language,
        name="",
        file_path="",
        annotations=annotations,
        config=config,
        builtin_map=mapping,
    )
    # Without name/path, cascade falls through to Component; preserve Unknown
    # only when literally nothing matched annotations.
    if not annotations:
        return "Unknown"
    for ann in annotations:
        short = ann.split("(")[0].split(".")[-1].lstrip("@")
        if config and config.custom_stereotype_for(language, short):
            return result
        if short in mapping or ann in mapping:
            return result
    return "Unknown"


def stereotype_from_path(
    file_path: str,
    config: ArchLensConfig | None = None,
    language: str = "python",
) -> str | None:
    if config:
        custom = config.convention_stereotype(language, file_path)
        if custom:
            return custom
    parts = Path(file_path).parts
    for part in parts:
        lower = part.lower()
        if lower in CONVENTION_DIRS:
            return CONVENTION_DIRS[lower]
    return None


def _builtin_map_for(language: str) -> dict[str, str]:
    if language == "java":
        return JAVA_STEREOTYPE_MAP
    if language in ("typescript", "javascript"):
        return TS_STEREOTYPE_MAP
    return PYTHON_STEREOTYPE_MAP


def load_query_file(name: str) -> str:
    query_path = Path(__file__).resolve().parent.parent / "queries" / name
    return query_path.read_text(encoding="utf-8")
