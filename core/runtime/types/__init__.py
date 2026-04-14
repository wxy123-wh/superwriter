from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    pass

JSONValue: TypeAlias = int | float | str | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


# Stub types needed by services but not yet fully implemented

@dataclass(frozen=True, slots=True)
class ReadObjectRequest:
    family: str
    object_id: str
    include_revisions: bool = False


@dataclass(frozen=True, slots=True)
class ServiceMutationRequest:
    target_family: str
    target_object_id: str | None = None
    base_revision_id: str | None = None
    source_scene_revision_id: str | None = None
    base_source_scene_revision_id: str | None = None
    payload: JSONObject | None = None
    actor: str = "system"
    source_surface: str = ""
    skill: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None
    revision_reason: str | None = None
    revision_source_message_id: str | None = None
    chapter_signals: JSONObject | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceObjectSummary:
    family: str
    object_id: str
    current_revision_id: str
    current_revision_number: int
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class CanonicalObjectSnapshot:
    object_id: str
    family: str
    current_revision_id: str
    current_revision_number: int
    created_at: str
    updated_at: str
    created_by: str
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class ReadObjectResult:
    head: CanonicalObjectSnapshot | None
    revisions: tuple[CanonicalObjectSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshotRequest:
    project_id: str
    novel_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshotResult:
    canonical_objects: tuple[WorkspaceObjectSummary, ...]


@dataclass(frozen=True, slots=True)
class ServiceMutationResult:
    target_object_id: str | None
    canonical_revision_id: str | None
    canonical_revision_number: int | None
    artifact_revision_id: str | None
    disposition: str
    policy_class: str
    proposal_id: str | None


@dataclass(frozen=True, slots=True)
class ExportArtifactRequest:
    actor: str
    source_surface: str
    source_scene_revision_id: str | None = None
    payload: JSONObject | None = None
    object_id: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExportArtifactResult:
    object_id: str
    artifact_revision_id: str


from core.runtime.types.chat_types import (
    ChatMessageRequest,
    ChatMessageSnapshot,
    ChatSessionSnapshot,
    ChatTurnRequest,
    ChatTurnResult,
    GetChatSessionRequest,
    OpenChatSessionRequest,
    OpenChatSessionResult,
)
from core.runtime.types.retrieval_types import (
    RetrievalMatchSnapshot,
    RetrievalRebuildRequest,
    RetrievalRebuildResult,
    RetrievalSearchRequest,
    RetrievalSearchResult,
    RetrievalStatusSnapshot,
)
from core.runtime.types.skill_types import (
    SkillExecutionRequest,
    SkillExecutionResult,
    SkillWorkshopCompareRequest,
    SkillWorkshopComparison,
    SkillWorkshopImportRequest,
    SkillWorkshopMutationResult,
    SkillWorkshopRequest,
    SkillWorkshopResult,
    SkillWorkshopRollbackRequest,
    SkillWorkshopSkillSnapshot,
    SkillWorkshopUpsertRequest,
    SkillWorkshopVersionSnapshot,
)

__all__ = [
    # JSON types
    "JSONValue",
    "JSONObject",
    # Stub types
    "ReadObjectRequest",
    "ServiceMutationRequest",
    # Chat types
    "ChatMessageRequest",
    "ChatMessageSnapshot",
    "ChatSessionSnapshot",
    "ChatTurnRequest",
    "ChatTurnResult",
    "GetChatSessionRequest",
    "OpenChatSessionRequest",
    "OpenChatSessionResult",
    # Retrieval types
    "RetrievalMatchSnapshot",
    "RetrievalRebuildRequest",
    "RetrievalRebuildResult",
    "RetrievalSearchRequest",
    "RetrievalSearchResult",
    "RetrievalStatusSnapshot",
    # Skill types
    "SkillExecutionRequest",
    "SkillExecutionResult",
    "SkillWorkshopCompareRequest",
    "SkillWorkshopComparison",
    "SkillWorkshopImportRequest",
    "SkillWorkshopMutationResult",
    "SkillWorkshopRequest",
    "SkillWorkshopResult",
    "SkillWorkshopRollbackRequest",
    "SkillWorkshopSkillSnapshot",
    "SkillWorkshopUpsertRequest",
    "SkillWorkshopVersionSnapshot",
]
