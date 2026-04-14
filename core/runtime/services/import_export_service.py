"""Import/Export service for managing donor imports and export artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from core.export import build_filesystem_projection_plan, write_projection_plan
from core.importers.contracts import ImportedObjectRecord
from core.importers.fanbianyi import (
    CONTRACT as FANBIANYI_CONTRACT,
    SOURCE_SURFACE as FANBIANYI_SOURCE_SURFACE,
    load_character_export_import_data,
)
from core.importers.webnovel_writer import (
    CONTRACT as WEBNOVEL_WRITER_CONTRACT,
    SOURCE_SURFACE as WEBNOVEL_WRITER_SOURCE_SURFACE,
    load_project_root_import_data,
)
from core.runtime.mutation_policy import MutationPolicyEngine
from core.runtime.storage import (
    CanonicalStorage,
    CanonicalWriteRequest,
    DerivedRecordInput,
    ImportRecordInput,
    JSONValue,
)
from core.runtime.types import (
    CanonicalObjectSnapshot,
    DerivedArtifactSnapshot,
    ExportArtifactRequest,
    ExportArtifactResult,
    ImportObjectResult,
    ImportRequest,
    ImportResult,
    PublishExportArtifactRequest,
    PublishExportArtifactResult,
    PublishExportRequest,
    PublishExportResult,
    ReadObjectRequest,
    SupportedDonor,
    WorkspaceSnapshotRequest,
)

JSONObject = dict[str, JSONValue]


class ImportExportService:
    """Service for managing import/export operations."""

    def __init__(self, storage: CanonicalStorage, mutation_engine: MutationPolicyEngine):
        self.__storage = storage
        self.__mutation_engine = mutation_engine

    def import_from_donor(self, request: ImportRequest) -> ImportResult:
        if request.donor_key is SupportedDonor.WEBNOVEL_WRITER:
            return self.import_webnovel_project_root(request.source_path, actor=request.actor)
        if request.project_id is None or request.novel_id is None:
            raise ValueError("restored-decompiled-artifacts import requires project_id and novel_id")
        return self.import_character_export(
            request.source_path,
            project_id=request.project_id,
            novel_id=request.novel_id,
            actor=request.actor,
        )

    def import_webnovel_project_root(self, source_path: Path, *, actor: str) -> ImportResult:
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

    def import_character_export(
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

    def create_export_artifact(
        self,
        request: ExportArtifactRequest,
    ) -> ExportArtifactResult:
        novel_id = self._payload_text_value(request.payload, "novel_id")
        if novel_id is None:
            raise ValueError("export payload must include novel_id")
        novel = self._read_object(ReadObjectRequest(family="novel", object_id=novel_id))
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

    def publish_export(
        self,
        request: PublishExportRequest,
        build_publish_export_payload_func,
    ) -> PublishExportResult:
        novel = self._read_object(ReadObjectRequest(family="novel", object_id=request.novel_id))
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
            scene = self._read_object(ReadObjectRequest(family="scene", object_id=source_scene_id))
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

        export_payload = build_publish_export_payload_func(
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

    def publish_export_artifact(
        self,
        request: PublishExportArtifactRequest,
    ) -> PublishExportArtifactResult:
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

    def _derived_artifact_by_revision(self, artifact_revision_id: str, *, family: str = "chapter_artifact") -> DerivedArtifactSnapshot | None:
        for artifact in self._list_derived_artifacts(family):
            if artifact.artifact_revision_id == artifact_revision_id:
                return artifact
        return None

    def _list_derived_artifacts(self, family: str) -> tuple[DerivedArtifactSnapshot, ...]:
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

    def _read_object(self, request: ReadObjectRequest):
        """Read a canonical object from storage."""
        from core.runtime.types import ReadObjectResult, CanonicalRevisionSnapshot, MutationRecordSnapshot

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
        return ReadObjectResult(head=head, revisions=(), mutations=())

    def _payload_text_value(self, payload: JSONObject, key: str) -> str | None:
        """Extract a text value from a payload."""
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _latest_artifact_for_object_id(self, object_id: str, *, family: str = "chapter_artifact") -> DerivedArtifactSnapshot | None:
        """Get the latest artifact for a given object_id."""
        candidates = [
            artifact
            for artifact in self._list_derived_artifacts(family)
            if artifact.object_id == object_id
        ]
        return candidates[-1] if candidates else None

    def _latest_import_source(self, project_id: str) -> str | None:
        """Get the latest import source for a project."""
        import_rows = self.__storage.fetch_import_records(project_id=project_id)
        if not import_rows:
            return None
        return str(import_rows[-1]["import_source"])

    @staticmethod
    def _import_object_result(row: ImportedObjectRecord) -> ImportObjectResult:
        return ImportObjectResult(
            family=row.family,
            object_id=row.object_id,
            revision_id=row.revision_id,
            source_ref=row.source_ref,
        )
