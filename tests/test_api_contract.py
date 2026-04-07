from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import BookCommandCenterWSGIApp  # noqa: E402
from core.runtime import (  # noqa: E402
    ChapterMutationSignals,
    ImportRequest,
    SceneToChapterWorkbenchRequest,
    ServiceMutationRequest,
    SuperwriterApplicationService,
    SupportedDonor,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402


def test_api_create_novel_and_command_center_return_json_contract(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    app = BookCommandCenterWSGIApp(service)
    workspace_root = tmp_path / "workspace"

    create_response = _invoke_json(
        app,
        method="POST",
        path="/api/create-novel",
        payload={
            "novel_title": "Harbor Ledger",
            "project_title": "Harbor Project",
            "folder_path": str(workspace_root),
        },
    )

    assert create_response["status"] == "201 Response"
    assert create_response["body"]["ok"] is True
    workspace = create_response["body"]["data"]["workspace"]
    manifest_path = Path(workspace["manifest_path"])
    assert manifest_path.exists()
    assert workspace["project_title"] == "Harbor Project"
    assert workspace["novel_title"] == "Harbor Ledger"

    command_center_response = _invoke_json(
        app,
        method="GET",
        path="/api/command-center",
        query=f"project_id={workspace['project_id']}&novel_id={workspace['novel_id']}",
    )

    assert command_center_response["status"] == "200 OK"
    assert command_center_response["body"]["ok"] is True
    snapshot = command_center_response["body"]["data"]["snapshot"]
    assert snapshot["project_title"] == "Harbor Project"
    assert snapshot["novel_title"] == "Harbor Ledger"


def test_api_create_novel_invalid_input_uses_error_envelope(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    app = BookCommandCenterWSGIApp(service)

    response = _invoke_json(
        app,
        method="POST",
        path="/api/create-novel",
        payload={
            "novel_title": "   ",
            "project_title": "Harbor Project",
            "folder_path": str(tmp_path / "workspace"),
        },
    )

    assert response["status"] == "400 错误请求"
    assert response["body"] == {
        "ok": False,
        "error": {
            "code": "invalid_input",
            "message": "请填写小说名称。",
            "details": {},
        },
    }


def test_api_startup_and_settings_routes_return_internal_context_json(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    app = BookCommandCenterWSGIApp(service)

    workspace = _invoke_json(
        app,
        method="POST",
        path="/api/create-novel",
        payload={
            "novel_title": "Harbor Ledger",
            "project_title": "Harbor Project",
            "folder_path": str(tmp_path / "workspace"),
        },
    )["body"]["data"]["workspace"]

    startup = _invoke_json(app, method="GET", path="/api/startup")
    assert startup["status"] == "200 OK"
    assert startup["body"]["ok"] is True
    assert startup["body"]["data"]["startup"]["workspace_contexts"] == [
        {
            "project_id": workspace["project_id"],
            "project_title": "Harbor Project",
            "novel_id": workspace["novel_id"],
            "novel_title": "Harbor Ledger",
        }
    ]

    providers = _invoke_json(app, method="GET", path="/api/providers")
    settings = _invoke_json(app, method="GET", path="/api/settings")
    assert settings["status"] == "200 OK"
    assert settings["body"] == providers["body"]


def test_api_workbench_returns_generated_review_required_and_conflict_states(tmp_path: Path) -> None:
    generated_service, generated_project_id, generated_novel_id, event_id, event_revision_id = _seed_event_workspace(tmp_path / "generated")
    generated_app = BookCommandCenterWSGIApp(generated_service)

    generated = _invoke_json(
        generated_app,
        method="POST",
        path="/api/workbench",
        query=f"project_id={generated_project_id}&novel_id={generated_novel_id}",
        payload={
            "link_type": "event_to_scene",
            "parent_object_id": event_id,
            "expected_parent_revision_id": event_revision_id,
        },
    )
    assert generated["status"] == "200 OK"
    assert generated["body"]["ok"] is True
    assert generated["body"]["data"]["result"]["disposition"] == "generated"
    assert generated["body"]["data"]["result"]["child_object_id"].startswith("scn_")

    review_service, review_project_id, review_novel_id, outline_id, plot_id, plot_revision_id = _seed_outline_review_workspace(tmp_path / "review")
    review_app = BookCommandCenterWSGIApp(review_service)

    review_required = _invoke_json(
        review_app,
        method="POST",
        path="/api/workbench",
        query=f"project_id={review_project_id}&novel_id={review_novel_id}",
        payload={
            "link_type": "outline_to_plot",
            "parent_object_id": outline_id,
            "target_child_object_id": plot_id,
            "base_child_revision_id": plot_revision_id,
        },
    )
    assert review_required["status"] == "200 OK"
    assert review_required["body"]["ok"] is True
    assert review_required["body"]["data"]["result"]["disposition"] == "review_required"
    assert review_required["body"]["data"]["result"]["proposal_id"].startswith("prp_")

    stale = _invoke_json(
        review_app,
        method="POST",
        path="/api/workbench",
        query=f"project_id={review_project_id}&novel_id={review_novel_id}",
        payload={
            "link_type": "outline_to_plot",
            "parent_object_id": outline_id,
            "expected_parent_revision_id": "rev_stale",
        },
    )
    assert stale["status"] == "409 Response"
    assert stale["body"]["error"]["code"] == "conflict"
    assert "stale" in stale["body"]["error"]["message"]


def test_api_review_desk_preserves_exact_once_stale_and_not_found_states(tmp_path: Path) -> None:
    service, project_id, novel_id, proposal_id, _ = _seed_chapter_review_proposal(tmp_path / "review")
    app = BookCommandCenterWSGIApp(service)

    approved = _invoke_json(
        app,
        method="POST",
        path="/api/review-desk",
        query=f"project_id={project_id}&novel_id={novel_id}",
        payload={
            "proposal_id": proposal_id,
            "approval_state": "approved",
            "created_by": "reviewer-1",
            "decision_payload": {"note": "apply it"},
        },
    )
    assert approved["status"] == "200 OK"
    assert approved["body"]["data"]["result"]["resolution"] == "applied"

    replay = _invoke_json(
        app,
        method="POST",
        path="/api/review-desk",
        query=f"project_id={project_id}&novel_id={novel_id}",
        payload={
            "proposal_id": proposal_id,
            "approval_state": "approved",
            "created_by": "reviewer-2",
        },
    )
    assert replay["status"] == "200 OK"
    assert replay["body"]["data"]["result"]["resolution"] == "already_applied"

    stale_service, stale_project_id, stale_novel_id, stale_proposal_id, scene_id = _seed_chapter_review_proposal(tmp_path / "stale")
    stale_app = BookCommandCenterWSGIApp(stale_service)
    stale_update = stale_service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            target_object_id=scene_id,
            payload={
                "novel_id": stale_novel_id,
                "event_id": "evt_harbor_001",
                "title": "Glass Harbor",
                "summary": "The witness speaks before dawn.",
            },
            actor="author-1",
            source_surface="scene_editor",
            revision_reason="advance scene before approval",
        )
    )
    assert stale_update.canonical_revision_id is not None

    stale = _invoke_json(
        stale_app,
        method="POST",
        path="/api/review-desk",
        query=f"project_id={stale_project_id}&novel_id={stale_novel_id}",
        payload={
            "proposal_id": stale_proposal_id,
            "approval_state": "approved",
            "created_by": "reviewer-1",
        },
    )
    assert stale["status"] == "200 OK"
    assert stale["body"]["data"]["result"]["resolution"] == "stale"
    assert stale["body"]["data"]["result"]["approval_state"] == "stale"

    missing = _invoke_json(
        stale_app,
        method="POST",
        path="/api/review-desk",
        query=f"project_id={stale_project_id}&novel_id={stale_novel_id}",
        payload={
            "proposal_id": "prp_missing",
            "approval_state": "approved",
            "created_by": "reviewer-1",
        },
    )
    assert missing["status"] == "404 未找到"
    assert missing["body"]["error"]["code"] == "not_found"


def test_api_skills_support_happy_invalid_and_not_found_contracts(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_skill_workspace(tmp_path)
    app = BookCommandCenterWSGIApp(service)

    created = _invoke_json(
        app,
        method="POST",
        path="/api/skills",
        query=f"project_id={project_id}&novel_id={novel_id}",
        payload={
            "action": "create",
            "name": "Harbor hush",
            "description": "Quiet prose",
            "instruction": "Prefer quiet sensory detail.",
            "style_scope": "scene_to_chapter",
            "is_active": True,
        },
    )
    assert created["status"] == "200 OK"
    skill_object_id = created["body"]["data"]["result"]["object_id"]
    assert skill_object_id.startswith("skl_")

    invalid = _invoke_json(
        app,
        method="POST",
        path="/api/skills",
        query=f"project_id={project_id}&novel_id={novel_id}",
        payload={
            "action": "create",
            "name": "Bad skill",
            "instruction": "Prefer quiet sensory detail.",
            "style_scope": "invalid_scope",
        },
    )
    assert invalid["status"] == "400 错误请求"
    assert invalid["body"]["error"]["code"] == "invalid_input"

    missing = _invoke_json(
        app,
        method="POST",
        path="/api/skills",
        query=f"project_id={project_id}&novel_id={novel_id}",
        payload={
            "action": "rollback",
            "skill_object_id": skill_object_id,
            "target_revision_id": "rev_missing",
        },
    )
    assert missing["status"] == "404 未找到"
    assert missing["body"]["error"]["code"] == "not_found"

    workshop = _invoke_json(
        app,
        method="GET",
        path="/api/skills",
        query=f"project_id={project_id}&novel_id={novel_id}&selected_skill_id={skill_object_id}",
    )
    assert workshop["status"] == "200 OK"
    assert workshop["body"]["data"]["workshop"]["selected_skill"]["object_id"] == skill_object_id


def test_api_publish_preserves_dispositions_and_recovery(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    imported = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=_write_donor_project(tmp_path / "donor-project"),
            actor="importer-1",
        )
    )
    project_id = imported.project_id
    novel_id = next(item.object_id for item in imported.imported_objects if item.family == "novel")
    scene_id = next(item.object_id for item in imported.imported_objects if item.family == "scene")
    scene_revision_id = next(item.revision_id for item in imported.imported_objects if item.family == "scene")
    chapter_object_id = next(item.object_id for item in imported.imported_objects if item.family == "chapter_artifact")
    chapter_revision_id = next(item.revision_id for item in imported.imported_objects if item.family == "chapter_artifact")
    app = BookCommandCenterWSGIApp(service)

    importer_mismatch = _invoke_json(
        app,
        method="POST",
        path="/api/publish",
        query=f"project_id={project_id}&novel_id={novel_id}",
        payload={
            "chapter_artifact_object_id": chapter_object_id,
            "base_artifact_revision_id": chapter_revision_id,
            "expected_source_scene_revision_id": scene_revision_id,
            "expected_import_source": SupportedDonor.RESTORED_DECOMPILED_ARTIFACTS.value,
            "output_root": str(tmp_path / "mismatch-output"),
        },
    )
    assert importer_mismatch["status"] == "200 OK"
    assert importer_mismatch["body"]["data"]["result"]["disposition"] == "importer_mismatch"

    scene_update = service.apply_mutation(
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
            revision_reason="advance source scene",
        )
    )
    assert scene_update.canonical_revision_id is not None

    stale = _invoke_json(
        app,
        method="POST",
        path="/api/publish",
        query=f"project_id={project_id}&novel_id={novel_id}",
        payload={
            "chapter_artifact_object_id": chapter_object_id,
            "base_artifact_revision_id": chapter_revision_id,
            "expected_source_scene_revision_id": scene_revision_id,
            "output_root": str(tmp_path / "stale-output"),
        },
    )
    assert stale["status"] == "200 OK"
    assert stale["body"]["data"]["result"]["disposition"] == "stale"

    retry_service = SuperwriterApplicationService.for_sqlite(tmp_path / "retry.sqlite3")
    retry_imported = retry_service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=_write_donor_project(tmp_path / "retry-donor"),
            actor="importer-2",
        )
    )
    retry_project_id = retry_imported.project_id
    retry_novel_id = next(item.object_id for item in retry_imported.imported_objects if item.family == "novel")
    retry_scene_revision_id = next(item.revision_id for item in retry_imported.imported_objects if item.family == "scene")
    retry_chapter_object_id = next(item.object_id for item in retry_imported.imported_objects if item.family == "chapter_artifact")
    retry_chapter_revision_id = next(item.revision_id for item in retry_imported.imported_objects if item.family == "chapter_artifact")
    retry_app = BookCommandCenterWSGIApp(retry_service)

    interrupted = _invoke_json(
        retry_app,
        method="POST",
        path="/api/publish",
        query=f"project_id={retry_project_id}&novel_id={retry_novel_id}",
        payload={
            "chapter_artifact_object_id": retry_chapter_object_id,
            "base_artifact_revision_id": retry_chapter_revision_id,
            "expected_source_scene_revision_id": retry_scene_revision_id,
            "output_root": str(tmp_path / "retry-output"),
            "fail_after_file_count": 1,
        },
    )
    assert interrupted["status"] == "200 OK"
    assert interrupted["body"]["data"]["result"]["disposition"] == "projection_failed"
    artifact_revision_id = interrupted["body"]["data"]["result"]["export_result"]["artifact_revision_id"]

    recovered = _invoke_json(
        retry_app,
        method="POST",
        path="/api/publish",
        query=f"project_id={retry_project_id}&novel_id={retry_novel_id}",
        payload={
            "action": "publish_export_artifact",
            "artifact_revision_id": artifact_revision_id,
            "output_root": str(tmp_path / "retry-output"),
        },
    )
    assert recovered["status"] == "200 OK"
    assert recovered["body"]["data"]["result"]["disposition"] == "published"


def test_api_providers_are_service_backed_and_test_missing_provider_is_not_transport_error(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    app = BookCommandCenterWSGIApp(service)

    saved = _invoke_json(
        app,
        method="POST",
        path="/api/providers",
        payload={
            "action": "save",
            "provider_name": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-secret-1234",
            "model_name": "gpt-4o",
            "temperature": 0.5,
            "max_tokens": 2048,
            "is_active": True,
        },
    )
    assert saved["status"] == "200 OK"
    providers = saved["body"]["data"]["result"]["providers"]
    assert providers[0]["provider_name"] == "openai"
    assert "api_key" not in providers[0]
    assert providers[0]["api_key_masked"].startswith("sk")

    listed = _invoke_json(app, method="GET", path="/api/providers")
    assert listed["status"] == "200 OK"
    assert listed["body"]["data"]["settings"]["active_provider"]["provider_name"] == "openai"

    tested = _invoke_json(
        app,
        method="POST",
        path="/api/providers",
        payload={
            "action": "test",
            "provider_id": "ai_missing",
        },
    )
    assert tested["status"] == "200 OK"
    assert tested["body"]["data"]["result"]["test_result"] == {
        "success": False,
        "message": "Provider not found",
    }


def test_api_method_and_payload_errors_use_explicit_error_codes(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    app = BookCommandCenterWSGIApp(service)

    wrong_method = _invoke_json(app, method="POST", path="/api/command-center")
    assert wrong_method["status"] == "405 Response"
    assert wrong_method["body"] == {
        "ok": False,
        "error": {
            "code": "method_not_allowed",
            "message": "method POST is not allowed for this route",
            "details": {},
        },
    }

    array_payload = _invoke_raw_json(app, method="POST", path="/api/providers", payload=["bad"])
    assert array_payload["status"] == "400 错误请求"
    assert array_payload["body"] == {
        "ok": False,
        "error": {
            "code": "invalid_input",
            "message": "/api/providers request body must be a JSON object",
            "details": {},
        },
    }


def _seed_event_workspace(tmp_path: Path) -> tuple[SuperwriterApplicationService, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_event_api",
            payload={"title": "Event API Project"},
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
            object_id="nvl_event_api",
            payload={"project_id": project.object_id, "title": "Event API Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    event = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="event",
            object_id="evt_event_api",
            payload={"novel_id": novel.object_id, "title": "Harbor Event"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )
    return SuperwriterApplicationService.for_sqlite(db_path), project.object_id, novel.object_id, event.object_id, event.revision_id


def _seed_outline_review_workspace(tmp_path: Path) -> tuple[SuperwriterApplicationService, str, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_outline_api",
            payload={"title": "Outline API Project"},
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
            object_id="nvl_outline_api",
            payload={"project_id": project.object_id, "title": "Outline API Novel"},
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
            object_id="out_outline_api",
            payload={"novel_id": novel.object_id, "title": "Root Outline"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed outline",
        )
    )
    plot = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="plot_node",
            object_id="plt_outline_api",
            payload={"novel_id": novel.object_id, "outline_node_id": outline.object_id, "title": "Old Plot"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed plot",
        )
    )
    return SuperwriterApplicationService.for_sqlite(db_path), project.object_id, novel.object_id, outline.object_id, plot.object_id, plot.revision_id


def _seed_chapter_review_proposal(tmp_path: Path) -> tuple[SuperwriterApplicationService, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_review_api",
            payload={"title": "Review API Project"},
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
            object_id="nvl_review_api",
            payload={"project_id": project.object_id, "title": "Review API Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    scene = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="scene",
            object_id="scn_review_api",
            payload={
                "novel_id": novel.object_id,
                "event_id": "evt_harbor_001",
                "title": "Glass Harbor",
                "summary": "The courier slips into the harbor chapel.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed scene",
        )
    )
    _ = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="fact_state_record",
            object_id="fsr_review_api_1",
            payload={
                "novel_id": novel.object_id,
                "source_scene_id": scene.object_id,
                "fact": "The seal is cracked before the courier arrives.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed fact",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    initial = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project.object_id,
            novel_id=novel.object_id,
            scene_object_id=scene.object_id,
            actor="author-1",
            expected_source_scene_revision_id=scene.revision_id,
        )
    )
    assert initial.artifact_object_id is not None
    assert initial.artifact_revision_id is not None
    _ = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="fact_state_record",
            object_id="fsr_review_api_2",
            payload={
                "novel_id": novel.object_id,
                "source_scene_id": scene.object_id,
                "fact": "A second witness saw the broken seal before sunrise.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed second fact",
        )
    )
    rerun = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project.object_id,
            novel_id=novel.object_id,
            scene_object_id=scene.object_id,
            actor="author-1",
            expected_source_scene_revision_id=scene.revision_id,
            target_artifact_object_id=initial.artifact_object_id,
            base_artifact_revision_id=initial.artifact_revision_id,
            chapter_signals=ChapterMutationSignals(
                prose_only=False,
                preserves_facts=False,
                preserves_event_order=True,
                preserves_reveal_order=True,
                preserves_character_decisions=True,
                preserves_continuity=False,
                mixed_with_structural_edit=True,
                ambiguous_intent=True,
            ),
        )
    )
    assert rerun.proposal_id is not None
    return service, project.object_id, novel.object_id, rerun.proposal_id, scene.object_id


def _seed_skill_workspace(tmp_path: Path) -> tuple[SuperwriterApplicationService, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_skill_api",
            payload={"title": "Skill API Project"},
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
            object_id="nvl_skill_api",
            payload={"project_id": project.object_id, "title": "Skill API Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    return SuperwriterApplicationService.for_sqlite(db_path), project.object_id, novel.object_id


def _write_donor_project(donor_root: Path) -> Path:
    state_dir = donor_root / ".webnovel"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
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


def _invoke_json(
    app: BookCommandCenterWSGIApp,
    *,
    method: str,
    path: str,
    query: str = "",
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        app(
            {
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": method,
                "CONTENT_TYPE": "application/json",
                "CONTENT_LENGTH": str(len(encoded)),
                "wsgi.input": io.BytesIO(encoded),
            },
            start_response,
        )
    ).decode("utf-8")
    return {
        "status": str(captured["status"]),
        "headers": list(captured["headers"] if isinstance(captured["headers"], list) else []),
        "body": json.loads(body),
    }


def _invoke_raw_json(
    app: BookCommandCenterWSGIApp,
    *,
    method: str,
    path: str,
    query: str = "",
    payload: object,
) -> dict[str, object]:
    captured: dict[str, object] = {}
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        app(
            {
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": method,
                "CONTENT_TYPE": "application/json",
                "CONTENT_LENGTH": str(len(encoded)),
                "wsgi.input": io.BytesIO(encoded),
            },
            start_response,
        )
    ).decode("utf-8")
    return {
        "status": str(captured["status"]),
        "headers": list(captured["headers"] if isinstance(captured["headers"], list) else []),
        "body": json.loads(body),
    }
