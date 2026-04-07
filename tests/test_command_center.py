from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.parse import urlencode


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import BookCommandCenter, BookCommandCenterWSGIApp  # noqa: E402
from core.runtime import (  # noqa: E402
    CreateWorkspaceRequest,
    ImportRequest,
    ImportOutlineRequest,
    ReadObjectRequest,
    ServiceMutationRequest,
    SkillExecutionRequest,
    SuperwriterApplicationService,
    SupportedDonor,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402
from superwriter_local_server import _frontend_mode  # noqa: E402


def test_command_center_diagnoses_scene_backlog_and_routes_to_workbench(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=2,
        chapter_count=1,
    )
    shell = BookCommandCenter(service)

    snapshot = shell.build_snapshot(project_id=project_id, novel_id=novel_id)

    assert snapshot.stage_label == "场景积压"
    assert snapshot.object_counts["scene"] == 2
    assert snapshot.object_counts["chapter_artifact"] == 1
    assert any(signal.route_id == "workbench" for signal in snapshot.stale_signals)
    assert snapshot.next_actions[0].route_id == "workbench"
    assert snapshot.routes[0].href == f"/workbench?project_id={project_id}&novel_id={novel_id}"

    page = shell.render_route("/command-center", project_id=project_id, novel_id=novel_id)
    page_body = _page_body_text(page)
    assert page.status_code == 200
    assert "推荐的下一步动作" in page_body
    assert "变更审计可见性" in page_body
    assert f"/workbench?project_id={project_id}&amp;novel_id={novel_id}" in page_body


def test_command_center_prioritizes_review_desk_and_keeps_policy_context_visible(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=1,
    )
    shell = BookCommandCenter(service)

    review_result = service.apply_mutation(
        ServiceMutationRequest(
            target_family="novel",
            target_object_id=novel_id,
            payload={
                "project_id": project_id,
                "title": "Imported Novel Revised",
                "genre": "mystery",
            },
            actor="editor-1",
            source_surface="review_desk",
            revision_reason="rename novel through review",
        )
    )
    assert review_result.disposition == "review_required"

    skill_result = service.execute_skill(
        SkillExecutionRequest(
            skill_name="scene-polish",
            actor="author-1",
            source_surface="skill_studio",
            mutation_request=ServiceMutationRequest(
                target_family="scene",
                payload={
                    "novel_id": novel_id,
                    "event_id": "evt_skill_1",
                    "title": "Lantern crossing",
                    "summary": "The ferryman admits he forged the travel ledger.",
                },
                actor="author-1",
                source_surface="ignored-inside-skill-wrapper",
                revision_reason="skill-generated scene",
            ),
        )
    )
    assert skill_result.mutation_result is not None

    snapshot = shell.build_snapshot(project_id=project_id, novel_id=novel_id)

    assert snapshot.review_queue_count == 1
    assert snapshot.stage_label == "审核瓶颈"
    assert snapshot.next_actions[0].route_id == "review-desk"
    assert any(signal.route_id == "review-desk" for signal in snapshot.blocked_signals)
    assert any(
        entry.policy_class == "scene_structured"
        and entry.source_surface == "skill_studio"
        and entry.skill_name == "scene-polish"
        for entry in snapshot.audit_entries
    )

    page = shell.render_route("/command-center", project_id=project_id, novel_id=novel_id)
    page_body = _page_body_text(page)
    assert "审核队列" in page_body
    assert "skill_studio" in page_body
    assert "scene_structured" in page_body


def test_command_center_wsgi_routes_placeholders_and_validates_project_query(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=0,
    )
    app = BookCommandCenterWSGIApp(service)

    bad_response = _invoke_wsgi(app, path="/command-center", query="")
    assert bad_response[0] == "200 OK"
    assert "Superwriter 本地外壳" in bad_response[2]
    assert project_id in bad_response[2]
    assert novel_id in bad_response[2]

    good_response = _invoke_wsgi(
        app,
        path="/skills",
        query=f"project_id={project_id}&novel_id={novel_id}",
    )
    assert good_response[0] == "200 OK"
    assert "技能工坊" in good_response[2]
    assert "返回全书总控台" in good_response[2]


def test_command_center_publish_route_projects_explicit_export_bundle_through_shared_services(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=1,
    )
    app = BookCommandCenterWSGIApp(service)
    shell = BookCommandCenter(service)

    snapshot = shell.build_snapshot(project_id=project_id, novel_id=novel_id)
    assert snapshot.stage_label == "发布就绪"
    assert any(route.route_id == "publish" for route in snapshot.routes)

    get_response = _invoke_wsgi(
        app,
        path="/publish",
        query=f"project_id={project_id}&novel_id={novel_id}",
    )
    assert get_response[0] == "200 OK"
    assert "发布导出" in get_response[2]
    assert "发布保持仅投影" in get_response[2]

    chapter_artifact = service.list_derived_artifacts("chapter_artifact")[0]
    post_response = _invoke_post(
        app,
        path="/publish",
        query=f"project_id={project_id}&novel_id={novel_id}",
        form={
            "chapter_artifact_object_id": chapter_artifact.object_id,
            "base_artifact_revision_id": chapter_artifact.artifact_revision_id,
            "expected_source_scene_revision_id": chapter_artifact.source_scene_revision_id,
            "output_root": str(tmp_path / "publish-output"),
        },
    )
    assert post_response[0] == "200 OK"
    assert "发布 published" in post_response[2]
    assert (tmp_path / "publish-output").exists()


def test_command_center_create_novel_from_existing_context_creates_workspace_and_returns_correct_page(tmp_path: Path) -> None:
    """Regression: submitting /create-novel from a page that already has project_id in the query
    should still execute the creation (not silently re-render the existing page).
    The workspace manifest must be written to the user-selected directory."""
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=0,
    )
    shell = BookCommandCenter(service)
    workspace_root = tmp_path / "fresh-workspace"

    page = shell.submit_create_novel_form({
        "novel_title": "全新小说",
        "project_title": "全新项目",
        "folder_path": str(workspace_root),
    })
    page_body = _page_body_text(page)

    assert page.status_code == 200
    assert "已初始化小说工作区" in page_body
    assert "全新项目" in page_body
    assert "全新小说" in page_body
    manifest_path = workspace_root / ".superwriter" / "workspace.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["project"]["title"] == "全新项目"
    assert manifest["novel"]["title"] == "全新小说"
    assert manifest["workspace_root"] == str(workspace_root)


def test_application_service_create_workspace_owns_project_and_novel_creation(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")

    result = service.create_workspace(
        CreateWorkspaceRequest(
            project_title="Service-owned project",
            novel_title="Service-owned novel",
            actor="web-shell",
        )
    )

    project = service.read_object(ReadObjectRequest(family="project", object_id=result.project_id))
    novel = service.read_object(ReadObjectRequest(family="novel", object_id=result.novel_id))
    assert project.head is not None
    assert novel.head is not None
    assert project.head.payload["title"] == "Service-owned project"
    assert novel.head.payload["title"] == "Service-owned novel"
    assert novel.head.payload["project_id"] == result.project_id


def test_command_center_wsgi_start_page_handles_empty_database(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    app = BookCommandCenterWSGIApp(service)

    response = _invoke_wsgi(app, path="/", query="")

    assert response[0] == "200 OK"
    assert "Superwriter 本地外壳" in response[2]
    assert "暂无项目" in response[2]


def test_command_center_hybrid_mode_serves_app_mount_and_keeps_legacy_shell_routes(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=0,
    )
    dist_dir = _write_frontend_dist(
        tmp_path,
        index_html="<html><body><div id='app'>hybrid frontend</div><script src='/assets/app.js'></script></body></html>",
        assets={"assets/app.js": "console.log('hybrid');"},
    )
    app = BookCommandCenterWSGIApp(service, frontend_mode="hybrid", frontend_dist_dir=dist_dir)

    legacy_response = _invoke_wsgi(
        app,
        path="/command-center",
        query=f"project_id={project_id}&novel_id={novel_id}",
    )
    hybrid_mount = _invoke_wsgi(app, path="/app", query="")
    hybrid_asset = _invoke_wsgi(app, path="/assets/app.js", query="")
    legacy_alias = _invoke_wsgi(
        app,
        path="/legacy/command-center",
        query=f"project_id={project_id}&novel_id={novel_id}",
    )

    assert legacy_response[0] == "200 OK"
    assert "推荐的下一步动作" in legacy_response[2]
    assert hybrid_mount[0] == "200 OK"
    assert "hybrid frontend" in hybrid_mount[2]
    assert hybrid_asset[0] == "200 OK"
    assert "console.log('hybrid');" in hybrid_asset[2]
    assert legacy_alias[0] == "200 OK"
    assert "推荐的下一步动作" in legacy_alias[2]
    assert f"/legacy/workbench?project_id={project_id}&amp;novel_id={novel_id}" in legacy_alias[2]


def test_command_center_spa_mode_serves_dist_on_product_routes_and_keeps_start_page_without_project(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=0,
    )
    dist_dir = _write_frontend_dist(
        tmp_path,
        index_html="<html><body><div id='app'>spa frontend</div></body></html>",
        assets={"assets/main.css": "body { color: #111; }"},
    )
    app = BookCommandCenterWSGIApp(service, frontend_mode="spa", frontend_dist_dir=dist_dir)

    start_page = _invoke_wsgi(app, path="/", query="")
    spa_route = _invoke_wsgi(
        app,
        path="/command-center",
        query=f"project_id={project_id}&novel_id={novel_id}",
    )
    static_asset = _invoke_wsgi(app, path="/assets/main.css", query="")
    legacy_alias = _invoke_wsgi(
        app,
        path="/legacy/command-center",
        query=f"project_id={project_id}&novel_id={novel_id}",
    )

    assert start_page[0] == "200 OK"
    assert "Superwriter 本地外壳" in start_page[2]
    assert spa_route[0] == "200 OK"
    assert "spa frontend" in spa_route[2]
    assert "推荐的下一步动作" not in spa_route[2]
    assert static_asset[0] == "200 OK"
    assert "body { color: #111; }" in static_asset[2]
    assert legacy_alias[0] == "200 OK"
    assert "推荐的下一步动作" in legacy_alias[2]


def test_command_center_spa_mode_reports_missing_dist_bundle(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=0,
    )
    app = BookCommandCenterWSGIApp(service, frontend_mode="spa", frontend_dist_dir=tmp_path / "missing-dist")

    response = _invoke_wsgi(
        app,
        path="/command-center",
        query=f"project_id={project_id}&novel_id={novel_id}",
    )

    assert response[0] == "503 Service Unavailable"
    assert "缺少前端构建产物" in response[2]
    assert "SUPERWRITER_FRONTEND_MODE=legacy" in response[2]


def test_frontend_mode_defaults_to_legacy_and_validates_values(monkeypatch) -> None:
    monkeypatch.delenv("SUPERWRITER_FRONTEND_MODE", raising=False)
    assert _frontend_mode() == "legacy"

    monkeypatch.setenv("SUPERWRITER_FRONTEND_MODE", "HYBRID")
    assert _frontend_mode() == "hybrid"

    monkeypatch.setenv("SUPERWRITER_FRONTEND_MODE", "broken")
    try:
        _frontend_mode()
    except RuntimeError as error:
        assert "SUPERWRITER_FRONTEND_MODE" in str(error)
    else:
        raise AssertionError("Expected invalid frontend mode to raise RuntimeError")


def test_command_center_settings_page_exposes_stable_dom_anchors(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(
        tmp_path,
        scene_count=1,
        chapter_count=0,
    )
    shell = BookCommandCenter(service)

    page = shell.render_route("/settings", project_id=project_id, novel_id=novel_id)
    page_body = _page_body_text(page)

    assert page.status_code == 200
    assert 'id="settings-page-root"' in page_body
    assert 'id="settings-layout-anchor"' in page_body
    assert 'data-page="settings"' in page_body
    assert 'id="provider-list-root"' in page_body



def test_workbench_renders_upstream_sections_with_forms_and_readiness(tmp_path: Path) -> None:
    """The /workbench page must render independent sections for all four upstream
    links (outline->plot, plot->event, event->scene, scene->chapter) with
    actionable forms that wire to the upstream service methods."""
    db_path = tmp_path / "workbench_upstream.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            payload={"title": "Workbench Test Project"},
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
            payload={"project_id": project.object_id, "title": "Workbench Test Novel"},
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
            payload={
                "novel_id": novel.object_id,
                "outline_node_id": outline.object_id,
                "title": "Root Plot",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed plot",
        )
    )
    event = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="event",
            payload={
                "novel_id": novel.object_id,
                "plot_node_id": plot.object_id,
                "title": "Root Event",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    app = BookCommandCenterWSGIApp(service)

    response = _invoke_wsgi(
        app,
        path="/workbench",
        query=f"project_id={project.object_id}&novel_id={novel.object_id}",
    )

    assert response[0] == "200 OK"
    body = response[2]
    assert "导入大纲" in body
    assert 'name="link_type" value="import_outline"' in body
    # All four upstream section headings are present
    assert "大纲 → 剧情节点" in body
    assert "剧情节点 → 事件" in body
    assert "事件 → 场景" in body
    assert "场景 → 章节" in body
    # Readiness text reflects lineage state
    assert "全部大纲已推进到剧情节点" in body
    assert "全部剧情已拆解为事件" in body
    assert "1 个事件等待场景生成" in body  # event has no scene child
    # Actionable forms are present with correct link_type hidden fields
    assert 'name="link_type" value="outline_to_plot"' in body
    assert 'name="link_type" value="plot_to_event"' in body
    assert 'name="link_type" value="event_to_scene"' in body
    # Forms POST to /workbench
    assert 'action="/workbench?' in body
    # Back link to command center
    assert "返回全书总控台" in body


def test_workbench_post_invokes_upstream_service_and_rerenders(tmp_path: Path) -> None:
    """POST /workbench with link_type=event_to_scene should invoke the
    generate_event_to_scene_workbench service method and re-render the page
    with a flash message."""
    db_path = tmp_path / "workbench_post.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            payload={"title": "Post Test Project"},
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
            payload={"project_id": project.object_id, "title": "Post Test Novel"},
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
            payload={
                "novel_id": novel.object_id,
                "title": "Actionable Event",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    app = BookCommandCenterWSGIApp(service)

    post_response = _invoke_post(
        app,
        path="/workbench",
        query=f"project_id={project.object_id}&novel_id={novel.object_id}",
        form={
            "link_type": "event_to_scene",
            "parent_object_id": event.object_id,
            "expected_parent_revision_id": event.revision_id,
        },
    )

    assert post_response[0] == "200 OK"
    body = post_response[2]
    # Flash message confirms the service method was invoked
    assert "事件→场景" in body
    assert "generated" in body


def test_workbench_post_outline_to_plot_invokes_service(tmp_path: Path) -> None:
    """POST /workbench with link_type=outline_to_plot should invoke
    generate_outline_to_plot_workbench and produce a flash with the result."""
    db_path = tmp_path / "workbench_o2p.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            payload={"title": "O2P Project"},
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
            payload={"project_id": project.object_id, "title": "O2P Novel"},
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
            payload={"novel_id": novel.object_id, "title": "Outline Alpha"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed outline",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    app = BookCommandCenterWSGIApp(service)

    post_response = _invoke_post(
        app,
        path="/workbench",
        query=f"project_id={project.object_id}&novel_id={novel.object_id}",
        form={
            "link_type": "outline_to_plot",
            "parent_object_id": outline.object_id,
            "expected_parent_revision_id": outline.revision_id,
        },
    )

    assert post_response[0] == "200 OK"
    body = post_response[2]
    assert "大纲→剧情" in body
    assert "generated" in body
    # After generation, the outline should now show a child plot_node
    assert "全部大纲已推进到剧情节点" in body


def test_workbench_post_import_outline_creates_outline_node_and_rerenders(tmp_path: Path) -> None:
    db_path = tmp_path / "workbench_import_outline.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            payload={"title": "Import Outline Project"},
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
            payload={"project_id": project.object_id, "title": "Import Outline Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    app = BookCommandCenterWSGIApp(service)

    post_response = _invoke_post(
        app,
        path="/workbench",
        query=f"project_id={project.object_id}&novel_id={novel.object_id}",
        form={
            "link_type": "import_outline",
            "outline_title": "第一卷主线",
            "outline_body": "主角在码头收到一封改变命运的来信。",
        },
    )

    assert post_response[0] == "200 OK"
    body = post_response[2]
    assert "已导入大纲" in body
    assert "第一卷主线" in body
    assert "大纲 → 剧情节点" in body


def test_application_service_import_outline_creates_outline_node_without_shell_storage_access(tmp_path: Path) -> None:
    db_path = tmp_path / "import_outline_service.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            payload={"title": "Import Outline Project"},
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
            payload={"project_id": project.object_id, "title": "Import Outline Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)

    result = service.import_outline(
        ImportOutlineRequest(
            novel_id=novel.object_id,
            title="第一卷主线",
            body="主角在码头收到一封改变命运的来信。",
            actor="web-shell",
        )
    )

    outline = service.read_object(ReadObjectRequest(family="outline_node", object_id=result.object_id))
    assert outline.head is not None
    assert outline.head.payload["novel_id"] == novel.object_id
    assert outline.head.payload["title"] == "第一卷主线"
    assert outline.head.payload["summary"] == "主角在码头收到一封改变命运的来信。"


def test_workbench_stale_signals_route_to_workbench_for_upstream_gaps(tmp_path: Path) -> None:
    """When upstream canonical objects exist without their downstream children,
    the command-center snapshot must produce stale signals that route to workbench."""
    db_path = tmp_path / "stale_upstream.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            payload={"title": "Stale Signal Project"},
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
            payload={"project_id": project.object_id, "title": "Stale Signal Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    # Outline exists but no plot_node → stale signal
    storage.write_canonical_object(
        CanonicalWriteRequest(
            family="outline_node",
            payload={"novel_id": novel.object_id, "title": "Orphan Outline"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed outline",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    shell = BookCommandCenter(service)

    snapshot = shell.build_snapshot(project_id=project.object_id, novel_id=novel.object_id)

    stale_workbench_signals = [s for s in snapshot.stale_signals if s.route_id == "workbench"]
    assert any("大纲" in s.title for s in stale_workbench_signals)


def _seed_workspace(
    tmp_path: Path,
    *,
    scene_count: int,
    chapter_count: int,
) -> tuple[SuperwriterApplicationService, str, str]:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    donor_root = tmp_path / "donor-project"
    donor_state_dir = donor_root / ".webnovel"
    donor_state_dir.mkdir(parents=True)
    state_path = donor_state_dir / "state.json"

    scenes = [
        {
            "id": f"scene-{index + 1:03d}",
            "event_id": f"evt_{index + 1:03d}",
            "title": f"Scene {index + 1}",
            "summary": f"Summary for scene {index + 1}.",
        }
        for index in range(scene_count)
    ]
    chapters = [
        {
            "source_scene_id": scenes[index]["id"],
            "title": f"Chapter {index + 1}",
            "body": f"Chapter body for scene {index + 1}.",
        }
        for index in range(min(scene_count, chapter_count))
    ]
    _ = state_path.write_text(
        json.dumps(
            {
                "project": {"id": "legacy-project", "title": "Imported Project"},
                "novel": {"id": "legacy-novel", "title": "Imported Novel", "genre": "mystery"},
                "scenes": scenes,
                "chapters": chapters,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    imported = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=donor_root,
            actor="importer-1",
        )
    )
    novel_id = next(item.object_id for item in imported.imported_objects if item.family == "novel")
    return service, imported.project_id, novel_id


def _write_frontend_dist(
    tmp_path: Path,
    *,
    index_html: str,
    assets: dict[str, str],
) -> Path:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text(index_html, encoding="utf-8")
    for relative_path, content in assets.items():
        asset_path = dist_dir / relative_path
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(content, encoding="utf-8")
    return dist_dir


def _page_body_text(page) -> str:
    return page.body.decode("utf-8") if isinstance(page.body, bytes) else page.body


def _invoke_wsgi(
    app: BookCommandCenterWSGIApp,
    *,
    path: str,
    query: str,
) -> tuple[str, list[tuple[str, str]], str]:
    captured: dict[str, str | list[tuple[str, str]]] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        app(
            {
                "PATH_INFO": path,
                "QUERY_STRING": query,
            },
            start_response,
        )
    ).decode("utf-8")
    return (
        str(captured["status"]),
        list(captured["headers"] if isinstance(captured["headers"], list) else []),
        body,
    )


def _invoke_post(
    app: BookCommandCenterWSGIApp,
    *,
    path: str,
    query: str,
    form: dict[str, str],
) -> tuple[str, list[tuple[str, str]], str]:
    payload = urlencode(form).encode("utf-8")
    captured: dict[str, str | list[tuple[str, str]]] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(
        app(
            {
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": "POST",
                "CONTENT_LENGTH": str(len(payload)),
                "wsgi.input": io.BytesIO(payload),
            },
            start_response,
        )
    ).decode("utf-8")
    return (
        str(captured["status"]),
        list(captured["headers"] if isinstance(captured["headers"], list) else []),
        body,
    )
