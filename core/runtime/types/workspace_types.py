from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from core.runtime.storage import JSONValue
from core.runtime.types.common_types import (
    CanonicalObjectSnapshot,
    CanonicalRevisionSnapshot,
    DerivedArtifactSnapshot,
    MutationRecordSnapshot,
)

if TYPE_CHECKING:
    from core.runtime.mutation_policy import ChapterMutationSignals, MutationRequest

JSONObject: TypeAlias = dict[str, JSONValue]


# Placeholder for review types that are referenced but not yet defined
@dataclass(frozen=True, slots=True)
class ReviewProposalSnapshot:
    proposal_id: str
    target_family: str
    target_object_id: str
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class WorkspaceObjectSummary:
    family: str
    object_id: str
    current_revision_id: str
    current_revision_number: int
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class WorkspaceContextSnapshot:
    project_id: str
    project_title: str
    novel_id: str | None = None
    novel_title: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshotRequest:
    project_id: str
    novel_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshotResult:
    project_id: str
    novel_id: str | None
    canonical_objects: tuple[WorkspaceObjectSummary, ...]
    derived_artifacts: tuple[DerivedArtifactSnapshot, ...]
    review_proposals: tuple[ReviewProposalSnapshot, ...]


@dataclass(frozen=True, slots=True)
class CreateWorkspaceRequest:
    project_title: str
    novel_title: str
    actor: str
    source_surface: str = "command_center_start"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CreateWorkspaceResult:
    project_id: str
    novel_id: str


@dataclass(frozen=True, slots=True)
class ImportOutlineRequest:
    novel_id: str
    title: str
    body: str
    actor: str
    source_surface: str = "workbench_outline_import"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ImportOutlineResult:
    object_id: str
    revision_id: str
    revision_number: int


@dataclass(frozen=True, slots=True)
class ReadObjectRequest:
    family: str
    object_id: str
    include_revisions: bool = False
    include_mutations: bool = False


@dataclass(frozen=True, slots=True)
class ReadObjectResult:
    head: CanonicalObjectSnapshot | None
    revisions: tuple[CanonicalRevisionSnapshot, ...] = ()
    mutations: tuple[MutationRecordSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceMutationRequest:
    target_family: str
    payload: JSONObject
    actor: str
    source_surface: str
    target_object_id: str | None = None
    base_revision_id: str | None = None
    source_scene_revision_id: str | None = None
    base_source_scene_revision_id: str | None = None
    skill: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None
    revision_reason: str | None = None
    revision_source_message_id: str | None = None
    chapter_signals: ChapterMutationSignals | None = None

    def to_policy_request(self, *, skill: str | None = None, revision_source_message_id: str | None = None) -> MutationRequest:
        from core.runtime.mutation_policy import MutationRequest
        return MutationRequest(
            target_family=self.target_family,
            target_object_id=self.target_object_id,
            base_revision_id=self.base_revision_id,
            source_scene_revision_id=self.source_scene_revision_id,
            base_source_scene_revision_id=self.base_source_scene_revision_id,
            payload=self.payload,
            actor=self.actor,
            source_surface=self.source_surface,
            skill=skill if skill is not None else self.skill,
            source_ref=self.source_ref,
            ingest_run_id=self.ingest_run_id,
            revision_reason=self.revision_reason,
            revision_source_message_id=(
                revision_source_message_id if revision_source_message_id is not None else self.revision_source_message_id
            ),
            chapter_signals=self.chapter_signals,
        )


@dataclass(frozen=True, slots=True)
class ServiceMutationResult:
    policy_class: str
    disposition: str
    target_family: str
    target_object_id: str
    reasons: tuple[str, ...]
    canonical_revision_id: str | None
    canonical_revision_number: int | None
    mutation_record_id: str | None
    artifact_revision_id: str | None
    proposal_id: str | None
