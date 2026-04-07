from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import BookCommandCenter  # noqa: E402
from core.runtime import (  # noqa: E402
    ChapterMutationSignals,
    EventToSceneWorkbenchRequest,
    ImportRequest,
    OutlineToPlotWorkbenchRequest,
    PlotToEventWorkbenchRequest,
    PublishExportArtifactRequest,
    PublishExportRequest,
    ReadObjectRequest,
    ReviewTransitionRequest,
    SceneToChapterWorkbenchRequest,
    ServiceMutationRequest,
    SkillWorkshopUpsertRequest,
    SuperwriterApplicationService,
    SupportedDonor,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402


def test_end_to_end_flow_imports_edits_reviews_skills_and_publishes_projection_only_bundle(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    donor_root = _write_donor_project(tmp_path / "donor-project")

    imported = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=donor_root,
            actor="importer-1",
        )
    )
    project_id = imported.project_id
    novel_id = next(item.object_id for item in imported.imported_objects if item.family == "novel")
    scene_id = next(item.object_id for item in imported.imported_objects if item.family == "scene")
    chapter_object_id = next(item.object_id for item in imported.imported_objects if item.family == "chapter_artifact")
    imported_chapter_revision_id = next(item.revision_id for item in imported.imported_objects if item.family == "chapter_artifact")

    shell = BookCommandCenter(service)
    snapshot = shell.build_snapshot(project_id=project_id, novel_id=novel_id)
    assert snapshot.stage_label == "发布就绪"
    assert any(route.route_id == "publish" for route in snapshot.routes)

    scene_edit = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            target_object_id=scene_id,
            payload={
                "novel_id": novel_id,
                "event_id": "evt_donor_1",
                "title": "Warehouse discovery",
                "summary": "The smuggler leaves the lock half-open and the floor wet with rain.",
            },
            actor="author-1",
            source_surface="scene_editor",
            revision_reason="tighten imported scene summary",
        )
    )
    assert scene_edit.disposition == "auto_applied"
    assert scene_edit.canonical_revision_id is not None

    chapter_edit = service.apply_mutation(
        ServiceMutationRequest(
            target_family="chapter_artifact",
            target_object_id=chapter_object_id,
            base_revision_id=imported_chapter_revision_id,
            source_scene_revision_id=scene_edit.canonical_revision_id,
            base_source_scene_revision_id=scene_edit.canonical_revision_id,
            payload={
                "novel_id": novel_id,
                "source_scene_id": scene_id,
                "source_scene_revision_id": scene_edit.canonical_revision_id,
                "chapter_title": "Chapter 1",
                "body": "The warehouse smelled of rain and iron, and every footstep sounded like a confession.",
            },
            actor="author-1",
            source_surface="chapter_editor",
            chapter_signals=ChapterMutationSignals(
                prose_only=True,
                preserves_facts=True,
                preserves_event_order=True,
                preserves_reveal_order=True,
                preserves_character_decisions=True,
                preserves_continuity=True,
            ),
        )
    )
    assert chapter_edit.disposition == "auto_applied"
    assert chapter_edit.artifact_revision_id is not None

    review_required = service.apply_mutation(
        ServiceMutationRequest(
            target_family="novel",
            target_object_id=novel_id,
            payload={
                "project_id": project_id,
                "title": "Legacy Novel Revised",
                "genre": "mystery",
            },
            actor="editor-1",
            source_surface="review_desk",
            revision_reason="rename imported novel",
        )
    )
    assert review_required.disposition == "review_required"
    assert review_required.proposal_id is not None
    approved = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=review_required.proposal_id,
            created_by="reviewer-1",
            approval_state="approved",
            decision_payload={"note": "approved before publish"},
        )
    )
    assert approved.approval_state == "approved"

    skill = service.upsert_skill_workshop_skill(
        SkillWorkshopUpsertRequest(
            novel_id=novel_id,
            actor="author-1",
            source_surface="skill_workshop_form",
            name="Harbor hush",
            description="Quietly observant prose",
            instruction="Prefer quiet sensory detail and delay the reveal until the end of the beat.",
            style_scope="scene_to_chapter",
            is_active=True,
        )
    )
    assert skill.object_id.startswith("skl_")

    publish_output_root = tmp_path / "publish-output"
    publish_result = service.publish_export(
        PublishExportRequest(
            project_id=project_id,
            novel_id=novel_id,
            actor="publisher-1",
            output_root=publish_output_root,
            chapter_artifact_object_id=chapter_object_id,
            base_chapter_artifact_revision_id=chapter_edit.artifact_revision_id,
            expected_source_scene_revision_id=scene_edit.canonical_revision_id,
        )
    )
    assert publish_result.disposition == "published"
    assert publish_result.export_result is not None
    assert publish_result.publish_result is not None
    bundle_path = Path(publish_result.publish_result.bundle_path)
    assert bundle_path.is_dir()
    assert (bundle_path / "manifest.json").exists()
    manuscript = (bundle_path / "manuscript.md").read_text(encoding="utf-8")
    assert "Legacy Novel Revised" in manuscript
    assert "every footstep sounded like a confession" in manuscript
    lineage = cast(dict[str, object], json.loads((bundle_path / "lineage.json").read_text(encoding="utf-8")))
    assert lineage["source_chapter_artifact_id"] == chapter_object_id
    assert lineage["source_scene_revision_id"] == scene_edit.canonical_revision_id
    assert skill.object_id in cast(list[str], lineage["active_skill_ids"])

    latest_export = service.list_derived_artifacts("export_artifact")[-1]
    latest_lineage = cast(dict[str, object], latest_export.payload["lineage"])
    assert latest_export.payload["source_chapter_artifact_id"] == chapter_object_id
    updated_novel = service.read_object(ReadObjectRequest(family="novel", object_id=novel_id))
    assert updated_novel.head is not None
    assert latest_lineage["novel_revision_id"] == updated_novel.head.current_revision_id

    publish_page = shell.render_route("/publish", project_id=project_id, novel_id=novel_id)
    assert publish_page.status_code == 200
    assert "发布导出" in publish_page.body
    assert publish_result.export_result.object_id in publish_page.body


def test_publish_export_recovery_handles_stale_lineage_importer_mismatch_and_interrupted_writes(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    donor_root = _write_donor_project(tmp_path / "donor-project")
    imported = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=donor_root,
            actor="importer-1",
        )
    )
    project_id = imported.project_id
    novel_id = next(item.object_id for item in imported.imported_objects if item.family == "novel")
    scene_id = next(item.object_id for item in imported.imported_objects if item.family == "scene")
    chapter_object_id = next(item.object_id for item in imported.imported_objects if item.family == "chapter_artifact")
    chapter_revision_id = next(item.revision_id for item in imported.imported_objects if item.family == "chapter_artifact")
    original_novel = service.read_object(ReadObjectRequest(family="novel", object_id=novel_id))
    assert original_novel.head is not None
    original_novel_revision = original_novel.head.current_revision_id

    mismatched_importer = service.publish_export(
        PublishExportRequest(
            project_id=project_id,
            novel_id=novel_id,
            actor="publisher-1",
            output_root=tmp_path / "publish-output-mismatch",
            chapter_artifact_object_id=chapter_object_id,
            base_chapter_artifact_revision_id=chapter_revision_id,
            expected_source_scene_revision_id=next(item.revision_id for item in imported.imported_objects if item.family == "scene"),
            expected_import_source=SupportedDonor.RESTORED_DECOMPILED_ARTIFACTS.value,
        )
    )
    assert mismatched_importer.disposition == "importer_mismatch"
    assert mismatched_importer.export_result is None

    scene_edit = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            target_object_id=scene_id,
            payload={
                "novel_id": novel_id,
                "event_id": "evt_donor_1",
                "title": "Warehouse discovery",
                "summary": "A second witness reaches the warehouse before dawn.",
            },
            actor="author-1",
            source_surface="scene_editor",
            revision_reason="advance the source scene beyond the imported chapter artifact",
        )
    )
    assert scene_edit.canonical_revision_id is not None
    stale_publish = service.publish_export(
        PublishExportRequest(
            project_id=project_id,
            novel_id=novel_id,
            actor="publisher-1",
            output_root=tmp_path / "publish-output-stale",
            chapter_artifact_object_id=chapter_object_id,
            base_chapter_artifact_revision_id=chapter_revision_id,
            expected_source_scene_revision_id=next(item.revision_id for item in imported.imported_objects if item.family == "scene"),
        )
    )
    assert stale_publish.disposition == "stale"
    assert stale_publish.stale_details is not None
    assert "source_scene" in stale_publish.stale_details
    assert service.list_derived_artifacts("export_artifact") == ()

    retry_service = SuperwriterApplicationService.for_sqlite(tmp_path / "retry.sqlite3")
    retry_imported = retry_service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=donor_root,
            actor="importer-2",
        )
    )
    retry_project_id = retry_imported.project_id
    retry_novel_id = next(item.object_id for item in retry_imported.imported_objects if item.family == "novel")
    retry_scene_revision_id = next(item.revision_id for item in retry_imported.imported_objects if item.family == "scene")
    retry_chapter_object_id = next(item.object_id for item in retry_imported.imported_objects if item.family == "chapter_artifact")
    retry_chapter_revision_id = next(item.revision_id for item in retry_imported.imported_objects if item.family == "chapter_artifact")
    retry_output_root = tmp_path / "publish-output-retry"
    retry_novel_before = retry_service.read_object(ReadObjectRequest(family="novel", object_id=retry_novel_id))
    assert retry_novel_before.head is not None
    retry_novel_revision_before = retry_novel_before.head.current_revision_id

    interrupted = retry_service.publish_export(
        PublishExportRequest(
            project_id=retry_project_id,
            novel_id=retry_novel_id,
            actor="publisher-2",
            output_root=retry_output_root,
            chapter_artifact_object_id=retry_chapter_object_id,
            base_chapter_artifact_revision_id=retry_chapter_revision_id,
            expected_source_scene_revision_id=retry_scene_revision_id,
            fail_after_file_count=1,
        )
    )
    assert interrupted.disposition == "projection_failed"
    assert interrupted.export_result is not None
    assert interrupted.publish_result is not None
    assert interrupted.publish_result.failure_kind == "interrupted_write"
    interrupted_bundle = Path(interrupted.publish_result.bundle_path)
    assert not interrupted_bundle.exists()
    retry_novel_after_failed_publish = retry_service.read_object(ReadObjectRequest(family="novel", object_id=retry_novel_id))
    assert retry_novel_after_failed_publish.head is not None
    assert retry_novel_after_failed_publish.head.current_revision_id == retry_novel_revision_before

    recovered = retry_service.publish_export_artifact(
        PublishExportArtifactRequest(
            artifact_revision_id=interrupted.export_result.artifact_revision_id,
            actor="publisher-2",
            output_root=retry_output_root,
        )
    )
    assert recovered.disposition == "published"
    assert Path(recovered.bundle_path).is_dir()
    assert (Path(recovered.bundle_path) / "manifest.json").exists()

    original_novel_after = service.read_object(ReadObjectRequest(family="novel", object_id=novel_id))
    assert original_novel_after.head is not None
    assert original_novel_after.head.current_revision_id == original_novel_revision


def test_end_to_end_upstream_generation_chain_flows_into_scene_to_chapter_behavior(tmp_path: Path) -> None:
    service, project_id, novel_id, outline_id, outline_revision_id = _seed_upstream_chain_workspace(tmp_path)

    plot = service.generate_outline_to_plot_workbench(
        OutlineToPlotWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            outline_node_object_id=outline_id,
            actor="author-1",
            expected_parent_revision_id=outline_revision_id,
        )
    )
    assert plot.disposition == "generated"
    assert plot.child_object_id is not None
    assert plot.child_revision_id is not None

    event = service.generate_plot_to_event_workbench(
        PlotToEventWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            plot_node_object_id=plot.child_object_id,
            actor="author-1",
            expected_parent_revision_id=plot.child_revision_id,
        )
    )
    assert event.disposition == "generated"
    assert event.child_object_id is not None
    assert event.child_revision_id is not None

    scene = service.generate_event_to_scene_workbench(
        EventToSceneWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            event_object_id=event.child_object_id,
            actor="author-1",
            expected_parent_revision_id=event.child_revision_id,
        )
    )
    assert scene.disposition == "generated"
    assert scene.child_object_id is not None
    assert scene.child_revision_id is not None
    assert scene.scene_payload["event_id"] == event.child_object_id
    assert scene.scene_payload["source_event_revision_id"] == event.child_revision_id

    generated_scene = service.read_object(ReadObjectRequest(family="scene", object_id=scene.child_object_id))
    assert generated_scene.head is not None
    assert generated_scene.head.payload["title"] == "Signal at Glass Harbor"

    chapter = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            scene_object_id=scene.child_object_id,
            actor="author-1",
            expected_source_scene_revision_id=scene.child_revision_id,
        )
    )
    assert chapter.disposition == "generated"
    assert chapter.artifact_object_id is not None
    assert chapter.artifact_revision_id is not None
    assert chapter.chapter_payload["source_scene_id"] == scene.child_object_id
    assert chapter.chapter_payload["source_scene_revision_id"] == scene.child_revision_id
    assert chapter.chapter_payload["chapter_title"] == "Signal at Glass Harbor"
    assert chapter.lineage_payload == {
        "source_scene_id": scene.child_object_id,
        "source_scene_revision_id": scene.child_revision_id,
        "previous_artifact_revision_id": None,
    }
    assert "Signal at Glass Harbor" in str(chapter.chapter_payload["body"])
    assert f"Event anchor: {event.child_object_id}." in str(chapter.chapter_payload["body"])


def _write_donor_project(donor_root: Path) -> Path:
    state_dir = donor_root / ".webnovel"
    state_dir.mkdir(parents=True)
    _ = (state_dir / "state.json").write_text(
        json.dumps(
            {
                "project": {"id": "legacy-project", "title": "Legacy Project"},
                "novel": {"id": "legacy-novel", "title": "Legacy Novel", "genre": "mystery"},
                "scenes": [
                    {
                        "id": "legacy-scene-1",
                        "event_id": "evt_donor_1",
                        "title": "Warehouse discovery",
                        "summary": "The smuggler leaves the lock half-open.",
                    }
                ],
                "chapters": [
                    {
                        "source_scene_id": "legacy-scene-1",
                        "title": "Chapter 1",
                        "body": "The warehouse smelled of rain and iron.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return donor_root


def _seed_upstream_chain_workspace(
    tmp_path: Path,
) -> tuple[SuperwriterApplicationService, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_chain",
            payload={"title": "Harbor Chain Project"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed project",
        )
    )
    novel = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="novel",
            object_id="nvl_chain",
            payload={"project_id": project.object_id, "title": "Harbor Chain Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    outline = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="outline_node",
            object_id="out_chain_root",
            payload={
                "novel_id": novel.object_id,
                "title": "Signal at Glass Harbor",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed outline node",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    return service, project.object_id, novel.object_id, outline.object_id, outline.revision_id
