"""Skill workshop service for managing style rules and skill execution."""

from __future__ import annotations

from typing import cast

from core.runtime.mutation_policy import MutationPolicyEngine
from core.runtime.storage import CanonicalStorage, JSONValue
from core.runtime.types import (
    ReadObjectRequest,
    ServiceMutationRequest,
    ServiceMutationResult,
    SkillWorkshopRequest,
    SkillWorkshopResult,
    SkillWorkshopSkillSnapshot,
    SkillWorkshopVersionSnapshot,
    SkillWorkshopCompareRequest,
    SkillWorkshopComparison,
    SkillWorkshopUpsertRequest,
    SkillWorkshopMutationResult,
    SkillWorkshopImportRequest,
    SkillWorkshopRollbackRequest,
    SkillExecutionRequest,
    SkillExecutionResult,
    ExportArtifactRequest,
    WorkspaceSnapshotRequest,
    WorkspaceObjectSummary,
)
from core.runtime.utils import _payload_text
from core.skills import (
    SkillAdapterRequest,
    adapt_donor_payload,
    diff_skill_payloads,
    render_skill_diff,
    validate_skill_payload,
)

JSONObject = dict[str, JSONValue]


class SkillService:
    """Service for managing skill workshop operations and skill execution."""

    def __init__(self, storage: CanonicalStorage, mutation_engine: MutationPolicyEngine):
        self.__storage = storage
        self.__mutation_engine = mutation_engine

    def get_skill_workshop(
        self,
        request: SkillWorkshopRequest,
        *,
        get_workspace_snapshot_func,
        compare_skill_versions_func,
    ) -> SkillWorkshopResult:
        """Get skill workshop data including skills, versions, and comparison."""
        workspace = get_workspace_snapshot_func(
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
                comparison = compare_skill_versions_func(
                    SkillWorkshopCompareRequest(
                        skill_object_id=selected_skill.object_id,
                        left_revision_id=request.left_revision_id,
                        right_revision_id=request.right_revision_id,
                    )
                )
            elif len(versions) >= 2:
                comparison = compare_skill_versions_func(
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

    def upsert_skill_workshop_skill(
        self,
        request: SkillWorkshopUpsertRequest,
        *,
        read_object_func,
        apply_mutation_func,
    ) -> SkillWorkshopMutationResult:
        """Create or update a skill workshop skill."""
        existing_payload: JSONObject = {}
        base_revision_id = request.base_revision_id
        target_object_id = request.skill_object_id
        if target_object_id is not None:
            current = read_object_func(ReadObjectRequest(family="skill", object_id=target_object_id))
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
        mutation = apply_mutation_func(
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

    def import_skill_workshop_skill(
        self,
        request: SkillWorkshopImportRequest,
        *,
        upsert_skill_workshop_skill_func,
    ) -> SkillWorkshopMutationResult:
        """Import a skill from a donor format."""
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
        return upsert_skill_workshop_skill_func(
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

    def rollback_skill_workshop_skill(
        self,
        request: SkillWorkshopRollbackRequest,
        *,
        read_object_func,
        upsert_skill_workshop_skill_func,
    ) -> SkillWorkshopMutationResult:
        """Rollback a skill to a previous revision."""
        read_result = read_object_func(
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
        return upsert_skill_workshop_skill_func(
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
        """Compare two versions of a skill."""
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

    def execute_skill(
        self,
        request: SkillExecutionRequest,
        *,
        apply_mutation_func,
        create_export_artifact_func,
    ) -> SkillExecutionResult:
        """Execute a skill with mutation and/or export operations."""
        mutation_result: ServiceMutationResult | None = None
        export_result = None
        if request.mutation_request is not None:
            mutation_result = apply_mutation_func(
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
            export_result = create_export_artifact_func(
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

    def _skill_workshop_snapshot(self, summary: WorkspaceObjectSummary) -> SkillWorkshopSkillSnapshot:
        """Convert a workspace object summary to a skill workshop snapshot."""
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
        """Get all versions of a skill."""
        head_row = self.__storage.fetch_canonical_head("skill", skill_object_id)
        if head_row is None:
            raise KeyError(skill_object_id)

        revision_rows = self.__storage.fetch_canonical_revisions(skill_object_id)
        versions = [
            SkillWorkshopVersionSnapshot(
                revision_id=cast(str, revision["revision_id"]),
                revision_number=cast(int, revision["revision_number"]),
                parent_revision_id=cast(str | None, revision.get("parent_revision_id")),
                name=_payload_text(cast(JSONObject, revision["snapshot"]), "name") or skill_object_id,
                instruction=_payload_text(cast(JSONObject, revision["snapshot"]), "instruction"),
                style_scope=_payload_text(cast(JSONObject, revision["snapshot"]), "style_scope") or "scene_to_chapter",
                is_active=bool(cast(JSONObject, revision["snapshot"]).get("is_active", False)),
                payload=cast(JSONObject, revision["snapshot"]),
            )
            for revision in revision_rows
        ]
        versions.sort(key=lambda revision: revision.revision_number, reverse=True)
        return tuple(versions)

    def _default_skill_revision_reason(self, target_object_id: str | None) -> str:
        """Get default revision reason for skill mutations."""
        return "create constrained skill workshop skill" if target_object_id is None else "update constrained skill workshop skill"
