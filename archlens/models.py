"""C4-compatible Pydantic data models for ArchLens."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class C4Level(str, Enum):
    CONTEXT = "Context"
    CONTAINER = "Container"
    COMPONENT = "Component"
    CODE = "Code"


class RelType(str, Enum):
    CALLS = "calls"
    INJECTS = "injects"
    INHERITS = "inherits"
    IMPORTS = "imports"
    ROUTES_TO = "routes_to"
    COMPOSES = "composes"
    IMPLEMENTS = "implements"
    REFERENCES = "references"  # data-model FK / association
    # Mainframe
    CICS_LINK = "cics_link"
    CICS_XCTL = "cics_xctl"
    CICS_START = "cics_start"
    COPIES = "copies"
    ACCESSES_TABLE = "accesses_table"
    WRITES_TABLE = "writes_table"
    READS_DATASET = "reads_dataset"
    WRITES_DATASET = "writes_dataset"
    EXECUTES = "executes"
    USES_MAP = "uses_map"
    SENDS_MQ = "sends_mq"
    RECEIVES_MQ = "receives_mq"


class Stereotype(str, Enum):
    CONTROLLER = "Controller"
    SERVICE = "Service"
    REPOSITORY = "Repository"
    COMPONENT = "Component"
    UI_COMPONENT = "UI Component"
    MIDDLEWARE = "Middleware"
    CONFIGURATION = "Configuration"
    GATEWAY = "Gateway"
    WORKER = "Worker"
    ENTITY = "Entity"
    BATCH_JOB = "Batch Job"
    SHARED_DATA = "Shared Data"
    UNKNOWN = "Unknown"


class ArchElement(BaseModel):
    """A component in the system (class, module, function)."""

    id: str
    name: str
    stereotype: str = Stereotype.UNKNOWN.value
    c4_level: str = C4Level.COMPONENT.value
    language: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    annotations: list[str] = Field(default_factory=list)
    extends: str | None = None
    implements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stereotype", mode="before")
    @classmethod
    def coerce_stereotype(cls, v: Any) -> str:
        if isinstance(v, Stereotype):
            return v.value
        return str(v) if v else Stereotype.UNKNOWN.value


class ArchRelationship(BaseModel):
    """A dependency between two elements."""

    source_id: str
    target_id: str
    rel_type: str
    description: str | None = None
    technology: str | None = None

    @field_validator("rel_type", mode="before")
    @classmethod
    def coerce_rel_type(cls, v: Any) -> str:
        if isinstance(v, RelType):
            return v.value
        return str(v)


class ArchSnapshot(BaseModel):
    """A point-in-time capture of the full architecture."""

    snapshot_id: str
    commit_sha: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    branch: str | None = None
    repo_path: str
    elements: list[ArchElement] = Field(default_factory=list)
    relationships: list[ArchRelationship] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ElementChange(BaseModel):
    element: ArchElement
    change_type: str  # added, removed, modified, moved
    diff_summary: str | None = None


class ArchDiff(BaseModel):
    """Difference between two snapshots."""

    from_snapshot_id: str
    to_snapshot_id: str
    added_elements: list[ArchElement] = Field(default_factory=list)
    removed_elements: list[ArchElement] = Field(default_factory=list)
    modified_elements: list[ElementChange] = Field(default_factory=list)
    added_relationships: list[ArchRelationship] = Field(default_factory=list)
    removed_relationships: list[ArchRelationship] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_elements
            or self.removed_elements
            or self.modified_elements
            or self.added_relationships
            or self.removed_relationships
        )


class AffectedElement(BaseModel):
    id: str
    name: str
    stereotype: str
    file_path: str
    reason: str
    hops: int = 1
    risk: str = "LOW"


class ImpactReport(BaseModel):
    """Result of impact analysis for a change."""

    changed_files: list[str] = Field(default_factory=list)
    changed_elements: list[str] = Field(default_factory=list)
    directly_affected: list[AffectedElement] = Field(default_factory=list)
    transitively_affected: list[AffectedElement] = Field(default_factory=list)
    risk_score: float = 0.0
    suggested_changes: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
