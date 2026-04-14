from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from core.runtime.storage import JSONValue

if TYPE_CHECKING:
    from core.runtime.types.workspace_types import ServiceMutationRequest, ServiceMutationResult
    from core.runtime.types.import_export_types import ExportArtifactRequest, ExportArtifactResult

JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class SkillWorkshopSkillSnapshot:
    object_id: str
    revision_id: str
    revision_number: int
    name: str
    description: str
    instruction: str
    style_scope: str
    is_active: bool
    source_kind: str
    donor_kind: str | None
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class SkillWorkshopVersionSnapshot:
    revision_id: str
    revision_number: int
    parent_revision_id: str | None
    name: str
    instruction: str
    style_scope: str
    is_active: bool
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class SkillWorkshopCompareRequest:
    skill_object_id: str
    left_revision_id: str
    right_revision_id: str


@dataclass(frozen=True, slots=True)
class SkillWorkshopComparison:
    skill_object_id: str
    left_revision_id: str
    left_revision_number: int
    right_revision_id: str
    right_revision_number: int
    structured_diff: JSONObject
    rendered_diff: str


@dataclass(frozen=True, slots=True)
class SkillWorkshopUpsertRequest:
    novel_id: str
    actor: str
    source_surface: str
    skill_object_id: str | None = None
    name: str | None = None
    description: str | None = None
    instruction: str | None = None
    style_scope: str | None = None
    is_active: bool | None = None
    base_revision_id: str | None = None
    revision_reason: str | None = None
    source_ref: str | None = None
    import_mapping: JSONObject | None = None
    source_kind: str = "skill_workshop"


@dataclass(frozen=True, slots=True)
class SkillWorkshopImportRequest:
    donor_kind: str
    novel_id: str
    actor: str
    source_surface: str
    donor_payload: JSONObject
    name: str | None = None
    description: str | None = None
    instruction: str | None = None
    style_scope: str = "scene_to_chapter"
    is_active: bool = True
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class SkillWorkshopRollbackRequest:
    skill_object_id: str
    target_revision_id: str
    actor: str
    source_surface: str
    revision_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SkillWorkshopMutationResult:
    object_id: str
    revision_id: str
    revision_number: int
    disposition: str
    policy_class: str
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class SkillWorkshopRequest:
    project_id: str
    novel_id: str
    selected_skill_id: str | None = None
    left_revision_id: str | None = None
    right_revision_id: str | None = None


@dataclass(frozen=True, slots=True)
class SkillWorkshopResult:
    project_id: str
    novel_id: str
    skills: tuple[SkillWorkshopSkillSnapshot, ...]
    selected_skill: SkillWorkshopSkillSnapshot | None
    versions: tuple[SkillWorkshopVersionSnapshot, ...]
    comparison: SkillWorkshopComparison | None


@dataclass(frozen=True, slots=True)
class SkillExecutionRequest:
    skill_name: str
    actor: str
    source_surface: str
    mutation_request: ServiceMutationRequest | None = None
    export_request: ExportArtifactRequest | None = None


@dataclass(frozen=True, slots=True)
class SkillExecutionResult:
    skill_name: str
    mutation_result: ServiceMutationResult | None
    export_result: ExportArtifactResult | None
