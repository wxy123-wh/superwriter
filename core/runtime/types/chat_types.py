from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from core.runtime.storage import JSONValue

if TYPE_CHECKING:
    from core.runtime.types.import_export_types import ExportArtifactRequest, ExportArtifactResult
    from core.runtime.types.skill_types import SkillExecutionRequest, SkillExecutionResult
    from core.runtime.types.workspace_types import ServiceMutationRequest, ServiceMutationResult

JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ChatMessageSnapshot:
    message_state_id: str
    chat_message_id: str
    chat_role: str
    linked_object_id: str | None
    linked_revision_id: str | None
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class ChatSessionSnapshot:
    session_id: str
    project_id: str
    novel_id: str | None
    title: str | None
    runtime_origin: str
    created_by: str
    messages: tuple[ChatMessageSnapshot, ...]


@dataclass(frozen=True, slots=True)
class OpenChatSessionRequest:
    project_id: str
    created_by: str
    runtime_origin: str
    novel_id: str | None = None
    title: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class OpenChatSessionResult:
    session_id: str
    project_id: str
    novel_id: str | None
    title: str | None
    runtime_origin: str


@dataclass(frozen=True, slots=True)
class GetChatSessionRequest:
    session_id: str


@dataclass(frozen=True, slots=True)
class ChatMessageRequest:
    chat_message_id: str
    chat_role: str
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class ChatTurnRequest:
    project_id: str
    created_by: str
    runtime_origin: str
    user_message: ChatMessageRequest
    assistant_message: ChatMessageRequest
    session_id: str | None = None
    novel_id: str | None = None
    title: str | None = None
    source_ref: str | None = None
    workbench_type: str | None = None
    source_object_id: str | None = None
    source_revision_id: str | None = None
    mutation_requests: tuple[ServiceMutationRequest, ...] = ()
    export_requests: tuple[ExportArtifactRequest, ...] = ()
    skill_requests: tuple[SkillExecutionRequest, ...] = ()


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    session_id: str
    user_message_state_id: str
    assistant_message_state_id: str
    assistant_content: str
    mutation_results: tuple[ServiceMutationResult, ...]
    export_results: tuple[ExportArtifactResult, ...]
    skill_results: tuple[SkillExecutionResult, ...]
