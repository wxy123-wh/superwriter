from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import ClassVar, TypeAlias, cast

from core.export import build_filesystem_projection_plan, write_projection_plan
from core.importers.contracts import ImportedObjectRecord
from core.importers.fanbianyi import CONTRACT as FANBIANYI_CONTRACT, SOURCE_SURFACE as FANBIANYI_SOURCE_SURFACE, load_character_export_import_data
from core.importers.webnovel_writer import CONTRACT as WEBNOVEL_WRITER_CONTRACT, SOURCE_SURFACE as WEBNOVEL_WRITER_SOURCE_SURFACE, load_project_root_import_data
from core.retrieval import (
    RetrievalSourceRecord,
    build_indexed_documents,
    build_support_documents,
    rank_support_documents,
    scope_consistency_stamp,
)
from core.skills import (
    SkillAdapterRequest,
    adapt_donor_payload,
    diff_skill_payloads,
    render_skill_diff,
    validate_skill_payload,
)
from core.review import ReviewResolutionRequest
from core.ai import AIProviderClient, AIProviderConfig
from core.ai.prompts import (
    build_outline_to_plot_prompt,
    build_plot_to_event_prompt,
    build_event_to_scene_prompt,
    build_scene_to_chapter_prompt,
    build_chapter_revision_prompt,
)
from core.ai.dialogue import DialogueProcessor, DialogueRequest as DialogueDialogueRequest
from core.runtime.mutation_policy import ChapterMutationSignals, MutationDisposition, MutationExecutionResult, MutationPolicyClass, MutationPolicyEngine, MutationRequest
from core.runtime.storage import (
    CanonicalStorage,
    CanonicalWriteRequest,
    ChatMessageLinkInput,
    ChatSessionInput,
    DerivedRecordInput,
    JSONValue,
    MetadataMarkerInput,
    MetadataMarkerSnapshot,
    ImportRecordInput,
)

JSONObject: TypeAlias = dict[str, JSONValue]


def _payload_text(payload: JSONObject, key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _build_object_diff(before: JSONObject, after: JSONObject) -> JSONObject:
    added: JSONObject = {}
    removed: JSONObject = {}
    changed: JSONObject = {}
    for key in sorted(set(before) | set(after)):
        if key not in before:
            added[key] = after[key]
            continue
        if key not in after:
            removed[key] = before[key]
            continue
        if before[key] != after[key]:
            changed[key] = {"before": before[key], "after": after[key]}
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
    }


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


@dataclass(frozen=True, slots=True)
class ReviewProposalSnapshot:
    proposal_id: str
    target_family: str
    target_object_id: str
    base_revision_id: str | None
    proposal_payload: JSONObject
    created_by: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ReviewDecisionSnapshot:
    approval_record_id: str
    proposal_id: str
    approval_state: str
    mutation_record_id: str | None
    decision_payload: JSONObject
    created_by: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ReviewDeskRequest:
    project_id: str
    novel_id: str | None = None
    include_resolved: bool = True


@dataclass(frozen=True, slots=True)
class ReviewDeskProposalSnapshot:
    proposal_id: str
    target_family: str
    target_object_id: str
    target_title: str
    source_surface: str
    policy_class: str
    base_revision_id: str | None
    current_revision_id: str | None
    created_by: str
    created_at: str
    approval_state: str
    approval_state_detail: str
    is_stale: bool
    reasons: tuple[str, ...]
    requested_payload: JSONObject
    current_payload: JSONObject
    structured_diff: JSONObject
    prose_diff: str
    revision_lineage: JSONObject
    drift_details: JSONObject
    decisions: tuple[ReviewDecisionSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ReviewDeskResult:
    proposals: tuple[ReviewDeskProposalSnapshot, ...]


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
class RetrievalStatusSnapshot:
    scope_family: str
    scope_object_id: str
    support_only: bool
    rebuildable: bool
    build_consistency_stamp: str
    indexed_object_count: int
    indexed_revision_count: int
    degraded: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalRebuildRequest:
    project_id: str
    actor: str
    novel_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalRebuildResult:
    status: RetrievalStatusSnapshot
    document_count: int
    replaced_marker_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalSearchRequest:
    project_id: str
    query: str
    novel_id: str | None = None
    limit: int = 5


@dataclass(frozen=True, slots=True)
class RetrievalMatchSnapshot:
    target_family: str
    target_object_id: str
    target_revision_id: str
    score: float
    summary_text: str
    ranking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    review_hints: tuple[str, ...]
    ranking_metadata: JSONObject


@dataclass(frozen=True, slots=True)
class RetrievalSearchResult:
    status: RetrievalStatusSnapshot
    matches: tuple[RetrievalMatchSnapshot, ...]
    warnings: tuple[str, ...]
    review_hints: tuple[str, ...]


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


@dataclass(frozen=True, slots=True)
class ListReviewProposalsRequest:
    target_object_id: str | None = None
    include_resolved: bool = False


@dataclass(frozen=True, slots=True)
class ReviewTransitionRequest:
    proposal_id: str
    created_by: str
    approval_state: str
    mutation_record_id: str | None = None
    decision_payload: JSONObject | None = None


@dataclass(frozen=True, slots=True)
class ReviewTransitionResult:
    approval_record_id: str
    proposal_id: str
    approval_state: str
    mutation_record_id: str | None
    resolution: str = "recorded"
    canonical_revision_id: str | None = None
    artifact_revision_id: str | None = None
    drift_details: JSONObject | None = None


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
class ExportArtifactRequest:
    actor: str
    source_surface: str
    source_scene_revision_id: str
    payload: JSONObject
    object_id: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExportArtifactResult:
    artifact_revision_id: str
    object_id: str
    family: str
    source_scene_revision_id: str


@dataclass(frozen=True, slots=True)
class PublishExportRequest:
    project_id: str
    novel_id: str
    actor: str
    output_root: Path
    chapter_artifact_object_id: str | None = None
    base_chapter_artifact_revision_id: str | None = None
    expected_source_scene_revision_id: str | None = None
    export_object_id: str | None = None
    expected_import_source: str | None = "webnovel-writer"
    export_format: str = "markdown"
    source_surface: str = "publish_surface"
    source_ref: str | None = None
    ingest_run_id: str | None = None
    fail_after_file_count: int | None = None


@dataclass(frozen=True, slots=True)
class PublishExportArtifactRequest:
    artifact_revision_id: str
    actor: str
    output_root: Path
    source_surface: str = "publish_surface"
    fail_after_file_count: int | None = None


@dataclass(frozen=True, slots=True)
class PublishExportArtifactResult:
    disposition: str
    artifact_revision_id: str
    object_id: str
    bundle_path: str
    projected_files: tuple[str, ...]
    failure_kind: str | None = None
    failure_detail: str | None = None
    recovery_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PublishExportResult:
    disposition: str
    export_result: ExportArtifactResult | None
    publish_result: PublishExportArtifactResult | None
    stale_details: JSONObject | None = None
    recovery_actions: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Upstream canonical-link workbench request/result contracts
# ---------------------------------------------------------------------------
# v1 semantics (locked before implementation):
#
# 1. SINGLE ROUTE: All three upstream links live under the existing /workbench
#    route as additional sections. No new top-level routes.
#
# 2. PARENT PINNING: Every request carries parent_id and
#    expected_parent_revision_id. The service MUST reject the request when the
#    parent's current revision differs from the expected value (stale-parent
#    rejection).
#
# 3. CREATE-ONLY DEFAULT: When target_child_object_id is None the service
#    creates a new canonical child object. Re-running the same request without
#    a target always creates a fresh child — callers that want idempotent
#    reruns must supply the previously-created child's ID.
#
# 4. EXPLICIT-TARGET UPDATES: When target_child_object_id is supplied the
#    service treats the call as an update. base_child_revision_id is then
#    required and the service performs a drift check (current head of the
#    target must match base_child_revision_id). Drift failures are rejected
#    deterministically. Unsafe updates are routed to review proposals.
#
# 5. IDEMPOTENT APPROVAL: Approving the same review proposal more than once
#    MUST NOT create duplicate child objects. The approval path checks whether
#    the proposal has already been applied and returns the existing result on
#    replay.
#
# 6. NO GENERIC ENGINE: Each link has its own request/result pair and its own
#    service method. No shared workbench abstraction in v1.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OutlineToPlotWorkbenchRequest:
    """Request to generate a canonical plot_node from an outline_node parent.

    Semantics (v1):
    - Create-only by default (target_child_object_id is None).
    - Explicit-target update when target_child_object_id is supplied;
      base_child_revision_id is then required and drift-checked.
    - expected_parent_revision_id pins the outline_node revision; stale
      parents are rejected before any generation occurs.
    - Approval replay is idempotent — no duplicate plot_node on re-approve.
    """

    project_id: str
    novel_id: str
    outline_node_object_id: str
    actor: str
    expected_parent_revision_id: str | None = None
    target_child_object_id: str | None = None
    base_child_revision_id: str | None = None
    source_surface: str = "outline_to_plot_workbench"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class OutlineToPlotWorkbenchResult:
    """Result of an outline_node -> plot_node workbench generation.

    disposition values:
    - "generated"        — new plot_node created directly.
    - "review_required"  — update routed to review proposal.
    - "applied"          — update applied directly (safe mutation).
    """

    disposition: str
    outline_node_object_id: str
    source_outline_revision_id: str
    child_object_id: str | None
    child_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    plot_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    reasons: tuple[str, ...]
    additional_plot_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class PlotToEventWorkbenchRequest:
    """Request to generate a canonical event from a plot_node parent.

    Semantics (v1):
    - Create-only by default (target_child_object_id is None).
    - Explicit-target update when target_child_object_id is supplied;
      base_child_revision_id is then required and drift-checked.
    - expected_parent_revision_id pins the plot_node revision; stale
      parents are rejected before any generation occurs.
    - Approval replay is idempotent — no duplicate event on re-approve.
    """

    project_id: str
    novel_id: str
    plot_node_object_id: str
    actor: str
    expected_parent_revision_id: str | None = None
    target_child_object_id: str | None = None
    base_child_revision_id: str | None = None
    source_surface: str = "plot_to_event_workbench"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class PlotToEventWorkbenchResult:
    """Result of a plot_node -> event workbench generation.

    disposition values:
    - "generated"        — new event created directly.
    - "review_required"  — update routed to review proposal.
    - "applied"          — update applied directly (safe mutation).
    """

    disposition: str
    plot_node_object_id: str
    source_plot_revision_id: str
    child_object_id: str | None
    child_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    event_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    reasons: tuple[str, ...]
    additional_event_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class EventToSceneWorkbenchRequest:
    """Request to generate a canonical scene from an event parent.

    Semantics (v1):
    - Create-only by default (target_child_object_id is None).
    - Explicit-target update when target_child_object_id is supplied;
      base_child_revision_id is then required and drift-checked.
    - expected_parent_revision_id pins the event revision; stale
      parents are rejected before any generation occurs.
    - Approval replay is idempotent — no duplicate scene on re-approve.
    """

    project_id: str
    novel_id: str
    event_object_id: str
    actor: str
    expected_parent_revision_id: str | None = None
    target_child_object_id: str | None = None
    base_child_revision_id: str | None = None
    source_surface: str = "event_to_scene_workbench"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class EventToSceneWorkbenchResult:
    """Result of an event -> scene workbench generation.

    disposition values:
    - "generated"        — new scene created directly.
    - "review_required"  — update routed to review proposal.
    - "applied"          — update applied directly (safe mutation).
    """

    disposition: str
    event_object_id: str
    source_event_revision_id: str
    child_object_id: str | None
    child_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    scene_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    reasons: tuple[str, ...]
    additional_scene_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SceneToChapterWorkbenchRequest:
    project_id: str
    novel_id: str
    scene_object_id: str
    actor: str
    expected_source_scene_revision_id: str | None = None
    target_artifact_object_id: str | None = None
    base_artifact_revision_id: str | None = None
    chapter_signals: ChapterMutationSignals | None = None
    source_surface: str = "scene_to_chapter_workbench"
    source_ref: str | None = None
    skill_name: str | None = None


@dataclass(frozen=True, slots=True)
class SceneToChapterWorkbenchResult:
    disposition: str
    scene_object_id: str
    source_scene_revision_id: str
    artifact_object_id: str | None
    artifact_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    chapter_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    style_rules: tuple[WorkspaceObjectSummary, ...]
    scoped_skills: tuple[WorkspaceObjectSummary, ...]
    canonical_facts: tuple[WorkspaceObjectSummary, ...]
    reasons: tuple[str, ...]


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


class SupportedDonor(str, Enum):
    WEBNOVEL_WRITER = "webnovel-writer"
    RESTORED_DECOMPILED_ARTIFACTS = "restored-decompiled-artifacts"


@dataclass(frozen=True, slots=True)
class ImportRequest:
    donor_key: SupportedDonor
    source_path: Path
    actor: str
    project_id: str | None = None
    novel_id: str | None = None


@dataclass(frozen=True, slots=True)
class ImportObjectResult:
    family: str
    object_id: str
    revision_id: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class ImportResult:
    donor_key: str
    ingest_run_id: str
    import_record_id: str
    project_id: str
    imported_objects: tuple[ImportObjectResult, ...]


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
    mutation_requests: tuple[ServiceMutationRequest, ...] = ()
    export_requests: tuple[ExportArtifactRequest, ...] = ()
    skill_requests: tuple[SkillExecutionRequest, ...] = ()


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    session_id: str
    user_message_state_id: str
    assistant_message_state_id: str
    mutation_results: tuple[ServiceMutationResult, ...]
    export_results: tuple[ExportArtifactResult, ...]
    skill_results: tuple[SkillExecutionResult, ...]


@dataclass(frozen=True, slots=True)
class _AppliedReviewMutation:
    mutation_record_id: str | None = None
    canonical_revision_id: str | None = None
    artifact_revision_id: str | None = None


class SuperwriterApplicationService:
    __slots__: ClassVar[tuple[str, str]] = ("__storage", "__policy")

    def __init__(self, storage: CanonicalStorage):
        self.__storage = storage
        self.__policy = MutationPolicyEngine(storage)

    @classmethod
    def for_sqlite(cls, db_path: Path) -> SuperwriterApplicationService:
        return cls(CanonicalStorage(db_path))

    def _get_active_ai_provider(self) -> AIProviderClient | None:
        """Get the active AI provider client, or None if not configured."""
        config_data = self.__storage.get_active_provider_config()
        if config_data is None:
            return None
        try:
            config = AIProviderConfig(
                provider_id=str(config_data["provider_id"]),
                provider_name=str(config_data["provider_name"]),
                base_url=str(config_data["base_url"]),
                api_key=str(config_data["api_key"]),
                model_name=str(config_data["model_name"]),
                temperature=float(config_data["temperature"]),
                max_tokens=int(config_data["max_tokens"]),
                is_active=bool(config_data["is_active"]),
            )
            return AIProviderClient(config)
        except Exception:
            return None

    def _get_dialogue_processor(self) -> DialogueProcessor | None:
        """Get or create a dialogue processor instance."""
        if self._get_active_ai_provider() is not None:
            return DialogueProcessor(self)
        return None

    def read_object(self, request: ReadObjectRequest) -> ReadObjectResult:
        head_row = self.__storage.fetch_canonical_head(request.family, request.object_id)
        head = None
        if head_row is not None:
            head = CanonicalObjectSnapshot(
                family=str(head_row["family"]),
                object_id=str(head_row["object_id"]),
                current_revision_id=str(head_row["current_revision_id"]),
                current_revision_number=int(cast(int, head_row["current_revision_number"])),
                payload=cast(JSONObject, head_row["payload"]),
            )
        revisions = ()
        mutations = ()
        if request.include_revisions:
            revisions = tuple(
                CanonicalRevisionSnapshot(
                    revision_id=str(row["revision_id"]),
                    revision_number=int(cast(int, row["revision_number"])),
                    parent_revision_id=cast(str | None, row["parent_revision_id"]),
                    snapshot=cast(JSONObject, row["snapshot"]),
                )
                for row in self.__storage.fetch_canonical_revisions(request.object_id)
            )
        if request.include_mutations:
            mutations = tuple(
                MutationRecordSnapshot(
                    record_id=str(row["record_id"]),
                    target_object_family=str(row["target_object_family"]),
                    target_object_id=str(row["target_object_id"]),
                    result_revision_id=str(row["result_revision_id"]),
                    resulting_revision_number=int(cast(int, row["resulting_revision_number"])),
                    actor_id=str(row["actor_id"]),
                    source_surface=str(row["source_surface"]),
                    skill_name=cast(str | None, row["skill_name"]),
                    policy_class=str(row["policy_class"]),
                    diff_payload=cast(JSONObject, row["diff_payload"]),
                    approval_state=str(row["approval_state"]),
                )
                for row in self.__storage.fetch_mutation_records(request.object_id)
            )
        return ReadObjectResult(head=head, revisions=revisions, mutations=mutations)

    def get_workspace_snapshot(self, request: WorkspaceSnapshotRequest) -> WorkspaceSnapshotResult:
        canonical_objects = [
            WorkspaceObjectSummary(
                family=row.family,
                object_id=row.object_id,
                current_revision_id=row.current_revision_id,
                current_revision_number=row.current_revision_number,
                payload=row.payload,
            )
            for row in self.__storage.fetch_workspace_canonical_rows(
                project_id=request.project_id,
                novel_id=request.novel_id,
            )
        ]

        derived_artifacts = tuple(
            artifact
            for family in ("chapter_artifact", "export_artifact")
            for artifact in self.list_derived_artifacts(family)
            if request.novel_id is None or artifact.payload.get("novel_id") == request.novel_id
        )
        review_proposals = tuple(
            proposal
            for proposal in self.list_review_proposals(ListReviewProposalsRequest()).proposals
            if any(summary.object_id == proposal.target_object_id for summary in canonical_objects)
        )
        return WorkspaceSnapshotResult(
            project_id=request.project_id,
            novel_id=request.novel_id,
            canonical_objects=tuple(canonical_objects),
            derived_artifacts=derived_artifacts,
            review_proposals=review_proposals,
        )

    def list_workspace_contexts(self) -> tuple[WorkspaceContextSnapshot, ...]:
        rows = self.__storage.fetch_all_canonical_rows()
        project_titles: dict[str, str] = {}
        novel_contexts: dict[str, list[WorkspaceContextSnapshot]] = {}
        for row in rows:
            if row.family == "project":
                project_titles[row.object_id] = _payload_text(row.payload, "title") or row.object_id
                continue
            if row.family != "novel":
                continue
            project_id_raw = row.payload.get("project_id")
            if not isinstance(project_id_raw, str):
                continue
            project_id = project_id_raw.strip()
            if not project_id:
                continue
            novel_contexts.setdefault(project_id, []).append(
                WorkspaceContextSnapshot(
                    project_id=project_id,
                    project_title=project_titles.get(project_id, project_id),
                    novel_id=row.object_id,
                    novel_title=_payload_text(row.payload, "title") or row.object_id,
                )
            )
        contexts: list[WorkspaceContextSnapshot] = []
        for project_id in sorted(set(project_titles) | set(novel_contexts)):
            project_title = project_titles.get(project_id, project_id)
            project_contexts = sorted(
                novel_contexts.get(project_id, []),
                key=lambda context: ((context.novel_title or "").lower(), context.novel_id or ""),
            )
            if project_contexts:
                contexts.extend(
                    WorkspaceContextSnapshot(
                        project_id=context.project_id,
                        project_title=project_title,
                        novel_id=context.novel_id,
                        novel_title=context.novel_title,
                    )
                    for context in project_contexts
                )
                continue
            contexts.append(WorkspaceContextSnapshot(project_id=project_id, project_title=project_title))
        return tuple(contexts)

    def create_workspace(self, request: CreateWorkspaceRequest) -> CreateWorkspaceResult:
        project_title = request.project_title.strip()
        novel_title = request.novel_title.strip()
        if not project_title:
            raise ValueError("project_title is required")
        if not novel_title:
            raise ValueError("novel_title is required")

        project_result = self.__storage.write_canonical_object(
            CanonicalWriteRequest(
                family="project",
                payload={"title": project_title},
                actor=request.actor,
                created_by=request.actor,
                source_surface=request.source_surface,
                source_ref=request.source_ref,
                policy_class="command_center_initialize",
                approval_state="auto_applied",
                revision_reason="initialize project from start page",
            )
        )
        novel_result = self.__storage.write_canonical_object(
            CanonicalWriteRequest(
                family="novel",
                payload={
                    "project_id": project_result.object_id,
                    "title": novel_title,
                },
                actor=request.actor,
                created_by=request.actor,
                source_surface=request.source_surface,
                source_ref=request.source_ref,
                policy_class="command_center_initialize",
                approval_state="auto_applied",
                revision_reason="initialize novel from start page",
            )
        )
        return CreateWorkspaceResult(
            project_id=project_result.object_id,
            novel_id=novel_result.object_id,
        )

    def import_outline(self, request: ImportOutlineRequest) -> ImportOutlineResult:
        title = request.title.strip()
        body = request.body.strip()
        if not title:
            raise ValueError("请填写大纲标题。")
        if not body:
            raise ValueError("请填写大纲内容。")

        result = self.__storage.write_canonical_object(
            CanonicalWriteRequest(
                family="outline_node",
                payload={
                    "novel_id": request.novel_id,
                    "title": title,
                    "summary": body,
                    "body": body,
                },
                actor=request.actor,
                created_by=request.actor,
                source_surface=request.source_surface,
                source_ref=request.source_ref,
                policy_class="workbench_outline_import",
                approval_state="auto_applied",
                revision_reason="import outline from workbench form",
            )
        )
        return ImportOutlineResult(
            object_id=result.object_id,
            revision_id=result.revision_id,
            revision_number=result.revision_number,
        )

    def list_provider_configs(self) -> tuple[dict[str, object], ...]:
        """List all AI provider configurations."""
        configs = self.__storage.list_provider_configs()
        return tuple(configs)

    def save_provider_config(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        is_active: bool = False,
        created_by: str = "user",
    ) -> str:
        """Save or update an AI provider configuration."""
        return self.__storage.save_provider_config(
            provider_id=None,
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            is_active=is_active,
            created_by=created_by,
        )

    def set_active_provider(self, provider_id: str) -> bool:
        """Set a provider as active."""
        return self.__storage.set_active_provider(provider_id)

    def delete_provider_config(self, provider_id: str) -> bool:
        """Delete an AI provider configuration."""
        return self.__storage.delete_provider_config(provider_id)

    def test_provider_config(self, provider_id: str) -> dict[str, object]:
        """Test an AI provider configuration."""
        from core.ai import AIProviderClient, AIProviderConfig

        config_data = self.__storage.get_provider_config(provider_id)
        if config_data is None:
            return {"success": False, "message": "Provider not found"}

        try:
            config = AIProviderConfig(
                provider_id=str(config_data["provider_id"]),
                provider_name=str(config_data["provider_name"]),
                base_url=str(config_data["base_url"]),
                api_key=str(config_data["api_key"]),
                model_name=str(config_data["model_name"]),
                temperature=float(config_data["temperature"]),
                max_tokens=int(config_data["max_tokens"]),
                is_active=bool(config_data["is_active"]),
            )
            client = AIProviderClient(config)
            result = client.test_connection()
            return {
                "success": result.success,
                "message": result.message,
                "latency_ms": result.latency_ms,
                "model_info": result.model_info,
                "error_detail": result.error_detail,
            }
        except Exception as e:
            return {"success": False, "message": f"Test failed: {e}"}

    def diagnose_project(self, project_id: str, novel_id: str | None) -> JSONObject:
        """
        Run intelligent diagnosis on the project.

        Returns a diagnosis report with issues, suggested actions, and health score.
        """
        from core.ai.diagnosis import IntelligentDiagnoser, DiagnosisRequest

        # Get workspace snapshot
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )

        # Check if AI is available for intelligent diagnosis
        ai_client = self._get_active_ai_provider()

        if ai_client is not None:
            diagnoser = IntelligentDiagnoser(ai_client)
            request = DiagnosisRequest(
                project_id=project_id,
                novel_id=novel_id,
                workspace_snapshot=workspace,
            )
            report = diagnoser.diagnose(request)

            return {
                "health_score": report.overall_health_score,
                "quality_level": report.quality_assessment.get("level", "unknown"),
                "issues": [
                    {
                        "severity": issue.severity,
                        "category": issue.category,
                        "title": issue.title,
                        "description": issue.description,
                        "suggested_action": issue.suggested_action,
                    }
                    for issue in report.issues_found
                ],
                "suggested_actions": report.suggested_actions,
                "next_priority": report.next_priority,
                "ai_powered": True,
            }
        else:
            # Fallback to basic analysis without AI
            return self._basic_diagnosis(project_id, novel_id, workspace)

    def _basic_diagnosis(self, project_id: str, novel_id: str | None, workspace: WorkspaceSnapshotResult) -> JSONObject:
        """Basic diagnosis without AI - simple rule-based analysis."""
        issues: list[JSONObject] = []
        suggested_actions: list[JSONObject] = []

        # Count objects by family
        counts: dict[str, int] = {}
        for obj in workspace.canonical_objects:
            counts[obj.family] = counts.get(obj.family, 0) + 1

        # Check for structural gaps
        if counts.get("outline_node", 0) > 0 and counts.get("plot_node", 0) == 0:
            issues.append({
                "severity": "warning",
                "category": "structure",
                "title": "大纲节点没有对应的剧情节点",
                "description": "项目中存在大纲节点，但尚未创建剧情节点。",
                "suggested_action": "outline_to_plot",
            })
            suggested_actions.append({
                "title": "扩展大纲为剧情",
                "description": "使用大纲→剧情工作台进行扩展",
                "route": "/workbench",
                "priority": "warning",
            })

        if counts.get("scene", 0) > 0 and counts.get("chapter_artifact", 0) == 0:
            issues.append({
                "severity": "info",
                "category": "completeness",
                "title": "场景尚未写成章节",
                "description": f"项目中有 {counts['scene']} 个场景，但尚未生成章节正文。",
                "suggested_action": "scene_to_chapter",
            })
            suggested_actions.append({
                "title": "写作章节正文",
                "description": "使用场景→章节工作台进行写作",
                "route": "/workbench",
                "priority": "info",
            })

        # Add provider configuration action if no AI
        if self._get_active_ai_provider() is None:
            suggested_actions.append({
                "title": "配置 AI 提供者",
                "description": "配置 AI 提供者以启用智能内容生成",
                "route": "/settings",
                "priority": "info",
            })

        # Calculate basic health score
        health_score = 100.0
        health_score -= len([i for i in issues if i["severity"] == "error"]) * 20
        health_score -= len([i for i in issues if i["severity"] == "warning"]) * 10
        health_score -= len([i for i in issues if i["severity"] == "info"]) * 5

        return {
            "health_score": max(0.0, health_score),
            "quality_level": "良好" if health_score > 70 else "需要注意" if health_score > 40 else "需要修复",
            "issues": issues,
            "suggested_actions": suggested_actions,
            "next_priority": suggested_actions[0].get("title") if suggested_actions else None,
            "ai_powered": False,
        }

    def list_derived_artifacts(self, family: str) -> tuple[DerivedArtifactSnapshot, ...]:
        return tuple(
            DerivedArtifactSnapshot(
                artifact_revision_id=str(row["artifact_revision_id"]),
                object_id=str(row["object_id"]),
                source_scene_revision_id=str(row["source_scene_revision_id"]),
                payload=cast(JSONObject, row["payload"]),
                is_authoritative=int(cast(int, row["is_authoritative"])),
                is_rebuildable=int(cast(int, row["is_rebuildable"])),
            )
            for row in self.__storage.fetch_derived_records(family)
        )

    def rebuild_retrieval_support(self, request: RetrievalRebuildRequest) -> RetrievalRebuildResult:
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        scope_family, scope_object_id = self._retrieval_scope(request.project_id, request.novel_id)
        scope_read = self.read_object(ReadObjectRequest(family=scope_family, object_id=scope_object_id))
        if scope_read.head is None:
            raise KeyError(f"{scope_family}:{scope_object_id}")

        sources = self._retrieval_sources(workspace.canonical_objects)
        documents, report = build_support_documents(
            sources,
            scope_project_id=request.project_id,
            scope_novel_id=request.novel_id,
        )

        replaced_marker_count = self.__storage.delete_metadata_markers(
            marker_name="retrieval_status",
            target_family=scope_family,
            target_object_id=scope_object_id,
        )
        for source in sources:
            replaced_marker_count += self.__storage.delete_metadata_markers(
                marker_name="retrieval_document",
                target_family=source.family,
                target_object_id=source.object_id,
            )

        for document in documents:
            _ = self.__storage.create_metadata_marker(
                MetadataMarkerInput(
                    target_family=document.target_family,
                    target_object_id=document.target_object_id,
                    target_revision_id=document.target_revision_id,
                    marker_name="retrieval_document",
                    created_by=request.actor,
                    marker_payload=document.marker_payload,
                )
            )

        status_payload: JSONObject = {
            "project_id": request.project_id,
            "novel_id": request.novel_id,
            "support_only": True,
            "rebuildable": True,
            "source_kind": "canonical_objects_and_revisions",
            "build_consistency_stamp": report.build_consistency_stamp,
            "indexed_object_count": report.canonical_object_count,
            "indexed_revision_count": report.canonical_revision_count,
            "warning_count": report.warning_count,
            "warnings": list(report.warnings),
        }
        _ = self.__storage.create_metadata_marker(
            MetadataMarkerInput(
                target_family=scope_family,
                target_object_id=scope_object_id,
                target_revision_id=scope_read.head.current_revision_id,
                marker_name="retrieval_status",
                created_by=request.actor,
                marker_payload=status_payload,
            )
        )
        status = RetrievalStatusSnapshot(
            scope_family=scope_family,
            scope_object_id=scope_object_id,
            support_only=True,
            rebuildable=True,
            build_consistency_stamp=report.build_consistency_stamp,
            indexed_object_count=report.canonical_object_count,
            indexed_revision_count=report.canonical_revision_count,
            degraded=False,
            warnings=report.warnings,
        )
        return RetrievalRebuildResult(
            status=status,
            document_count=len(documents),
            replaced_marker_count=replaced_marker_count,
            warnings=report.warnings,
        )

    def search_retrieval_support(self, request: RetrievalSearchRequest) -> RetrievalSearchResult:
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        scope_family, scope_object_id = self._retrieval_scope(request.project_id, request.novel_id)
        sources = self._retrieval_sources(workspace.canonical_objects)
        current_revision_ids = {source.object_id: source.revision_id for source in sources}
        current_stamp = scope_consistency_stamp(sources)

        document_markers = self._retrieval_document_markers(request.project_id, request.novel_id)
        indexed_documents = build_indexed_documents(tuple(marker.payload for marker in document_markers))
        ranked_documents = rank_support_documents(request.query, indexed_documents)

        warnings: list[str] = []
        review_hints: list[str] = []
        degraded = False
        status_marker = self._latest_retrieval_status_marker(scope_family=scope_family, scope_object_id=scope_object_id)
        if status_marker is None:
            degraded = True
            warnings.append("Retrieval support status is missing; rankings are advisory until a rebuild runs.")
        else:
            status_stamp = self._payload_text_value(status_marker.payload, "build_consistency_stamp")
            if status_stamp != current_stamp:
                degraded = True
                warnings.append(
                    "Retrieval support is stale relative to canonical revisions; rankings were downgraded instead of mutating canonical state."
                )
        if not document_markers:
            degraded = True
            warnings.append("Retrieval support documents are missing for this scope; authoring remains available while rebuild catches up.")

        match_rows: list[tuple[float, RetrievalMatchSnapshot]] = []
        for ranked_document in ranked_documents:
            current_revision_id = current_revision_ids.get(ranked_document.target_object_id)
            if current_revision_id is None:
                continue
            match_warnings: list[str] = []
            match_review_hints: list[str] = []
            adjusted_score = ranked_document.score
            if degraded:
                adjusted_score *= 0.75
            if current_revision_id != ranked_document.target_revision_id:
                degraded = True
                adjusted_score *= 0.5
                stale_warning = (
                    f"retrieval snapshot for {ranked_document.target_family}:{ranked_document.target_object_id} is stale against canonical revision {current_revision_id}"
                )
                match_warnings.append(stale_warning)
                warnings.append(stale_warning)
                match_review_hints.append("Verify the current canonical revision before acting on this retrieval match.")
            ranking_metadata = dict(ranked_document.ranking_metadata)
            ranking_metadata.update(
                {
                    "support_only": True,
                    "rebuildable": True,
                    "adjusted_score": adjusted_score,
                    "current_revision_id": current_revision_id,
                }
            )
            match_rows.append(
                (
                    adjusted_score,
                    RetrievalMatchSnapshot(
                        target_family=ranked_document.target_family,
                        target_object_id=ranked_document.target_object_id,
                        target_revision_id=ranked_document.target_revision_id,
                        score=adjusted_score,
                        summary_text=ranked_document.summary_text,
                        ranking_reasons=ranked_document.ranking_reasons,
                        warnings=tuple(match_warnings),
                        review_hints=tuple(match_review_hints),
                        ranking_metadata=ranking_metadata,
                    ),
                )
            )

        match_rows.sort(key=lambda item: (-item[0], item[1].target_family, item[1].target_object_id))
        limited_matches = [row[1] for row in match_rows[: max(1, request.limit)]]
        if len(limited_matches) >= 2:
            top_score = limited_matches[0].score
            second_score = limited_matches[1].score
            if top_score > 0 and abs(top_score - second_score) <= 10:
                degraded = True
                conflict_warning = (
                    f"Retrieval conflict: {limited_matches[0].target_object_id} and {limited_matches[1].target_object_id} ranked too closely to trust without review."
                )
                warnings.append(conflict_warning)
                review_hints.append("Verify both top retrieval matches against canonical revisions before applying any world-state change.")
                enriched_matches: list[RetrievalMatchSnapshot] = []
                for index, match in enumerate(limited_matches):
                    if index < 2:
                        metadata = dict(match.ranking_metadata)
                        metadata["conflict_penalty"] = 0.9
                        enriched_matches.append(
                            RetrievalMatchSnapshot(
                                target_family=match.target_family,
                                target_object_id=match.target_object_id,
                                target_revision_id=match.target_revision_id,
                                score=match.score * 0.9,
                                summary_text=match.summary_text,
                                ranking_reasons=match.ranking_reasons,
                                warnings=match.warnings + (conflict_warning,),
                                review_hints=match.review_hints + (
                                    "Conflicting support-only recall detected; route any consequential change through review-minded verification.",
                                ),
                                ranking_metadata=metadata,
                            )
                        )
                    else:
                        enriched_matches.append(match)
                limited_matches = sorted(
                    enriched_matches,
                    key=lambda item: (-item.score, item.target_family, item.target_object_id),
                )

        status = self._retrieval_status_snapshot(
            scope_family=scope_family,
            scope_object_id=scope_object_id,
            current_stamp=current_stamp,
            document_markers=document_markers,
            status_marker=status_marker,
            degraded=degraded,
            warnings=tuple(dict.fromkeys(warnings)),
        )
        return RetrievalSearchResult(
            status=status,
            matches=tuple(limited_matches),
            warnings=tuple(dict.fromkeys(warnings)),
            review_hints=tuple(dict.fromkeys(review_hints)),
        )

    def apply_mutation(self, request: ServiceMutationRequest) -> ServiceMutationResult:
        if request.target_family == "skill":
            request = replace(request, payload=validate_skill_payload(dict(request.payload)))
        result = self.__policy.apply_mutation(request.to_policy_request())
        return self._service_mutation_result(result)

    def get_skill_workshop(self, request: SkillWorkshopRequest) -> SkillWorkshopResult:
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        skills = sorted(
            (
                self._skill_workshop_snapshot(summary)
                for summary in workspace.canonical_objects
                if summary.family == "skill"
                and summary.payload.get("novel_id") == request.novel_id
                and summary.payload.get("skill_type") == "style_rule"
            ),
            key=lambda skill: (skill.name.lower(), skill.object_id),
        )
        selected_skill = next(
            (skill for skill in skills if skill.object_id == request.selected_skill_id),
            skills[0] if skills else None,
        )
        versions: tuple[SkillWorkshopVersionSnapshot, ...] = ()
        comparison: SkillWorkshopComparison | None = None
        if selected_skill is not None:
            versions = self._skill_versions(selected_skill.object_id)
            if request.left_revision_id and request.right_revision_id:
                comparison = self.compare_skill_versions(
                    SkillWorkshopCompareRequest(
                        skill_object_id=selected_skill.object_id,
                        left_revision_id=request.left_revision_id,
                        right_revision_id=request.right_revision_id,
                    )
                )
            elif len(versions) >= 2:
                comparison = self.compare_skill_versions(
                    SkillWorkshopCompareRequest(
                        skill_object_id=selected_skill.object_id,
                        left_revision_id=versions[1].revision_id,
                        right_revision_id=versions[0].revision_id,
                    )
                )
        return SkillWorkshopResult(
            project_id=request.project_id,
            novel_id=request.novel_id,
            skills=tuple(skills),
            selected_skill=selected_skill,
            versions=versions,
            comparison=comparison,
        )

    def upsert_skill_workshop_skill(self, request: SkillWorkshopUpsertRequest) -> SkillWorkshopMutationResult:
        existing_payload: JSONObject = {}
        base_revision_id = request.base_revision_id
        target_object_id = request.skill_object_id
        if target_object_id is not None:
            current = self.read_object(ReadObjectRequest(family="skill", object_id=target_object_id))
            if current.head is None:
                raise KeyError(target_object_id)
            existing_payload = dict(current.head.payload)
            if existing_payload.get("novel_id") != request.novel_id:
                raise ValueError("skill does not belong to requested novel_id")
            if base_revision_id is None:
                base_revision_id = current.head.current_revision_id
        payload = validate_skill_payload(
            {
                "novel_id": request.novel_id,
                "skill_type": "style_rule",
                "name": request.name if request.name is not None else existing_payload.get("name", ""),
                "description": (
                    request.description if request.description is not None else existing_payload.get("description", "")
                ),
                "instruction": (
                    request.instruction if request.instruction is not None else existing_payload.get("instruction", "")
                ),
                "style_scope": (
                    request.style_scope if request.style_scope is not None else existing_payload.get("style_scope", "scene_to_chapter")
                ),
                "is_active": request.is_active if request.is_active is not None else existing_payload.get("is_active", True),
                "source_kind": request.source_kind,
                "import_mapping": request.import_mapping,
            }
        )
        mutation = self.apply_mutation(
            ServiceMutationRequest(
                target_family="skill",
                target_object_id=target_object_id,
                base_revision_id=base_revision_id,
                payload=payload,
                actor=request.actor,
                source_surface=request.source_surface,
                revision_reason=request.revision_reason or self._default_skill_revision_reason(target_object_id),
                source_ref=request.source_ref,
            )
        )
        if mutation.canonical_revision_id is None or mutation.canonical_revision_number is None:
            raise RuntimeError("constrained skill workshop mutation did not produce a canonical revision")
        return SkillWorkshopMutationResult(
            object_id=mutation.target_object_id,
            revision_id=mutation.canonical_revision_id,
            revision_number=mutation.canonical_revision_number,
            disposition=mutation.disposition,
            policy_class=mutation.policy_class,
            payload=payload,
        )

    def import_skill_workshop_skill(self, request: SkillWorkshopImportRequest) -> SkillWorkshopMutationResult:
        adapted = adapt_donor_payload(
            SkillAdapterRequest(
                donor_kind=request.donor_kind,
                novel_id=request.novel_id,
                name=request.name,
                description=request.description,
                instruction=request.instruction,
                style_scope=request.style_scope,
                is_active=request.is_active,
                source_ref=request.source_ref,
                donor_payload=request.donor_payload,
            )
        )
        return self.upsert_skill_workshop_skill(
            SkillWorkshopUpsertRequest(
                novel_id=request.novel_id,
                actor=request.actor,
                source_surface=request.source_surface,
                name=cast(str, adapted.payload["name"]),
                description=cast(str, adapted.payload.get("description", "")),
                instruction=cast(str, adapted.payload["instruction"]),
                style_scope=cast(str, adapted.payload["style_scope"]),
                is_active=cast(bool, adapted.payload["is_active"]),
                revision_reason=f"import {adapted.donor_kind} into constrained skill workshop",
                source_ref=request.source_ref,
                import_mapping=cast(JSONObject | None, adapted.payload.get("import_mapping")),
                source_kind=cast(str, adapted.payload["source_kind"]),
            )
        )

    def rollback_skill_workshop_skill(self, request: SkillWorkshopRollbackRequest) -> SkillWorkshopMutationResult:
        read_result = self.read_object(
            ReadObjectRequest(family="skill", object_id=request.skill_object_id, include_revisions=True)
        )
        if read_result.head is None:
            raise KeyError(request.skill_object_id)
        target_revision = next(
            (revision for revision in read_result.revisions if revision.revision_id == request.target_revision_id),
            None,
        )
        if target_revision is None:
            raise KeyError(request.target_revision_id)
        target_payload = validate_skill_payload(dict(target_revision.snapshot))
        return self.upsert_skill_workshop_skill(
            SkillWorkshopUpsertRequest(
                novel_id=cast(str, target_payload["novel_id"]),
                actor=request.actor,
                source_surface=request.source_surface,
                skill_object_id=request.skill_object_id,
                name=cast(str, target_payload["name"]),
                description=cast(str, target_payload.get("description", "")),
                instruction=cast(str, target_payload["instruction"]),
                style_scope=cast(str, target_payload["style_scope"]),
                is_active=cast(bool, target_payload["is_active"]),
                base_revision_id=read_result.head.current_revision_id,
                revision_reason=request.revision_reason or f"rollback constrained skill to {request.target_revision_id}",
                import_mapping=cast(JSONObject | None, target_payload.get("import_mapping")),
                source_kind=cast(str, target_payload["source_kind"]),
            )
        )

    def compare_skill_versions(self, request: SkillWorkshopCompareRequest) -> SkillWorkshopComparison:
        revisions = self._skill_versions(request.skill_object_id)
        left = next((revision for revision in revisions if revision.revision_id == request.left_revision_id), None)
        right = next((revision for revision in revisions if revision.revision_id == request.right_revision_id), None)
        if left is None:
            raise KeyError(request.left_revision_id)
        if right is None:
            raise KeyError(request.right_revision_id)
        return SkillWorkshopComparison(
            skill_object_id=request.skill_object_id,
            left_revision_id=left.revision_id,
            left_revision_number=left.revision_number,
            right_revision_id=right.revision_id,
            right_revision_number=right.revision_number,
            structured_diff=diff_skill_payloads(left.payload, right.payload),
            rendered_diff=render_skill_diff(left.payload, right.payload),
        )

    def list_review_proposals(self, request: ListReviewProposalsRequest) -> ListReviewProposalsResult:
        rows = self.__storage.fetch_proposals(target_object_id=request.target_object_id)
        proposals = tuple(self._review_proposal_snapshot_from_row(row) for row in rows)
        if not request.include_resolved:
            proposals = tuple(
                proposal
                for proposal in proposals
                if not self._review_state_is_resolved(self._proposal_latest_state(proposal.proposal_id))
            )
        return ListReviewProposalsResult(
            proposals=proposals
        )

    def transition_review(self, request: ReviewTransitionRequest) -> ReviewTransitionResult:
        proposal = self._review_proposal_by_id(request.proposal_id)
        if proposal is None:
            raise KeyError(request.proposal_id)

        normalized_state = self._normalize_review_state(request.approval_state)
        replay = self._approved_replay_result(proposal.proposal_id)
        if replay is not None:
            return replay

        if normalized_state == "approved":
            drift_details = self._proposal_drift_details(proposal)
            if drift_details:
                result = self.__policy.record_review_resolution(
                    ReviewResolutionRequest(
                        proposal_id=request.proposal_id,
                        created_by=request.created_by,
                        approval_state="stale",
                        decision_payload=self._merge_decision_payload(
                            request.decision_payload,
                            {
                                "requested_state": "approved",
                                "drift_details": drift_details,
                            },
                        ),
                    )
                )
                return ReviewTransitionResult(
                    approval_record_id=result.approval_record_id,
                    proposal_id=result.proposal_id,
                    approval_state=result.approval_state,
                    mutation_record_id=result.mutation_record_id,
                    resolution="stale",
                    drift_details=drift_details,
                )

            apply_result = self._apply_review_proposal(proposal, actor=request.created_by)
            result = self.__policy.record_review_resolution(
                ReviewResolutionRequest(
                    proposal_id=request.proposal_id,
                    created_by=request.created_by,
                    approval_state="approved",
                    mutation_record_id=apply_result.mutation_record_id,
                    decision_payload=self._merge_decision_payload(
                        request.decision_payload,
                        {
                            "canonical_revision_id": apply_result.canonical_revision_id,
                            "artifact_revision_id": apply_result.artifact_revision_id,
                            "apply_behavior": "applied_exactly_once",
                        },
                    ),
                )
            )
            return ReviewTransitionResult(
                approval_record_id=result.approval_record_id,
                proposal_id=result.proposal_id,
                approval_state=result.approval_state,
                mutation_record_id=result.mutation_record_id,
                resolution="applied",
                canonical_revision_id=apply_result.canonical_revision_id,
                artifact_revision_id=apply_result.artifact_revision_id,
            )

        result = self.__policy.record_review_resolution(
            ReviewResolutionRequest(
                proposal_id=request.proposal_id,
                created_by=request.created_by,
                approval_state=normalized_state,
                mutation_record_id=request.mutation_record_id,
                decision_payload=request.decision_payload,
            )
        )
        return ReviewTransitionResult(
            approval_record_id=result.approval_record_id,
            proposal_id=result.proposal_id,
            approval_state=result.approval_state,
            mutation_record_id=result.mutation_record_id,
            resolution="recorded",
        )

    def get_review_desk(self, request: ReviewDeskRequest) -> ReviewDeskResult:
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        visible_object_ids = {summary.object_id for summary in workspace.canonical_objects}
        visible_object_ids.update(artifact.object_id for artifact in workspace.derived_artifacts)
        proposals = tuple(
            proposal
            for proposal in self.list_review_proposals(
                ListReviewProposalsRequest(include_resolved=request.include_resolved)
            ).proposals
            if proposal.target_object_id in visible_object_ids
        )
        snapshots = [self._build_review_desk_proposal_snapshot(proposal) for proposal in proposals]
        snapshots.sort(
            key=lambda proposal: (
                0 if not self._review_state_is_resolved(proposal.approval_state) else 1,
                proposal.created_at,
                proposal.proposal_id,
            )
        )
        return ReviewDeskResult(proposals=tuple(snapshots))

    def open_chat_session(self, request: OpenChatSessionRequest) -> OpenChatSessionResult:
        session_id = self.__storage.create_chat_session(
            ChatSessionInput(
                project_id=request.project_id,
                novel_id=request.novel_id,
                title=request.title,
                runtime_origin=request.runtime_origin,
                created_by=request.created_by,
                source_ref=request.source_ref,
            )
        )
        return OpenChatSessionResult(
            session_id=session_id,
            project_id=request.project_id,
            novel_id=request.novel_id,
            title=request.title,
            runtime_origin=request.runtime_origin,
        )

    def get_chat_session(self, request: GetChatSessionRequest) -> ChatSessionSnapshot:
        session_row = self.__storage.fetch_chat_session_row(request.session_id)
        if session_row is None:
            raise KeyError(request.session_id)
        message_rows = self.__storage.fetch_chat_message_link_rows(request.session_id)
        return ChatSessionSnapshot(
            session_id=session_row.session_id,
            project_id=session_row.project_id,
            novel_id=session_row.novel_id,
            title=session_row.title,
            runtime_origin=session_row.runtime_origin,
            created_by=session_row.created_by,
            messages=tuple(
                ChatMessageSnapshot(
                    message_state_id=row.message_state_id,
                    chat_message_id=row.chat_message_id,
                    chat_role=row.chat_role,
                    linked_object_id=row.linked_object_id,
                    linked_revision_id=row.linked_revision_id,
                    payload=row.payload,
                )
                for row in message_rows
            ),
        )

    def process_chat_turn(self, request: ChatTurnRequest) -> ChatTurnResult:
        session_id = request.session_id
        if session_id is None:
            session_id = self.open_chat_session(
                OpenChatSessionRequest(
                    project_id=request.project_id,
                    novel_id=request.novel_id,
                    title=request.title,
                    runtime_origin=request.runtime_origin,
                    created_by=request.created_by,
                    source_ref=request.source_ref,
                )
            ).session_id

        user_message_state_id = self.__storage.create_chat_message_link(
            ChatMessageLinkInput(
                chat_session_id=session_id,
                created_by=request.created_by,
                chat_message_id=request.user_message.chat_message_id,
                chat_role=request.user_message.chat_role,
                payload=request.user_message.payload,
                source_ref=request.source_ref,
            )
        )

        mutation_results = tuple(
            self.apply_mutation(
                ServiceMutationRequest(
                    target_family=mutation.target_family,
                    target_object_id=mutation.target_object_id,
                    base_revision_id=mutation.base_revision_id,
                    source_scene_revision_id=mutation.source_scene_revision_id,
                    base_source_scene_revision_id=mutation.base_source_scene_revision_id,
                    payload=mutation.payload,
                    actor=mutation.actor,
                    source_surface=mutation.source_surface,
                    skill=mutation.skill,
                    source_ref=mutation.source_ref,
                    ingest_run_id=mutation.ingest_run_id,
                    revision_reason=mutation.revision_reason,
                    revision_source_message_id=request.user_message.chat_message_id,
                    chapter_signals=mutation.chapter_signals,
                )
            )
            for mutation in request.mutation_requests
        )
        export_results = tuple(self.create_export_artifact(export_request) for export_request in request.export_requests)
        skill_results = tuple(self.execute_skill(skill_request) for skill_request in request.skill_requests)

        # Generate AI response if no explicit operations were requested
        assistant_payload = request.assistant_message.payload
        if not mutation_results and not export_results and not skill_results:
            # Extract user message text
            user_text = _payload_text(request.user_message.payload, "content") or _payload_text(request.user_message.payload, "text") or ""
            if not user_text:
                user_text = str(request.user_message.payload.get("message", ""))

            if user_text:
                # Try to use dialogue processor for intelligent response
                processor = self._get_dialogue_processor()
                if processor is not None:
                    try:
                        dialogue_response = processor.process_turn(
                            DialogueDialogueRequest(
                                session_id=session_id,
                                user_message=user_text,
                                project_id=request.project_id,
                                novel_id=request.novel_id,
                                actor=request.created_by,
                            )
                        )
                        assistant_payload = {
                            "content": dialogue_response.response_text,
                            "intent": dialogue_response.intent.value,
                            "suggested_actions": dialogue_response.suggested_actions,
                        }
                    except Exception:
                        # Fallback to simple acknowledgment
                        assistant_payload = {
                            "content": f"收到你的消息: {user_text[:100]}...",
                            "note": "AI 对话处理器不可用，请配置 AI 提供者",
                        }
                else:
                    assistant_payload = {
                        "content": f"收到你的消息: {user_text[:100]}...",
                        "note": "请先在设置中配置 AI 提供者以启用智能对话",
                    }

        linked_object_id: str | None = None
        linked_revision_id: str | None = None
        if mutation_results:
            linked_object_id = mutation_results[-1].target_object_id
            linked_revision_id = (
                mutation_results[-1].canonical_revision_id
                if mutation_results[-1].canonical_revision_id is not None
                else mutation_results[-1].artifact_revision_id
            )
        elif export_results:
            linked_object_id = export_results[-1].object_id
            linked_revision_id = export_results[-1].artifact_revision_id
        elif skill_results:
            last_skill = skill_results[-1]
            if last_skill.mutation_result is not None:
                linked_object_id = last_skill.mutation_result.target_object_id
                linked_revision_id = (
                    last_skill.mutation_result.canonical_revision_id
                    if last_skill.mutation_result.canonical_revision_id is not None
                    else last_skill.mutation_result.artifact_revision_id
                )
            elif last_skill.export_result is not None:
                linked_object_id = last_skill.export_result.object_id
                linked_revision_id = last_skill.export_result.artifact_revision_id

        assistant_message_state_id = self.__storage.create_chat_message_link(
            ChatMessageLinkInput(
                chat_session_id=session_id,
                created_by=request.created_by,
                chat_message_id=request.assistant_message.chat_message_id,
                chat_role=request.assistant_message.chat_role,
                payload=assistant_payload,
                linked_object_id=linked_object_id,
                linked_revision_id=linked_revision_id,
                source_ref=request.source_ref,
            )
        )
        return ChatTurnResult(
            session_id=session_id,
            user_message_state_id=user_message_state_id,
            assistant_message_state_id=assistant_message_state_id,
            mutation_results=mutation_results,
            export_results=export_results,
            skill_results=skill_results,
        )

    def create_export_artifact(self, request: ExportArtifactRequest) -> ExportArtifactResult:
        novel_id = self._payload_text_value(request.payload, "novel_id")
        if novel_id is None:
            raise ValueError("export payload must include novel_id")
        novel = self.read_object(ReadObjectRequest(family="novel", object_id=novel_id))
        if novel.head is None:
            raise KeyError(f"novel:{novel_id}")

        payload_scene_revision_id = self._payload_text_value(request.payload, "source_scene_revision_id")
        if payload_scene_revision_id is not None and payload_scene_revision_id != request.source_scene_revision_id:
            raise ValueError("export payload source_scene_revision_id must match request source_scene_revision_id")

        source_chapter_artifact_id = self._payload_text_value(request.payload, "source_chapter_artifact_id")
        if source_chapter_artifact_id is not None:
            chapter_artifact = self._latest_artifact_for_object_id(source_chapter_artifact_id, family="chapter_artifact")
            if chapter_artifact is None:
                raise ValueError(f"missing source chapter artifact {source_chapter_artifact_id}")
            if chapter_artifact.payload.get("novel_id") != novel_id:
                raise ValueError("source chapter artifact does not belong to requested novel_id")

        return self._create_derived_artifact(
            family="export_artifact",
            payload=request.payload,
            source_scene_revision_id=request.source_scene_revision_id,
            actor=request.actor,
            object_id=request.object_id,
            source_ref=request.source_ref,
            ingest_run_id=request.ingest_run_id,
        )

    def _create_derived_artifact(
        self,
        *,
        family: str,
        payload: JSONObject,
        source_scene_revision_id: str,
        actor: str,
        object_id: str | None,
        source_ref: str | None,
        ingest_run_id: str | None,
    ) -> ExportArtifactResult:

        artifact_revision_id = self.__storage.create_derived_record(
            DerivedRecordInput(
                family=family,
                object_id=object_id,
                payload=payload,
                source_scene_revision_id=source_scene_revision_id,
                created_by=actor,
                source_ref=source_ref,
                ingest_run_id=ingest_run_id,
            )
        )
        exported_row = next(
            row for row in self.__storage.fetch_derived_records(family) if row["artifact_revision_id"] == artifact_revision_id
        )
        return ExportArtifactResult(
            artifact_revision_id=artifact_revision_id,
            object_id=str(exported_row["object_id"]),
            family=family,
            source_scene_revision_id=source_scene_revision_id,
        )

    def publish_export(self, request: PublishExportRequest) -> PublishExportResult:
        novel = self.read_object(ReadObjectRequest(family="novel", object_id=request.novel_id))
        if novel.head is None:
            raise KeyError(f"novel:{request.novel_id}")
        if novel.head.payload.get("project_id") != request.project_id:
            raise ValueError("novel does not belong to requested project_id")

        import_source = self._latest_import_source(request.project_id)
        if request.expected_import_source is not None and import_source != request.expected_import_source:
            return PublishExportResult(
                disposition="importer_mismatch",
                export_result=None,
                publish_result=None,
                recovery_actions=(
                    f"Project import source is {import_source or 'missing'}; re-import from {request.expected_import_source} or clear the donor expectation before publishing.",
                ),
            )
        if request.chapter_artifact_object_id is None:
            raise ValueError("publish export requires chapter_artifact_object_id in the current MVP")

        chapter_artifact: DerivedArtifactSnapshot | None = None
        stale_details: JSONObject = {}
        chapter_artifact = self._latest_artifact_for_object_id(request.chapter_artifact_object_id, family="chapter_artifact")
        if chapter_artifact is None:
            raise ValueError(f"missing chapter artifact {request.chapter_artifact_object_id}")
        if chapter_artifact.payload.get("novel_id") != request.novel_id:
            raise ValueError("chapter artifact does not belong to requested novel_id")
        if (
            request.base_chapter_artifact_revision_id is not None
            and chapter_artifact.artifact_revision_id != request.base_chapter_artifact_revision_id
        ):
            stale_details["chapter_artifact"] = {
                "kind": "artifact_revision_drift",
                "expected_base_revision_id": request.base_chapter_artifact_revision_id,
                "current_revision_id": chapter_artifact.artifact_revision_id,
            }
        source_scene_id = self._payload_text_value(chapter_artifact.payload, "source_scene_id")
        if source_scene_id is not None:
            scene = self.read_object(ReadObjectRequest(family="scene", object_id=source_scene_id))
            if scene.head is None:
                stale_details["source_scene"] = {
                    "kind": "missing_source_scene",
                    "source_scene_id": source_scene_id,
                }
            elif scene.head.current_revision_id != chapter_artifact.source_scene_revision_id:
                stale_details["source_scene"] = {
                    "kind": "source_scene_revision_drift",
                    "source_scene_id": source_scene_id,
                    "expected_revision_id": chapter_artifact.source_scene_revision_id,
                    "current_revision_id": scene.head.current_revision_id,
                }
        if (
            request.expected_source_scene_revision_id is not None
            and chapter_artifact.source_scene_revision_id != request.expected_source_scene_revision_id
        ):
            stale_details["requested_source_scene"] = {
                "kind": "request_source_scene_revision_drift",
                "expected_revision_id": request.expected_source_scene_revision_id,
                "current_revision_id": chapter_artifact.source_scene_revision_id,
            }
        if stale_details:
            return PublishExportResult(
                disposition="stale",
                export_result=None,
                publish_result=None,
                stale_details=stale_details,
                recovery_actions=(
                    "Refresh the chapter artifact or scene lineage, then re-run publish against the current approved revisions.",
                ),
            )

        export_payload = self._build_publish_export_payload(
            project_id=request.project_id,
            novel=novel.head,
            chapter_artifact=chapter_artifact,
            export_format=request.export_format,
        )
        export_result = self.create_export_artifact(
            ExportArtifactRequest(
                actor=request.actor,
                source_surface=request.source_surface,
                source_scene_revision_id=chapter_artifact.source_scene_revision_id,
                payload=export_payload,
                object_id=request.export_object_id,
                source_ref=request.source_ref,
                ingest_run_id=request.ingest_run_id,
            )
        )
        publish_result = self.publish_export_artifact(
            PublishExportArtifactRequest(
                artifact_revision_id=export_result.artifact_revision_id,
                actor=request.actor,
                output_root=request.output_root,
                source_surface=request.source_surface,
                fail_after_file_count=request.fail_after_file_count,
            )
        )
        recovery_actions = publish_result.recovery_actions
        return PublishExportResult(
            disposition=publish_result.disposition,
            export_result=export_result,
            publish_result=publish_result,
            recovery_actions=recovery_actions,
        )

    def publish_export_artifact(self, request: PublishExportArtifactRequest) -> PublishExportArtifactResult:
        artifact = self._derived_artifact_by_revision(request.artifact_revision_id, family="export_artifact")
        if artifact is None:
            raise ValueError(f"missing export artifact revision {request.artifact_revision_id}")
        try:
            plan = build_filesystem_projection_plan(
                artifact_revision_id=artifact.artifact_revision_id,
                object_id=artifact.object_id,
                payload=artifact.payload,
            )
        except ValueError as error:
            return PublishExportArtifactResult(
                disposition="projection_failed",
                artifact_revision_id=artifact.artifact_revision_id,
                object_id=artifact.object_id,
                bundle_path=str(request.output_root / f"{artifact.object_id}-{artifact.artifact_revision_id}"),
                projected_files=(),
                failure_kind="invalid_projection_plan",
                failure_detail=str(error),
                recovery_actions=(
                    "Regenerate the export artifact with explicit projection entries before publishing again.",
                ),
            )

        write_result = write_projection_plan(
            plan=plan,
            output_root=request.output_root,
            fail_after_file_count=request.fail_after_file_count,
        )
        failure = write_result.failure
        return PublishExportArtifactResult(
            disposition=write_result.disposition,
            artifact_revision_id=artifact.artifact_revision_id,
            object_id=artifact.object_id,
            bundle_path=write_result.bundle_path,
            projected_files=write_result.projected_files,
            failure_kind=(failure.kind if failure is not None else None),
            failure_detail=(failure.detail if failure is not None else None),
            recovery_actions=((failure.recovery_action,) if failure is not None else ()),
        )

    def generate_scene_to_chapter_workbench(
        self,
        request: SceneToChapterWorkbenchRequest,
    ) -> SceneToChapterWorkbenchResult:
        scene_read = self.read_object(ReadObjectRequest(family="scene", object_id=request.scene_object_id))
        if scene_read.head is None:
            raise KeyError(f"scene:{request.scene_object_id}")
        scene = scene_read.head
        if scene.payload.get("novel_id") != request.novel_id:
            raise ValueError("scene does not belong to requested novel_id")
        if request.expected_source_scene_revision_id is not None and scene.current_revision_id != request.expected_source_scene_revision_id:
            raise ValueError(
                f"scene revision is stale; expected {request.expected_source_scene_revision_id} but found {scene.current_revision_id}"
            )

        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        style_rules = tuple(
            summary
            for summary in workspace.canonical_objects
            if summary.family == "style_rule" and summary.payload.get("novel_id") == request.novel_id
        )
        scoped_skills = tuple(
            summary
            for summary in workspace.canonical_objects
            if summary.family == "skill"
            and summary.payload.get("novel_id") == request.novel_id
            and self._skill_matches_scene_to_chapter_scope(summary.payload)
        )
        canonical_facts = tuple(
            summary
            for summary in workspace.canonical_objects
            if summary.family == "fact_state_record"
            and summary.payload.get("novel_id") == request.novel_id
            and summary.payload.get("source_scene_id") == request.scene_object_id
        )

        latest_artifact = self._latest_scene_chapter_artifact(
            request.scene_object_id,
            novel_id=request.novel_id,
        )
        previous_payload = latest_artifact.payload if latest_artifact is not None else {}
        generated_payload = self._build_scene_to_chapter_payload(
            scene=scene,
            style_rules=style_rules,
            scoped_skills=scoped_skills,
            canonical_facts=canonical_facts,
            previous_payload=previous_payload,
            previous_artifact_revision_id=(latest_artifact.artifact_revision_id if latest_artifact is not None else None),
        )
        delta_payload = _build_object_diff(previous_payload, generated_payload)
        lineage_payload = cast(JSONObject, generated_payload["lineage"])
        reasons = (
            f"loaded {len(style_rules)} style rule(s)",
            f"loaded {len(scoped_skills)} scoped skill(s)",
            f"loaded {len(canonical_facts)} canonical fact(s)",
        )

        if request.target_artifact_object_id is None:
            artifact_revision_id = self.__storage.create_derived_record(
                DerivedRecordInput(
                    family="chapter_artifact",
                    object_id=None,
                    payload=generated_payload,
                    source_scene_revision_id=scene.current_revision_id,
                    created_by=request.actor,
                    source_ref=request.source_ref,
                )
            )
            created_artifact = next(
                artifact
                for artifact in self.list_derived_artifacts("chapter_artifact")
                if artifact.artifact_revision_id == artifact_revision_id
            )
            return SceneToChapterWorkbenchResult(
                disposition="generated",
                scene_object_id=request.scene_object_id,
                source_scene_revision_id=scene.current_revision_id,
                artifact_object_id=created_artifact.object_id,
                artifact_revision_id=artifact_revision_id,
                proposal_id=None,
                review_route=None,
                chapter_payload=generated_payload,
                delta_payload=delta_payload,
                lineage_payload=lineage_payload,
                style_rules=style_rules,
                scoped_skills=scoped_skills,
                canonical_facts=canonical_facts,
                reasons=reasons,
            )

        if request.base_artifact_revision_id is None:
            raise ValueError("base_artifact_revision_id is required when updating an existing chapter artifact")
        base_artifact = self._derived_artifact_by_revision(request.base_artifact_revision_id)
        if base_artifact is None:
            raise ValueError(f"missing base chapter artifact revision {request.base_artifact_revision_id}")
        if base_artifact.object_id != request.target_artifact_object_id:
            raise ValueError("base chapter artifact revision does not belong to target_artifact_object_id")

        mutation_result = self.apply_mutation(
            ServiceMutationRequest(
                target_family="chapter_artifact",
                target_object_id=request.target_artifact_object_id,
                base_revision_id=request.base_artifact_revision_id,
                source_scene_revision_id=scene.current_revision_id,
                base_source_scene_revision_id=base_artifact.source_scene_revision_id,
                payload=generated_payload,
                actor=request.actor,
                source_surface=request.source_surface,
                skill=request.skill_name,
                source_ref=request.source_ref,
                chapter_signals=request.chapter_signals,
            )
        )
        review_route = None
        if mutation_result.disposition == "review_required":
            review_route = self._review_route(project_id=request.project_id, novel_id=request.novel_id)
        return SceneToChapterWorkbenchResult(
            disposition=mutation_result.disposition,
            scene_object_id=request.scene_object_id,
            source_scene_revision_id=scene.current_revision_id,
            artifact_object_id=request.target_artifact_object_id,
            artifact_revision_id=mutation_result.artifact_revision_id,
            proposal_id=mutation_result.proposal_id,
            review_route=review_route,
            chapter_payload=generated_payload,
            delta_payload=delta_payload,
            lineage_payload=lineage_payload,
            style_rules=style_rules,
            scoped_skills=scoped_skills,
            canonical_facts=canonical_facts,
            reasons=mutation_result.reasons if mutation_result.reasons else reasons,
        )

    def generate_outline_to_plot_workbench(
        self,
        request: OutlineToPlotWorkbenchRequest,
    ) -> OutlineToPlotWorkbenchResult:
        # --- 1. Read and validate the parent outline_node ---
        outline_read = self.read_object(
            ReadObjectRequest(family="outline_node", object_id=request.outline_node_object_id)
        )
        if outline_read.head is None:
            raise KeyError(f"outline_node:{request.outline_node_object_id}")
        outline = outline_read.head
        if outline.payload.get("novel_id") != request.novel_id:
            raise ValueError("outline_node does not belong to requested novel_id")

        # --- 2. Stale parent revision check ---
        if (
            request.expected_parent_revision_id is not None
            and outline.current_revision_id != request.expected_parent_revision_id
        ):
            raise ValueError(
                f"outline_node revision is stale; expected {request.expected_parent_revision_id}"
                f" but found {outline.current_revision_id}"
            )

        # --- 2.5. Get novel context and parent outline for AI generation ---
        novel_read = self.read_object(ReadObjectRequest(family="novel", object_id=request.novel_id))
        novel_context: JSONObject = {}
        if novel_read.head is not None:
            novel_context = {
                "title": novel_read.head.payload.get("title", "Untitled"),
                "premise": novel_read.head.payload.get("premise", ""),
                "genre": novel_read.head.payload.get("genre", ""),
            }

        parent_outline_id = outline.payload.get("parent_outline_node_id")
        parent_outline: CanonicalObjectSnapshot | None = None
        if parent_outline_id:
            parent_read = self.read_object(ReadObjectRequest(family="outline_node", object_id=str(parent_outline_id)))
            parent_outline = parent_read.head

        # Get active skills
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        skills = tuple(
            summary for summary in workspace.canonical_objects
            if summary.family == "skill" and summary.payload.get("novel_id") == request.novel_id
        )

        # --- 3. Build the plot_node payload from the outline_node ---
        # Try AI generation for multiple plot nodes
        generated_plots = self._generate_plot_nodes_with_ai(
            outline_node=outline,
            novel_context=novel_context,
            skills=skills,
            parent_outline=parent_outline,
        )

        # For CREATE path, create the first plot node (or a default one if AI failed)
        if generated_plots:
            first_plot = generated_plots[0]
            plot_payload: JSONObject = {
                "novel_id": request.novel_id,
                "outline_node_id": request.outline_node_object_id,
                "title": first_plot.get("title", outline.payload.get("title", "")),
                "summary": first_plot.get("summary", ""),
                "sequence_order": first_plot.get("sequence_order", 1),
                "notes": first_plot.get("notes", ""),
                "source_outline_revision_id": outline.current_revision_id,
                "ai_generated": True,
            }
            reasons = (
                f"AI-generated {len(generated_plots)} plot node(s) from outline",
                f"first plot: {first_plot.get('title', 'Untitled')}",
            )
        else:
            # Fall back to simple copy
            plot_payload = {
                "novel_id": request.novel_id,
                "outline_node_id": request.outline_node_object_id,
                "title": outline.payload.get("title", ""),
                "source_outline_revision_id": outline.current_revision_id,
            }
            reasons = ("created plot_node from outline_node (AI not available)",)

        lineage_payload: JSONObject = {
            "novel_id": request.novel_id,
            "outline_node_id": request.outline_node_object_id,
            "source_outline_revision_id": outline.current_revision_id,
        }

        # --- 4. CREATE path (no target_child_object_id) ---
        if request.target_child_object_id is None:
            write_result = self.__storage.write_canonical_object(
                CanonicalWriteRequest(
                    family="plot_node",
                    payload=plot_payload,
                    actor=request.actor,
                    source_surface=request.source_surface,
                    policy_class=MutationPolicyClass.OUTLINE_STRUCTURED.value,
                    approval_state=MutationDisposition.AUTO_APPLIED.value,
                    source_ref=request.source_ref,
                    revision_reason="generated from outline_node",
                )
            )
            # Create additional plot nodes if AI generated more than one
            additional_plot_ids: list[str] = []
            for i, plot_data in enumerate(generated_plots[1:], 1):
                additional_payload: JSONObject = {
                    "novel_id": request.novel_id,
                    "outline_node_id": request.outline_node_object_id,
                    "title": plot_data.get("title", f"Plot {i}"),
                    "summary": plot_data.get("summary", ""),
                    "sequence_order": plot_data.get("sequence_order", i + 1),
                    "notes": plot_data.get("notes", ""),
                    "source_outline_revision_id": outline.current_revision_id,
                    "ai_generated": True,
                }
                additional_result = self.__storage.write_canonical_object(
                    CanonicalWriteRequest(
                        family="plot_node",
                        payload=additional_payload,
                        actor=request.actor,
                        source_surface=request.source_surface,
                        policy_class=MutationPolicyClass.OUTLINE_STRUCTURED.value,
                        approval_state=MutationDisposition.AUTO_APPLIED.value,
                        source_ref=request.source_ref,
                        revision_reason=f"AI-generated additional plot node {i}",
                    )
                )
                additional_plot_ids.append(additional_result.object_id)

            return OutlineToPlotWorkbenchResult(
                disposition="generated",
                outline_node_object_id=request.outline_node_object_id,
                source_outline_revision_id=outline.current_revision_id,
                child_object_id=write_result.object_id,
                child_revision_id=write_result.revision_id,
                proposal_id=None,
                review_route=None,
                plot_payload=plot_payload,
                delta_payload={},
                lineage_payload=lineage_payload,
                reasons=reasons + (f"created {len(additional_plot_ids)} additional plot node(s)",) if additional_plot_ids else reasons,
                additional_plot_ids=tuple(additional_plot_ids) if additional_plot_ids else None,
            )

        # --- 5. UPDATE path (target_child_object_id is set) ---
        if request.base_child_revision_id is None:
            raise ValueError(
                "base_child_revision_id is required when updating an existing plot_node"
            )

        # Drift check: verify the base revision matches the current head
        target_read = self.read_object(
            ReadObjectRequest(family="plot_node", object_id=request.target_child_object_id)
        )
        if target_read.head is None:
            raise KeyError(f"plot_node:{request.target_child_object_id}")
        if target_read.head.current_revision_id != request.base_child_revision_id:
            raise ValueError(
                f"plot_node revision drift; expected base {request.base_child_revision_id}"
                f" but head is {target_read.head.current_revision_id}"
            )

        previous_payload = target_read.head.payload
        delta_payload = _build_object_diff(previous_payload, plot_payload)

        # Route through mutation policy engine (OUTLINE_STRUCTURED → review_required)
        mutation_result = self.apply_mutation(
            ServiceMutationRequest(
                target_family="plot_node",
                target_object_id=request.target_child_object_id,
                base_revision_id=request.base_child_revision_id,
                payload=plot_payload,
                actor=request.actor,
                source_surface=request.source_surface,
                source_ref=request.source_ref,
            )
        )

        review_route = None
        if mutation_result.disposition == "review_required":
            review_route = self._review_route(
                project_id=request.project_id, novel_id=request.novel_id
            )

        return OutlineToPlotWorkbenchResult(
            disposition=mutation_result.disposition,
            outline_node_object_id=request.outline_node_object_id,
            source_outline_revision_id=outline.current_revision_id,
            child_object_id=request.target_child_object_id,
            child_revision_id=mutation_result.canonical_revision_id,
            proposal_id=mutation_result.proposal_id,
            review_route=review_route,
            plot_payload=plot_payload,
            delta_payload=delta_payload,
            lineage_payload=lineage_payload,
            reasons=mutation_result.reasons if mutation_result.reasons else ("updated plot_node",),
            additional_plot_ids=None,
        )

    def generate_plot_to_event_workbench(
        self,
        request: PlotToEventWorkbenchRequest,
    ) -> PlotToEventWorkbenchResult:
        # --- 1. Read and validate the parent plot_node ---
        plot_read = self.read_object(
            ReadObjectRequest(family="plot_node", object_id=request.plot_node_object_id)
        )
        if plot_read.head is None:
            raise KeyError(f"plot_node:{request.plot_node_object_id}")
        plot_node = plot_read.head
        if plot_node.payload.get("novel_id") != request.novel_id:
            raise ValueError("plot_node does not belong to requested novel_id")

        # --- 2. Stale parent revision check ---
        if (
            request.expected_parent_revision_id is not None
            and plot_node.current_revision_id != request.expected_parent_revision_id
        ):
            raise ValueError(
                f"plot_node revision is stale; expected {request.expected_parent_revision_id}"
                f" but found {plot_node.current_revision_id}"
            )

        # --- 2.5. Get context for AI generation ---
        novel_read = self.read_object(ReadObjectRequest(family="novel", object_id=request.novel_id))
        novel_context: JSONObject = {}
        if novel_read.head is not None:
            novel_context = {
                "title": novel_read.head.payload.get("title", "Untitled"),
                "premise": novel_read.head.payload.get("premise", ""),
                "genre": novel_read.head.payload.get("genre", ""),
            }

        outline_node_id = plot_node.payload.get("outline_node_id")
        outline_context: CanonicalObjectSnapshot | None = None
        if outline_node_id:
            outline_read = self.read_object(ReadObjectRequest(family="outline_node", object_id=str(outline_node_id)))
            outline_context = outline_read.head

        # Get active skills
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        skills = tuple(
            summary for summary in workspace.canonical_objects
            if summary.family == "skill" and summary.payload.get("novel_id") == request.novel_id
        )

        # --- 3. Build the event payload from the plot_node ---
        # Try AI generation for multiple events
        generated_events = self._generate_events_with_ai(
            plot_node=plot_node,
            novel_context=novel_context,
            outline_context=outline_context,  # type: ignore
            skills=skills,
        )

        if generated_events:
            first_event = generated_events[0]
            event_payload: JSONObject = {
                "novel_id": request.novel_id,
                "plot_node_id": request.plot_node_object_id,
                "title": first_event.get("title", plot_node.payload.get("title", "")),
                "description": first_event.get("description", ""),
                "sequence_order": first_event.get("sequence_order", 1),
                "location": first_event.get("location", ""),
                "characters_involved": first_event.get("characters_involved", []),
                "source_plot_revision_id": plot_node.current_revision_id,
                "ai_generated": True,
            }
            reasons = (
                f"AI-generated {len(generated_events)} event(s) from plot",
                f"first event: {first_event.get('title', 'Untitled')}",
            )
        else:
            event_payload = {
                "novel_id": request.novel_id,
                "plot_node_id": request.plot_node_object_id,
                "title": plot_node.payload.get("title", ""),
                "source_plot_revision_id": plot_node.current_revision_id,
            }
            reasons = ("created event from plot_node (AI not available)",)

        lineage_payload: JSONObject = {
            "novel_id": request.novel_id,
            "plot_node_id": request.plot_node_object_id,
            "source_plot_revision_id": plot_node.current_revision_id,
        }

        # --- 4. CREATE path (no target_child_object_id) ---
        if request.target_child_object_id is None:
            write_result = self.__storage.write_canonical_object(
                CanonicalWriteRequest(
                    family="event",
                    payload=event_payload,
                    actor=request.actor,
                    source_surface=request.source_surface,
                    policy_class=MutationPolicyClass.OUTLINE_STRUCTURED.value,
                    approval_state=MutationDisposition.AUTO_APPLIED.value,
                    source_ref=request.source_ref,
                    revision_reason="generated from plot_node",
                )
            )
            # Create additional events if AI generated more than one
            additional_event_ids: list[str] = []
            for i, event_data in enumerate(generated_events[1:], 1):
                additional_payload: JSONObject = {
                    "novel_id": request.novel_id,
                    "plot_node_id": request.plot_node_object_id,
                    "title": event_data.get("title", f"Event {i}"),
                    "description": event_data.get("description", ""),
                    "sequence_order": event_data.get("sequence_order", i + 1),
                    "location": event_data.get("location", ""),
                    "characters_involved": event_data.get("characters_involved", []),
                    "source_plot_revision_id": plot_node.current_revision_id,
                    "ai_generated": True,
                }
                additional_result = self.__storage.write_canonical_object(
                    CanonicalWriteRequest(
                        family="event",
                        payload=additional_payload,
                        actor=request.actor,
                        source_surface=request.source_surface,
                        policy_class=MutationPolicyClass.OUTLINE_STRUCTURED.value,
                        approval_state=MutationDisposition.AUTO_APPLIED.value,
                        source_ref=request.source_ref,
                        revision_reason=f"AI-generated additional event {i}",
                    )
                )
                additional_event_ids.append(additional_result.object_id)

            return PlotToEventWorkbenchResult(
                disposition="generated",
                plot_node_object_id=request.plot_node_object_id,
                source_plot_revision_id=plot_node.current_revision_id,
                child_object_id=write_result.object_id,
                child_revision_id=write_result.revision_id,
                proposal_id=None,
                review_route=None,
                event_payload=event_payload,
                delta_payload={},
                lineage_payload=lineage_payload,
                reasons=reasons + (f"created {len(additional_event_ids)} additional event(s)",) if additional_event_ids else reasons,
                additional_event_ids=tuple(additional_event_ids) if additional_event_ids else None,
            )

        # --- 5. UPDATE path (target_child_object_id is set) ---
        if request.base_child_revision_id is None:
            raise ValueError(
                "base_child_revision_id is required when updating an existing event"
            )

        # Drift check: verify the base revision matches the current head
        target_read = self.read_object(
            ReadObjectRequest(family="event", object_id=request.target_child_object_id)
        )
        if target_read.head is None:
            raise KeyError(f"event:{request.target_child_object_id}")
        if target_read.head.current_revision_id != request.base_child_revision_id:
            raise ValueError(
                f"event revision drift; expected base {request.base_child_revision_id}"
                f" but head is {target_read.head.current_revision_id}"
            )

        previous_payload = target_read.head.payload
        delta_payload = _build_object_diff(previous_payload, event_payload)

        # Route through mutation policy engine (OUTLINE_STRUCTURED → review_required)
        mutation_result = self.apply_mutation(
            ServiceMutationRequest(
                target_family="event",
                target_object_id=request.target_child_object_id,
                base_revision_id=request.base_child_revision_id,
                payload=event_payload,
                actor=request.actor,
                source_surface=request.source_surface,
                source_ref=request.source_ref,
            )
        )

        review_route = None
        if mutation_result.disposition == "review_required":
            review_route = self._review_route(
                project_id=request.project_id, novel_id=request.novel_id
            )

        return PlotToEventWorkbenchResult(
            disposition=mutation_result.disposition,
            plot_node_object_id=request.plot_node_object_id,
            source_plot_revision_id=plot_node.current_revision_id,
            child_object_id=request.target_child_object_id,
            child_revision_id=mutation_result.canonical_revision_id,
            proposal_id=mutation_result.proposal_id,
            review_route=review_route,
            event_payload=event_payload,
            delta_payload=delta_payload,
            lineage_payload=lineage_payload,
            reasons=mutation_result.reasons if mutation_result.reasons else ("updated event",),
            additional_event_ids=None,
        )

    def generate_event_to_scene_workbench(
        self,
        request: EventToSceneWorkbenchRequest,
    ) -> EventToSceneWorkbenchResult:
        # --- 1. Read and validate the parent event ---
        event_read = self.read_object(
            ReadObjectRequest(family="event", object_id=request.event_object_id)
        )
        if event_read.head is None:
            raise KeyError(f"event:{request.event_object_id}")
        event = event_read.head
        if event.payload.get("novel_id") != request.novel_id:
            raise ValueError("event does not belong to requested novel_id")

        # --- 2. Stale parent revision check ---
        if (
            request.expected_parent_revision_id is not None
            and event.current_revision_id != request.expected_parent_revision_id
        ):
            raise ValueError(
                f"event revision is stale; expected {request.expected_parent_revision_id}"
                f" but found {event.current_revision_id}"
            )

        # --- 2.5. Get context for AI generation ---
        novel_read = self.read_object(ReadObjectRequest(family="novel", object_id=request.novel_id))
        novel_context: JSONObject = {}
        if novel_read.head is not None:
            novel_context = {
                "title": novel_read.head.payload.get("title", "Untitled"),
                "premise": novel_read.head.payload.get("premise", ""),
                "genre": novel_read.head.payload.get("genre", ""),
            }

        plot_node_id = event.payload.get("plot_node_id")
        plot_context: CanonicalObjectSnapshot | None = None
        if plot_node_id:
            plot_read = self.read_object(ReadObjectRequest(family="plot_node", object_id=str(plot_node_id)))
            plot_context = plot_read.head

        # Get active skills, characters, and settings
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        skills = tuple(
            summary for summary in workspace.canonical_objects
            if summary.family == "skill" and summary.payload.get("novel_id") == request.novel_id
        )
        characters = tuple(
            summary for summary in workspace.canonical_objects
            if summary.family == "character" and summary.payload.get("novel_id") == request.novel_id
        )
        settings = tuple(
            summary for summary in workspace.canonical_objects
            if summary.family == "setting" and summary.payload.get("novel_id") == request.novel_id
        )

        # --- 3. Build the scene payload from the event ---
        # Try AI generation for multiple scenes
        generated_scenes = self._generate_scenes_with_ai(
            event=event,
            novel_context=novel_context,
            plot_context=plot_context,  # type: ignore
            skills=skills,
            characters=characters,
            settings=settings,
        )

        if generated_scenes:
            first_scene = generated_scenes[0]
            scene_payload: JSONObject = {
                "novel_id": request.novel_id,
                "event_id": request.event_object_id,
                "title": first_scene.get("title", event.payload.get("title", "")),
                "setting": first_scene.get("setting", ""),
                "pov_character": first_scene.get("pov_character", ""),
                "characters_present": first_scene.get("characters_present", []),
                "summary": first_scene.get("scene_summary", ""),
                "beat_breakdown": first_scene.get("beat_breakdown", []),
                "source_event_revision_id": event.current_revision_id,
                "ai_generated": True,
            }
            reasons = (
                f"AI-generated {len(generated_scenes)} scene(s) from event",
                f"first scene: {first_scene.get('title', 'Untitled')}",
            )
        else:
            scene_payload = {
                "novel_id": request.novel_id,
                "event_id": request.event_object_id,
                "title": event.payload.get("title", ""),
                "source_event_revision_id": event.current_revision_id,
            }
            reasons = ("created scene from event (AI not available)",)

        lineage_payload: JSONObject = {
            "novel_id": request.novel_id,
            "event_id": request.event_object_id,
            "source_event_revision_id": event.current_revision_id,
        }

        # --- 4. CREATE path (no target_child_object_id) ---
        if request.target_child_object_id is None:
            write_result = self.__storage.write_canonical_object(
                CanonicalWriteRequest(
                    family="scene",
                    payload=scene_payload,
                    actor=request.actor,
                    source_surface=request.source_surface,
                    policy_class=MutationPolicyClass.SCENE_STRUCTURED.value,
                    approval_state=MutationDisposition.AUTO_APPLIED.value,
                    source_ref=request.source_ref,
                    revision_reason="generated from event",
                )
            )
            # Create additional scenes if AI generated more than one
            additional_scene_ids: list[str] = []
            for i, scene_data in enumerate(generated_scenes[1:], 1):
                additional_payload: JSONObject = {
                    "novel_id": request.novel_id,
                    "event_id": request.event_object_id,
                    "title": scene_data.get("title", f"Scene {i}"),
                    "setting": scene_data.get("setting", ""),
                    "pov_character": scene_data.get("pov_character", ""),
                    "characters_present": scene_data.get("characters_present", []),
                    "summary": scene_data.get("scene_summary", ""),
                    "beat_breakdown": scene_data.get("beat_breakdown", []),
                    "source_event_revision_id": event.current_revision_id,
                    "ai_generated": True,
                }
                additional_result = self.__storage.write_canonical_object(
                    CanonicalWriteRequest(
                        family="scene",
                        payload=additional_payload,
                        actor=request.actor,
                        source_surface=request.source_surface,
                        policy_class=MutationPolicyClass.SCENE_STRUCTURED.value,
                        approval_state=MutationDisposition.AUTO_APPLIED.value,
                        source_ref=request.source_ref,
                        revision_reason=f"AI-generated additional scene {i}",
                    )
                )
                additional_scene_ids.append(additional_result.object_id)

            return EventToSceneWorkbenchResult(
                disposition="generated",
                event_object_id=request.event_object_id,
                source_event_revision_id=event.current_revision_id,
                child_object_id=write_result.object_id,
                child_revision_id=write_result.revision_id,
                proposal_id=None,
                review_route=None,
                scene_payload=scene_payload,
                delta_payload={},
                lineage_payload=lineage_payload,
                reasons=reasons + (f"created {len(additional_scene_ids)} additional scene(s)",) if additional_scene_ids else reasons,
                additional_scene_ids=tuple(additional_scene_ids) if additional_scene_ids else None,
            )

        # --- 5. UPDATE path (target_child_object_id is set) ---
        if request.base_child_revision_id is None:
            raise ValueError(
                "base_child_revision_id is required when updating an existing scene"
            )

        # Drift check: verify the base revision matches the current head
        target_read = self.read_object(
            ReadObjectRequest(family="scene", object_id=request.target_child_object_id)
        )
        if target_read.head is None:
            raise KeyError(f"scene:{request.target_child_object_id}")
        if target_read.head.current_revision_id != request.base_child_revision_id:
            raise ValueError(
                f"scene revision drift; expected base {request.base_child_revision_id}"
                f" but head is {target_read.head.current_revision_id}"
            )

        previous_payload = target_read.head.payload
        delta_payload = _build_object_diff(previous_payload, scene_payload)

        # Route through mutation policy engine (SCENE_STRUCTURED → review_required)
        mutation_result = self.apply_mutation(
            ServiceMutationRequest(
                target_family="scene",
                target_object_id=request.target_child_object_id,
                base_revision_id=request.base_child_revision_id,
                payload=scene_payload,
                actor=request.actor,
                source_surface=request.source_surface,
                source_ref=request.source_ref,
            )
        )

        review_route = None
        if mutation_result.disposition == "review_required":
            review_route = self._review_route(
                project_id=request.project_id, novel_id=request.novel_id
            )

        return EventToSceneWorkbenchResult(
            disposition=mutation_result.disposition,
            event_object_id=request.event_object_id,
            source_event_revision_id=event.current_revision_id,
            child_object_id=request.target_child_object_id,
            child_revision_id=mutation_result.canonical_revision_id,
            proposal_id=mutation_result.proposal_id,
            review_route=review_route,
            scene_payload=scene_payload,
            delta_payload=delta_payload,
            lineage_payload=lineage_payload,
            reasons=mutation_result.reasons if mutation_result.reasons else ("updated scene",),
            additional_scene_ids=None,
        )

    def import_from_donor(self, request: ImportRequest) -> ImportResult:
        if request.donor_key is SupportedDonor.WEBNOVEL_WRITER:
            return self._import_webnovel_project_root(request.source_path, actor=request.actor)
        if request.project_id is None or request.novel_id is None:
            raise ValueError("restored-decompiled-artifacts import requires project_id and novel_id")
        return self._import_character_export(
            request.source_path,
            project_id=request.project_id,
            novel_id=request.novel_id,
            actor=request.actor,
        )

    def _import_webnovel_project_root(self, source_path: Path, *, actor: str) -> ImportResult:
        parsed = load_project_root_import_data(source_path)
        imported_objects: list[ImportedObjectRecord] = []

        project_result = self.__storage.write_canonical_object(
            CanonicalWriteRequest(
                family="project",
                payload={
                    "title": parsed.project_title,
                    "donor_project_id": parsed.donor_project_id,
                },
                actor=actor,
                created_by=actor,
                source_surface=WEBNOVEL_WRITER_SOURCE_SURFACE,
                source_ref=str(parsed.state_path),
                ingest_run_id=parsed.ingest_run_id,
                policy_class="import_contract:webnovel_writer",
                approval_state="imported",
                revision_reason="imported donor project root",
            )
        )
        imported_objects.append(
            ImportedObjectRecord(
                family="project",
                object_id=project_result.object_id,
                revision_id=project_result.revision_id,
                source_ref=str(parsed.state_path),
            )
        )

        novel_result = self.__storage.write_canonical_object(
            CanonicalWriteRequest(
                family="novel",
                payload={
                    "project_id": project_result.object_id,
                    "title": parsed.novel_title,
                    "genre": parsed.genre,
                    "donor_novel_id": parsed.donor_novel_id,
                },
                actor=actor,
                created_by=actor,
                source_surface=WEBNOVEL_WRITER_SOURCE_SURFACE,
                source_ref=str(parsed.state_path),
                ingest_run_id=parsed.ingest_run_id,
                policy_class="import_contract:webnovel_writer",
                approval_state="imported",
                revision_reason="imported donor novel state",
            )
        )
        imported_objects.append(
            ImportedObjectRecord(
                family="novel",
                object_id=novel_result.object_id,
                revision_id=novel_result.revision_id,
                source_ref=str(parsed.state_path),
            )
        )

        scene_revision_ids: dict[str, tuple[str, str]] = {}
        for scene in parsed.scenes:
            scene_result = self.__storage.write_canonical_object(
                CanonicalWriteRequest(
                    family="scene",
                    payload={
                        "novel_id": novel_result.object_id,
                        "event_id": scene.event_id,
                        "title": scene.title,
                        "summary": scene.summary,
                        "donor_scene_id": scene.donor_scene_id,
                    },
                    actor=actor,
                    created_by=actor,
                    source_surface=WEBNOVEL_WRITER_SOURCE_SURFACE,
                    source_ref=scene.source_ref,
                    ingest_run_id=parsed.ingest_run_id,
                    policy_class="import_contract:webnovel_writer",
                    approval_state="imported",
                    revision_reason="imported donor scene",
                )
            )
            scene_revision_ids[scene.donor_scene_id] = (scene_result.object_id, scene_result.revision_id)
            imported_objects.append(
                ImportedObjectRecord(
                    family="scene",
                    object_id=scene_result.object_id,
                    revision_id=scene_result.revision_id,
                    source_ref=scene.source_ref,
                )
            )

        for chapter in parsed.chapters:
            scene_link = scene_revision_ids.get(chapter.donor_scene_id)
            if scene_link is None:
                raise ValueError(
                    f"Chapter import requires an imported scene for donor scene id {chapter.donor_scene_id}"
                )
            scene_object_id, scene_revision_id = scene_link
            export_payload: JSONObject = {
                "novel_id": novel_result.object_id,
                "source_scene_id": scene_object_id,
                "source_scene_revision_id": scene_revision_id,
                "chapter_title": chapter.chapter_title,
                "body": chapter.body,
                "source_kind": WEBNOVEL_WRITER_SOURCE_SURFACE,
                "source_ref": chapter.source_ref,
                "ingest_run_id": parsed.ingest_run_id,
            }
            artifact_result = self._create_derived_artifact(
                family="chapter_artifact",
                payload=export_payload,
                source_scene_revision_id=scene_revision_id,
                actor=actor,
                object_id=None,
                source_ref=chapter.source_ref,
                ingest_run_id=parsed.ingest_run_id,
            )
            imported_objects.append(
                ImportedObjectRecord(
                    family="chapter_artifact",
                    object_id=artifact_result.object_id,
                    revision_id=artifact_result.artifact_revision_id,
                    source_ref=chapter.source_ref,
                )
            )

        import_record_id = self.__storage.create_import_record(
            ImportRecordInput(
                project_id=project_result.object_id,
                created_by=actor,
                import_source=WEBNOVEL_WRITER_CONTRACT.donor_key,
                import_payload={
                    "donor_owner": WEBNOVEL_WRITER_CONTRACT.donor_owner,
                    "target_owner": WEBNOVEL_WRITER_CONTRACT.target_owner,
                    "trust_level": WEBNOVEL_WRITER_CONTRACT.trust_level.value,
                    "input_only": WEBNOVEL_WRITER_CONTRACT.input_only,
                    "source_root": str(parsed.source_root),
                    "artifacts": [contract.path_hint for contract in WEBNOVEL_WRITER_CONTRACT.supported_artifacts],
                    "ingest_run_id": parsed.ingest_run_id,
                    "imported": [
                        {
                            "family": row.family,
                            "object_id": row.object_id,
                            "revision_id": row.revision_id,
                            "source_ref": row.source_ref,
                        }
                        for row in imported_objects
                    ],
                },
            )
        )
        return ImportResult(
            donor_key=WEBNOVEL_WRITER_CONTRACT.donor_key,
            ingest_run_id=parsed.ingest_run_id,
            import_record_id=import_record_id,
            project_id=project_result.object_id,
            imported_objects=tuple(self._import_object_result(row) for row in imported_objects),
        )

    def _import_character_export(
        self,
        source_path: Path,
        *,
        project_id: str,
        novel_id: str,
        actor: str,
    ) -> ImportResult:
        parsed = load_character_export_import_data(source_path)
        imported_objects: list[ImportedObjectRecord] = []
        for row in parsed.rows:
            result = self.__storage.write_canonical_object(
                CanonicalWriteRequest(
                    family="character",
                    payload={
                        "novel_id": novel_id,
                        "name": row.name,
                        "role": row.role,
                        "description": row.description,
                        "personality": row.personality,
                        "background": row.background,
                        "donor_character_id": row.donor_character_id,
                        "revalidated_from_decompiled_export": True,
                    },
                    actor=actor,
                    created_by=actor,
                    source_surface=FANBIANYI_SOURCE_SURFACE,
                    source_ref=row.source_ref,
                    ingest_run_id=parsed.ingest_run_id,
                    policy_class="import_contract:restored_decompiled_artifacts",
                    approval_state="imported",
                    revision_reason="imported donor character export",
                )
            )
            imported_objects.append(
                ImportedObjectRecord(
                    family="character",
                    object_id=result.object_id,
                    revision_id=result.revision_id,
                    source_ref=row.source_ref,
                )
            )

        import_record_id = self.__storage.create_import_record(
            ImportRecordInput(
                project_id=project_id,
                created_by=actor,
                import_source=FANBIANYI_CONTRACT.donor_key,
                import_payload={
                    "donor_owner": FANBIANYI_CONTRACT.donor_owner,
                    "target_owner": FANBIANYI_CONTRACT.target_owner,
                    "trust_level": FANBIANYI_CONTRACT.trust_level.value,
                    "input_only": FANBIANYI_CONTRACT.input_only,
                    "source_path": str(parsed.source_path),
                    "ingest_run_id": parsed.ingest_run_id,
                    "imported": [
                        {
                            "family": row.family,
                            "object_id": row.object_id,
                            "revision_id": row.revision_id,
                            "source_ref": row.source_ref,
                        }
                        for row in imported_objects
                    ],
                    "forbidden_runtime_dependencies": list(FANBIANYI_CONTRACT.forbidden_runtime_dependencies),
                },
            )
        )
        return ImportResult(
            donor_key=FANBIANYI_CONTRACT.donor_key,
            ingest_run_id=parsed.ingest_run_id,
            import_record_id=import_record_id,
            project_id=project_id,
            imported_objects=tuple(self._import_object_result(row) for row in imported_objects),
        )

    def execute_skill(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        mutation_result: ServiceMutationResult | None = None
        export_result: ExportArtifactResult | None = None
        if request.mutation_request is not None:
            mutation_result = self.apply_mutation(
                ServiceMutationRequest(
                    target_family=request.mutation_request.target_family,
                    target_object_id=request.mutation_request.target_object_id,
                    base_revision_id=request.mutation_request.base_revision_id,
                    source_scene_revision_id=request.mutation_request.source_scene_revision_id,
                    base_source_scene_revision_id=request.mutation_request.base_source_scene_revision_id,
                    payload=request.mutation_request.payload,
                    actor=request.actor,
                    source_surface=request.source_surface,
                    skill=request.skill_name,
                    source_ref=request.mutation_request.source_ref,
                    ingest_run_id=request.mutation_request.ingest_run_id,
                    revision_reason=request.mutation_request.revision_reason,
                    revision_source_message_id=request.mutation_request.revision_source_message_id,
                    chapter_signals=request.mutation_request.chapter_signals,
                )
            )
        if request.export_request is not None:
            export_payload = dict(request.export_request.payload)
            export_payload["skill_name"] = request.skill_name
            export_result = self.create_export_artifact(
                ExportArtifactRequest(
                    actor=request.actor,
                    source_surface=request.source_surface,
                    source_scene_revision_id=request.export_request.source_scene_revision_id,
                    payload=export_payload,
                    object_id=request.export_request.object_id,
                    source_ref=request.export_request.source_ref,
                    ingest_run_id=request.export_request.ingest_run_id,
                )
            )
        if mutation_result is None and export_result is None:
            raise ValueError("skill execution requires a typed mutation_request or export_request")
        return SkillExecutionResult(
            skill_name=request.skill_name,
            mutation_result=mutation_result,
            export_result=export_result,
        )

    def _review_proposal_snapshot_from_row(self, row: dict[str, str | JSONObject | None]) -> ReviewProposalSnapshot:
        return ReviewProposalSnapshot(
            proposal_id=str(row["record_id"]),
            target_family=str(row["target_family"]),
            target_object_id=str(row["target_object_id"]),
            base_revision_id=cast(str | None, row["base_revision_id"]),
            proposal_payload=cast(JSONObject, row["proposal_payload"]),
            created_by=str(row["created_by"]),
            created_at=str(row["created_at"]),
        )

    def _review_decision_snapshot_from_row(self, row: dict[str, str | JSONObject | None]) -> ReviewDecisionSnapshot:
        return ReviewDecisionSnapshot(
            approval_record_id=str(row["record_id"]),
            proposal_id=str(row["proposal_id"]),
            approval_state=str(row["approval_state"]),
            mutation_record_id=cast(str | None, row["mutation_record_id"]),
            decision_payload=cast(JSONObject, row["decision_payload"]),
            created_by=str(row["created_by"]),
            created_at=str(row["created_at"]),
        )

    def _review_proposal_by_id(self, proposal_id: str) -> ReviewProposalSnapshot | None:
        for proposal in self.list_review_proposals(ListReviewProposalsRequest(include_resolved=True)).proposals:
            if proposal.proposal_id == proposal_id:
                return proposal
        return None

    def _proposal_decisions(self, proposal_id: str) -> tuple[ReviewDecisionSnapshot, ...]:
        return tuple(
            self._review_decision_snapshot_from_row(row)
            for row in self.__storage.fetch_approval_records(proposal_id=proposal_id)
        )

    def _proposal_latest_state(self, proposal_id: str) -> str:
        decisions = self._proposal_decisions(proposal_id)
        return decisions[-1].approval_state if decisions else "pending"

    def _normalize_review_state(self, state: str) -> str:
        normalized = state.strip().lower()
        if normalized in {"approved", "reject", "rejected", "revise", "revision_requested", "stale"}:
            if normalized == "reject":
                return "rejected"
            if normalized == "revise":
                return "revision_requested"
            return normalized
        raise ValueError(f"Unsupported review transition state: {state}")

    def _review_state_is_resolved(self, state: str) -> bool:
        return state in {"approved", "rejected"}

    def _merge_decision_payload(self, primary: JSONObject | None, extras: JSONObject) -> JSONObject:
        payload: JSONObject = dict(primary or {})
        payload.update(extras)
        return payload

    def _approved_replay_result(self, proposal_id: str) -> ReviewTransitionResult | None:
        for decision in reversed(self._proposal_decisions(proposal_id)):
            if decision.approval_state != "approved":
                continue
            return ReviewTransitionResult(
                approval_record_id=decision.approval_record_id,
                proposal_id=proposal_id,
                approval_state="approved",
                mutation_record_id=decision.mutation_record_id,
                resolution="already_applied",
                canonical_revision_id=self._payload_text_value(decision.decision_payload, "canonical_revision_id"),
                artifact_revision_id=self._payload_text_value(decision.decision_payload, "artifact_revision_id"),
            )
        return None

    def _apply_review_proposal(self, proposal: ReviewProposalSnapshot, *, actor: str) -> _AppliedReviewMutation:
        payload = proposal.proposal_payload
        requested_payload = self._requested_payload(payload)
        if proposal.target_family == "chapter_artifact":
            source_scene_revision_id = self._payload_text_value(payload, "source_scene_revision_id")
            if source_scene_revision_id is None:
                raise ValueError("chapter artifact proposal is missing source_scene_revision_id")
            artifact_revision_id = self.__storage.create_derived_record(
                DerivedRecordInput(
                    family="chapter_artifact",
                    object_id=proposal.target_object_id,
                    payload=requested_payload,
                    source_scene_revision_id=source_scene_revision_id,
                    created_by=actor,
                    source_ref=f"proposal:{proposal.proposal_id}",
                )
            )
            return _AppliedReviewMutation(artifact_revision_id=artifact_revision_id)

        write_result = self.__storage.write_canonical_object(
            CanonicalWriteRequest(
                family=proposal.target_family,
                object_id=proposal.target_object_id,
                payload=requested_payload,
                actor=actor,
                source_surface="review_desk",
                policy_class=str(payload.get("policy_class", "review_resolution")),
                approval_state="approved",
                skill=self._payload_text_value(payload, "skill"),
                source_ref=f"proposal:{proposal.proposal_id}",
                revision_reason=f"apply review proposal {proposal.proposal_id}",
            )
        )
        return _AppliedReviewMutation(
            mutation_record_id=write_result.mutation_record_id,
            canonical_revision_id=write_result.revision_id,
        )

    def _requested_payload(self, proposal_payload: JSONObject) -> JSONObject:
        wrapped_payload = proposal_payload.get("payload")
        if not isinstance(wrapped_payload, dict):
            return {}
        requested_payload = wrapped_payload.get("requested_payload")
        if not isinstance(requested_payload, dict):
            return {}
        return cast(JSONObject, requested_payload)

    def _proposal_reasons(self, proposal_payload: JSONObject) -> tuple[str, ...]:
        reasons = proposal_payload.get("reasons")
        if not isinstance(reasons, list):
            return ()
        return tuple(str(reason) for reason in reasons if isinstance(reason, str) and reason.strip())

    def _proposal_drift_details(self, proposal: ReviewProposalSnapshot) -> JSONObject:
        if proposal.target_family == "chapter_artifact":
            return self._chapter_proposal_drift_details(proposal)
        return self._canonical_proposal_drift_details(proposal)

    def _canonical_proposal_drift_details(self, proposal: ReviewProposalSnapshot) -> JSONObject:
        if proposal.base_revision_id is None:
            return {}
        target = self.read_object(ReadObjectRequest(family=proposal.target_family, object_id=proposal.target_object_id))
        if target.head is None:
            return {
                "kind": "missing_target",
                "target_family": proposal.target_family,
                "target_object_id": proposal.target_object_id,
            }
        if target.head.current_revision_id == proposal.base_revision_id:
            return {}
        return {
            "kind": "canonical_revision_drift",
            "expected_base_revision_id": proposal.base_revision_id,
            "current_revision_id": target.head.current_revision_id,
        }

    def _chapter_proposal_drift_details(self, proposal: ReviewProposalSnapshot) -> JSONObject:
        details: JSONObject = {}
        latest_artifact = self._latest_artifact_for_object_id(proposal.target_object_id)
        if latest_artifact is None:
            details["target_artifact"] = {
                "kind": "missing_target",
                "target_object_id": proposal.target_object_id,
            }
            return details
        if proposal.base_revision_id is not None and latest_artifact.artifact_revision_id != proposal.base_revision_id:
            details["target_artifact"] = {
                "kind": "artifact_revision_drift",
                "expected_base_revision_id": proposal.base_revision_id,
                "current_revision_id": latest_artifact.artifact_revision_id,
            }

        requested_payload = self._requested_payload(proposal.proposal_payload)
        source_scene_id = self._payload_text_value(requested_payload, "source_scene_id")
        pinned_scene_revision_id = self._payload_text_value(proposal.proposal_payload, "source_scene_revision_id")
        if source_scene_id is not None and pinned_scene_revision_id is not None:
            scene = self.read_object(ReadObjectRequest(family="scene", object_id=source_scene_id))
            if scene.head is None:
                details["source_scene"] = {
                    "kind": "missing_source_scene",
                    "source_scene_id": source_scene_id,
                }
            elif scene.head.current_revision_id != pinned_scene_revision_id:
                details["source_scene"] = {
                    "kind": "source_scene_revision_drift",
                    "source_scene_id": source_scene_id,
                    "expected_revision_id": pinned_scene_revision_id,
                    "current_revision_id": scene.head.current_revision_id,
                }
        return details

    def _build_review_desk_proposal_snapshot(self, proposal: ReviewProposalSnapshot) -> ReviewDeskProposalSnapshot:
        decisions = self._proposal_decisions(proposal.proposal_id)
        current_payload, current_revision_id, base_payload, revision_lineage = self._proposal_payload_context(proposal)
        requested_payload = self._requested_payload(proposal.proposal_payload)
        drift_details = self._proposal_drift_details(proposal)
        reasons = self._proposal_reasons(proposal.proposal_payload)
        raw_state = decisions[-1].approval_state if decisions else "pending"
        approval_state = "stale" if drift_details and raw_state in {"pending", "revision_requested", "stale"} else raw_state
        return ReviewDeskProposalSnapshot(
            proposal_id=proposal.proposal_id,
            target_family=proposal.target_family,
            target_object_id=proposal.target_object_id,
            target_title=self._review_target_title(proposal, requested_payload, current_payload),
            source_surface=str(proposal.proposal_payload.get("source_surface", "review")),
            policy_class=str(proposal.proposal_payload.get("policy_class", "review_required")),
            base_revision_id=proposal.base_revision_id,
            current_revision_id=current_revision_id,
            created_by=proposal.created_by,
            created_at=proposal.created_at,
            approval_state=approval_state,
            approval_state_detail=self._review_state_detail(approval_state, decisions, drift_details),
            is_stale=bool(drift_details),
            reasons=reasons,
            requested_payload=requested_payload,
            current_payload=current_payload,
            structured_diff=_build_object_diff(base_payload, requested_payload),
            prose_diff=self._render_prose_diff(base_payload, requested_payload),
            revision_lineage=revision_lineage,
            drift_details=drift_details,
            decisions=decisions,
        )

    def _proposal_payload_context(
        self,
        proposal: ReviewProposalSnapshot,
    ) -> tuple[JSONObject, str | None, JSONObject, JSONObject]:
        if proposal.target_family == "chapter_artifact":
            latest_artifact = self._latest_artifact_for_object_id(proposal.target_object_id)
            base_artifact = (
                self._derived_artifact_by_revision(proposal.base_revision_id)
                if proposal.base_revision_id is not None
                else latest_artifact
            )
            current_payload = latest_artifact.payload if latest_artifact is not None else {}
            base_payload = base_artifact.payload if base_artifact is not None else {}
            requested_payload = self._requested_payload(proposal.proposal_payload)
            return (
                current_payload,
                latest_artifact.artifact_revision_id if latest_artifact is not None else None,
                base_payload,
                {
                    "target_object_id": proposal.target_object_id,
                    "base_artifact_revision_id": proposal.base_revision_id,
                    "current_artifact_revision_id": latest_artifact.artifact_revision_id if latest_artifact is not None else None,
                    "source_scene_id": requested_payload.get("source_scene_id"),
                    "pinned_source_scene_revision_id": proposal.proposal_payload.get("source_scene_revision_id"),
                    "current_source_scene_revision_id": latest_artifact.source_scene_revision_id if latest_artifact is not None else None,
                },
            )

        target = self.read_object(ReadObjectRequest(family=proposal.target_family, object_id=proposal.target_object_id, include_revisions=True))
        current_payload = target.head.payload if target.head is not None else {}
        base_payload = current_payload
        for revision in target.revisions:
            if revision.revision_id == proposal.base_revision_id:
                base_payload = revision.snapshot
                break
        return (
            current_payload,
            target.head.current_revision_id if target.head is not None else None,
            base_payload,
            {
                "target_object_id": proposal.target_object_id,
                "base_revision_id": proposal.base_revision_id,
                "current_revision_id": target.head.current_revision_id if target.head is not None else None,
                "current_revision_number": target.head.current_revision_number if target.head is not None else None,
            },
        )

    def _latest_artifact_for_object_id(self, object_id: str, *, family: str = "chapter_artifact") -> DerivedArtifactSnapshot | None:
        candidates = [
            artifact
            for artifact in self.list_derived_artifacts(family)
            if artifact.object_id == object_id
        ]
        return candidates[-1] if candidates else None

    def _latest_import_source(self, project_id: str) -> str | None:
        import_rows = self.__storage.fetch_import_records(project_id=project_id)
        if not import_rows:
            return None
        return str(import_rows[-1]["import_source"])

    def _build_publish_export_payload(
        self,
        *,
        project_id: str,
        novel: CanonicalObjectSnapshot,
        chapter_artifact: DerivedArtifactSnapshot | None,
        export_format: str,
    ) -> JSONObject:
        if chapter_artifact is None:
            raise ValueError("publish export requires a chapter_artifact source in the current MVP")
        chapter_title = self._payload_text_value(chapter_artifact.payload, "chapter_title") or chapter_artifact.object_id
        chapter_body = self._payload_text_value(chapter_artifact.payload, "body") or ""
        source_scene_id = self._payload_text_value(chapter_artifact.payload, "source_scene_id")
        active_skills = tuple(
            summary.object_id
            for summary in self.get_workspace_snapshot(
                WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel.object_id)
            ).canonical_objects
            if summary.family == "skill"
            and summary.payload.get("novel_id") == novel.object_id
            and bool(summary.payload.get("is_active", False))
        )
        markdown_body = (
            f"# {self._payload_text_value(novel.payload, 'title') or novel.object_id}\n\n"
            f"## {chapter_title}\n\n"
            f"{chapter_body.strip()}\n"
        )
        lineage: JSONObject = {
            "project_id": project_id,
            "novel_id": novel.object_id,
            "novel_revision_id": novel.current_revision_id,
            "source_chapter_artifact_id": chapter_artifact.object_id,
            "source_chapter_artifact_revision_id": chapter_artifact.artifact_revision_id,
            "source_scene_id": source_scene_id,
            "source_scene_revision_id": chapter_artifact.source_scene_revision_id,
            "active_skill_ids": list(active_skills),
        }
        projections: list[JSONValue] = [
            {
                "path": "manuscript.md",
                "media_type": "text/markdown",
                "content": markdown_body,
            },
            {
                "path": "lineage.json",
                "media_type": "application/json",
                "content": json.dumps(lineage, ensure_ascii=False, indent=2, sort_keys=True),
            },
        ]
        return cast(
            JSONObject,
            {
            "project_id": project_id,
            "novel_id": novel.object_id,
            "source_chapter_artifact_id": chapter_artifact.object_id,
            "source_scene_id": source_scene_id,
            "source_scene_revision_id": chapter_artifact.source_scene_revision_id,
            "export_format": export_format,
            "chapter_title": chapter_title,
            "body": markdown_body,
            "lineage": lineage,
            "projections": projections,
            },
        )

    def _review_target_title(
        self,
        proposal: ReviewProposalSnapshot,
        requested_payload: JSONObject,
        current_payload: JSONObject,
    ) -> str:
        for payload in (requested_payload, current_payload):
            for key in ("chapter_title", "title", "summary"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return proposal.target_object_id

    def _review_state_detail(
        self,
        approval_state: str,
        decisions: tuple[ReviewDecisionSnapshot, ...],
        drift_details: JSONObject,
    ) -> str:
        if approval_state == "approved":
            return "Applied exactly once; replaying approval returns the original apply result."
        if approval_state == "rejected":
            latest_reason = self._decision_reason(decisions[-1]) if decisions else None
            return latest_reason or "Rejected; canonical state is unchanged."
        if approval_state == "revision_requested":
            revise_count = sum(1 for decision in decisions if decision.approval_state == "revision_requested")
            return f"Revision requested {revise_count} time(s); the proposal remains open for another pass."
        if approval_state == "stale":
            return self._drift_summary(drift_details)
        return "Pending review; no apply has been recorded yet."

    def _decision_reason(self, decision: ReviewDecisionSnapshot) -> str | None:
        for key in ("reason", "note", "summary"):
            value = decision.decision_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _drift_summary(self, drift_details: JSONObject) -> str:
        fragments: list[str] = []
        for key, value in drift_details.items():
            if not isinstance(value, dict):
                continue
            expected = value.get("expected_base_revision_id") or value.get("expected_revision_id")
            current = value.get("current_revision_id")
            if expected is not None or current is not None:
                fragments.append(f"{key} drifted from {expected} to {current}")
        return "; ".join(fragments) or "Revision drift detected; approval was blocked before mutating canonical state."

    def _render_prose_diff(self, before: JSONObject, after: JSONObject) -> str:
        before_text = self._prose_payload_text(before)
        after_text = self._prose_payload_text(after)
        if before_text == after_text:
            return "No rendered prose delta."
        diff = list(
            difflib.unified_diff(
                before_text.splitlines(),
                after_text.splitlines(),
                fromfile="current",
                tofile="proposed",
                lineterm="",
            )
        )
        if not diff:
            return "Rendered prose changed."
        return "\n".join(diff[:24])

    def _prose_payload_text(self, payload: JSONObject) -> str:
        parts: list[str] = []
        for key in ("title", "chapter_title", "summary", "body"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(f"{key}:\n{value.strip()}")
        if parts:
            return "\n\n".join(parts)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _payload_text_value(self, payload: JSONObject, key: str) -> str | None:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _payload_int_value(self, payload: JSONObject, key: str, default: int) -> int:
        value = payload.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float | str):
            return int(value)
        return default

    def _service_mutation_result(self, result: MutationExecutionResult) -> ServiceMutationResult:
        return ServiceMutationResult(
            policy_class=result.policy_class.value,
            disposition=result.disposition.value,
            target_family=result.target_family,
            target_object_id=result.target_object_id,
            reasons=result.reasons,
            canonical_revision_id=result.canonical_revision_id,
            canonical_revision_number=result.canonical_revision_number,
            mutation_record_id=result.mutation_record_id,
            artifact_revision_id=result.artifact_revision_id,
            proposal_id=result.proposal_id,
        )

    @staticmethod
    def _import_object_result(row: ImportedObjectRecord) -> ImportObjectResult:
        return ImportObjectResult(
            family=row.family,
            object_id=row.object_id,
            revision_id=row.revision_id,
            source_ref=row.source_ref,
        )

    def _latest_scene_chapter_artifact(
        self,
        scene_object_id: str,
        *,
        novel_id: str,
    ) -> DerivedArtifactSnapshot | None:
        matching = [
            artifact
            for artifact in self.list_derived_artifacts("chapter_artifact")
            if artifact.payload.get("source_scene_id") == scene_object_id and artifact.payload.get("novel_id") == novel_id
        ]
        return matching[-1] if matching else None

    def _derived_artifact_by_revision(self, artifact_revision_id: str, *, family: str = "chapter_artifact") -> DerivedArtifactSnapshot | None:
        for artifact in self.list_derived_artifacts(family):
            if artifact.artifact_revision_id == artifact_revision_id:
                return artifact
        return None

    def _skill_workshop_snapshot(self, summary: WorkspaceObjectSummary) -> SkillWorkshopSkillSnapshot:
        donor_kind = None
        import_mapping = summary.payload.get("import_mapping")
        if isinstance(import_mapping, dict):
            donor_kind_value = import_mapping.get("donor_kind")
            if isinstance(donor_kind_value, str) and donor_kind_value.strip():
                donor_kind = donor_kind_value.strip()
        return SkillWorkshopSkillSnapshot(
            object_id=summary.object_id,
            revision_id=summary.current_revision_id,
            revision_number=summary.current_revision_number,
            name=_payload_text(summary.payload, "name") or summary.object_id,
            description=_payload_text(summary.payload, "description"),
            instruction=_payload_text(summary.payload, "instruction"),
            style_scope=_payload_text(summary.payload, "style_scope") or "scene_to_chapter",
            is_active=bool(summary.payload.get("is_active", False)),
            source_kind=_payload_text(summary.payload, "source_kind") or "skill_workshop",
            donor_kind=donor_kind,
            payload=summary.payload,
        )

    def _skill_versions(self, skill_object_id: str) -> tuple[SkillWorkshopVersionSnapshot, ...]:
        read_result = self.read_object(
            ReadObjectRequest(family="skill", object_id=skill_object_id, include_revisions=True)
        )
        if read_result.head is None:
            raise KeyError(skill_object_id)
        versions = [
            SkillWorkshopVersionSnapshot(
                revision_id=revision.revision_id,
                revision_number=revision.revision_number,
                parent_revision_id=revision.parent_revision_id,
                name=_payload_text(revision.snapshot, "name") or skill_object_id,
                instruction=_payload_text(revision.snapshot, "instruction"),
                style_scope=_payload_text(revision.snapshot, "style_scope") or "scene_to_chapter",
                is_active=bool(revision.snapshot.get("is_active", False)),
                payload=revision.snapshot,
            )
            for revision in read_result.revisions
        ]
        versions.sort(key=lambda revision: revision.revision_number, reverse=True)
        return tuple(versions)

    def _default_skill_revision_reason(self, target_object_id: str | None) -> str:
        return "create constrained skill workshop skill" if target_object_id is None else "update constrained skill workshop skill"

    def _build_scene_to_chapter_payload(
        self,
        *,
        scene: CanonicalObjectSnapshot,
        style_rules: tuple[WorkspaceObjectSummary, ...],
        scoped_skills: tuple[WorkspaceObjectSummary, ...],
        canonical_facts: tuple[WorkspaceObjectSummary, ...],
        previous_payload: JSONObject,
        previous_artifact_revision_id: str | None,
    ) -> JSONObject:
        chapter_title = self._scene_chapter_title(scene.payload, scene.object_id)

        # Try AI generation first
        ai_client = self._get_active_ai_provider()
        body: str

        if ai_client is not None:
            try:
                # Get novel context for the prompt
                novel_id = cast(str, scene.payload.get("novel_id"))
                novel_read = self.read_object(ReadObjectRequest(family="novel", object_id=novel_id))
                novel_context: JSONObject = {}
                if novel_read.head is not None:
                    novel_context = {
                        "title": novel_read.head.payload.get("title", "Untitled"),
                        "premise": novel_read.head.payload.get("premise", ""),
                        "genre": novel_read.head.payload.get("genre", ""),
                        "voice": novel_read.head.payload.get("voice", "Third person limited"),
                    }

                # Prepare context objects
                style_rule_payloads = [rule.payload for rule in style_rules]
                skill_payloads = [skill.payload for skill in scoped_skills]
                fact_payloads = [fact.payload for fact in canonical_facts]

                # Get previous chapter if available for continuity
                previous_chapter: JSONObject | None = None
                if previous_artifact_revision_id and previous_payload.get("chapter_title"):
                    previous_chapter = {
                        "chapter_title": str(previous_payload.get("chapter_title", "")),
                        "ending_note": str(previous_payload.get("body", ""))[-500:] if previous_payload.get("body") else "",
                    }

                # Build prompt and generate
                messages = build_scene_to_chapter_prompt(
                    scene=scene.payload,
                    novel_context=novel_context,
                    style_rules=style_rule_payloads,
                    skills=skill_payloads,
                    canonical_facts=fact_payloads,
                    previous_chapter=previous_chapter,
                )

                # Use structured generation for consistent output
                output_schema = {
                    "type": "object",
                    "properties": {
                        "chapter_title": {"type": "string"},
                        "chapter_body": {"type": "string"},
                        "word_count": {"type": "integer"},
                        "notes": {"type": "string"},
                    },
                    "required": ["chapter_title", "chapter_body", "word_count"],
                }

                result = ai_client.generate_structured(
                    messages=messages,
                    output_schema=output_schema,
                )

                # Extract generated content
                generated_title = str(result.get("chapter_title", chapter_title))
                body = str(result.get("chapter_body", ""))
                word_count = int(result.get("word_count", 0))
                notes = str(result.get("notes", ""))

                # Use AI-generated title if provided
                if generated_title and generated_title != "Untitled":
                    chapter_title = generated_title

                # Add metadata about AI generation
                generation_notes = f"AI-generated chapter (~{word_count} words)."
                if notes:
                    generation_notes += f" {notes}"

            except Exception as e:
                # Fall back to mock generation on error
                body_sections = [self._scene_body_seed(scene.payload)]
                body_sections.append(f"[AI generation unavailable: {e}])")
                if style_rules:
                    style_notes = "; ".join(self._workspace_summary_text(item) for item in style_rules)
                    body_sections.append(f"Style guidance: {style_notes}.")
                if scoped_skills:
                    skill_notes = "; ".join(self._workspace_summary_text(item) for item in scoped_skills)
                    body_sections.append(f"Skill guidance: {skill_notes}.")
                if canonical_facts:
                    fact_notes = "; ".join(self._workspace_summary_text(item) for item in canonical_facts)
                    body_sections.append(f"Canonical facts: {fact_notes}.")
                body = "\n\n".join(section for section in body_sections if section)
                generation_notes = "Mock content (AI provider not configured or generation failed)."
        else:
            # No AI provider configured - use mock generation
            body_sections = [self._scene_body_seed(scene.payload)]
            if style_rules:
                style_notes = "; ".join(self._workspace_summary_text(item) for item in style_rules)
                body_sections.append(f"Style guidance: {style_notes}.")
            if scoped_skills:
                skill_notes = "; ".join(self._workspace_summary_text(item) for item in scoped_skills)
                body_sections.append(f"Skill guidance: {skill_notes}.")
            if canonical_facts:
                fact_notes = "; ".join(self._workspace_summary_text(item) for item in canonical_facts)
                body_sections.append(f"Canonical facts: {fact_notes}.")
            body = "\n\n".join(section for section in body_sections if section)
            generation_notes = "Mock content (no AI provider configured)."

        lineage_payload: JSONObject = {
            "source_scene_id": scene.object_id,
            "source_scene_revision_id": scene.current_revision_id,
            "previous_artifact_revision_id": previous_artifact_revision_id,
        }
        payload: JSONObject = {
            "novel_id": cast(str, scene.payload["novel_id"]),
            "source_scene_id": scene.object_id,
            "source_scene_revision_id": scene.current_revision_id,
            "chapter_title": chapter_title,
            "body": body,
            "lineage": lineage_payload,
            "generation_notes": generation_notes,
            "delta_from_previous": _build_object_diff(previous_payload, {
                "novel_id": cast(str, scene.payload["novel_id"]),
                "source_scene_id": scene.object_id,
                "source_scene_revision_id": scene.current_revision_id,
                "chapter_title": chapter_title,
                "body": body,
            }),
            "generation_context": {
                "style_rule_ids": [item.object_id for item in style_rules],
                "skill_ids": [item.object_id for item in scoped_skills],
                "fact_ids": [item.object_id for item in canonical_facts],
            },
        }
        return payload

    def _scene_chapter_title(self, payload: JSONObject, scene_object_id: str) -> str:
        title = payload.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        return f"Chapter from {scene_object_id}"

    def _scene_body_seed(self, payload: JSONObject) -> str:
        title = payload.get("title")
        summary = payload.get("summary")
        event_id = payload.get("event_id")
        parts: list[str] = []
        if isinstance(title, str) and title.strip():
            parts.append(title.strip())
        if isinstance(summary, str) and summary.strip():
            parts.append(summary.strip())
        if isinstance(event_id, str) and event_id.strip():
            parts.append(f"Event anchor: {event_id.strip()}.")
        return " ".join(parts) if parts else "Scene seed imported without prose summary."

    def _workspace_summary_text(self, summary: WorkspaceObjectSummary) -> str:
        for key in ("title", "rule", "instruction", "summary", "fact", "state", "name"):
            value = summary.payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return summary.object_id

    def _skill_matches_scene_to_chapter_scope(self, payload: JSONObject) -> bool:
        scope_candidates = (
            payload.get("scope"),
            payload.get("pipeline_scope"),
            payload.get("target_pair"),
            payload.get("target_family"),
        )
        normalized = {
            candidate.strip().lower()
            for candidate in scope_candidates
            if isinstance(candidate, str) and candidate.strip()
        }
        if {"scene_to_chapter", "scene->chapter", "chapter_artifact"} & normalized:
            return True
        skill_type = payload.get("skill_type")
        return isinstance(skill_type, str) and skill_type.strip().lower() == "style_rule"

    def _review_route(self, *, project_id: str, novel_id: str) -> str:
        return f"/review-desk?project_id={project_id}&novel_id={novel_id}"

    # AI-powered generation helpers for workbenches

    def _generate_plot_nodes_with_ai(
        self,
        outline_node: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        skills: tuple[WorkspaceObjectSummary, ...],
        parent_outline: CanonicalObjectSnapshot | None,
    ) -> list[JSONObject]:
        """Generate plot nodes from outline using AI."""
        ai_client = self._get_active_ai_provider()
        if ai_client is None:
            return []

        try:
            skill_payloads = [skill.payload for skill in skills]
            messages = build_outline_to_plot_prompt(
                outline_node=outline_node.payload,
                novel_context=novel_context,
                skills=skill_payloads,
                parent_outline=parent_outline.payload if parent_outline else None,
            )

            output_schema = {
                "type": "object",
                "properties": {
                    "plot_nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "summary": {"type": "string"},
                                "sequence_order": {"type": "integer"},
                                "notes": {"type": "string"},
                            },
                            "required": ["title", "summary", "sequence_order"],
                        },
                    },
                },
                "required": ["plot_nodes"],
            }

            result = ai_client.generate_structured(messages=messages, output_schema=output_schema)
            return cast(list[JSONObject], result.get("plot_nodes", []))
        except Exception:
            return []

    def _generate_events_with_ai(
        self,
        plot_node: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        outline_context: CanonicalObjectSnapshot,
        skills: tuple[WorkspaceObjectSummary, ...],
    ) -> list[JSONObject]:
        """Generate events from plot node using AI."""
        ai_client = self._get_active_ai_provider()
        if ai_client is None:
            return []

        try:
            skill_payloads = [skill.payload for skill in skills]
            messages = build_plot_to_event_prompt(
                plot_node=plot_node.payload,
                novel_context=novel_context,
                outline_context=outline_context.payload,
                skills=skill_payloads,
            )

            output_schema = {
                "type": "object",
                "properties": {
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "sequence_order": {"type": "integer"},
                                "location": {"type": "string"},
                                "characters_involved": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["title", "description", "sequence_order"],
                        },
                    },
                },
                "required": ["events"],
            }

            result = ai_client.generate_structured(messages=messages, output_schema=output_schema)
            return cast(list[JSONObject], result.get("events", []))
        except Exception:
            return []

    def _generate_scenes_with_ai(
        self,
        event: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        plot_context: CanonicalObjectSnapshot,
        skills: tuple[WorkspaceObjectSummary, ...],
        characters: tuple[WorkspaceObjectSummary, ...],
        settings: tuple[WorkspaceObjectSummary, ...],
    ) -> list[JSONObject]:
        """Generate scenes from event using AI."""
        ai_client = self._get_active_ai_provider()
        if ai_client is None:
            return []

        try:
            skill_payloads = [skill.payload for skill in skills]
            character_payloads = [c.payload for c in characters]
            setting_payloads = [s.payload for s in settings]
            messages = build_event_to_scene_prompt(
                event=event.payload,
                novel_context=novel_context,
                plot_context=plot_context.payload,
                skills=skill_payloads,
                characters=character_payloads,
                settings=setting_payloads,
            )

            output_schema = {
                "type": "object",
                "properties": {
                    "scenes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "setting": {"type": "string"},
                                "pov_character": {"type": "string"},
                                "characters_present": {"type": "array", "items": {"type": "string"}},
                                "scene_summary": {"type": "string"},
                                "beat_breakdown": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["title", "setting", "scene_summary", "beat_breakdown"],
                        },
                    },
                },
                "required": ["scenes"],
            }

            result = ai_client.generate_structured(messages=messages, output_schema=output_schema)
            return cast(list[JSONObject], result.get("scenes", []))
        except Exception:
            return []

    def _retrieval_scope(self, project_id: str, novel_id: str | None) -> tuple[str, str]:
        if novel_id is not None:
            return ("novel", novel_id)
        return ("project", project_id)

    def _retrieval_sources(
        self,
        canonical_objects: tuple[WorkspaceObjectSummary, ...],
    ) -> tuple[RetrievalSourceRecord, ...]:
        sources: list[RetrievalSourceRecord] = []
        for summary in canonical_objects:
            revisions = self.read_object(
                ReadObjectRequest(
                    family=summary.family,
                    object_id=summary.object_id,
                    include_revisions=True,
                )
            ).revisions
            sources.append(
                RetrievalSourceRecord(
                    family=summary.family,
                    object_id=summary.object_id,
                    revision_id=summary.current_revision_id,
                    revision_number=summary.current_revision_number,
                    project_id=self._payload_text_value(summary.payload, "project_id"),
                    novel_id=self._payload_text_value(summary.payload, "novel_id"),
                    payload=summary.payload,
                    revision_count=max(1, len(revisions)),
                )
            )
        return tuple(sources)

    def _retrieval_document_markers(
        self,
        project_id: str,
        novel_id: str | None,
    ) -> tuple[MetadataMarkerSnapshot, ...]:
        markers = self.__storage.fetch_metadata_markers(marker_name="retrieval_document")
        filtered: list[MetadataMarkerSnapshot] = []
        for marker in markers:
            marker_project_id = self._payload_text_value(marker.payload, "project_id")
            marker_novel_id = self._payload_text_value(marker.payload, "novel_id")
            if marker_project_id != project_id:
                continue
            if novel_id is not None and marker_novel_id != novel_id:
                continue
            filtered.append(marker)
        return tuple(filtered)

    def _latest_retrieval_status_marker(
        self,
        *,
        scope_family: str,
        scope_object_id: str,
    ) -> MetadataMarkerSnapshot | None:
        markers = self.__storage.fetch_metadata_markers(
            marker_name="retrieval_status",
            target_family=scope_family,
            target_object_id=scope_object_id,
        )
        return markers[-1] if markers else None

    def _retrieval_status_snapshot(
        self,
        *,
        scope_family: str,
        scope_object_id: str,
        current_stamp: str,
        document_markers: tuple[MetadataMarkerSnapshot, ...],
        status_marker: MetadataMarkerSnapshot | None,
        degraded: bool,
        warnings: tuple[str, ...],
    ) -> RetrievalStatusSnapshot:
        indexed_object_count = len(document_markers)
        indexed_revision_count = sum(
            cast(int, marker.payload["revision_count"])
            for marker in document_markers
            if isinstance(marker.payload.get("revision_count"), int) and not isinstance(marker.payload.get("revision_count"), bool)
        )
        if status_marker is None:
            return RetrievalStatusSnapshot(
                scope_family=scope_family,
                scope_object_id=scope_object_id,
                support_only=True,
                rebuildable=True,
                build_consistency_stamp=current_stamp,
                indexed_object_count=indexed_object_count,
                indexed_revision_count=indexed_revision_count,
                degraded=True,
                warnings=warnings,
            )
        return RetrievalStatusSnapshot(
            scope_family=scope_family,
            scope_object_id=scope_object_id,
            support_only=bool(status_marker.payload.get("support_only", True)),
            rebuildable=bool(status_marker.payload.get("rebuildable", True)),
            build_consistency_stamp=self._payload_text_value(status_marker.payload, "build_consistency_stamp") or current_stamp,
            indexed_object_count=self._payload_int_value(status_marker.payload, "indexed_object_count", indexed_object_count),
            indexed_revision_count=self._payload_int_value(status_marker.payload, "indexed_revision_count", indexed_revision_count),
            degraded=degraded,
            warnings=warnings,
        )

    # Workbench iteration methods

    def start_workbench_iteration(
        self,
        request: WorkbenchIterationRequest,
    ) -> WorkbenchIterationResult:
        """Start a workbench iteration session.

        Creates a new session and generates initial candidates based on the
        parent object and workbench type.

        Args:
            request: The iteration request with project, novel, and parent object info

        Returns:
            WorkbenchIterationResult with session ID and initial candidates
        """
        # Create the session
        session_id = self.__storage.create_workbench_session(
            project_id=request.project_id,
            novel_id=request.novel_id,
            workbench_type=request.workbench_type,
            parent_object_id=request.parent_object_id,
            actor=request.actor,
            source_surface=request.source_surface,
            source_ref=request.source_ref,
        )

        # Generate initial candidates based on workbench type
        initial_candidates = self._generate_iteration_candidates(
            workbench_type=request.workbench_type,
            parent_object_id=request.parent_object_id,
            novel_id=request.novel_id,
            project_id=request.project_id,
            actor=request.actor,
            session_id=session_id,
            iteration_number=1,
        )

        return WorkbenchIterationResult(
            session_id=session_id,
            workbench_type=request.workbench_type,
            parent_object_id=request.parent_object_id,
            initial_candidates=tuple(
                CandidateDraftSnapshot(
                    draft_id=c["draft_id"],
                    session_id=c["session_id"],
                    iteration_number=c["iteration_number"],
                    payload=c["payload"],
                    generation_context=c["generation_context"],
                    is_selected=c["is_selected"],
                    created_at=c["created_at"],
                )
                for c in initial_candidates
            ),
            iteration_number=1,
        )

    def submit_workbench_feedback(
        self,
        request: WorkbenchFeedbackRequest,
    ) -> WorkbenchFeedbackResult:
        """Submit feedback on a candidate and generate new candidates.

        Records the feedback and generates revised candidates based on the feedback.

        Args:
            request: The feedback request with session, target draft, and feedback text

        Returns:
            WorkbenchFeedbackResult with new candidates and iteration info
        """
        # Get the session to determine current iteration
        session = self.__storage.get_workbench_session(request.session_id)
        if session is None:
            raise KeyError(f"Session not found: {request.session_id}")

        # Get the target draft to base revisions on (check before creating feedback)
        target_draft = self.__storage.get_candidate_draft(request.target_draft_id)
        if target_draft is None:
            raise KeyError(f"Draft not found: {request.target_draft_id}")

        # Record the feedback
        feedback_id = self.__storage.create_workbench_feedback(
            session_id=request.session_id,
            target_draft_id=request.target_draft_id,
            feedback_type=request.feedback_type,
            feedback_text=request.feedback_text,
            target_section=request.target_section,
            created_by=request.created_by,
        )

        # Increment iteration counter
        new_iteration = self.__storage.increment_workbench_iteration(request.session_id)

        # Generate new candidates based on feedback
        new_candidates = self._generate_revision_candidates(
            session=session,
            base_draft=target_draft,
            feedback=request,
            iteration_number=new_iteration,
        )

        return WorkbenchFeedbackResult(
            session_id=request.session_id,
            new_iteration_number=new_iteration,
            new_candidates=tuple(
                CandidateDraftSnapshot(
                    draft_id=c["draft_id"],
                    session_id=c["session_id"],
                    iteration_number=c["iteration_number"],
                    payload=c["payload"],
                    generation_context=c["generation_context"],
                    is_selected=c["is_selected"],
                    created_at=c["created_at"],
                )
                for c in new_candidates
            ),
            feedback_recorded_id=feedback_id,
        )

    def select_workbench_candidate(
        self,
        request: CandidateSelectionRequest,
    ) -> CandidateSelectionResult:
        """Select a final candidate and complete the session.

        Marks the selected candidate and optionally applies it to the canonical object.

        Args:
            request: The selection request with session and selected draft ID

        Returns:
            CandidateSelectionResult with selection details
        """
        # Get the session
        session = self.__storage.get_workbench_session(request.session_id)
        if session is None:
            raise KeyError(f"Session not found: {request.session_id}")

        # Get the selected draft
        selected_draft = self.__storage.get_candidate_draft(request.selected_draft_id)
        if selected_draft is None:
            raise KeyError(f"Draft not found: {request.selected_draft_id}")

        # Mark as selected
        self.__storage.select_candidate_draft(request.selected_draft_id)

        # Optionally apply to canonical
        mutation_applied = False
        mutation_record_id = None
        revision_id = None

        if request.apply_to_canonical:
            result = self._apply_candidate_to_canonical(
                session=session,
                draft=selected_draft,
                actor=request.actor,
            )
            mutation_applied = result["applied"]
            mutation_record_id = result.get("mutation_record_id")
            revision_id = result.get("revision_id")

        # Complete the session
        self.__storage.update_workbench_session_status(request.session_id, "completed")

        return CandidateSelectionResult(
            session_id=request.session_id,
            selected_draft_id=request.selected_draft_id,
            selected_payload=selected_draft["payload"],
            mutation_applied=mutation_applied,
            mutation_record_id=mutation_record_id,
            revision_id=revision_id,
            completion_status="completed",
        )

    def _generate_iteration_candidates(
        self,
        workbench_type: str,
        parent_object_id: str,
        novel_id: str,
        project_id: str,
        actor: str,
        session_id: str,
        iteration_number: int,
    ) -> list[dict]:
        """Generate initial candidates for a workbench iteration session.

        Delegates to the appropriate workbench method based on type.
        """
        # Map workbench types to their corresponding methods
        workbench_methods = {
            "outline_to_plot": self._outline_to_plot_candidates,
            "plot_to_event": self._plot_to_event_candidates,
            "event_to_scene": self._event_to_scene_candidates,
            "scene_to_chapter": self._scene_to_chapter_candidates,
        }

        method = workbench_methods.get(workbench_type)
        if method is None:
            raise ValueError(f"Unknown workbench type: {workbench_type}")

        return method(
            parent_object_id=parent_object_id,
            novel_id=novel_id,
            project_id=project_id,
            actor=actor,
            session_id=session_id,
            iteration_number=iteration_number,
        )

    def _generate_revision_candidates(
        self,
        session: dict,
        base_draft: dict,
        feedback: WorkbenchFeedbackRequest,
        iteration_number: int,
    ) -> list[dict]:
        """Generate revised candidates based on feedback using AI when available."""
        base_payload = dict(base_draft["payload"])
        ai_client = self._get_active_ai_provider()

        revised_payload: JSONObject | None = None
        ai_generated = False

        if ai_client is not None and session.get("workbench_type") == "scene_to_chapter":
            try:
                novel_id = session.get("novel_id", "")
                project_id = session.get("project_id", "")
                skills = self._gather_workspace_skills(project_id, novel_id)
                style_rules = self._gather_workspace_objects(project_id, novel_id, "style_rule")
                facts = self._gather_workspace_objects(project_id, novel_id, "fact_state_record")

                # Get scene context for the revision
                parent_object_id = session.get("parent_object_id", "")
                scene_read = self.read_object(
                    ReadObjectRequest(family="scene", object_id=parent_object_id)
                )
                scene_context = scene_read.head.payload if scene_read.head else {}

                messages = build_chapter_revision_prompt(
                    current_chapter=base_payload,
                    revision_instructions=feedback.feedback_text,
                    scene_context=scene_context,
                    style_rules=[rule.payload for rule in style_rules],
                    skills=[skill.payload for skill in skills],
                    canonical_facts=[fact.payload for fact in facts],
                )

                output_schema = {
                    "type": "object",
                    "properties": {
                        "chapter_title": {"type": "string"},
                        "chapter_body": {"type": "string"},
                        "word_count": {"type": "integer"},
                        "changes_made": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["chapter_title", "chapter_body", "word_count"],
                }

                result = ai_client.generate_structured(
                    messages=messages, output_schema=output_schema,
                )

                revised_payload = {
                    "chapter_title": result.get("chapter_title", base_payload.get("chapter_title", "")),
                    "body": result.get("chapter_body", ""),
                    "word_count": result.get("word_count", 0),
                    "changes_made": result.get("changes_made", ""),
                    "notes": result.get("notes", ""),
                    "ai_generated": True,
                }
                ai_generated = True

            except Exception:
                revised_payload = None  # Fall through to fallback

        elif ai_client is not None:
            # Generic revision for non-chapter workbench types
            try:
                system_msg = {
                    "role": "system",
                    "content": (
                        "You are a creative writing assistant. Revise the following content "
                        "according to the user's feedback. Maintain the original structure "
                        "and style while incorporating the requested changes.\n\n"
                        "Respond with a JSON object matching the original content structure "
                        "with the revisions applied."
                    ),
                }
                user_msg = {
                    "role": "user",
                    "content": (
                        f"# Current content\n{json.dumps(base_payload, ensure_ascii=False, indent=2)}\n\n"
                        f"# Revision instructions\n{feedback.feedback_text}\n\n"
                        "Return the revised content as JSON."
                    ),
                }
                result = ai_client.generate_structured(
                    messages=[system_msg, user_msg],
                    output_schema={"type": "object"},
                )
                if isinstance(result, dict) and result:
                    revised_payload = dict(result)
                    revised_payload["ai_generated"] = True
                    ai_generated = True
            except Exception:
                revised_payload = None  # Fall through to fallback

        # Fallback: simple text append when AI unavailable or failed
        if revised_payload is None:
            revised_payload = dict(base_payload)
            notes = revised_payload.get("notes", "")
            revised_payload["notes"] = f"{notes}\n[Revision {iteration_number}: {feedback.feedback_text}]".strip()
            revised_payload["ai_generated"] = False

        # Create the revised candidate
        draft_id = self.__storage.create_candidate_draft(
            session_id=session["session_id"],
            iteration_number=iteration_number,
            payload=revised_payload,
            generation_context={
                "base_draft_id": base_draft["draft_id"],
                "feedback_type": feedback.feedback_type,
                "feedback_text": feedback.feedback_text,
                "iteration_number": iteration_number,
                "ai_generated": ai_generated,
            },
        )

        draft = self.__storage.get_candidate_draft(draft_id)
        if draft is None:
            raise RuntimeError("Failed to create candidate draft")

        return [draft]

    def _apply_candidate_to_canonical(
        self,
        session: dict,
        draft: dict,
        actor: str,
    ) -> dict:
        """Apply a selected candidate to the canonical object.

        Returns a dict with 'applied', 'mutation_record_id', and 'revision_id'.
        """
        # For scene_to_chapter workbenches, create a derived artifact
        if session["workbench_type"] == "scene_to_chapter":
            artifact_revision_id = self.__storage.create_derived_record(
                DerivedRecordInput(
                    family="chapter_artifact",
                    object_id=None,
                    payload=draft["payload"],
                    source_scene_revision_id=session["parent_object_id"],
                    created_by=actor,
                    source_ref=f"workbench_session:{session['session_id']}",
                )
            )
            return {
                "applied": True,
                "mutation_record_id": None,
                "revision_id": artifact_revision_id,
            }

        # For canonical objects (outline, plot, event, scene), use mutation
        # This is a simplified implementation - full version would use the policy engine
        return {
            "applied": False,
            "mutation_record_id": None,
            "revision_id": None,
        }

    # --- Workbench candidate generation with AI wiring ---

    def _gather_novel_context(self, novel_id: str) -> JSONObject:
        """Read novel-level context for AI prompt construction."""
        novel_read = self.read_object(ReadObjectRequest(family="novel", object_id=novel_id))
        if novel_read.head is None:
            return {}
        return {
            "title": novel_read.head.payload.get("title", "Untitled"),
            "premise": novel_read.head.payload.get("premise", ""),
            "genre": novel_read.head.payload.get("genre", ""),
            "voice": novel_read.head.payload.get("voice", "Third person limited"),
        }

    def _gather_workspace_skills(
        self, project_id: str, novel_id: str,
    ) -> tuple[WorkspaceObjectSummary, ...]:
        """Get active skills scoped to a novel."""
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        return tuple(
            s for s in workspace.canonical_objects
            if s.family == "skill" and s.payload.get("novel_id") == novel_id
        )

    def _gather_workspace_objects(
        self, project_id: str, novel_id: str, *families: str,
    ) -> tuple[WorkspaceObjectSummary, ...]:
        """Get workspace objects of specified families scoped to a novel."""
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        return tuple(
            s for s in workspace.canonical_objects
            if s.family in families and s.payload.get("novel_id") == novel_id
        )

    def _create_candidates_from_items(
        self,
        items: list[JSONObject],
        session_id: str,
        iteration_number: int,
        method: str,
        ai_generated: bool,
    ) -> list[dict]:
        """Create candidate drafts from a list of AI-generated items."""
        if not items:
            return []
        results: list[dict] = []
        for item in items:
            draft_id = self.__storage.create_candidate_draft(
                session_id=session_id,
                iteration_number=iteration_number,
                payload=item,
                generation_context={"method": method, "ai_generated": ai_generated},
            )
            draft = self.__storage.get_candidate_draft(draft_id)
            if draft:
                results.append(draft)
        return results

    def _outline_to_plot_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate plot candidates from an outline node using AI."""
        outline_read = self.read_object(
            ReadObjectRequest(family="outline_node", object_id=parent_object_id)
        )

        if outline_read.head is not None:
            outline = outline_read.head
            novel_context = self._gather_novel_context(novel_id)
            skills = self._gather_workspace_skills(project_id, novel_id)

            parent_outline_id = outline.payload.get("parent_outline_node_id")
            parent_outline: CanonicalObjectSnapshot | None = None
            if parent_outline_id:
                parent_read = self.read_object(
                    ReadObjectRequest(family="outline_node", object_id=str(parent_outline_id))
                )
                parent_outline = parent_read.head

            generated = self._generate_plot_nodes_with_ai(
                outline_node=outline,
                novel_context=novel_context,
                skills=skills,
                parent_outline=parent_outline,
            )

            if generated:
                items = [
                    {
                        "novel_id": novel_id,
                        "outline_node_id": parent_object_id,
                        "title": node.get("title", ""),
                        "summary": node.get("summary", ""),
                        "sequence_order": node.get("sequence_order", i + 1),
                        "notes": node.get("notes", ""),
                        "ai_generated": True,
                    }
                    for i, node in enumerate(generated)
                ]
                return self._create_candidates_from_items(
                    items, session_id, iteration_number, "outline_to_plot", ai_generated=True,
                )

            # AI returned nothing — use outline title for fallback
            fallback_payload: JSONObject = {
                "novel_id": novel_id,
                "outline_node_id": parent_object_id,
                "title": outline.payload.get("title", "Untitled Plot"),
                "summary": "Plot from outline (AI not available)",
                "ai_generated": False,
            }
            return self._create_candidates_from_items(
                [fallback_payload], session_id, iteration_number, "outline_to_plot", ai_generated=False,
            )

        # Fallback when parent not found
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "outline_node_id": parent_object_id,
            "title": "Generated Plot",
            "summary": "Plot candidate (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "outline_to_plot", ai_generated=False,
        )

    def _plot_to_event_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate event candidates from a plot node using AI."""
        plot_read = self.read_object(
            ReadObjectRequest(family="plot_node", object_id=parent_object_id)
        )
        if plot_read.head is not None:
            plot_node = plot_read.head
            novel_context = self._gather_novel_context(novel_id)
            skills = self._gather_workspace_skills(project_id, novel_id)

            outline_node_id = plot_node.payload.get("outline_node_id")
            outline_context: CanonicalObjectSnapshot | None = None
            if outline_node_id:
                outline_read = self.read_object(
                    ReadObjectRequest(family="outline_node", object_id=str(outline_node_id))
                )
                outline_context = outline_read.head

            generated = self._generate_events_with_ai(
                plot_node=plot_node,
                novel_context=novel_context,
                outline_context=outline_context,  # type: ignore
                skills=skills,
            )

            if generated:
                items = [
                    {
                        "novel_id": novel_id,
                        "plot_node_id": parent_object_id,
                        "title": node.get("title", ""),
                        "description": node.get("description", ""),
                        "sequence_order": node.get("sequence_order", i + 1),
                        "location": node.get("location", ""),
                        "characters_involved": node.get("characters_involved", []),
                        "ai_generated": True,
                    }
                    for i, node in enumerate(generated)
                ]
                return self._create_candidates_from_items(
                    items, session_id, iteration_number, "plot_to_event", ai_generated=True,
                )

            # AI returned nothing — use plot node title for fallback
            fallback_payload: JSONObject = {
                "novel_id": novel_id,
                "plot_node_id": parent_object_id,
                "title": plot_node.payload.get("title", "Untitled Event"),
                "description": "Event from plot node (AI not available)",
                "ai_generated": False,
            }
            return self._create_candidates_from_items(
                [fallback_payload], session_id, iteration_number, "plot_to_event", ai_generated=False,
            )

        # Fallback when parent not found
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "plot_node_id": parent_object_id,
            "title": "Generated Event",
            "description": "Event candidate (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "plot_to_event", ai_generated=False,
        )

    def _event_to_scene_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate scene candidates from an event using AI."""
        event_read = self.read_object(
            ReadObjectRequest(family="event", object_id=parent_object_id)
        )

        if event_read.head is not None:
            event = event_read.head
            novel_context = self._gather_novel_context(novel_id)
            skills = self._gather_workspace_skills(project_id, novel_id)
            characters = self._gather_workspace_objects(project_id, novel_id, "character")
            settings = self._gather_workspace_objects(project_id, novel_id, "setting")

            plot_node_id = event.payload.get("plot_node_id")
            plot_context: CanonicalObjectSnapshot | None = None
            if plot_node_id:
                plot_read = self.read_object(
                    ReadObjectRequest(family="plot_node", object_id=str(plot_node_id))
                )
                plot_context = plot_read.head

            generated = self._generate_scenes_with_ai(
                event=event,
                novel_context=novel_context,
                plot_context=plot_context,  # type: ignore
                skills=skills,
                characters=characters,
                settings=settings,
            )

            if generated:
                items = [
                    {
                        "novel_id": novel_id,
                        "event_id": parent_object_id,
                        "title": node.get("title", ""),
                        "setting": node.get("setting", ""),
                        "pov_character": node.get("pov_character", ""),
                        "characters_present": node.get("characters_present", []),
                        "summary": node.get("scene_summary", ""),
                        "beat_breakdown": node.get("beat_breakdown", []),
                        "ai_generated": True,
                    }
                    for node in generated
                ]
                return self._create_candidates_from_items(
                    items, session_id, iteration_number, "event_to_scene", ai_generated=True,
                )

            # AI returned nothing — use event title for fallback
            fallback_payload: JSONObject = {
                "novel_id": novel_id,
                "event_id": parent_object_id,
                "title": event.payload.get("title", "Untitled Scene"),
                "summary": "Scene from event (AI not available)",
                "ai_generated": False,
            }
            return self._create_candidates_from_items(
                [fallback_payload], session_id, iteration_number, "event_to_scene", ai_generated=False,
            )

        # Fallback when parent not found
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "event_id": parent_object_id,
            "title": "Generated Scene",
            "summary": "Scene candidate (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "event_to_scene", ai_generated=False,
        )

    def _scene_to_chapter_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate chapter candidates from a scene using AI."""
        scene_read = self.read_object(
            ReadObjectRequest(family="scene", object_id=parent_object_id)
        )
        if scene_read.head is not None:
            scene = scene_read.head

            # Gather context for chapter generation
            style_rules = self._gather_workspace_objects(project_id, novel_id, "style_rule")
            skills = self._gather_workspace_skills(project_id, novel_id)
            facts = self._gather_workspace_objects(project_id, novel_id, "fact_state_record")

            chapter_payload = self._build_scene_to_chapter_payload(
                scene=scene,
                style_rules=style_rules,
                scoped_skills=skills,
                canonical_facts=facts,
                previous_payload={},
                previous_artifact_revision_id=None,
            )

            if chapter_payload.get("generation_notes", "").startswith("AI"):
                chapter_payload["ai_generated"] = True
                return self._create_candidates_from_items(
                    [chapter_payload], session_id, iteration_number, "scene_to_chapter", ai_generated=True,
                )

            # Fallback from _build_scene_to_chapter_payload (mock or no AI)
            chapter_payload["ai_generated"] = False
            return self._create_candidates_from_items(
                [chapter_payload], session_id, iteration_number, "scene_to_chapter", ai_generated=False,
            )

        # Fallback when scene has no head revision
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "scene_id": parent_object_id,
            "chapter_title": "Generated Chapter",
            "body": "Chapter content (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "scene_to_chapter", ai_generated=False,
        )

@dataclass(frozen=True, slots=True)
class ListReviewProposalsResult:
    proposals: tuple[ReviewProposalSnapshot, ...]


# Workbench iteration support

@dataclass(frozen=True, slots=True)
class WorkbenchIterationRequest:
    """Request to start a workbench iteration session."""
    project_id: str
    novel_id: str
    workbench_type: str
    parent_object_id: str
    actor: str
    source_surface: str = "workbench_iteration"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchIterationResult:
    """Result of starting a workbench iteration session."""
    session_id: str
    workbench_type: str
    parent_object_id: str
    initial_candidates: tuple[CandidateDraftSnapshot, ...]
    iteration_number: int


@dataclass(frozen=True, slots=True)
class CandidateDraftSnapshot:
    """Snapshot of a candidate draft in a workbench session."""
    draft_id: str
    session_id: str
    iteration_number: int
    payload: JSONObject
    generation_context: JSONObject
    is_selected: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class WorkbenchFeedbackRequest:
    """Request to submit feedback on a candidate draft."""
    session_id: str
    target_draft_id: str
    feedback_type: str
    feedback_text: str
    target_section: str | None = None
    created_by: str = ""


@dataclass(frozen=True, slots=True)
class WorkbenchFeedbackResult:
    """Result of submitting feedback and generating new candidates."""
    session_id: str
    new_iteration_number: int
    new_candidates: tuple[CandidateDraftSnapshot, ...]
    feedback_recorded_id: str


@dataclass(frozen=True, slots=True)
class CandidateSelectionRequest:
    """Request to select a final candidate and complete the session."""
    session_id: str
    selected_draft_id: str
    actor: str
    apply_to_canonical: bool = True


@dataclass(frozen=True, slots=True)
class CandidateSelectionResult:
    """Result of selecting a candidate and completing the session."""
    session_id: str
    selected_draft_id: str
    selected_payload: JSONObject
    mutation_applied: bool
    mutation_record_id: str | None
    revision_id: str | None
    completion_status: str


__all__ = [
    "CanonicalObjectSnapshot",
    "CanonicalRevisionSnapshot",
    "ChatMessageRequest",
    "ChatMessageSnapshot",
    "ChatSessionSnapshot",
    "ChatTurnRequest",
    "ChatTurnResult",
    "DerivedArtifactSnapshot",
    "ExportArtifactRequest",
    "ExportArtifactResult",
    "GetChatSessionRequest",
    "ImportObjectResult",
    "ImportRequest",
    "ImportResult",
    "ListReviewProposalsRequest",
    "ListReviewProposalsResult",
    "MutationRecordSnapshot",
    "OpenChatSessionRequest",
    "OpenChatSessionResult",
    "ReviewDecisionSnapshot",
    "ReviewDeskProposalSnapshot",
    "ReviewDeskRequest",
    "ReviewDeskResult",
    "ReadObjectRequest",
    "ReadObjectResult",
    "RetrievalMatchSnapshot",
    "RetrievalRebuildRequest",
    "RetrievalRebuildResult",
    "RetrievalSearchRequest",
    "RetrievalSearchResult",
    "RetrievalStatusSnapshot",
    "ReviewProposalSnapshot",
    "ReviewTransitionRequest",
    "ReviewTransitionResult",
    "EventToSceneWorkbenchRequest",
    "EventToSceneWorkbenchResult",
    "OutlineToPlotWorkbenchRequest",
    "OutlineToPlotWorkbenchResult",
    "PlotToEventWorkbenchRequest",
    "PlotToEventWorkbenchResult",
    "SceneToChapterWorkbenchRequest",
    "SceneToChapterWorkbenchResult",
    "ServiceMutationRequest",
    "ServiceMutationResult",
    "SkillWorkshopCompareRequest",
    "SkillWorkshopComparison",
    "SkillExecutionRequest",
    "SkillExecutionResult",
    "SkillWorkshopImportRequest",
    "SkillWorkshopMutationResult",
    "SkillWorkshopRequest",
    "SkillWorkshopResult",
    "SkillWorkshopRollbackRequest",
    "SkillWorkshopSkillSnapshot",
    "SkillWorkshopUpsertRequest",
    "SkillWorkshopVersionSnapshot",
    "SuperwriterApplicationService",
    "SupportedDonor",
    "WorkspaceObjectSummary",
    "WorkspaceSnapshotRequest",
    "WorkspaceSnapshotResult",
    # Workbench iteration
    "WorkbenchIterationRequest",
    "WorkbenchIterationResult",
    "CandidateDraftSnapshot",
    "WorkbenchFeedbackRequest",
    "WorkbenchFeedbackResult",
    "CandidateSelectionRequest",
    "CandidateSelectionResult",
]
