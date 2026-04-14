from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, replace
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
from core.ai import AIProviderClient, AIProviderConfig
from core.ai.provider import AIProviderError
from core.ai.prompts import (
    build_outline_to_plot_prompt,
    build_plot_to_event_prompt,
    build_event_to_scene_prompt,
    build_scene_to_chapter_prompt,
    build_chapter_revision_prompt,
    build_partial_revision_prompt,
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
from core.runtime.utils import (
    _build_object_diff,
    _candidate_string_list,
    _non_empty_candidate_text,
    _payload_text,
)
from core.runtime.types import (
    CanonicalObjectSnapshot,
    CanonicalRevisionSnapshot,
    MutationRecordSnapshot,
    DerivedArtifactSnapshot,
    SupportedDonor,
    WorkspaceSnapshotRequest,
    WorkspaceSnapshotResult,
    WorkspaceObjectSummary,
    WorkspaceContextSnapshot,
    CreateWorkspaceRequest,
    CreateWorkspaceResult,
    ImportOutlineRequest,
    ImportOutlineResult,
    ReadObjectRequest,
    ReadObjectResult,
    ServiceMutationRequest,
    ServiceMutationResult,
    RetrievalStatusSnapshot,
    RetrievalRebuildRequest,
    RetrievalRebuildResult,
    RetrievalSearchRequest,
    RetrievalMatchSnapshot,
    RetrievalSearchResult,
    ChatMessageSnapshot,
    ChatSessionSnapshot,
    OpenChatSessionRequest,
    OpenChatSessionResult,
    GetChatSessionRequest,
    ChatMessageRequest,
    ChatTurnRequest,
    ChatTurnResult,
    OutlineToPlotWorkbenchRequest,
    OutlineToPlotWorkbenchResult,
    PlotToEventWorkbenchRequest,
    PlotToEventWorkbenchResult,
    EventToSceneWorkbenchRequest,
    EventToSceneWorkbenchResult,
    SceneToChapterWorkbenchRequest,
    SceneToChapterWorkbenchResult,
    SkillWorkshopSkillSnapshot,
    SkillWorkshopVersionSnapshot,
    SkillWorkshopCompareRequest,
    SkillWorkshopComparison,
    SkillWorkshopUpsertRequest,
    SkillWorkshopImportRequest,
    SkillWorkshopRollbackRequest,
    SkillWorkshopMutationResult,
    SkillWorkshopRequest,
    SkillWorkshopResult,
    ImportRequest,
    ImportObjectResult,
    ImportResult,
    SkillExecutionRequest,
    SkillExecutionResult,
    ExportArtifactRequest,
    ExportArtifactResult,
    PublishExportRequest,
    PublishExportArtifactRequest,
    PublishExportArtifactResult,
    PublishExportResult,
    WorkbenchIterationRequest,
    WorkbenchIterationResult,
    CandidateDraftSnapshot,
    WorkbenchFeedbackRequest,
    WorkbenchFeedbackResult,
    CandidateSelectionRequest,
    CandidateSelectionResult,
)

JSONObject: TypeAlias = dict[str, JSONValue]


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
class _AppliedReviewMutation:
    mutation_record_id: str | None = None
    canonical_revision_id: str | None = None
    artifact_revision_id: str | None = None


class SuperwriterApplicationService:

    def __init__(self, storage: CanonicalStorage):
        self.__storage = storage
        self.__policy = MutationPolicyEngine(storage)
        # Feature services
        from features.workspace.service import WorkspaceService
        from features.pipeline.service import PipelineGenerationService
        from core.runtime.services import (
            AIConfigService,
            RetrievalService,
            SkillService,
            ImportExportService,
            ChatService,
            IterationService,
            WorkbenchService,
            DiagnosisService,
            HelperUtils,
            PayloadBuilderService,
            ReviewHelpers,
            LegacyWorkbenchService,
        )
        self._workspace_service = WorkspaceService(storage=self.__storage)
        self._pipeline_service = PipelineGenerationService(
            storage=self.__storage,
            ai_provider=None,
            mutation_engine=self.__policy,
            workspace_service=self._workspace_service,
            apply_mutation_func=self.apply_mutation,
        )
        self._ai_config_service = AIConfigService(storage=self.__storage)
        self._retrieval_service = RetrievalService(storage=self.__storage)
        self._skill_service = SkillService(storage=self.__storage, mutation_engine=self.__policy)
        self._import_export_service = ImportExportService(storage=self.__storage, mutation_engine=self.__policy)
        self._iteration_service = IterationService(storage=self.__storage, ai_config_service=self._ai_config_service)
        self._chat_service = ChatService(
            storage=self.__storage,
            mutation_engine=self.__policy,
            ai_config_service=self._ai_config_service,
        )
        self._workbench_service = WorkbenchService(
            storage=self.__storage,
            ai_config_service=self._ai_config_service,
            pipeline_service=self._pipeline_service,
        )

        # Extracted services
        self._helper_utils = HelperUtils(storage=self.__storage)
        self._diagnosis_service = DiagnosisService(
            get_active_ai_provider_func=self._get_active_ai_provider,
            get_workspace_snapshot_func=self.get_workspace_snapshot,
        )
        self._payload_builder_service = PayloadBuilderService(
            get_active_ai_provider_func=self._get_active_ai_provider,
            read_object_func=self.read_object,
            get_workspace_snapshot_func=self.get_workspace_snapshot,
            payload_text_value_func=self._helper_utils.payload_text_value,
            workspace_summary_text_func=self._helper_utils.workspace_summary_text,
        )
        self._review_helpers = ReviewHelpers()
        self._legacy_workbench_service = LegacyWorkbenchService(
            storage=self.__storage,
            get_active_ai_provider_func=self._get_active_ai_provider,
            read_object_func=self.read_object,
            get_workspace_snapshot_func=self.get_workspace_snapshot,
            build_scene_to_chapter_payload_func=self._build_scene_to_chapter_payload,
        )

        # Set callbacks for chat service
        self._chat_service.set_callbacks(
            apply_mutation_func=self.apply_mutation,
            read_object_func=self.read_object,
            generate_outline_to_plot_func=self.generate_outline_to_plot_workbench,
            generate_plot_to_event_func=self.generate_plot_to_event_workbench,
            generate_event_to_scene_func=self.generate_event_to_scene_workbench,
            generate_scene_to_chapter_func=self.generate_scene_to_chapter_workbench,
            create_export_artifact_func=self.create_export_artifact,
            execute_skill_func=self.execute_skill,
        )

    @classmethod
    def for_sqlite(cls, db_path: Path) -> SuperwriterApplicationService:
        return cls(CanonicalStorage(db_path))

    def _get_active_ai_provider(self) -> AIProviderClient | None:
        """Get the active AI provider client, or None if not configured."""
        return self._ai_config_service.get_active_ai_provider()

    def _get_dialogue_processor(self) -> DialogueProcessor | None:
        """Get or create a dialogue processor instance."""
        try:
            return DialogueProcessor(self)
        except Exception:
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
        return WorkspaceSnapshotResult(
            project_id=request.project_id,
            novel_id=request.novel_id,
            canonical_objects=tuple(canonical_objects),
            derived_artifacts=derived_artifacts,
            review_proposals=tuple(),
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
        return self._ai_config_service.list_provider_configs()

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
        return self._ai_config_service.save_provider_config(
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
        return self._ai_config_service.set_active_provider(provider_id)

    def delete_provider_config(self, provider_id: str) -> bool:
        """Delete an AI provider configuration."""
        return self._ai_config_service.delete_provider_config(provider_id)

    def test_provider_config(self, provider_id: str) -> dict[str, object]:
        """Test an AI provider configuration."""
        return self._ai_config_service.test_provider_config(provider_id)

    def diagnose_project(self, project_id: str, novel_id: str | None) -> JSONObject:
        """
        Run intelligent diagnosis on the project.

        Returns a diagnosis report with issues, suggested actions, and health score.
        """
        return self._diagnosis_service.diagnose_project(project_id, novel_id)

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

    def delete_workspace_object(self, *, family: str, object_id: str) -> bool:
        if family == "chapter_artifact":
            return self.__storage.delete_derived_object(family, object_id)
        return self.__storage.delete_canonical_object(family, object_id)


    def get_retrieval_status(self, project_id: str, novel_id: str | None) -> RetrievalStatusSnapshot:
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        return self._retrieval_service.get_retrieval_status(
            project_id=project_id,
            novel_id=novel_id,
            workspace_canonical_objects=workspace.canonical_objects,
            read_object_func=self.read_object,
        )

    def rebuild_retrieval_support(self, request: RetrievalRebuildRequest) -> RetrievalRebuildResult:
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        return self._retrieval_service.rebuild_retrieval_support(
            request=request,
            workspace_canonical_objects=workspace.canonical_objects,
            read_object_func=self.read_object,
        )

    def search_retrieval_support(self, request: RetrievalSearchRequest) -> RetrievalSearchResult:
        workspace = self.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=request.project_id, novel_id=request.novel_id)
        )
        return self._retrieval_service.search_retrieval_support(
            request=request,
            workspace_canonical_objects=workspace.canonical_objects,
            read_object_func=self.read_object,
        )

    def apply_mutation(self, request: ServiceMutationRequest) -> ServiceMutationResult:
        if request.target_family == "skill":
            request = replace(request, payload=validate_skill_payload(dict(request.payload)))
        result = self.__policy.apply_mutation(request.to_policy_request())
        return self._service_mutation_result(result)

    def get_skill_workshop(self, request: SkillWorkshopRequest) -> SkillWorkshopResult:
        return self._skill_service.get_skill_workshop(
            request,
            get_workspace_snapshot_func=self.get_workspace_snapshot,
            compare_skill_versions_func=self.compare_skill_versions,
        )

    def upsert_skill_workshop_skill(self, request: SkillWorkshopUpsertRequest) -> SkillWorkshopMutationResult:
        return self._skill_service.upsert_skill_workshop_skill(
            request,
            read_object_func=self.read_object,
            apply_mutation_func=self.apply_mutation,
        )

    def import_skill_workshop_skill(self, request: SkillWorkshopImportRequest) -> SkillWorkshopMutationResult:
        return self._skill_service.import_skill_workshop_skill(
            request,
            upsert_skill_workshop_skill_func=self.upsert_skill_workshop_skill,
        )

    def rollback_skill_workshop_skill(self, request: SkillWorkshopRollbackRequest) -> SkillWorkshopMutationResult:
        return self._skill_service.rollback_skill_workshop_skill(
            request,
            read_object_func=self.read_object,
            upsert_skill_workshop_skill_func=self.upsert_skill_workshop_skill,
        )

    def compare_skill_versions(self, request: SkillWorkshopCompareRequest) -> SkillWorkshopComparison:
        return self._skill_service.compare_skill_versions(request)

    def open_chat_session(self, request: OpenChatSessionRequest) -> OpenChatSessionResult:
        return self._chat_service.open_chat_session(request)

    def get_chat_session(self, request: GetChatSessionRequest) -> ChatSessionSnapshot:
        return self._chat_service.get_chat_session(request)

    def process_chat_turn(self, request: ChatTurnRequest) -> ChatTurnResult:
        return self._chat_service.process_chat_turn(request)

    def _classify_chat_intent(self, user_text: str, request: "ChatTurnRequest") -> str | None:
        """Classify chat intent: 'edit_content', a workbench_type string, or None (fallback to dialogue)."""
        return self._chat_service.classify_chat_intent(user_text, request)

    def _apply_chat_edit(
        self,
        *,
        request: "ChatTurnRequest",
        user_instruction: str,
    ) -> "tuple[JSONObject, str, str] | None":
        """Apply an AI-driven content edit to the source object via chat."""
        return self._chat_service.apply_chat_edit(request=request, user_instruction=user_instruction)

    def _generate_downstream_content_from_chat(
        self,
        *,
        request: ChatTurnRequest,
    ) -> tuple[JSONObject, str, str] | None:
        """Generate downstream content based on chat context."""
        return self._chat_service.generate_downstream_content_from_chat(request=request)

    def create_export_artifact(self, request: ExportArtifactRequest) -> ExportArtifactResult:
        return self._import_export_service.create_export_artifact(request)


    def publish_export(self, request: PublishExportRequest) -> PublishExportResult:
        return self._import_export_service.publish_export(
            request,
            build_publish_export_payload_func=self._build_publish_export_payload,
        )

    def publish_export_artifact(self, request: PublishExportArtifactRequest) -> PublishExportArtifactResult:
        return self._import_export_service.publish_export_artifact(request)

    def generate_scene_to_chapter_workbench(
        self,
        request: SceneToChapterWorkbenchRequest,
    ) -> SceneToChapterWorkbenchResult:
        return self._workbench_service.generate_scene_to_chapter_workbench(request)

    def _generate_scene_to_chapter_workbench_legacy(
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
        return self._workbench_service.generate_outline_to_plot_workbench(request)

    def _generate_outline_to_plot_workbench_legacy(
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
        try:
            generated_plots = self._generate_plot_nodes_with_ai(
                outline_node=outline,
                novel_context=novel_context,
                skills=skills,
                parent_outline=parent_outline,
            )
        except AIProviderError:
            if request.require_ai:
                raise
            generated_plots = []

        if request.require_ai and not generated_plots:
            raise AIProviderError("AI 未返回可用的剧情节点，请检查模型配置或提示词输出。")

        # For CREATE path, create the first plot node (or a default one if AI failed)
        if generated_plots:
            first_plot = generated_plots[0]
            plot_payload: JSONObject = {
                "novel_id": request.novel_id,
                "outline_node_id": request.outline_node_object_id,
                "title": _non_empty_candidate_text(first_plot, "title", _payload_text(outline.payload, "title")),
                "summary": _non_empty_candidate_text(
                    first_plot,
                    "summary",
                    _payload_text(outline.payload, "summary") or _payload_text(outline.payload, "body"),
                ),
                "sequence_order": first_plot.get("sequence_order", 1),
                "notes": _non_empty_candidate_text(first_plot, "notes"),
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
                    "title": _non_empty_candidate_text(plot_data, "title", f"Plot {i}"),
                    "summary": _non_empty_candidate_text(
                        plot_data,
                        "summary",
                        _payload_text(outline.payload, "summary") or _payload_text(outline.payload, "body"),
                    ),
                    "sequence_order": plot_data.get("sequence_order", i + 1),
                    "notes": _non_empty_candidate_text(plot_data, "notes"),
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
        return self._workbench_service.generate_plot_to_event_workbench(request)

    def _generate_plot_to_event_workbench_legacy(
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
        try:
            generated_events = self._generate_events_with_ai(
                plot_node=plot_node,
                novel_context=novel_context,
                outline_context=outline_context,
                skills=skills,
            )
        except AIProviderError:
            if request.require_ai:
                raise
            generated_events = []

        if request.require_ai and not generated_events:
            raise AIProviderError("AI 未返回可用的事件节点，请检查模型配置或提示词输出。")

        if generated_events:
            first_event = generated_events[0]
            event_payload: JSONObject = {
                "novel_id": request.novel_id,
                "plot_node_id": request.plot_node_object_id,
                "title": _non_empty_candidate_text(first_event, "title", _payload_text(plot_node.payload, "title")),
                "description": _non_empty_candidate_text(
                    first_event,
                    "description",
                    _payload_text(plot_node.payload, "summary") or _payload_text(plot_node.payload, "notes"),
                ),
                "sequence_order": first_event.get("sequence_order", 1),
                "location": _non_empty_candidate_text(first_event, "location"),
                "characters_involved": _candidate_string_list(first_event, "characters_involved"),
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
                    "title": _non_empty_candidate_text(event_data, "title", f"Event {i}"),
                    "description": _non_empty_candidate_text(
                        event_data,
                        "description",
                        _payload_text(plot_node.payload, "summary") or _payload_text(plot_node.payload, "notes"),
                    ),
                    "sequence_order": event_data.get("sequence_order", i + 1),
                    "location": _non_empty_candidate_text(event_data, "location"),
                    "characters_involved": _candidate_string_list(event_data, "characters_involved"),
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
        return self._workbench_service.generate_event_to_scene_workbench(request)

    def _generate_event_to_scene_workbench_legacy(
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
        try:
            generated_scenes = self._generate_scenes_with_ai(
                event=event,
                novel_context=novel_context,
                plot_context=plot_context,
                skills=skills,
                characters=characters,
                settings=settings,
            )
        except AIProviderError:
            if request.require_ai:
                raise
            generated_scenes = []

        if request.require_ai and not generated_scenes:
            raise AIProviderError("AI 未返回可用的场景节点，请检查模型配置或提示词输出。")

        if generated_scenes:
            first_scene = generated_scenes[0]
            scene_payload: JSONObject = {
                "novel_id": request.novel_id,
                "event_id": request.event_object_id,
                "title": _non_empty_candidate_text(first_scene, "title", _payload_text(event.payload, "title")),
                "setting": _non_empty_candidate_text(first_scene, "setting", _payload_text(event.payload, "location")),
                "pov_character": _non_empty_candidate_text(first_scene, "pov_character"),
                "characters_present": _candidate_string_list(first_scene, "characters_present"),
                "summary": _non_empty_candidate_text(
                    first_scene,
                    "scene_summary",
                    _payload_text(event.payload, "summary") or _payload_text(event.payload, "description"),
                ),
                "beat_breakdown": _candidate_string_list(first_scene, "beat_breakdown"),
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
                    "title": _non_empty_candidate_text(scene_data, "title", f"Scene {i}"),
                    "setting": _non_empty_candidate_text(scene_data, "setting", _payload_text(event.payload, "location")),
                    "pov_character": _non_empty_candidate_text(scene_data, "pov_character"),
                    "characters_present": _candidate_string_list(scene_data, "characters_present"),
                    "summary": _non_empty_candidate_text(
                        scene_data,
                        "scene_summary",
                        _payload_text(event.payload, "summary") or _payload_text(event.payload, "description"),
                    ),
                    "beat_breakdown": _candidate_string_list(scene_data, "beat_breakdown"),
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
        return self._import_export_service.import_from_donor(request)

    def execute_skill(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        return self._skill_service.execute_skill(
            request,
            apply_mutation_func=self.apply_mutation,
            create_export_artifact_func=self.create_export_artifact,
        )

    def _latest_artifact_for_object_id(self, object_id: str, *, family: str = "chapter_artifact") -> DerivedArtifactSnapshot | None:
        return self._helper_utils.latest_artifact_for_object_id(
            object_id,
            family=family,
            list_derived_artifacts_func=self.list_derived_artifacts,
        )

    def _latest_import_source(self, project_id: str) -> str | None:
        return self._helper_utils.latest_import_source(project_id)

    def _build_publish_export_payload(
        self,
        *,
        project_id: str,
        novel: CanonicalObjectSnapshot,
        chapter_artifact: DerivedArtifactSnapshot | None,
        export_format: str,
    ) -> JSONObject:
        return self._payload_builder_service.build_publish_export_payload(
            project_id=project_id,
            novel=novel,
            chapter_artifact=chapter_artifact,
            export_format=export_format,
        )

    def _review_target_title(
        self,
        proposal: ReviewProposalSnapshot,
        requested_payload: JSONObject,
        current_payload: JSONObject,
    ) -> str:
        return self._review_helpers.review_target_title(proposal, requested_payload, current_payload)

    def _review_state_detail(
        self,
        approval_state: str,
        decisions: tuple[ReviewDecisionSnapshot, ...],
        drift_details: JSONObject,
    ) -> str:
        return self._review_helpers.review_state_detail(approval_state, decisions, drift_details)

    def _decision_reason(self, decision: ReviewDecisionSnapshot) -> str | None:
        return self._review_helpers.decision_reason(decision)

    def _drift_summary(self, drift_details: JSONObject) -> str:
        return self._review_helpers.drift_summary(drift_details)

    def _render_prose_diff(self, before: JSONObject, after: JSONObject) -> str:
        return self._review_helpers.render_prose_diff(before, after)

    def _prose_payload_text(self, payload: JSONObject) -> str:
        return self._review_helpers.prose_payload_text(payload)

    def _payload_text_value(self, payload: JSONObject, key: str) -> str | None:
        return self._helper_utils.payload_text_value(payload, key)

    def _payload_int_value(self, payload: JSONObject, key: str, default: int) -> int:
        return self._helper_utils.payload_int_value(payload, key, default)

    def _service_mutation_result(self, result: MutationExecutionResult) -> ServiceMutationResult:
        return self._helper_utils.service_mutation_result(result)

    def _latest_scene_chapter_artifact(
        self,
        scene_object_id: str,
        *,
        novel_id: str,
    ) -> DerivedArtifactSnapshot | None:
        return self._helper_utils.latest_scene_chapter_artifact(
            scene_object_id,
            novel_id=novel_id,
            list_derived_artifacts_func=self.list_derived_artifacts,
        )

    def _derived_artifact_by_revision(self, artifact_revision_id: str, *, family: str = "chapter_artifact") -> DerivedArtifactSnapshot | None:
        return self._helper_utils.derived_artifact_by_revision(
            artifact_revision_id,
            family=family,
            list_derived_artifacts_func=self.list_derived_artifacts,
        )

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
        return self._payload_builder_service.build_scene_to_chapter_payload(
            scene=scene,
            style_rules=style_rules,
            scoped_skills=scoped_skills,
            canonical_facts=canonical_facts,
            previous_payload=previous_payload,
            previous_artifact_revision_id=previous_artifact_revision_id,
        )

    def _scene_chapter_title(self, payload: JSONObject, scene_object_id: str) -> str:
        return self._payload_builder_service.scene_chapter_title(payload, scene_object_id)

    def _scene_body_seed(self, payload: JSONObject) -> str:
        return self._payload_builder_service.scene_body_seed(payload)

    def _workspace_summary_text(self, summary: WorkspaceObjectSummary) -> str:
        return self._helper_utils.workspace_summary_text(summary)

    def _skill_matches_scene_to_chapter_scope(self, payload: JSONObject) -> bool:
        return self._payload_builder_service.skill_matches_scene_to_chapter_scope(payload)

    # AI-powered generation helpers for workbenches

    def _generate_plot_nodes_with_ai(
        self,
        outline_node: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        skills: tuple[WorkspaceObjectSummary, ...],
        parent_outline: CanonicalObjectSnapshot | None,
    ) -> list[JSONObject]:
        """Generate plot nodes from outline using AI."""
        return self._legacy_workbench_service._generate_plot_nodes_with_ai(
            outline_node, novel_context, skills, parent_outline
        )

    def _generate_events_with_ai(
        self,
        plot_node: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        outline_context: CanonicalObjectSnapshot | None,
        skills: tuple[WorkspaceObjectSummary, ...],
    ) -> list[JSONObject]:
        """Generate events from plot node using AI."""
        return self._legacy_workbench_service._generate_events_with_ai(
            plot_node, novel_context, outline_context, skills
        )

    def _generate_scenes_with_ai(
        self,
        event: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        plot_context: CanonicalObjectSnapshot | None,
        skills: tuple[WorkspaceObjectSummary, ...],
        characters: tuple[WorkspaceObjectSummary, ...],
        settings: tuple[WorkspaceObjectSummary, ...],
    ) -> list[JSONObject]:
        """Generate scenes from event using AI."""
        return self._legacy_workbench_service._generate_scenes_with_ai(
            event, novel_context, plot_context, skills, characters, settings
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
        return self._iteration_service.start_workbench_iteration(
            request=request,
            generate_candidates_callback=self._generate_iteration_candidates,
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
        return self._iteration_service.submit_workbench_feedback(
            request=request,
            generate_revision_callback=self._generate_revision_candidates,
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
        return self._iteration_service.select_workbench_candidate(
            request=request,
            apply_to_canonical_callback=self._apply_candidate_to_canonical,
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

        return self._iteration_service.generate_iteration_candidates(
            workbench_type=workbench_type,
            parent_object_id=parent_object_id,
            novel_id=novel_id,
            project_id=project_id,
            actor=actor,
            session_id=session_id,
            iteration_number=iteration_number,
            workbench_methods=workbench_methods,
        )

    def _generate_revision_candidates(
        self,
        session: dict,
        base_draft: dict,
        feedback: WorkbenchFeedbackRequest,
        iteration_number: int,
    ) -> list[dict]:
        """Generate revised candidates based on feedback using AI when available."""
        return self._iteration_service.generate_revision_candidates(
            session=session,
            base_draft=base_draft,
            feedback=feedback,
            iteration_number=iteration_number,
            ai_client=self._get_active_ai_provider(),
            gather_workspace_skills_callback=self._gather_workspace_skills,
            gather_workspace_objects_callback=self._gather_workspace_objects,
            read_object_callback=self.read_object,
        )

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
        return self._legacy_workbench_service._gather_novel_context(novel_id)

    def _gather_workspace_skills(
        self, project_id: str, novel_id: str,
    ) -> tuple[WorkspaceObjectSummary, ...]:
        """Get active skills scoped to a novel."""
        return self._legacy_workbench_service._gather_workspace_skills(project_id, novel_id)

    def _gather_workspace_objects(
        self, project_id: str, novel_id: str, *families: str,
    ) -> tuple[WorkspaceObjectSummary, ...]:
        """Get workspace objects of specified families scoped to a novel."""
        return self._legacy_workbench_service._gather_workspace_objects(project_id, novel_id, *families)

    def _create_candidates_from_items(
        self,
        items: list[JSONObject],
        session_id: str,
        iteration_number: int,
        method: str,
        ai_generated: bool,
    ) -> list[dict]:
        """Create candidate drafts from a list of AI-generated items."""
        return self._legacy_workbench_service._create_candidates_from_items(
            items, session_id, iteration_number, method, ai_generated
        )

    def _outline_to_plot_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate plot candidates from an outline node using AI."""
        return self._legacy_workbench_service._outline_to_plot_candidates(
            parent_object_id, novel_id, project_id, actor, session_id, iteration_number
        )

    def _plot_to_event_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate event candidates from a plot node using AI."""
        return self._legacy_workbench_service._plot_to_event_candidates(
            parent_object_id, novel_id, project_id, actor, session_id, iteration_number
        )

    def _event_to_scene_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate scene candidates from an event using AI."""
        return self._legacy_workbench_service._event_to_scene_candidates(
            parent_object_id, novel_id, project_id, actor, session_id, iteration_number
        )

    def _scene_to_chapter_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate chapter candidates from a scene using AI."""
        return self._legacy_workbench_service._scene_to_chapter_candidates(
            parent_object_id, novel_id, project_id, actor, session_id, iteration_number
        )

