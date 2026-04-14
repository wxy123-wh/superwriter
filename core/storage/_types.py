from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from core.storage._utils import JSONValue

if TYPE_CHECKING:
    pass

JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ChatSessionInput:
    project_id: str
    created_by: str
    runtime_origin: str
    novel_id: str | None = None
    title: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ChatMessageLinkInput:
    chat_session_id: str
    created_by: str
    chat_message_id: str
    chat_role: str
    payload: JSONObject
    linked_object_id: str | None = None
    linked_revision_id: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ChatSessionRow:
    session_id: str
    project_id: str
    novel_id: str | None
    title: str | None
    runtime_origin: str
    created_by: str


@dataclass(frozen=True, slots=True)
class ChatMessageLinkRow:
    message_state_id: str
    chat_message_id: str
    chat_role: str
    linked_object_id: str | None
    linked_revision_id: str | None
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class MetadataMarkerInput:
    target_family: str
    target_object_id: str
    target_revision_id: str | None
    marker_name: str
    created_by: str
    marker_payload: JSONObject


@dataclass(frozen=True, slots=True)
class MetadataMarkerSnapshot:
    marker_id: str
    target_family: str
    target_object_id: str
    target_revision_id: str | None
    marker_name: str
    payload: JSONObject
    is_authoritative: int
    is_rebuildable: int
    created_at: str
    created_by: str
