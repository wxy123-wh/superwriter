from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from core.runtime.storage import JSONValue

JSONObject: TypeAlias = dict[str, JSONValue]


class SupportedDonor(str, Enum):
    WEBNOVEL_WRITER = "webnovel-writer"
    RESTORED_DECOMPILED_ARTIFACTS = "restored-decompiled-artifacts"


@dataclass(frozen=True, slots=True)
class CanonicalObjectSnapshot:
    family: str
    object_id: str
    current_revision_id: str
    current_revision_number: int
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class CanonicalRevisionSnapshot:
    revision_id: str
    revision_number: int
    parent_revision_id: str | None
    snapshot: JSONObject


@dataclass(frozen=True, slots=True)
class MutationRecordSnapshot:
    record_id: str
    target_object_family: str
    target_object_id: str
    result_revision_id: str
    resulting_revision_number: int
    actor_id: str
    source_surface: str
    skill_name: str | None
    policy_class: str
    diff_payload: JSONObject
    approval_state: str


@dataclass(frozen=True, slots=True)
class DerivedArtifactSnapshot:
    artifact_revision_id: str
    object_id: str
    source_scene_revision_id: str
    payload: JSONObject
    is_authoritative: int
    is_rebuildable: int
