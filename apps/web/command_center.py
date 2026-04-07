from __future__ import annotations

import html
import json
import mimetypes
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol, cast, runtime_checkable
from urllib.parse import parse_qs

from core.runtime import (
    ChapterMutationSignals,
    CreateWorkspaceRequest,
    DerivedArtifactSnapshot,
    EventToSceneWorkbenchRequest,
    ImportOutlineRequest,
    ListReviewProposalsRequest,
    OutlineToPlotWorkbenchRequest,
    PlotToEventWorkbenchRequest,
    PublishExportArtifactRequest,
    PublishExportRequest,
    ReadObjectRequest,
    ReviewDecisionSnapshot,
    ReviewDeskProposalSnapshot,
    ReviewDeskRequest,
    ReviewProposalSnapshot,
    ReviewTransitionRequest,
    SceneToChapterWorkbenchRequest,
    ServiceMutationRequest,
    SkillWorkshopComparison,
    SkillWorkshopImportRequest,
    SkillWorkshopRequest,
    SkillWorkshopRollbackRequest,
    SkillWorkshopSkillSnapshot,
    SkillWorkshopUpsertRequest,
    SkillWorkshopVersionSnapshot,
    SuperwriterApplicationService,
    WorkspaceContextSnapshot,
    WorkspaceObjectSummary,
    WorkspaceSnapshotRequest,
)
from core.skills import ALLOWED_STYLE_SCOPES


@dataclass(frozen=True, slots=True)
class CommandCenterRoute:
    route_id: str
    label: str
    href: str
    description: str
    readiness: str


@dataclass(frozen=True, slots=True)
class CommandCenterSignal:
    kind: str
    title: str
    detail: str
    route_id: str


@dataclass(frozen=True, slots=True)
class NextAction:
    priority: str
    title: str
    reason: str
    route_id: str


@dataclass(frozen=True, slots=True)
class CommandCenterAuditEntry:
    target_family: str
    target_object_id: str
    revision_id: str
    revision_number: int
    policy_class: str
    approval_state: str
    source_surface: str
    skill_name: str | None
    diff_excerpt: str


@dataclass(frozen=True, slots=True)
class CommandCenterSnapshot:
    project_id: str
    novel_id: str | None
    project_title: str
    novel_title: str
    stage_label: str
    stage_detail: str
    object_counts: dict[str, int]
    blocked_signals: tuple[CommandCenterSignal, ...]
    stale_signals: tuple[CommandCenterSignal, ...]
    next_actions: tuple[NextAction, ...]
    routes: tuple[CommandCenterRoute, ...]
    audit_entries: tuple[CommandCenterAuditEntry, ...]
    review_queue_count: int


@dataclass(frozen=True, slots=True)
class CommandCenterPage:
    status_code: int
    title: str
    body: str | bytes
    content_type: str = "text/html; charset=utf-8"


FrontendMode = Literal["legacy", "hybrid", "spa"]


@dataclass(frozen=True, slots=True)
class FrontendRuntimeConfig:
    mode: FrontendMode
    dist_dir: Path


@runtime_checkable
class _RequestBodyReader(Protocol):
    def read(self, size: int = ...) -> bytes | str: ...


class BookCommandCenter:
    __slots__: ClassVar[tuple[str]] = ("_service",)
    _service: SuperwriterApplicationService

    def __init__(self, service: SuperwriterApplicationService):
        self._service = service

    def build_snapshot(self, *, project_id: str, novel_id: str | None = None) -> CommandCenterSnapshot:
        workspace = self._service.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        project = self._first_family(workspace.canonical_objects, "project", project_id)
        novel = self._first_family(workspace.canonical_objects, "novel", novel_id)
        project_title = self._payload_text(project.payload, "title") if project is not None else "未绑定项目"
        novel_title = self._payload_text(novel.payload, "title") if novel is not None else "未选择小说"

        canonical_counts = Counter(summary.family for summary in workspace.canonical_objects)
        chapter_artifacts = self._filter_artifacts(
            self._service.list_derived_artifacts("chapter_artifact"),
            novel_id=novel_id,
        )
        export_artifacts = self._filter_artifacts(
            self._service.list_derived_artifacts("export_artifact"),
            novel_id=novel_id,
        )
        object_counts = dict(canonical_counts)
        object_counts["chapter_artifact"] = len(chapter_artifacts)
        object_counts["export_artifact"] = len(export_artifacts)

        scenes = [summary for summary in workspace.canonical_objects if summary.family == "scene"]
        events = [summary for summary in workspace.canonical_objects if summary.family == "event"]
        outlines = [summary for summary in workspace.canonical_objects if summary.family == "outline_node"]
        plots = [summary for summary in workspace.canonical_objects if summary.family == "plot_node"]
        skills = [summary for summary in workspace.canonical_objects if summary.family == "skill"]
        scene_ids_with_chapters = {
            self._payload_text(artifact.payload, "source_scene_id")
            for artifact in chapter_artifacts
            if self._payload_text(artifact.payload, "source_scene_id")
        }
        scenes_without_chapters = [scene for scene in scenes if scene.object_id not in scene_ids_with_chapters]

        review_queue = tuple(
            proposal
            for proposal in self._service.list_review_proposals(ListReviewProposalsRequest()).proposals
            if any(summary.object_id == proposal.target_object_id for summary in workspace.canonical_objects)
        )
        blocked_signals = self._build_blocked_signals(
            project=project,
            novel=novel,
            review_queue=review_queue,
        )
        stale_signals = self._build_stale_signals(
            outlines=outlines,
            plots=plots,
            events=events,
            scenes=scenes,
            scenes_without_chapters=scenes_without_chapters,
            skills=skills,
        )
        routes = self._build_routes(
            project_id=project_id,
            novel_id=novel_id,
            scenes_without_chapters=scenes_without_chapters,
            review_queue_count=len(review_queue),
            skills_count=len(skills),
            chapter_artifact_count=len(chapter_artifacts),
            export_artifact_count=len(export_artifacts),
        )
        next_actions = self._build_next_actions(
            routes=routes,
            blocked_signals=blocked_signals,
            stale_signals=stale_signals,
            review_queue=review_queue,
            scenes_without_chapters=scenes_without_chapters,
            skills=skills,
            chapter_artifacts=chapter_artifacts,
            export_artifacts=export_artifacts,
        )
        audit_entries = self._build_audit_entries(workspace.canonical_objects)
        stage_label, stage_detail = self._stage_summary(
            novel=novel,
            scenes=scenes,
            chapter_artifacts=chapter_artifacts,
            export_artifacts=export_artifacts,
            review_queue=review_queue,
            scenes_without_chapters=scenes_without_chapters,
        )
        return CommandCenterSnapshot(
            project_id=project_id,
            novel_id=novel_id,
            project_title=project_title,
            novel_title=novel_title,
            stage_label=stage_label,
            stage_detail=stage_detail,
            object_counts=object_counts,
            blocked_signals=blocked_signals,
            stale_signals=stale_signals,
            next_actions=next_actions,
            routes=routes,
            audit_entries=audit_entries,
            review_queue_count=len(review_queue),
        )

    def render_command_center(self, *, project_id: str, novel_id: str | None = None) -> str:
        snapshot = self.build_snapshot(project_id=project_id, novel_id=novel_id)
        return self._render_command_center_html(snapshot)

    def render_route(self, path: str, *, project_id: str, novel_id: str | None = None) -> CommandCenterPage:
        normalized_path = path.rstrip("/") or "/"
        if normalized_path in {"/", "/command-center"}:
            return CommandCenterPage(
                status_code=200,
                title="全书总控台",
                body=self.render_command_center(project_id=project_id, novel_id=novel_id),
            )
        if normalized_path == "/workbench":
            return self._render_workbench_page(project_id=project_id, novel_id=novel_id)
        if normalized_path == "/review-desk":
            return self._render_review_desk_page(project_id=project_id, novel_id=novel_id)
        if normalized_path == "/skills":
            if novel_id is None:
                return CommandCenterPage(
                    status_code=400,
                    title="技能工坊需要小说上下文",
                    body=self._render_layout(
                        "技能工坊需要小说上下文",
                        "受约束的工坊仅编辑小说范围的风格规则技能。",
                        f"<p><a href=\"/command-center{html.escape(self._route_query(project_id=project_id, novel_id=novel_id), quote=True)}\">返回全书总控台</a></p>",
                        current_route_id="skills",
                        project_id=project_id,
                        novel_id=novel_id,
                    ),
                )
            return self._render_skill_workshop_page(
                project_id=project_id,
                novel_id=novel_id,
            )
        if normalized_path == "/publish":
            if novel_id is None:
                return CommandCenterPage(
                    status_code=400,
                    title="发布导出需要小说上下文",
                    body=self._render_layout(
                        "发布导出需要小说上下文",
                        "发布界面仅投影小说范围的导出制品。",
                        f"<p><a href=\"/command-center{html.escape(self._route_query(project_id=project_id, novel_id=novel_id), quote=True)}\">返回全书总控台</a></p>",
                        current_route_id="publish",
                        project_id=project_id,
                        novel_id=novel_id,
                    ),
                )
            return self._render_publish_page(project_id=project_id, novel_id=novel_id)
        if normalized_path == "/settings":
            return self._render_settings_page(project_id=project_id, novel_id=novel_id)
        if normalized_path == "/api/providers":
            # Handle provider API requests
            return self._handle_providers_api(project_id=project_id, novel_id=novel_id)
        return CommandCenterPage(
            status_code=404,
            title="路由未找到",
            body=self._render_layout(
                "未找到",
                "此外壳目前仅暴露总控台和占位符调度界面。",
                "<p><a href=\"/command-center\">返回全书总控台</a></p>",
                project_id=project_id,
                novel_id=novel_id,
            ),
        )

    def render_missing_project_page(
        self,
        *,
        flash_message: str | None = None,
        flash_error: str | None = None,
        form: Mapping[str, str] | None = None,
    ) -> str:
        contexts = self._service.list_workspace_contexts()
        flash_markup = ""
        if flash_message:
            flash_markup = f'<p class="status-banner status-banner-success">{html.escape(flash_message)}</p>'
        elif flash_error:
            flash_markup = f'<p class="status-banner status-banner-danger">{html.escape(flash_error)}</p>'
        creation_markup = self._render_create_novel_form(form=form)
        if contexts:
            context_markup = "".join(self._render_start_context_card(context) for context in contexts)
            content = (
                "<section class=\"panel panel-wide\">"
                "<div class=\"panel-heading\"><h2>打开现有工作区</h2>"
                "<p>本地 SQLite 数据库已有规范项目数据。选择一个项目或项目+小说上下文进入总控台。</p></div>"
                f"<div class=\"route-grid\">{context_markup}</div>"
                "</section>"
                "<section class=\"panel panel-wide\">"
                "<div class=\"panel-heading\"><h2>新建小说</h2>"
                "<p>选择一个本地文件夹，立即初始化项目与小说上下文，并写入工作区清单。</p></div>"
                f"{flash_markup}{creation_markup}"
                "</section>"
            )
        else:
            content = (
                "<section class=\"panel panel-wide\">"
                "<div class=\"panel-heading\"><h2>新建小说</h2>"
                "<p>选择一个本地文件夹，创建全新的项目与小说工作区。</p></div>"
                f"{flash_markup}{creation_markup}"
                "</section>"
                "<section class=\"panel panel-wide\">"
                "<div class=\"panel-heading\"><h2>暂无项目</h2>"
                "<p>本地 SQLite 数据库已就绪，但尚未包含任何规范项目记录。</p></div>"
                "<ul>"
                "<li><strong>本地启动已就绪。</strong><p>服务器正在运行，仓库本地数据库已初始化完成。</p></li>"
                "<li><strong>下一步：创建第一个小说工作区。</strong><p>填写上方表单并选择本地文件夹后，将自动创建项目、小说和工作区清单。</p></li>"
                "<li><strong>深度链接仍然有效。</strong><p>如果您已知规范项目 ID，请打开 <code>/command-center?project_id=&lt;您的项目ID&gt;</code>。</p></li>"
                "</ul>"
                "</section>"
            )
        return self._render_layout(
            title="Superwriter 本地外壳",
            subtitle="本地 WSGI 应用正在运行。从仓库根目录启动 Superwriter 时从这里开始。",
            content=content,
        )

    def submit_create_novel_form(self, form: Mapping[str, str]) -> CommandCenterPage:
        try:
            created = self._create_novel_workspace(form)
        except (OSError, ValueError) as error:
            return CommandCenterPage(
                status_code=400,
                title="新建小说",
                body=self.render_missing_project_page(
                    flash_error=str(error),
                    form=form,
                ),
            )
        command_center_page = self.render_route(
            "/command-center",
            project_id=created["project_id"],
            novel_id=created["novel_id"],
        )
        command_center_body = command_center_page.body
        if isinstance(command_center_body, bytes):
            command_center_body = command_center_body.decode("utf-8")
        return CommandCenterPage(
            status_code=200,
            title="新建小说",
            body=command_center_body.replace(
                "<section class=\"hero-panel\">",
                "<p class=\"status-banner status-banner-success\">"
                + html.escape(f"已初始化小说工作区，并写入 {created['manifest_path']}。")
                + "</p><section class=\"hero-panel\">",
                1,
            ),
        )

    def handle_api_request(
        self,
        *,
        path: str,
        method: str,
        project_id: str | None,
        novel_id: str | None,
        query: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> CommandCenterPage:
        normalized_path = path.rstrip("/") or "/"
        try:
            if normalized_path == "/api/startup":
                self._require_method(method, {"GET"})
                return self._json_success({"startup": self._build_startup_api_snapshot()})
            if normalized_path == "/api/command-center":
                self._require_method(method, {"GET"})
                required_project_id = self._require_project_id(project_id)
                return self._json_success(
                    {"snapshot": self._serialize_json(self.build_snapshot(project_id=required_project_id, novel_id=novel_id))}
                )
            if normalized_path == "/api/create-novel":
                self._require_method(method, {"POST"})
                created = self._create_novel_workspace(self._string_mapping(payload))
                return self._json_success({"workspace": created}, status_code=201)
            if normalized_path == "/api/workbench":
                required_project_id = self._require_project_id(project_id)
                required_novel_id = self._require_novel_id(novel_id)
                if method == "GET":
                    return self._json_success(
                        {"workbench": self._build_workbench_api_snapshot(project_id=required_project_id, novel_id=required_novel_id)}
                    )
                self._require_method(method, {"POST"})
                return self._json_success(
                    {"result": self._serialize_json(self._submit_workbench_api(project_id=required_project_id, novel_id=required_novel_id, payload=payload))}
                )
            if normalized_path == "/api/review-desk":
                required_project_id = self._require_project_id(project_id)
                if method == "GET":
                    include_resolved = self._bool_from_value(query.get("include_resolved"), default=True)
                    desk = self._service.get_review_desk(
                        ReviewDeskRequest(project_id=required_project_id, novel_id=novel_id, include_resolved=include_resolved)
                    )
                    return self._json_success({"desk": self._serialize_json(desk)})
                self._require_method(method, {"POST"})
                result = self._service.transition_review(
                    self._review_transition_request(payload)
                )
                return self._json_success({"result": self._serialize_json(result)})
            if normalized_path == "/api/skills":
                required_project_id = self._require_project_id(project_id)
                required_novel_id = self._require_novel_id(novel_id)
                if method == "GET":
                    workshop = self._service.get_skill_workshop(
                        SkillWorkshopRequest(
                            project_id=required_project_id,
                            novel_id=required_novel_id,
                            selected_skill_id=self._optional_string(query, "selected_skill_id"),
                            left_revision_id=self._optional_string(query, "left_revision_id"),
                            right_revision_id=self._optional_string(query, "right_revision_id"),
                        )
                    )
                    return self._json_success({"workshop": self._serialize_json(workshop)})
                self._require_method(method, {"POST"})
                result = self._submit_skill_workshop_api(novel_id=required_novel_id, payload=payload)
                return self._json_success({"result": self._serialize_json(result)})
            if normalized_path == "/api/publish":
                required_project_id = self._require_project_id(project_id)
                required_novel_id = self._require_novel_id(novel_id)
                if method == "GET":
                    return self._json_success(
                        {"publish": self._build_publish_api_snapshot(project_id=required_project_id, novel_id=required_novel_id)}
                    )
                self._require_method(method, {"POST"})
                result = self._submit_publish_api(project_id=required_project_id, novel_id=required_novel_id, payload=payload)
                return self._json_success({"result": self._serialize_json(result)})
            if normalized_path in {"/api/providers", "/api/settings"}:
                if method == "GET":
                    return self._json_success({"settings": self._build_provider_settings_snapshot()})
                self._require_method(method, {"POST"})
                return self._json_success({"result": self._submit_provider_api(payload)})
            return self._json_error("not_found", f"Unknown API route: {normalized_path}", status_code=404)
        except KeyError as error:
            return self._json_error("not_found", self._error_message(error), status_code=404)
        except ValueError as error:
            message = self._error_message(error)
            status_code, code = self._value_error_status(message)
            return self._json_error(code, message, status_code=status_code)
        except (OSError, RuntimeError) as error:
            return self._json_error("dependency_failure", self._error_message(error), status_code=502)

    def _build_startup_api_snapshot(self) -> dict[str, object]:
        workspace_contexts = self._service.list_workspace_contexts()
        return {
            "workspace_contexts": self._serialize_json(workspace_contexts),
            "has_workspace_contexts": bool(workspace_contexts),
        }

    def _create_novel_workspace(self, form: Mapping[str, str]) -> dict[str, str]:
        folder_path = (form.get("folder_path") or "").strip()
        novel_title = (form.get("novel_title") or "").strip()
        project_title = (form.get("project_title") or "").strip() or novel_title
        if not folder_path:
            raise ValueError("请选择用于初始化小说的本地文件夹。")
        if not novel_title:
            raise ValueError("请填写小说名称。")
        workspace_root = Path(folder_path).expanduser().resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        workspace_result = self._service.create_workspace(
            CreateWorkspaceRequest(
                project_title=project_title,
                novel_title=novel_title,
                actor="web-shell",
                source_surface="command_center_start",
                source_ref="web-shell:/create-novel",
            )
        )
        manifest_path = self._write_workspace_manifest(
            workspace_root=workspace_root,
            project_id=workspace_result.project_id,
            project_title=project_title,
            novel_id=workspace_result.novel_id,
            novel_title=novel_title,
        )
        return {
            "project_id": workspace_result.project_id,
            "project_title": project_title,
            "novel_id": workspace_result.novel_id,
            "novel_title": novel_title,
            "workspace_root": str(workspace_root),
            "manifest_path": manifest_path,
        }

    def _submit_workbench_api(
        self,
        *,
        project_id: str,
        novel_id: str,
        payload: Mapping[str, object],
    ) -> object:
        link_type = self._required_string(payload, "link_type")
        if link_type == "import_outline":
            return self._service.import_outline(
                ImportOutlineRequest(
                    novel_id=novel_id,
                    title=self._required_string(payload, "outline_title"),
                    body=self._required_string(payload, "outline_body"),
                    actor="web-shell",
                    source_surface="workbench_outline_import",
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "outline_to_plot":
            parent_object_id = self._required_string(payload, "parent_object_id")
            return self._service.generate_outline_to_plot_workbench(
                OutlineToPlotWorkbenchRequest(
                    project_id=project_id,
                    novel_id=novel_id,
                    outline_node_object_id=parent_object_id,
                    actor="web-shell",
                    expected_parent_revision_id=self._optional_string(payload, "expected_parent_revision_id"),
                    target_child_object_id=self._optional_string(payload, "target_child_object_id"),
                    base_child_revision_id=self._optional_string(payload, "base_child_revision_id"),
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "plot_to_event":
            parent_object_id = self._required_string(payload, "parent_object_id")
            return self._service.generate_plot_to_event_workbench(
                PlotToEventWorkbenchRequest(
                    project_id=project_id,
                    novel_id=novel_id,
                    plot_node_object_id=parent_object_id,
                    actor="web-shell",
                    expected_parent_revision_id=self._optional_string(payload, "expected_parent_revision_id"),
                    target_child_object_id=self._optional_string(payload, "target_child_object_id"),
                    base_child_revision_id=self._optional_string(payload, "base_child_revision_id"),
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "event_to_scene":
            parent_object_id = self._required_string(payload, "parent_object_id")
            return self._service.generate_event_to_scene_workbench(
                EventToSceneWorkbenchRequest(
                    project_id=project_id,
                    novel_id=novel_id,
                    event_object_id=parent_object_id,
                    actor="web-shell",
                    expected_parent_revision_id=self._optional_string(payload, "expected_parent_revision_id"),
                    target_child_object_id=self._optional_string(payload, "target_child_object_id"),
                    base_child_revision_id=self._optional_string(payload, "base_child_revision_id"),
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "scene_to_chapter":
            scene_object_id = self._optional_string(payload, "scene_object_id") or self._optional_string(payload, "parent_object_id")
            if scene_object_id is None:
                raise ValueError("scene_object_id is required")
            chapter_signals_payload = payload.get("chapter_signals")
            chapter_signals = None
            if isinstance(chapter_signals_payload, dict):
                chapter_signals = ChapterMutationSignals(**chapter_signals_payload)
            return self._service.generate_scene_to_chapter_workbench(
                SceneToChapterWorkbenchRequest(
                    project_id=project_id,
                    novel_id=novel_id,
                    scene_object_id=scene_object_id,
                    actor="web-shell",
                    expected_source_scene_revision_id=self._optional_string(payload, "expected_source_scene_revision_id"),
                    target_artifact_object_id=self._optional_string(payload, "target_artifact_object_id"),
                    base_artifact_revision_id=self._optional_string(payload, "base_artifact_revision_id"),
                    chapter_signals=chapter_signals,
                    source_ref="web-shell:/api/workbench",
                    skill_name=self._optional_string(payload, "skill_name"),
                )
            )
        raise ValueError(f"unsupported workbench link_type: {link_type}")

    def _submit_skill_workshop_api(self, *, novel_id: str, payload: Mapping[str, object]) -> object:
        action = self._required_string(payload, "action").lower()
        if action == "create":
            return self._service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id,
                    actor="web-shell",
                    source_surface="skill_workshop_form",
                    name=self._required_string(payload, "name"),
                    description=self._string_value(payload.get("description")),
                    instruction=self._required_string(payload, "instruction"),
                    style_scope=self._optional_string(payload, "style_scope") or "scene_to_chapter",
                    is_active=self._bool_from_value(payload.get("is_active"), default=True),
                    revision_reason="从 API 创建受约束技能",
                    source_ref="web-shell:/api/skills",
                )
            )
        if action == "update":
            return self._service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id,
                    actor="web-shell",
                    source_surface="skill_workshop_form",
                    skill_object_id=self._required_string(payload, "skill_object_id"),
                    name=self._optional_string(payload, "name"),
                    description=self._optional_string(payload, "description"),
                    instruction=self._optional_string(payload, "instruction"),
                    style_scope=self._optional_string(payload, "style_scope"),
                    is_active=self._bool_from_optional_value(payload.get("is_active")),
                    base_revision_id=self._optional_string(payload, "base_revision_id"),
                    revision_reason="从 API 更新受约束技能",
                    source_ref="web-shell:/api/skills",
                )
            )
        if action == "toggle":
            return self._service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id,
                    actor="web-shell",
                    source_surface="skill_workshop_form",
                    skill_object_id=self._required_string(payload, "skill_object_id"),
                    is_active=self._bool_from_value(payload.get("is_active"), default=False),
                    base_revision_id=self._optional_string(payload, "base_revision_id"),
                    revision_reason="从 API 切换受约束技能激活状态",
                    source_ref="web-shell:/api/skills",
                )
            )
        if action == "rollback":
            return self._service.rollback_skill_workshop_skill(
                SkillWorkshopRollbackRequest(
                    skill_object_id=self._required_string(payload, "skill_object_id"),
                    target_revision_id=self._required_string(payload, "target_revision_id"),
                    actor="web-shell",
                    source_surface="skill_workshop_form",
                    revision_reason="从 API 回滚受约束技能",
                )
            )
        if action == "import":
            return self._service.import_skill_workshop_skill(
                SkillWorkshopImportRequest(
                    donor_kind=self._optional_string(payload, "donor_kind") or "prompt_template",
                    novel_id=novel_id,
                    actor="web-shell",
                    source_surface="skill_workshop_form",
                    donor_payload={
                        "name": self._string_value(payload.get("name")),
                        "title": self._string_value(payload.get("name")),
                        "description": self._string_value(payload.get("description")),
                        "instruction": self._string_value(payload.get("instruction")),
                        "prompt": self._string_value(payload.get("instruction")),
                        "role": self._string_value(payload.get("name")),
                    },
                    style_scope=self._optional_string(payload, "style_scope") or "scene_to_chapter",
                    is_active=self._bool_from_value(payload.get("is_active"), default=True),
                    source_ref="web-shell:/api/skills",
                )
            )
        raise ValueError("unsupported skill workshop action")

    def _submit_publish_api(
        self,
        *,
        project_id: str,
        novel_id: str,
        payload: Mapping[str, object],
    ) -> object:
        action = self._optional_string(payload, "action") or "publish"
        if action == "publish_export_artifact":
            return self._service.publish_export_artifact(
                PublishExportArtifactRequest(
                    artifact_revision_id=self._required_string(payload, "artifact_revision_id"),
                    actor="web-shell",
                    output_root=Path(self._required_string(payload, "output_root")).expanduser(),
                    source_surface="publish_surface",
                    fail_after_file_count=self._optional_int(payload, "fail_after_file_count"),
                )
            )
        if action != "publish":
            raise ValueError(f"unsupported publish action: {action}")
        return self._service.publish_export(
            PublishExportRequest(
                project_id=project_id,
                novel_id=novel_id,
                actor="web-shell",
                output_root=Path(self._required_string(payload, "output_root")).expanduser(),
                chapter_artifact_object_id=self._optional_string(payload, "chapter_artifact_object_id"),
                base_chapter_artifact_revision_id=self._optional_string(payload, "base_artifact_revision_id")
                or self._optional_string(payload, "base_chapter_artifact_revision_id"),
                expected_source_scene_revision_id=self._optional_string(payload, "expected_source_scene_revision_id"),
                export_object_id=self._optional_string(payload, "export_object_id"),
                expected_import_source=self._optional_string(payload, "expected_import_source") or "webnovel-writer",
                source_surface="publish_surface",
                source_ref="web-shell:/api/publish",
                fail_after_file_count=self._optional_int(payload, "fail_after_file_count"),
            )
        )

    def _submit_provider_api(self, payload: Mapping[str, object]) -> dict[str, object]:
        action = self._optional_string(payload, "action") or "save"
        if action == "save":
            provider_id = self._service.save_provider_config(
                provider_name=self._required_string(payload, "provider_name"),
                base_url=self._required_string(payload, "base_url"),
                api_key=self._required_string(payload, "api_key"),
                model_name=self._required_string(payload, "model_name"),
                temperature=self._float_from_value(payload.get("temperature"), default=0.7),
                max_tokens=self._int_from_value(payload.get("max_tokens"), default=4096),
                is_active=self._bool_from_value(payload.get("is_active"), default=False),
                created_by="web-shell",
            )
            return {
                "action": "save",
                "provider_id": provider_id,
                "providers": self._sanitize_provider_configs(self._service.list_provider_configs()),
            }
        provider_id = self._required_string(payload, "provider_id")
        if action == "activate":
            if not self._service.set_active_provider(provider_id):
                raise KeyError(provider_id)
            return {
                "action": "activate",
                "provider_id": provider_id,
                "providers": self._sanitize_provider_configs(self._service.list_provider_configs()),
            }
        if action == "delete":
            if not self._service.delete_provider_config(provider_id):
                raise KeyError(provider_id)
            return {
                "action": "delete",
                "provider_id": provider_id,
                "providers": self._sanitize_provider_configs(self._service.list_provider_configs()),
            }
        if action == "test":
            return {
                "action": "test",
                "provider_id": provider_id,
                "test_result": self._service.test_provider_config(provider_id),
            }
        raise ValueError(f"unsupported provider action: {action}")

    def _build_workbench_api_snapshot(self, *, project_id: str, novel_id: str) -> dict[str, object]:
        workspace = self._service.get_workspace_snapshot(WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id))
        chapter_artifacts = self._filter_artifacts(self._service.list_derived_artifacts("chapter_artifact"), novel_id=novel_id)
        review_proposals = tuple(
            proposal
            for proposal in self._service.list_review_proposals(ListReviewProposalsRequest()).proposals
            if proposal.target_family == "chapter_artifact"
        )
        return {
            "project_id": project_id,
            "novel_id": novel_id,
            "canonical_objects": self._serialize_json(workspace.canonical_objects),
            "chapter_artifacts": self._serialize_json(chapter_artifacts),
            "chapter_review_proposals": self._serialize_json(review_proposals),
        }

    def _build_publish_api_snapshot(self, *, project_id: str, novel_id: str) -> dict[str, object]:
        return {
            "project_id": project_id,
            "novel_id": novel_id,
            "chapter_artifacts": self._serialize_json(
                self._filter_artifacts(self._service.list_derived_artifacts("chapter_artifact"), novel_id=novel_id)
            ),
            "export_artifacts": self._serialize_json(
                self._filter_artifacts(self._service.list_derived_artifacts("export_artifact"), novel_id=novel_id)
            ),
        }

    def _build_provider_settings_snapshot(self) -> dict[str, object]:
        providers = self._sanitize_provider_configs(self._service.list_provider_configs())
        active_provider = next((provider for provider in providers if provider.get("is_active") is True), None)
        return {
            "providers": providers,
            "active_provider": active_provider,
        }

    def _sanitize_provider_configs(self, providers: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
        sanitized: list[dict[str, object]] = []
        for provider in providers:
            provider_dict = dict(provider)
            if "api_key" in provider_dict and isinstance(provider_dict["api_key"], str):
                provider_dict["api_key_masked"] = self._mask_secret(cast(str, provider_dict["api_key"]))
                del provider_dict["api_key"]
            sanitized.append(provider_dict)
        return sanitized

    def _mask_secret(self, value: str) -> str:
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"

    def _review_transition_request(self, payload: Mapping[str, object]) -> ReviewTransitionRequest:
        decision_payload = payload.get("decision_payload")
        if decision_payload is None:
            decision_payload = self._decision_payload_from_flat_fields(payload)
        if decision_payload is not None and not isinstance(decision_payload, dict):
            raise ValueError("decision_payload must be a JSON object when provided")
        return ReviewTransitionRequest(
            proposal_id=self._required_string(payload, "proposal_id"),
            created_by=self._optional_string(payload, "created_by") or "web-shell",
            approval_state=self._required_string(payload, "approval_state"),
            mutation_record_id=self._optional_string(payload, "mutation_record_id"),
            decision_payload=cast(dict[str, object] | None, decision_payload),
        )

    def _decision_payload_from_flat_fields(self, payload: Mapping[str, object]) -> dict[str, object] | None:
        decision_payload: dict[str, object] = {}
        note = self._optional_string(payload, "note")
        reason = self._optional_string(payload, "reason")
        if note is not None:
            decision_payload["note"] = note
        if reason is not None:
            decision_payload["reason"] = reason
        return decision_payload or None

    def _json_success(self, data: Mapping[str, object], *, status_code: int = 200) -> CommandCenterPage:
        return self._json_page({"ok": True, "data": self._serialize_json(data)}, status_code=status_code)

    def _json_error(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        details: Mapping[str, object] | None = None,
    ) -> CommandCenterPage:
        return self._json_page(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "details": self._serialize_json(details or {}),
                },
            },
            status_code=status_code,
        )

    def _json_page(self, payload: Mapping[str, object], *, status_code: int) -> CommandCenterPage:
        return CommandCenterPage(
            status_code=status_code,
            title="json",
            body=json.dumps(self._serialize_json(payload), ensure_ascii=False, sort_keys=True),
            content_type="application/json; charset=utf-8",
        )

    def _serialize_json(self, value: object) -> object:
        if is_dataclass(value):
            return self._serialize_json(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._serialize_json(child) for key, child in value.items()}
        if isinstance(value, tuple | list):
            return [self._serialize_json(child) for child in value]
        if isinstance(value, Path):
            return str(value)
        return value

    def _string_mapping(self, payload: Mapping[str, object]) -> dict[str, str]:
        return {str(key): self._string_value(value) for key, value in payload.items()}

    def _required_string(self, payload: Mapping[str, object], key: str) -> str:
        value = self._optional_string(payload, key)
        if value is None:
            raise ValueError(f"{key} is required")
        return value

    def _optional_string(self, payload: Mapping[str, object], key: str) -> str | None:
        return self._string_or_none(payload.get(key))

    def _string_or_none(self, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("expected string value")
        stripped = value.strip()
        return stripped or None

    def _string_value(self, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("expected string value")
        return value

    def _bool_from_optional_value(self, value: object) -> bool | None:
        if value is None:
            return None
        return self._bool_from_value(value, default=False)

    def _bool_from_value(self, value: object, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized:
                return default
            return normalized in {"true", "1", "yes", "on", "active"}
        raise ValueError("expected boolean value")

    def _optional_int(self, payload: Mapping[str, object], key: str) -> int | None:
        value = payload.get(key)
        if value is None:
            return None
        return self._int_from_value(value, default=0)

    def _int_from_value(self, value: object, *, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip():
            return int(value.strip())
        raise ValueError("expected integer value")

    def _float_from_value(self, value: object, *, default: float) -> float:
        if value is None:
            return default
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str) and value.strip():
            return float(value.strip())
        raise ValueError("expected number value")

    def _require_method(self, method: str, allowed: set[str]) -> None:
        if method not in allowed:
            raise ValueError(f"method {method} is not allowed for this route")

    def _require_project_id(self, project_id: str | None) -> str:
        if project_id is None:
            raise ValueError("project_id is required")
        return project_id

    def _require_novel_id(self, novel_id: str | None) -> str:
        if novel_id is None:
            raise ValueError("novel_id is required")
        return novel_id

    def _value_error_status(self, message: str) -> tuple[int, str]:
        lowered = message.lower()
        if "method " in lowered and " is not allowed" in lowered:
            return 405, "method_not_allowed"
        if any(token in lowered for token in ("illegal transition", "invalid transition", "unsupported approval_state")):
            return 409, "illegal_transition"
        if any(token in lowered for token in ("stale", "drift", "mismatch")):
            return 409, "conflict"
        return 400, "invalid_input"

    def _error_message(self, error: BaseException) -> str:
        return str(error.args[0]) if error.args else str(error)

    def _render_create_novel_form(self, *, form: Mapping[str, str] | None = None) -> str:
        values = form or {}
        return (
            "<form method=\"post\" action=\"/create-novel\" class=\"skill-form\">"
            "<label>小说名称<input type=\"text\" name=\"novel_title\" value=\"{novel_title}\" required /></label>"
            "<label>项目名称<input type=\"text\" name=\"project_title\" value=\"{project_title}\" placeholder=\"默认与小说名称一致\" /></label>"
            "<label>文件夹位置<input type=\"text\" name=\"folder_path\" value=\"{folder_path}\" placeholder=\"例如 D:\\\\Novels\\\\MyBook\" required /></label>"
            "<div class=\"button-row\"><button type=\"submit\">新建小说</button></div>"
            "<p class=\"form-note\">当前本地外壳使用文本路径输入初始化工作区；选择的文件夹会被创建，并写入 <code>.superwriter/workspace.json</code> 清单。</p>"
            "</form>"
        ).format(
            novel_title=html.escape((values.get("novel_title") or "").strip(), quote=True),
            project_title=html.escape((values.get("project_title") or "").strip(), quote=True),
            folder_path=html.escape((values.get("folder_path") or "").strip(), quote=True),
        )

    def _write_workspace_manifest(
        self,
        *,
        workspace_root: Path,
        project_id: str,
        project_title: str,
        novel_id: str,
        novel_title: str,
    ) -> str:
        manifest_dir = workspace_root / ".superwriter"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "workspace.json"
        manifest_payload = {
            "project": {
                "id": project_id,
                "title": project_title,
            },
            "novel": {
                "id": novel_id,
                "title": novel_title,
            },
            "workspace_root": str(workspace_root),
        }
        _ = manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(manifest_path)

    def _render_start_context_card(self, context: WorkspaceContextSnapshot) -> str:
        href = f"/command-center{self._route_query(project_id=context.project_id, novel_id=context.novel_id)}"
        detail = (
            f"小说上下文：<strong>{html.escape(context.novel_title or context.novel_id or '未知小说')}</strong>"
            if context.novel_id is not None
            else "仅项目上下文"
        )
        return (
            "<a class=\"route-card\" href=\"{href}\">"
            "<strong>{project_title}</strong>"
            "<p>{detail}</p>"
            "<span>project_id <code>{project_id}</code>{novel_line}</span>"
            "</a>"
        ).format(
            href=html.escape(href, quote=True),
            project_title=html.escape(context.project_title),
            detail=detail,
            project_id=html.escape(context.project_id),
            novel_line=(
                f" · novel_id <code>{html.escape(context.novel_id)}</code>"
                if context.novel_id is not None
                else ""
            ),
        )

    def _build_routes(
        self,
        *,
        project_id: str,
        novel_id: str | None,
        scenes_without_chapters: list[WorkspaceObjectSummary],
        review_queue_count: int,
        skills_count: int,
        chapter_artifact_count: int,
        export_artifact_count: int,
    ) -> tuple[CommandCenterRoute, ...]:
        query = self._route_query(project_id=project_id, novel_id=novel_id)
        return (
            CommandCenterRoute(
                route_id="workbench",
                label="流水线工作台",
                href=f"/workbench{query}",
                description="统一展示大纲→剧情、剧情→事件、事件→场景、场景→章节四条上下游链路的就绪状态。",
                readiness=(
                    f"{len(scenes_without_chapters)} 个场景排队中"
                    if scenes_without_chapters
                    else "无排队场景"
                ),
            ),
            CommandCenterRoute(
                route_id="review-desk",
                label="审核台",
                href=f"/review-desk{query}",
                description="通过服务层拥有的审批流程解决需要审核的提案。",
                readiness=(
                    f"{review_queue_count} 个提案等待中"
                    if review_queue_count
                    else "队列清空"
                ),
            ),
            CommandCenterRoute(
                route_id="skills",
                label="技能工坊",
                href=f"/skills{query}",
                description="调整影响后续生产界面的作者控制技能。",
                readiness=(
                    f"{skills_count} 个技能已附加"
                    if skills_count
                    else "尚未附加技能"
                ),
            ),
            CommandCenterRoute(
                route_id="publish",
                label="发布导出",
                href=f"/publish{query}",
                description="从已批准的规范和章节谱系投影显式导出包，而不将文件转变为真相。",
                readiness=(
                    f"{chapter_artifact_count} 个章节制品就绪 · {export_artifact_count} 个导出制品已记录"
                    if chapter_artifact_count
                    else "尚无章节制品就绪"
                ),
            ),
        )

    def _build_blocked_signals(
        self,
        *,
        project: WorkspaceObjectSummary | None,
        novel: WorkspaceObjectSummary | None,
        review_queue: tuple[ReviewProposalSnapshot, ...],
    ) -> tuple[CommandCenterSignal, ...]:
        signals: list[CommandCenterSignal] = []
        if project is None:
            signals.append(
                CommandCenterSignal(
                    kind="blocked",
                    title="项目上下文缺失",
                    detail="总控台在规范项目存在之前无法派发下游工作。",
                    route_id="command-center",
                )
            )
        if novel is None:
            signals.append(
                CommandCenterSignal(
                    kind="blocked",
                    title="小说范围未选择",
                    detail="工作台、审核和技能路由依赖于规范小说上下文。",
                    route_id="command-center",
                )
            )
        if review_queue:
            signals.append(
                CommandCenterSignal(
                    kind="blocked",
                    title="需要审核的变更正在等待",
                    detail=f"{len(review_queue)} 个提案必须在此外壳宣传清晰前进路径之前解决。",
                    route_id="review-desk",
                )
            )
        return tuple(signals)

    def _build_stale_signals(
        self,
        *,
        outlines: list[WorkspaceObjectSummary],
        plots: list[WorkspaceObjectSummary],
        events: list[WorkspaceObjectSummary],
        scenes: list[WorkspaceObjectSummary],
        scenes_without_chapters: list[WorkspaceObjectSummary],
        skills: list[WorkspaceObjectSummary],
    ) -> tuple[CommandCenterSignal, ...]:
        signals: list[CommandCenterSignal] = []
        if outlines and not plots:
            signals.append(
                CommandCenterSignal(
                    kind="stale",
                    title="大纲尚未推进到剧情节点",
                    detail="书籍已有结构种子，但尚无剧情层扩展可见。",
                    route_id="workbench",
                )
            )
        if plots and not events:
            signals.append(
                CommandCenterSignal(
                    kind="stale",
                    title="剧情节点正在等待事件拆解",
                    detail="叙事线在上游已存在，但事件级执行尚未跟上。",
                    route_id="workbench",
                )
            )
        if events and not scenes:
            signals.append(
                CommandCenterSignal(
                    kind="stale",
                    title="事件存在但场景未执行",
                    detail="流水线正在承载事件真相，但场景载荷尚未生成。",
                    route_id="workbench",
                )
            )
        if scenes_without_chapters:
            lead_scene = scenes_without_chapters[0]
            lead_title = self._payload_text(lead_scene.payload, "title") or lead_scene.object_id
            signals.append(
                CommandCenterSignal(
                    kind="stale",
                    title="场景正在等待成为章节",
                    detail=f"{len(scenes_without_chapters)} 个场景缺少章节制品；下一个是 {lead_title}。",
                    route_id="workbench",
                )
            )
        if scenes and not skills:
            signals.append(
                CommandCenterSignal(
                    kind="stale",
                    title="叙事工作正在无技能指导下进行",
                    detail="总控台可以看到场景进展，但没有规范技能对象附加以塑造后续处理。",
                    route_id="skills",
                )
            )
        return tuple(signals)

    def _build_next_actions(
        self,
        *,
        routes: tuple[CommandCenterRoute, ...],
        blocked_signals: tuple[CommandCenterSignal, ...],
        stale_signals: tuple[CommandCenterSignal, ...],
        review_queue: tuple[ReviewProposalSnapshot, ...],
        scenes_without_chapters: list[WorkspaceObjectSummary],
        skills: list[WorkspaceObjectSummary],
        chapter_artifacts: tuple[DerivedArtifactSnapshot, ...],
        export_artifacts: tuple[DerivedArtifactSnapshot, ...],
    ) -> tuple[NextAction, ...]:
        route_by_id = {route.route_id: route for route in routes}
        actions: list[NextAction] = []
        if review_queue and "review-desk" in route_by_id:
            target = review_queue[0]
            actions.append(
                NextAction(
                    priority="high",
                    title="Resolve the oldest review proposal",
                    reason=f"Policy already downgraded {target.target_family}:{target.target_object_id} into review, so the next safe move is approval work rather than more mutations.",
                    route_id="review-desk",
                )
            )
        if scenes_without_chapters and "workbench" in route_by_id:
            scene = scenes_without_chapters[0]
            scene_title = self._payload_text(scene.payload, "title") or scene.object_id
            actions.append(
                NextAction(
                    priority="high" if not blocked_signals else "medium",
                    title="将下一个场景推进为章节制品",
                    reason=f"{scene_title} 已是结构化真相，因此工作台是散文生产的正确下游界面。",
                    route_id="workbench",
                )
            )
        if not skills and "skills" in route_by_id:
            actions.append(
                NextAction(
                    priority="medium",
                    title="附加至少一个规范技能",
                    reason="外壳可以在没有技能的情况下路由生产，但作者控制规则在可见工作区状态中仍然缺失。",
                    route_id="skills",
                )
            )
        if (
            not review_queue
            and chapter_artifacts
            and "publish" in route_by_id
            and len(export_artifacts) < len(chapter_artifacts)
        ):
            actions.append(
                NextAction(
                    priority="medium",
                    title="将最新批准的章节投影为导出包",
                    reason="章节散文已在下游派生并批准，因此发布应仅从该谱系中具象化显式文件系统投影。",
                    route_id="publish",
                )
            )
        if not actions:
            fallback_route = "review-desk" if any(signal.route_id == "review-desk" for signal in blocked_signals) else "workbench"
            reason = (
                "审核队列已清空且章节覆盖已更新；从生产工作台继续。"
                if fallback_route == "workbench"
                else "使用审核界面检查最新的待决决策。"
            )
            actions.append(
                NextAction(
                    priority="medium",
                    title="从外壳的活动界面继续",
                    reason=reason,
                    route_id=fallback_route,
                )
            )
        if stale_signals and len(actions) < 3:
            seen_routes = {action.route_id for action in actions}
            for signal in stale_signals:
                if signal.route_id in seen_routes or signal.route_id == "command-center":
                    continue
                actions.append(
                    NextAction(
                        priority="medium",
                        title=signal.title,
                        reason=signal.detail,
                        route_id=signal.route_id,
                    )
                )
                seen_routes.add(signal.route_id)
                if len(actions) >= 3:
                    break
        return tuple(actions)

    def _build_audit_entries(
        self,
        objects: Iterable[WorkspaceObjectSummary],
    ) -> tuple[CommandCenterAuditEntry, ...]:
        audit_entries: list[CommandCenterAuditEntry] = []
        for summary in objects:
            read_result = self._service.read_object(
                ReadObjectRequest(
                    family=summary.family,
                    object_id=summary.object_id,
                    include_mutations=True,
                )
            )
            if not read_result.mutations:
                continue
            latest = read_result.mutations[-1]
            audit_entries.append(
                CommandCenterAuditEntry(
                    target_family=latest.target_object_family,
                    target_object_id=latest.target_object_id,
                    revision_id=latest.result_revision_id,
                    revision_number=latest.resulting_revision_number,
                    policy_class=latest.policy_class,
                    approval_state=latest.approval_state,
                    source_surface=latest.source_surface,
                    skill_name=latest.skill_name,
                    diff_excerpt=self._diff_excerpt(latest.diff_payload),
                )
            )
        audit_entries.sort(
            key=lambda entry: (entry.revision_number, entry.target_family, entry.target_object_id),
            reverse=True,
        )
        return tuple(audit_entries[:8])

    def _stage_summary(
        self,
        *,
        novel: WorkspaceObjectSummary | None,
        scenes: list[WorkspaceObjectSummary],
        chapter_artifacts: tuple[DerivedArtifactSnapshot, ...],
        export_artifacts: tuple[DerivedArtifactSnapshot, ...],
        review_queue: tuple[ReviewProposalSnapshot, ...],
        scenes_without_chapters: list[WorkspaceObjectSummary],
    ) -> tuple[str, str]:
        if novel is None:
            return (
                "项目接入",
                "规范项目数据已存在，但外壳仍需要一个活动小说才能派发生产工作。",
            )
        if not scenes:
            return (
                "结构引导",
                "小说已注册，但场景级真相尚未建立。",
            )
        if review_queue:
            return (
                "审核瓶颈",
                f"{len(review_queue)} 个提案使可见工作区处于审核优先状态。",
            )
        if scenes_without_chapters:
            return (
                "场景积压",
                f"{len(chapter_artifacts)} 个章节制品已存在，但 {len(scenes_without_chapters)} 个场景仍需下游散文工作。",
            )
        if chapter_artifacts and len(export_artifacts) < len(chapter_artifacts):
            return (
                "发布就绪",
                f"{len(chapter_artifacts)} 个章节制品可用，目前已投影 {len(export_artifacts)} 个导出制品。",
            )
        return (
            "外壳运转正常",
            "规范场景、章节制品和审核队列已足够对齐，总控台可以作为清晰的调度器运作。",
        )

    def _render_command_center_html(self, snapshot: CommandCenterSnapshot) -> str:
        stats_markup = "".join(
            f"<div class=\"metric-card\"><span>{html.escape(family.replace('_', ' '))}</span><strong>{count}</strong></div>"
            for family, count in sorted(snapshot.object_counts.items())
        )
        action_lookup = {route.route_id: route for route in snapshot.routes}
        action_markup = "".join(
            (
                "<li><strong>{title}</strong><p>{reason}</p><a href=\"{href}\">Open {route_label}</a></li>"
            ).format(
                title=html.escape(action.title),
                reason=html.escape(action.reason),
                href=html.escape(action_lookup.get(action.route_id, CommandCenterRoute("command-center", "command center", "/command-center", "", "")).href, quote=True),
                route_label=html.escape(action_lookup.get(action.route_id, CommandCenterRoute("command-center", "command center", "/command-center", "", "")).label),
            )
            for action in snapshot.next_actions
        ) or "<li><strong>无待执行动作</strong><p>外壳尚未发现更强的下一步动作。</p></li>"
        blocked_markup = self._render_signals(snapshot.blocked_signals, empty_copy="未检测到硬性阻塞。")
        stale_markup = self._render_signals(snapshot.stale_signals, empty_copy="从可见服务快照中未检测到陈旧区域。")
        audit_markup = "".join(
            (
                "<li>"
                "<div><strong>{family}</strong> <code>{object_id}</code> rev {revision_number}</div>"
                "<p>{excerpt}</p>"
                "<span>{policy} · {approval} · {surface}{skill}</span>"
                "</li>"
            ).format(
                family=html.escape(entry.target_family),
                object_id=html.escape(entry.target_object_id),
                revision_number=entry.revision_number,
                excerpt=html.escape(entry.diff_excerpt),
                policy=html.escape(entry.policy_class),
                approval=html.escape(entry.approval_state),
                surface=html.escape(entry.source_surface),
                skill=(f" · skill:{html.escape(entry.skill_name)}" if entry.skill_name else ""),
            )
            for entry in snapshot.audit_entries
        ) or "<li><strong>尚无审计条目。</strong><p>一旦规范对象被触及，变更历史将在此显示。</p></li>"

        content = (
            f"<section class=\"hero-panel\">"
            f"<div class=\"hero-copy\"><span class=\"eyebrow\">主 Web 外壳</span><h1>{html.escape(snapshot.project_title)}</h1>"
            f"<p class=\"hero-subtitle\">{html.escape(snapshot.novel_title)}</p>"
            f"<div class=\"hero-stage\"><strong>{html.escape(snapshot.stage_label)}</strong><p>{html.escape(snapshot.stage_detail)}</p></div></div>"
            f"<div class=\"hero-side\"><div class=\"queue-card\"><span>审核队列</span><strong>{snapshot.review_queue_count}</strong></div>"
            f"<div class=\"metric-grid\">{stats_markup}</div></div></section>"
            f"<section class=\"content-grid\"><article class=\"panel\"><div class=\"panel-heading\"><h2>推荐的下一步动作</h2><p>仅调度 — 每个推荐指向另一个界面。</p></div><ol class=\"action-list\">{action_markup}</ol></article>"
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>阻塞区域</h2><p>应立即改变优先级的硬性阻塞。</p></div><ul class=\"signal-list\">{blocked_markup}</ul></article>"
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>陈旧区域</h2><p>外壳可从规范和派生状态中看到的流水线缺口。</p></div><ul class=\"signal-list\">{stale_markup}</ul></article>"
            f"<article class=\"panel panel-wide\"><div class=\"panel-heading\"><h2>变更审计可见性</h2><p>直接来源于服务层变更历史，使外壳对策略类和审批状态保持透明。</p></div><ul class=\"audit-list\">{audit_markup}</ul></article></section>"
        )
        return self._render_layout(
            title="全书总控台",
            subtitle="Web 外壳诊断书籍状态，指出摩擦点，并将用户派发到正确的下游界面。",
            content=content,
            current_route_id="command-center",
            project_id=snapshot.project_id,
            novel_id=snapshot.novel_id,
        )

    def _render_placeholder_page(
        self,
        *,
        title: str,
        eyebrow: str,
        detail: str,
        project_id: str,
        novel_id: str | None,
    ) -> CommandCenterPage:
        query = self._route_query(project_id=project_id, novel_id=novel_id)
        body = self._render_layout(
            title=title,
            subtitle=detail,
            project_id=project_id,
            novel_id=novel_id,
            content=(
                f"<section class=\"hero-panel\"><div class=\"hero-copy\"><span class=\"eyebrow\">{html.escape(eyebrow)}</span>"
                f"<h1>{html.escape(title)}</h1><p class=\"hero-subtitle\">{html.escape(detail)}</p>"
                f"<div class=\"hero-stage\"><strong>占位符路由</strong><p>总控台已经可以派发到这里，而无需假装这个更深层界面已完成。</p></div>"
                f"<p><a class=\"back-link\" href=\"/command-center{html.escape(query, quote=True)}\">返回全书总控台</a></p></div></section>"
            ),
        )
        return CommandCenterPage(status_code=200, title=title, body=body)

    def submit_publish_form(
        self,
        *,
        project_id: str,
        novel_id: str,
        form: Mapping[str, str],
    ) -> CommandCenterPage:
        chapter_artifact_object_id = form.get("chapter_artifact_object_id") or None
        base_revision_id = form.get("base_artifact_revision_id") or None
        expected_source_scene_revision_id = form.get("expected_source_scene_revision_id") or None
        output_root = Path(form.get("output_root") or "").expanduser()
        try:
            if not str(output_root).strip():
                raise ValueError("publish output_root is required")
            result = self._service.publish_export(
                PublishExportRequest(
                    project_id=project_id,
                    novel_id=novel_id,
                    actor="web-shell",
                    output_root=output_root,
                    chapter_artifact_object_id=chapter_artifact_object_id,
                    base_chapter_artifact_revision_id=base_revision_id,
                    expected_source_scene_revision_id=expected_source_scene_revision_id,
                    source_surface="publish_surface",
                    source_ref="web-shell:/publish",
                )
            )
            if result.publish_result is not None and result.disposition in {"published", "already_published"}:
                return self._render_publish_page(
                    project_id=project_id,
                    novel_id=novel_id,
                    flash_message=(
                        f"发布 {result.disposition.replace('_', ' ')}：{result.publish_result.object_id} 位于 {result.publish_result.bundle_path}。"
                    ),
                )
            if result.disposition == "stale":
                return self._render_publish_page(
                    project_id=project_id,
                    novel_id=novel_id,
                    flash_error=(
                        "发布被陈旧谱系阻塞："
                        + json.dumps(result.stale_details or {}, ensure_ascii=False, sort_keys=True)
                    ),
                )
            return self._render_publish_page(
                project_id=project_id,
                novel_id=novel_id,
                flash_error=" ".join(result.recovery_actions) or "发布无法完成。",
            )
        except (KeyError, ValueError) as error:
            return self._render_publish_page(
                project_id=project_id,
                novel_id=novel_id,
                flash_error=str(error),
            )

    def submit_workbench_form(
        self,
        *,
        project_id: str,
        novel_id: str,
        form: Mapping[str, str],
    ) -> CommandCenterPage:
        link_type = (form.get("link_type") or "").strip()
        parent_object_id = (form.get("parent_object_id") or "").strip()
        expected_parent_revision_id = form.get("expected_parent_revision_id") or None
        try:
            if link_type == "import_outline":
                result = self._service.import_outline(
                    ImportOutlineRequest(
                        novel_id=novel_id,
                        title=form.get("outline_title") or "",
                        body=form.get("outline_body") or "",
                        actor="web-shell",
                        source_surface="workbench_outline_import",
                        source_ref="web-shell:/workbench",
                    )
                )
                flash = f"已导入大纲：{result.object_id}。"
            elif link_type == "outline_to_plot":
                result = self._service.generate_outline_to_plot_workbench(
                    OutlineToPlotWorkbenchRequest(
                        project_id=project_id,
                        novel_id=novel_id,
                        outline_node_object_id=parent_object_id,
                        actor="web-shell",
                        expected_parent_revision_id=expected_parent_revision_id,
                    )
                )
                flash = f"大纲→剧情 {result.disposition}：child {result.child_object_id or 'pending review'}。"
            elif link_type == "plot_to_event":
                result = self._service.generate_plot_to_event_workbench(
                    PlotToEventWorkbenchRequest(
                        project_id=project_id,
                        novel_id=novel_id,
                        plot_node_object_id=parent_object_id,
                        actor="web-shell",
                        expected_parent_revision_id=expected_parent_revision_id,
                    )
                )
                flash = f"剧情→事件 {result.disposition}：child {result.child_object_id or 'pending review'}。"
            elif link_type == "event_to_scene":
                result = self._service.generate_event_to_scene_workbench(
                    EventToSceneWorkbenchRequest(
                        project_id=project_id,
                        novel_id=novel_id,
                        event_object_id=parent_object_id,
                        actor="web-shell",
                        expected_parent_revision_id=expected_parent_revision_id,
                    )
                )
                flash = f"事件→场景 {result.disposition}：child {result.child_object_id or 'pending review'}。"
            else:
                raise ValueError(f"unsupported workbench link_type: {link_type}")
        except (KeyError, ValueError) as error:
            return self._render_workbench_page(
                project_id=project_id,
                novel_id=novel_id,
                flash_error=str(error),
            )
        return self._render_workbench_page(
            project_id=project_id,
            novel_id=novel_id,
            flash_message=flash,
        )

    def submit_skill_workshop_form(
        self,
        *,
        project_id: str,
        novel_id: str,
        form: Mapping[str, str],
    ) -> CommandCenterPage:
        action = form.get("action", "").strip().lower()
        try:
            if action == "create":
                created = self._service.upsert_skill_workshop_skill(
                    SkillWorkshopUpsertRequest(
                        novel_id=novel_id,
                        actor="web-shell",
                        source_surface="skill_workshop_form",
                        name=form.get("name"),
                        description=form.get("description"),
                        instruction=form.get("instruction"),
                        style_scope=form.get("style_scope") or "scene_to_chapter",
                        is_active=self._form_bool(form, "is_active", default=True),
                        revision_reason="从工坊表单创建受约束技能",
                    )
                )
                return self._render_skill_workshop_page(
                    project_id=project_id,
                    novel_id=novel_id,
                    selected_skill_id=created.object_id,
                    flash_message=f"Created constrained skill / 已创建受约束技能 {created.object_id}。",
                )
            if action == "update":
                updated = self._service.upsert_skill_workshop_skill(
                    SkillWorkshopUpsertRequest(
                        novel_id=novel_id,
                        actor="web-shell",
                        source_surface="skill_workshop_form",
                        skill_object_id=form.get("skill_object_id") or None,
                        name=form.get("name"),
                        description=form.get("description"),
                        instruction=form.get("instruction"),
                        style_scope=form.get("style_scope") or None,
                        is_active=self._form_bool(form, "is_active", default=False),
                        base_revision_id=form.get("base_revision_id") or None,
                        revision_reason="从工坊表单更新受约束技能",
                    )
                )
                return self._render_skill_workshop_page(
                    project_id=project_id,
                    novel_id=novel_id,
                    selected_skill_id=updated.object_id,
                    flash_message=f"Updated constrained skill / 已更新受约束技能 {updated.object_id} 至版本 {updated.revision_number}。",
                )
            if action == "toggle":
                active = self._form_bool(form, "is_active", default=False)
                updated = self._service.upsert_skill_workshop_skill(
                    SkillWorkshopUpsertRequest(
                        novel_id=novel_id,
                        actor="web-shell",
                        source_surface="skill_workshop_form",
                        skill_object_id=form.get("skill_object_id") or None,
                        is_active=active,
                        base_revision_id=form.get("base_revision_id") or None,
                        revision_reason=("从工坊表单激活" if active else "从工坊表单停用") + "受约束技能",
                    )
                )
                state_text = "已激活" if active else "已停用"
                return self._render_skill_workshop_page(
                    project_id=project_id,
                    novel_id=novel_id,
                    selected_skill_id=updated.object_id,
                    flash_message=f"技能 {updated.object_id} {state_text}。",
                )
            if action == "rollback":
                rolled_back = self._service.rollback_skill_workshop_skill(
                    SkillWorkshopRollbackRequest(
                        skill_object_id=form.get("skill_object_id", ""),
                        target_revision_id=form.get("target_revision_id", ""),
                        actor="web-shell",
                        source_surface="skill_workshop_form",
                        revision_reason="从工坊表单回滚受约束技能",
                    )
                )
                return self._render_skill_workshop_page(
                    project_id=project_id,
                    novel_id=novel_id,
                    selected_skill_id=rolled_back.object_id,
                    flash_message=f"Rolled back skill / 已将技能 {rolled_back.object_id} 从 {form.get('target_revision_id', '')} 回滚至新版本。",
                )
            if action == "import":
                imported = self._service.import_skill_workshop_skill(
                    SkillWorkshopImportRequest(
                        donor_kind=form.get("donor_kind", "prompt_template"),
                        novel_id=novel_id,
                        actor="web-shell",
                        source_surface="skill_workshop_form",
                        donor_payload={
                            "name": form.get("name", ""),
                            "title": form.get("name", ""),
                            "description": form.get("description", ""),
                            "instruction": form.get("instruction", ""),
                            "prompt": form.get("instruction", ""),
                            "role": form.get("name", ""),
                        },
                        style_scope=form.get("style_scope") or "scene_to_chapter",
                        is_active=self._form_bool(form, "is_active", default=True),
                        source_ref="web-shell:/skills",
                    )
                )
                return self._render_skill_workshop_page(
                    project_id=project_id,
                    novel_id=novel_id,
                    selected_skill_id=imported.object_id,
                    flash_message=f"已将 {form.get('donor_kind', 'prompt_template')} 导入受约束技能 {imported.object_id}。",
                )
            raise ValueError("unsupported skill workshop action")
        except (KeyError, ValueError) as error:
            return self._render_skill_workshop_page(
                project_id=project_id,
                novel_id=novel_id,
                selected_skill_id=form.get("skill_object_id") or None,
                flash_error=str(error),
            )

    def _render_skill_workshop_page(
        self,
        *,
        project_id: str,
        novel_id: str,
        selected_skill_id: str | None = None,
        left_revision_id: str | None = None,
        right_revision_id: str | None = None,
        flash_message: str | None = None,
        flash_error: str | None = None,
    ) -> CommandCenterPage:
        workshop = self._service.get_skill_workshop(
            SkillWorkshopRequest(
                project_id=project_id,
                novel_id=novel_id,
                selected_skill_id=selected_skill_id,
                left_revision_id=left_revision_id,
                right_revision_id=right_revision_id,
            )
        )
        selected = workshop.selected_skill
        versions = workshop.versions
        compare = workshop.comparison
        query = self._route_query(project_id=project_id, novel_id=novel_id)
        flash_markup = ""
        if flash_message:
            flash_markup = f'<p class="status-banner status-banner-success">{html.escape(flash_message)}</p>'
        elif flash_error:
            flash_markup = f'<p class="status-banner status-banner-danger">{html.escape(flash_error)}</p>'
        skill_cards = "".join(
            self._render_skill_summary_card(project_id=project_id, novel_id=novel_id, skill=skill)
            for skill in workshop.skills
        ) or "<li><strong>No constrained skills yet.</strong><p>Create one from the workshop form or import a donor prompt template, custom agent, or AI role through the adapter.</p></li>"
        version_cards = "".join(
            self._render_skill_version_card(project_id=project_id, novel_id=novel_id, selected_skill_id=selected.object_id if selected is not None else None, version=version)
            for version in versions
        ) or "<li><strong>No versions yet.</strong><p>The selected constrained skill has not produced revision history yet.</p></li>"
        compare_markup = (
            self._render_skill_comparison(compare)
            if compare is not None
            else "<p>Select a skill with at least two revisions to compare versions.</p>"
        )
        selected_markup = self._render_skill_editor(project_id=project_id, novel_id=novel_id, skill=selected)
        import_markup = self._render_skill_import_form(project_id=project_id, novel_id=novel_id)
        body = self._render_layout(
            title="技能工坊",
            subtitle="受约束的技能工坊仅通过共享服务编辑统一的风格规则技能模型；生成参数、检索范围和工具权限在服务端保持禁止。",
            current_route_id="skills",
            project_id=project_id,
            novel_id=novel_id,
            content=(
                f"<section class=\"hero-panel\"><div class=\"hero-copy\"><span class=\"eyebrow\">受约束工坊</span>"
                f"<h1>技能工坊</h1><p class=\"hero-subtitle\">创建、修订、比较、版本化、范围设置、激活、停用、导入和回滚风格规则技能，无需引入并行运行时抽象。</p>"
                f"<div class=\"hero-stage\"><strong>{len(workshop.skills)} 个受约束技能</strong><p>允许的风格范围：{html.escape(', '.join(ALLOWED_STYLE_SCOPES))}。禁止字段由共享服务门面显式拒绝。</p></div>"
                f"{flash_markup}<p><a class=\"back-link\" href=\"/command-center{html.escape(query, quote=True)}\">返回全书总控台</a></p></div>"
                f"<div class=\"hero-side\"><div class=\"queue-card\"><span>已选技能</span><strong>{html.escape(selected.name if selected is not None else '—')}</strong></div><div class=\"metric-grid\"><div class=\"metric-card\"><span>版本数</span><strong>{len(versions)}</strong></div><div class=\"metric-card\"><span>活跃技能</span><strong>{sum(1 for skill in workshop.skills if skill.is_active)}</strong></div></div></div></section>"
                f"<section class=\"content-grid\"><article class=\"panel\"><div class=\"panel-heading\"><h2>统一技能列表</h2><p>提示模板、自定义代理和 AI 角色通过导入映射规范化为这一规范技能形态。</p></div><ul class=\"audit-list\">{skill_cards}</ul></article>"
                f"<article class=\"panel\"><div class=\"panel-heading\"><h2>创建或编辑</h2><p>对话捕获和表单控件仅暴露受约束的风格规则字段。</p></div>{selected_markup}</article>"
                f"<article class=\"panel\"><div class=\"panel-heading\"><h2>导入捐赠者概念 · Import donor concepts</h2><p>适配器将捐赠者概念映射到统一技能抽象，而非保留捐赠者运行时类型。</p></div>{import_markup}</article>"
                f"<article class=\"panel\"><div class=\"panel-heading\"><h2>版本历史</h2><p>每个技能修订都是规范修订链条目，因此回滚创建新头部而非改变历史。</p></div><ul class=\"audit-list\">{version_cards}</ul></article>"
                f"<article class=\"panel panel-wide\"><div class=\"panel-heading\"><h2>比较修订 · Compare revisions</h2><p>结构化差异和渲染的 JSON 差异帮助工坊明确了解变更内容。</p></div>{compare_markup}</article></section>"
            ),
        )
        return CommandCenterPage(status_code=200, title="技能工坊", body=body)

    def _render_publish_page(
        self,
        *,
        project_id: str,
        novel_id: str,
        flash_message: str | None = None,
        flash_error: str | None = None,
    ) -> CommandCenterPage:
        chapter_artifacts = self._filter_artifacts(
            self._service.list_derived_artifacts("chapter_artifact"),
            novel_id=novel_id,
        )
        export_artifacts = self._filter_artifacts(
            self._service.list_derived_artifacts("export_artifact"),
            novel_id=novel_id,
        )
        flash_markup = ""
        if flash_message:
            flash_markup = f'<p class="status-banner status-banner-success">{html.escape(flash_message)}</p>'
        elif flash_error:
            flash_markup = f'<p class="status-banner status-banner-danger">{html.escape(flash_error)}</p>'
        artifact_cards = "".join(self._render_artifact_card(artifact) for artifact in chapter_artifacts) or (
            "<li><strong>尚无章节制品。</strong><p>发布仍然是章节生成和审批的下游，因此尚无内容可投影。</p></li>"
        )
        export_cards = "".join(self._render_export_artifact_card(artifact) for artifact in export_artifacts) or (
            "<li><strong>尚无导出制品。</strong><p>发布仅在共享服务组装完谱系锁定投影后才写入显式包。</p></li>"
        )
        form_markup = "".join(
            self._render_publish_form(project_id=project_id, novel_id=novel_id, artifact=artifact)
            for artifact in chapter_artifacts
        ) or "<p>范围内无可发布的章节制品。</p>"
        body = self._render_layout(
            title="发布导出",
            subtitle="发布保持仅投影：它创建派生导出制品，然后仅具象化该制品载荷中声明的显式文件系统包。",
            current_route_id="publish",
            project_id=project_id,
            novel_id=novel_id,
            content=(
                f"<section class=\"hero-panel\"><div class=\"hero-copy\"><span class=\"eyebrow\">投影发布</span>"
                f"<h1>发布导出</h1><p class=\"hero-subtitle\">章节制品保持为派生输入，导出制品保持为派生快照，文件系统包保持为下游投影而非成为新的真相来源。</p>"
                f"<div class=\"hero-stage\"><strong>{len(chapter_artifacts)} 个章节制品</strong><p>已为该小说记录 {len(export_artifacts)} 个导出制品。</p></div>{flash_markup}"
                f"<p><a class=\"back-link\" href=\"/command-center{html.escape(self._route_query(project_id=project_id, novel_id=novel_id), quote=True)}\">返回全书总控台</a></p></div></section>"
                f"<section class=\"content-grid\"><article class=\"panel\"><div class=\"panel-heading\"><h2>可发布的章节谱系</h2><p>每个表单固定当前章节制品版本和源场景版本，使陈旧输入在写入任何文件系统包之前失败。</p></div>{form_markup}</article>"
                f"<article class=\"panel\"><div class=\"panel-heading\"><h2>范围内章节制品</h2><p>发布界面读取工作台已显示的相同派生章节谱系。</p></div><ul class=\"audit-list\">{artifact_cards}</ul></article>"
                f"<article class=\"panel panel-wide\"><div class=\"panel-heading\"><h2>导出制品历史</h2><p>每个导出记录仍是派生且可重建的；它投影的包是交付输出，而非规范真相。</p></div><ul class=\"audit-list\">{export_cards}</ul></article></section>"
            ),
        )
        return CommandCenterPage(status_code=200, title="发布导出", body=body)

    def _render_skill_summary_card(
        self,
        *,
        project_id: str,
        novel_id: str,
        skill: SkillWorkshopSkillSnapshot,
    ) -> str:
        donor_note = f" · donor:{html.escape(skill.donor_kind)}" if skill.donor_kind else ""
        return (
            "<li><div><strong>{name}</strong> <code>{object_id}</code></div>"
            "<p>{instruction}</p>"
            "<span>{scope} · {state} · 版本 {revision}{donor}</span>"
            "<p><a class=\"back-link\" href=\"/skills?project_id={project_id}&novel_id={novel_id}&selected_skill_id={object_id}\">在工坊中打开</a></p></li>"
        ).format(
            name=html.escape(skill.name),
            object_id=html.escape(skill.object_id),
            instruction=html.escape(self._diff_excerpt(skill.payload)),
            scope=html.escape(skill.style_scope),
            state=("活跃" if skill.is_active else "停用"),
            revision=skill.revision_number,
            donor=donor_note,
            project_id=html.escape(project_id, quote=True),
            novel_id=html.escape(novel_id, quote=True),
        )

    def _render_skill_editor(self, *, project_id: str, novel_id: str, skill: SkillWorkshopSkillSnapshot | None) -> str:
        scope_options = "".join(
            f'<option value="{html.escape(scope, quote=True)}"{" selected" if skill is not None and skill.style_scope == scope else ""}>{html.escape(scope)}</option>'
            for scope in ALLOWED_STYLE_SCOPES
        )
        selected_object_id = html.escape(skill.object_id, quote=True) if skill is not None else ""
        selected_revision_id = html.escape(skill.revision_id, quote=True) if skill is not None else ""
        return (
            "<form method=\"post\" action=\"/skills?project_id={project_id}&novel_id={novel_id}\" class=\"skill-form\">"
            "<input type=\"hidden\" name=\"action\" value=\"{action}\" />"
            "<input type=\"hidden\" name=\"skill_object_id\" value=\"{object_id}\" />"
            "<input type=\"hidden\" name=\"base_revision_id\" value=\"{revision_id}\" />"
            "<label>名称<input type=\"text\" name=\"name\" value=\"{name}\" required /></label>"
            "<label>描述<textarea name=\"description\">{description}</textarea></label>"
            "<label>对话/指令<textarea name=\"instruction\" required>{instruction}</textarea></label>"
            "<label>风格范围<select name=\"style_scope\">{scope_options}</select></label>"
            "<label class=\"checkbox-row\"><input type=\"checkbox\" name=\"is_active\" value=\"true\"{checked} /> 活跃</label>"
            "<div class=\"button-row\"><button type=\"submit\">{submit_label}</button></div>"
            "</form>"
            "<form method=\"post\" action=\"/skills?project_id={project_id}&novel_id={novel_id}\" class=\"inline-form\">"
            "<input type=\"hidden\" name=\"action\" value=\"toggle\" />"
            "<input type=\"hidden\" name=\"skill_object_id\" value=\"{object_id}\" />"
            "<input type=\"hidden\" name=\"base_revision_id\" value=\"{revision_id}\" />"
            "<input type=\"hidden\" name=\"is_active\" value=\"{toggle_value}\" />"
            "<button type=\"submit\" {toggle_disabled}>{toggle_label}</button>"
            "</form>"
            "<p class=\"form-note\">禁止编辑字段在服务端被拒绝：生成参数、检索范围、工具权限。Forbidden fields are rejected explicitly: generation parameters, retrieval scope, tool permissions.</p>"
        ).format(
            project_id=html.escape(project_id, quote=True),
            novel_id=html.escape(novel_id, quote=True),
            action=("update" if skill is not None else "create"),
            object_id=selected_object_id,
            revision_id=selected_revision_id,
            name=html.escape(skill.name if skill is not None else ""),
            description=html.escape(skill.description if skill is not None else ""),
            instruction=html.escape(skill.instruction if skill is not None else ""),
            scope_options=scope_options,
            checked=(" checked" if skill is None or skill.is_active else ""),
            submit_label=("保存修订" if skill is not None else "创建技能"),
            toggle_value=("false" if skill is not None and skill.is_active else "true"),
            toggle_label=("停用" if skill is not None and skill.is_active else "激活"),
            toggle_disabled=("" if skill is not None else "disabled"),
        )

    def _render_skill_import_form(self, *, project_id: str, novel_id: str) -> str:
        scope_options = "".join(
            f'<option value="{html.escape(scope, quote=True)}">{html.escape(scope)}</option>' for scope in ALLOWED_STYLE_SCOPES
        )
        return (
            "<form method=\"post\" action=\"/skills?project_id={project_id}&novel_id={novel_id}\" class=\"skill-form\">"
            "<input type=\"hidden\" name=\"action\" value=\"import\" />"
            "<label>捐赠者概念<select name=\"donor_kind\"><option value=\"prompt_template\">提示模板</option><option value=\"custom_agent\">自定义代理</option><option value=\"ai_role\">AI 角色</option></select></label>"
            "<label>名称<input type=\"text\" name=\"name\" required /></label>"
            "<label>描述<textarea name=\"description\"></textarea></label>"
            "<label>捐赠者指令/提示<textarea name=\"instruction\" required></textarea></label>"
            "<label>风格范围<select name=\"style_scope\">{scope_options}</select></label>"
            "<label class=\"checkbox-row\"><input type=\"checkbox\" name=\"is_active\" value=\"true\" checked /> 活跃</label>"
            "<div class=\"button-row\"><button type=\"submit\">导入为统一技能</button></div>"
            "</form>"
        ).format(
            project_id=html.escape(project_id, quote=True),
            novel_id=html.escape(novel_id, quote=True),
            scope_options=scope_options,
        )

    def _render_skill_version_card(self, *, project_id: str, novel_id: str, selected_skill_id: str | None, version: SkillWorkshopVersionSnapshot) -> str:
        rollback_form = ""
        if selected_skill_id is not None:
            rollback_form = (
                "<form method=\"post\" action=\"/skills?project_id={project_id}&novel_id={novel_id}\" class=\"inline-form\">"
                "<input type=\"hidden\" name=\"action\" value=\"rollback\" />"
                "<input type=\"hidden\" name=\"skill_object_id\" value=\"{skill_object_id}\" />"
                "<input type=\"hidden\" name=\"target_revision_id\" value=\"{revision_id}\" />"
                "<button type=\"submit\">回滚到此修订</button>"
                "</form>"
            ).format(
                project_id=html.escape(project_id, quote=True),
                novel_id=html.escape(novel_id, quote=True),
                skill_object_id=html.escape(selected_skill_id, quote=True),
                revision_id=html.escape(version.revision_id, quote=True),
            )
        compare_link = ""
        if selected_skill_id is not None:
            compare_link = (
                f'<p><a class="back-link" href="/skills?project_id={html.escape(project_id, quote=True)}&novel_id={html.escape(novel_id, quote=True)}&selected_skill_id={html.escape(selected_skill_id, quote=True)}&left_revision_id={html.escape(version.revision_id, quote=True)}&right_revision_id={html.escape(version.revision_id, quote=True)}">检查修订</a></p>'
            )
        return (
            "<li><div><strong>修订 {revision_number}</strong> <code>{revision_id}</code></div>"
            "<p>{instruction}</p>"
            "<span>{scope} · {state}</span>{rollback}{compare}</li>"
        ).format(
            revision_number=version.revision_number,
            revision_id=html.escape(version.revision_id),
            instruction=html.escape(self._diff_excerpt(version.payload)),
            scope=html.escape(version.style_scope),
            state=("活跃" if version.is_active else "停用"),
            rollback=rollback_form,
            compare=compare_link,
        )

    def _render_skill_comparison(self, comparison: SkillWorkshopComparison) -> str:
        structured_markup = self._render_json_pairs(comparison.structured_diff)
        rendered = html.escape(comparison.rendered_diff or "无渲染差异。")
        return (
            "<div class=\"review-grid\">"
            "<section class=\"review-section\"><h3>修订范围</h3><p><code>{left}</code> (版本 {left_number}) → <code>{right}</code> (版本 {right_number})</p></section>"
            "<section class=\"review-section\"><h3>结构化差异</h3>{structured}</section>"
            "<section class=\"review-section panel-wide\"><h3>Rendered diff</h3><pre>{rendered}</pre></section>"
            "</div>"
        ).format(
            left=html.escape(comparison.left_revision_id),
            left_number=comparison.left_revision_number,
            right=html.escape(comparison.right_revision_id),
            right_number=comparison.right_revision_number,
            structured=structured_markup,
            rendered=rendered,
        )

    def _form_bool(self, form: Mapping[str, str], key: str, *, default: bool) -> bool:
        value = form.get(key)
        if value is None:
            return default
        return value.strip().lower() in {"true", "1", "yes", "on", "active"}

    def _render_outline_import_form(self, *, project_id: str, novel_id: str | None) -> str:
        return (
            "<form method=\"post\" action=\"/workbench?project_id={project_id}&novel_id={novel_id}\" class=\"skill-form\">"
            "<input type=\"hidden\" name=\"link_type\" value=\"import_outline\" />"
            "<label>大纲标题<input type=\"text\" name=\"outline_title\" placeholder=\"例如：第一卷主线\" required /></label>"
            "<label>大纲内容<textarea name=\"outline_body\" placeholder=\"把你的大纲正文粘贴到这里，支持分段文本。\" required></textarea></label>"
            "<div class=\"button-row\"><button type=\"submit\">导入大纲</button></div>"
            "<p class=\"form-note\">当前为最小可用导入：每次提交创建一个规范 <code>outline_node</code>，随后即可继续推进到剧情节点。</p>"
            "</form>"
        ).format(
            project_id=html.escape(project_id, quote=True),
            novel_id=html.escape(novel_id or "", quote=True),
        )

    def _render_workbench_page(
        self,
        *,
        project_id: str,
        novel_id: str | None,
        flash_message: str | None = None,
        flash_error: str | None = None,
    ) -> CommandCenterPage:
        workspace = self._service.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        outlines = [summary for summary in workspace.canonical_objects if summary.family == "outline_node"]
        plots = [summary for summary in workspace.canonical_objects if summary.family == "plot_node"]
        events = [summary for summary in workspace.canonical_objects if summary.family == "event"]
        scene_summaries = [summary for summary in workspace.canonical_objects if summary.family == "scene"]
        chapter_artifacts = self._filter_artifacts(
            self._service.list_derived_artifacts("chapter_artifact"),
            novel_id=novel_id,
        )
        chapter_proposals = tuple(
            proposal
            for proposal in self._service.list_review_proposals(ListReviewProposalsRequest()).proposals
            if proposal.target_family == "chapter_artifact"
        )
        style_rules = [summary for summary in workspace.canonical_objects if summary.family == "style_rule"]

        # --- Upstream link: outline_node -> plot_node ---
        plot_parent_ids = {self._payload_text(p.payload, "outline_node_id") or self._payload_text(p.payload, "parent_id") for p in plots}
        outlines_without_plots = [o for o in outlines if o.object_id not in plot_parent_ids]
        outline_to_plot_readiness = (
            f"{len(outlines_without_plots)} 个大纲节点等待剧情扩展"
            if outlines_without_plots
            else ("全部大纲已推进到剧情节点" if outlines else "尚无大纲节点")
        )
        outline_cards = "".join(
            self._render_upstream_parent_card(
                parent=outline,
                link_type="outline_to_plot",
                link_label="大纲 → 剧情",
                child_family="plot_node",
                children=plots,
                parent_id_key="outline_node_id",
                project_id=project_id,
                novel_id=novel_id,
            )
            for outline in outlines
        ) or "<li><strong>尚无大纲节点。</strong><p>大纲 → 剧情工作台在规范大纲节点存在后出现。</p></li>"

        # --- Upstream link: plot_node -> event ---
        event_parent_ids = {self._payload_text(e.payload, "plot_node_id") or self._payload_text(e.payload, "parent_id") for e in events}
        plots_without_events = [p for p in plots if p.object_id not in event_parent_ids]
        plot_to_event_readiness = (
            f"{len(plots_without_events)} 个剧情节点等待事件拆解"
            if plots_without_events
            else ("全部剧情已拆解为事件" if plots else "尚无剧情节点")
        )
        plot_cards = "".join(
            self._render_upstream_parent_card(
                parent=plot,
                link_type="plot_to_event",
                link_label="剧情 → 事件",
                child_family="event",
                children=events,
                parent_id_key="plot_node_id",
                project_id=project_id,
                novel_id=novel_id,
            )
            for plot in plots
        ) or "<li><strong>尚无剧情节点。</strong><p>剧情 → 事件工作台在规范剧情节点存在后出现。</p></li>"

        # --- Upstream link: event -> scene ---
        scene_parent_ids = {self._payload_text(s.payload, "event_id") or self._payload_text(s.payload, "parent_id") for s in scene_summaries}
        events_without_scenes = [e for e in events if e.object_id not in scene_parent_ids]
        event_to_scene_readiness = (
            f"{len(events_without_scenes)} 个事件等待场景生成"
            if events_without_scenes
            else ("全部事件已生成场景" if events else "尚无事件")
        )
        event_cards = "".join(
            self._render_upstream_parent_card(
                parent=event,
                link_type="event_to_scene",
                link_label="事件 → 场景",
                child_family="scene",
                children=scene_summaries,
                parent_id_key="event_id",
                project_id=project_id,
                novel_id=novel_id,
            )
            for event in events
        ) or "<li><strong>尚无事件。</strong><p>事件 → 场景工作台在规范事件存在后出现。</p></li>"

        # --- Existing: scene -> chapter ---
        queued_markup = "".join(
            self._render_workbench_scene_card(
                scene=scene,
                project_id=project_id,
                novel_id=novel_id,
                style_rules=style_rules,
                skills=[summary for summary in workspace.canonical_objects if summary.family == "skill"],
                facts=[summary for summary in workspace.canonical_objects if summary.family == "fact_state_record"],
                chapter_artifacts=chapter_artifacts,
            )
            for scene in scene_summaries
        ) or "<li><strong>No approved scenes are ready.</strong><p>The workbench appears once canonical scene truth exists.</p></li>"
        artifact_markup = "".join(self._render_artifact_card(artifact) for artifact in chapter_artifacts) or (
            "<li><strong>尚无章节制品。</strong><p>从已批准场景生成以在此固定来源谱系。</p></li>"
        )
        proposal_markup = "".join(self._render_chapter_proposal_card(proposal, project_id=project_id, novel_id=novel_id) for proposal in chapter_proposals) or (
            "<li><strong>无章节提案等待。</strong><p>不安全的章节变更将路由到审核台而非绕过策略。</p></li>"
        )

        query = self._route_query(project_id=project_id, novel_id=novel_id)
        flash_markup = ""
        if flash_message:
            flash_markup = f'<p class="status-banner status-banner-success">{html.escape(flash_message)}</p>'
        elif flash_error:
            flash_markup = f'<p class="status-banner status-banner-danger">{html.escape(flash_error)}</p>'
        content = (
            f"<section class=\"hero-panel\"><div class=\"hero-copy\"><span class=\"eyebrow\">全流水线工作台</span>"
            f"<h1>流水线工作台</h1><p class=\"hero-subtitle\">四条上下游链路在同一工作台中展示：大纲→剧情、剧情→事件、事件→场景、场景→章节。每条链路独立显示就绪状态和排队项。</p>"
            f"<div class=\"hero-stage\"><strong>{len(outlines)} 大纲 · {len(plots)} 剧情 · {len(events)} 事件 · {len(scene_summaries)} 场景</strong>"
            f"<p>{len(chapter_artifacts)} 个章节制品 · {len(chapter_proposals)} 个章节提案等待中</p></div>"
            f"{flash_markup}"
            f"<p><a class=\"back-link\" href=\"/command-center{html.escape(query, quote=True)}\">返回全书总控台</a></p></div></section>"
            # --- Outline -> Plot section ---
            f"<section class=\"content-grid\">"
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>导入大纲</h2><p>最小本地导入入口：创建一个规范 outline_node，随后继续推进上游链路。</p></div>{self._render_outline_import_form(project_id=project_id, novel_id=novel_id)}</article>"
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>大纲 → 剧情节点</h2>"
            f"<p>{html.escape(outline_to_plot_readiness)}</p></div>"
            f"<ul class=\"signal-list\">{outline_cards}</ul></article>"
            # --- Plot -> Event section ---
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>剧情节点 → 事件</h2>"
            f"<p>{html.escape(plot_to_event_readiness)}</p></div>"
            f"<ul class=\"signal-list\">{plot_cards}</ul></article>"
            # --- Event -> Scene section ---
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>事件 → 场景</h2>"
            f"<p>{html.escape(event_to_scene_readiness)}</p></div>"
            f"<ul class=\"signal-list\">{event_cards}</ul></article>"
            # --- Scene -> Chapter section (existing) ---
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>场景 → 章节 · Scene → Chapter Workbench</h2>"
            f"<p>已批准场景以其固定的场景版本和可见的差异送入章节制品。</p></div>"
            f"<ul class=\"signal-list\">{queued_markup}</ul></article>"
            f"<article class=\"panel\"><div class=\"panel-heading\"><h2>已生成的章节谱系</h2><p>派生章节行保持可重建，同时暴露存储的谱系和差异元数据。</p></div><ul class=\"audit-list\">{artifact_markup}</ul></article>"
            f"<article class=\"panel panel-wide\"><div class=\"panel-heading\"><h2>需要审核的输出</h2><p>当章节变更不能安全地仅进行散文处理时，工作台将其路由到审核台进行静默应用。</p></div><ul class=\"audit-list\">{proposal_markup}</ul></article></section>"
        )
        return CommandCenterPage(
            status_code=200,
            title="流水线工作台",
            body=self._render_layout(
                title="流水线工作台",
                subtitle="全流水线工作台统一展示四条上下游链路的就绪状态，使用已批准的规范对象和服务层上下文。",
                content=content,
                current_route_id="workbench",
                project_id=project_id,
                novel_id=novel_id,
            ),
        )

    def _render_review_desk_page(self, *, project_id: str, novel_id: str | None) -> CommandCenterPage:
        desk = self._service.get_review_desk(ReviewDeskRequest(project_id=project_id, novel_id=novel_id))
        active_count = sum(1 for proposal in desk.proposals if proposal.approval_state not in {"approved", "rejected"})
        resolved_count = len(desk.proposals) - active_count
        review_query = html.escape(self._route_query(project_id=project_id, novel_id=novel_id), quote=True)
        proposal_markup = "".join(
            self._render_review_desk_proposal_card(proposal)
            for proposal in desk.proposals
        ) or "<li><strong>审核队列已清空。</strong><p>目前没有需要审核的提案等待批准、拒绝或修订。</p></li>"
        body = self._render_layout(
            title="审核台",
            subtitle="审核台读取一个服务层拥有的审核账本，暴露谱系、差异、精确一次审批和漂移安全的陈旧处理。",
            current_route_id="review-desk",
            project_id=project_id,
            novel_id=novel_id,
            content=(
                f"<section class=\"hero-panel\"><div class=\"hero-copy\"><span class=\"eyebrow\">审批界面</span>"
                f"<h1>审核台</h1><p class=\"hero-subtitle\">任务 8 工作台提案与此处降落，连同任何其他需要审核的变更，基础修订和修订漂移在任何人应用之前都会暴露。</p>"
                f"<div class=\"hero-stage\"><strong>{len(desk.proposals)} 个提案</strong><p>{active_count} 个活跃 · {resolved_count} 个已解决 · 宯批可以安全重放而不会重复变更。</p></div>"
                f"<p><a class=\"back-link\" href=\"/review-desk{review_query}\">Open Review Desk</a></p>"
                f"<p><a class=\"back-link\" href=\"/command-center{html.escape(self._route_query(project_id=project_id, novel_id=novel_id), quote=True)}\">返回全书总控台</a></p></div></section>"
                f"<section class=\"content-grid\"><article class=\"panel panel-wide\"><div class=\"panel-heading\"><h2>提案队列</h2><p>每个卡片显示来源谱系、结构化和渲染差异、当前审批状态，以及服务层捕获的任何修订漂移详情。</p></div><ul class=\"audit-list review-desk-list\">{proposal_markup}</ul></article></section>"
            ),
        )
        return CommandCenterPage(status_code=200, title="审核台", body=body)

    def _render_review_desk_proposal_card(self, proposal: ReviewDeskProposalSnapshot) -> str:
        revise_count = sum(1 for decision in proposal.decisions if decision.approval_state == "revision_requested")
        reason_markup = "".join(f"<li>{html.escape(reason)}</li>" for reason in proposal.reasons) or "<li>未捕获明确的审核原因。</li>"
        decision_markup = "".join(self._render_review_decision(decision) for decision in proposal.decisions) or (
            "<li><strong>待处理</strong><p>尚未记录批准、拒绝或修订循环。</p></li>"
        )
        loop_markup = (
            f"<p class=\"review-loop-note\">已请求修订 {revise_count} 次； 此提案在批准、替换或拒绝之前保持可见。</p>"
            if revise_count
            else ""
        )
        drift_markup = self._render_json_pairs(proposal.drift_details) if proposal.drift_details else "<p>未检测到修订漂移。</p>"
        lineage_markup = self._render_json_pairs(proposal.revision_lineage)
        structured_diff_markup = self._render_json_pairs(proposal.structured_diff)
        prose_diff_markup = html.escape(proposal.prose_diff)
        state_class = self._review_state_css_class(proposal.approval_state)
        return (
            "<li class=\"review-card\">"
            "<div class=\"review-card-header\"><div><strong>{title}</strong> <code>{proposal_id}</code></div><span class=\"review-state {state_class}\">{state}</span></div>"
            "<p>{detail}</p>"
            "<div class=\"review-meta-grid\">"
            "<div><span>Target</span><strong>{target_family} · <code>{target_object_id}</code></strong></div>"
            "<div><span>Policy</span><strong>{policy}</strong></div>"
            "<div><span>Source surface</span><strong>{source_surface}</strong></div>"
            "<div><span>Base → current</span><strong><code>{base_revision}</code> → <code>{current_revision}</code></strong></div>"
            "</div>"
            "{loop_note}"
            "<div class=\"review-grid\">"
            "<section class=\"review-section\"><h3>修订谱系</h3>{lineage}</section>"
            "<section class=\"review-section\"><h3>审核原因</h3><ul class=\"nested-list\">{reasons}</ul></section>"
            "<section class=\"review-section\"><h3>结构化差异</h3>{structured_diff}</section>"
            "<section class=\"review-section\"><h3>渲染的散文差异</h3><pre>{prose_diff}</pre></section>"
            "<section class=\"review-section\"><h3>漂移状态</h3>{drift}</section>"
            "<section class=\"review-section\"><h3>审核历史</h3><ul class=\"nested-list\">{decisions}</ul></section>"
            "</div>"
            "</li>"
        ).format(
            title=html.escape(proposal.target_title),
            proposal_id=html.escape(proposal.proposal_id),
            state_class=html.escape(state_class),
            state=html.escape(proposal.approval_state.replace("_", " ")),
            detail=html.escape(proposal.approval_state_detail),
            target_family=html.escape(proposal.target_family),
            target_object_id=html.escape(proposal.target_object_id),
            policy=html.escape(proposal.policy_class),
            source_surface=html.escape(proposal.source_surface),
            base_revision=html.escape(proposal.base_revision_id or "none"),
            current_revision=html.escape(proposal.current_revision_id or "none"),
            loop_note=loop_markup,
            lineage=lineage_markup,
            reasons=reason_markup,
            structured_diff=structured_diff_markup,
            prose_diff=prose_diff_markup,
            drift=drift_markup,
            decisions=decision_markup,
        )

    def _render_review_decision(self, decision: ReviewDecisionSnapshot) -> str:
        detail = ""
        detail = self._payload_text(decision.decision_payload, "reason") or self._payload_text(decision.decision_payload, "note")
        if not detail:
            detail = "未记录审核者备注。"
        mutation_record_id = decision.mutation_record_id
        mutation_markup = (
            f"<span>linked mutation <code>{html.escape(mutation_record_id)}</code></span>"
            if isinstance(mutation_record_id, str) and mutation_record_id.strip()
            else ""
        )
        return (
            "<li><strong>{state}</strong><p>{detail}</p><span>{created_by} · {created_at}</span>{mutation}</li>"
        ).format(
            state=html.escape(decision.approval_state.replace("_", " ")),
            detail=html.escape(detail),
            created_by=html.escape(decision.created_by),
            created_at=html.escape(decision.created_at),
            mutation=mutation_markup,
        )

    def _render_json_pairs(self, payload: Mapping[str, object]) -> str:
        if not payload:
            return "<p>无。</p>"
        markup = "".join(
            "<li><strong>{key}</strong><pre>{value}</pre></li>".format(
                key=html.escape(str(key)),
                value=html.escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)),
            )
            for key, value in payload.items()
        )
        return f"<ul class=\"nested-list nested-json\">{markup}</ul>"

    def _review_state_css_class(self, state: str) -> str:
        if state == "approved":
            return "review-state-success"
        if state == "rejected":
            return "review-state-danger"
        if state == "stale":
            return "review-state-warning"
        return "review-state-pending"

    def _render_workbench_scene_card(
        self,
        *,
        scene: WorkspaceObjectSummary,
        project_id: str,
        novel_id: str | None,
        style_rules: list[WorkspaceObjectSummary],
        skills: list[WorkspaceObjectSummary],
        facts: list[WorkspaceObjectSummary],
        chapter_artifacts: tuple[DerivedArtifactSnapshot, ...],
    ) -> str:
        scoped_skills = [
            skill
            for skill in skills
            if skill.payload.get("novel_id") == scene.payload.get("novel_id")
            and self._skill_matches_scene_to_chapter_scope(skill.payload)
        ]
        relevant_facts = [
            fact
            for fact in facts
            if fact.payload.get("source_scene_id") == scene.object_id
        ]
        matching_artifacts = [
            artifact for artifact in chapter_artifacts if artifact.payload.get("source_scene_id") == scene.object_id
        ]
        scene_title = self._payload_text(scene.payload, "title") or scene.object_id
        revision_hint = html.escape(scene.current_revision_id)
        workbench_query = SceneToChapterWorkbenchRequest(
            project_id=project_id,
            novel_id=str(scene.payload.get("novel_id", novel_id or "")),
            scene_object_id=scene.object_id,
            actor="web-shell",
            expected_source_scene_revision_id=scene.current_revision_id,
        )
        return (
            "<li><strong>{title}</strong>"
            "<p>版本 <code>{revision}</code> · {artifact_count} 个章节制品已固定到此场景。</p>"
            "<p>风格规则: {style_count} · 范围技能: {skill_count} · 规范事实: {fact_count}</p>"
            "<p>就绪请求固定 <code>{pinned_revision}</code> 场景 <code>{scene_id}</code>。</p>"
            "</li>"
        ).format(
            title=html.escape(scene_title),
            revision=revision_hint,
            artifact_count=len(matching_artifacts),
            style_count=len([item for item in style_rules if item.payload.get("novel_id") == scene.payload.get("novel_id")]),
            skill_count=len(scoped_skills),
            fact_count=len(relevant_facts),
            pinned_revision=html.escape(workbench_query.expected_source_scene_revision_id or ""),
            scene_id=html.escape(scene.object_id),
        )

    def _render_upstream_parent_card(
        self,
        *,
        parent: WorkspaceObjectSummary,
        link_type: str,
        link_label: str,
        child_family: str,
        children: list[WorkspaceObjectSummary],
        parent_id_key: str,
        project_id: str,
        novel_id: str | None,
    ) -> str:
        parent_title = self._payload_text(parent.payload, "title") or parent.object_id
        matching_children = [
            child for child in children
            if (self._payload_text(child.payload, parent_id_key) == parent.object_id
                or self._payload_text(child.payload, "parent_id") == parent.object_id)
        ]
        revision_hint = html.escape(parent.current_revision_id)
        child_status = (
            f"{len(matching_children)} 个{child_family}已生成"
            if matching_children
            else f"尚无{child_family}"
        )
        form_markup = (
            "<form method=\"post\" action=\"/workbench?{query}\" class=\"inline-form\">"
            "<input type=\"hidden\" name=\"link_type\" value=\"{link_type}\" />"
            "<input type=\"hidden\" name=\"parent_object_id\" value=\"{parent_id}\" />"
            "<input type=\"hidden\" name=\"expected_parent_revision_id\" value=\"{parent_revision}\" />"
            "<button type=\"submit\">生成{child_family}</button>"
            "</form>"
        ).format(
            query=html.escape(self._route_query(project_id=project_id, novel_id=novel_id).lstrip("?"), quote=True),
            link_type=html.escape(link_type, quote=True),
            parent_id=html.escape(parent.object_id, quote=True),
            parent_revision=html.escape(parent.current_revision_id, quote=True),
            child_family=html.escape(child_family),
        )
        return (
            "<li><strong>{title}</strong>"
            "<p>版本 <code>{revision}</code> · {child_status}</p>"
            "<p>{link_label} · 对象 <code>{object_id}</code></p>"
            "{form}"
            "</li>"
        ).format(
            title=html.escape(parent_title),
            revision=revision_hint,
            child_status=html.escape(child_status),
            link_label=html.escape(link_label),
            object_id=html.escape(parent.object_id),
            form=form_markup,
        )

    def _render_artifact_card(self, artifact: DerivedArtifactSnapshot) -> str:
        payload = artifact.payload
        lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
        delta = payload.get("delta_from_previous") if isinstance(payload.get("delta_from_previous"), dict) else {}
        chapter_title = self._payload_text(payload, "chapter_title") or artifact.object_id
        body_excerpt = self._diff_excerpt(payload)
        return (
            "<li><div><strong>{title}</strong> <code>{object_id}</code></div>"
            "<p>{excerpt}</p>"
            "<span>source scene <code>{scene_id}</code> · pinned revision <code>{scene_revision}</code></span>"
            "<span>lineage keys: {lineage_keys} · delta keys: {delta_keys}</span></li>"
        ).format(
            title=html.escape(chapter_title),
            object_id=html.escape(artifact.object_id),
            excerpt=html.escape(body_excerpt),
            scene_id=html.escape(str(payload.get("source_scene_id", ""))),
            scene_revision=html.escape(artifact.source_scene_revision_id),
            lineage_keys=html.escape(", ".join(sorted(lineage.keys())) if isinstance(lineage, dict) and lineage else "none"),
            delta_keys=html.escape(", ".join(sorted(delta.keys())) if isinstance(delta, dict) and delta else "none"),
        )

    def _render_export_artifact_card(self, artifact: DerivedArtifactSnapshot) -> str:
        payload = artifact.payload
        lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
        projections = payload.get("projections")
        projection_count = len(projections) if isinstance(projections, list) else 0
        return (
            "<li><div><strong>{title}</strong> <code>{object_id}</code></div>"
            "<p>{excerpt}</p>"
            "<span>artifact revision <code>{artifact_revision_id}</code> · source scene revision <code>{scene_revision}</code></span>"
            "<span>{projection_count} explicit projection(s) · lineage keys: {lineage_keys}</span></li>"
        ).format(
            title=html.escape(self._payload_text(payload, "chapter_title") or artifact.object_id),
            object_id=html.escape(artifact.object_id),
            excerpt=html.escape(self._diff_excerpt(payload)),
            artifact_revision_id=html.escape(artifact.artifact_revision_id),
            scene_revision=html.escape(artifact.source_scene_revision_id),
            projection_count=projection_count,
            lineage_keys=html.escape(", ".join(sorted(lineage.keys())) if isinstance(lineage, dict) and lineage else "none"),
        )

    def _render_publish_form(self, *, project_id: str, novel_id: str, artifact: DerivedArtifactSnapshot) -> str:
        output_root = Path.cwd() / "tmp-publish-output"
        return (
            "<form method=\"post\" action=\"/publish?project_id={project_id}&novel_id={novel_id}\" class=\"skill-form\">"
            "<input type=\"hidden\" name=\"chapter_artifact_object_id\" value=\"{object_id}\" />"
            "<input type=\"hidden\" name=\"base_artifact_revision_id\" value=\"{artifact_revision_id}\" />"
            "<input type=\"hidden\" name=\"expected_source_scene_revision_id\" value=\"{source_scene_revision_id}\" />"
            "<label>Output root<input type=\"text\" name=\"output_root\" value=\"{output_root}\" /></label>"
            "<p><strong>{title}</strong> <code>{object_id}</code><br>固定制品 <code>{artifact_revision_id}</code> 和源场景版本 <code>{source_scene_revision_id}</code>。</p>"
            "<button type=\"submit\">发布显式导出包</button>"
            "</form>"
        ).format(
            project_id=html.escape(project_id, quote=True),
            novel_id=html.escape(novel_id, quote=True),
            object_id=html.escape(artifact.object_id, quote=True),
            artifact_revision_id=html.escape(artifact.artifact_revision_id, quote=True),
            source_scene_revision_id=html.escape(artifact.source_scene_revision_id, quote=True),
            output_root=html.escape(str(output_root), quote=True),
            title=html.escape(self._payload_text(artifact.payload, "chapter_title") or artifact.object_id),
        )

    def _render_chapter_proposal_card(
        self,
        proposal: ReviewProposalSnapshot,
        *,
        project_id: str,
        novel_id: str | None,
    ) -> str:
        payload = proposal.proposal_payload
        wrapped_payload_raw = payload.get("payload")
        wrapped_payload = wrapped_payload_raw if isinstance(wrapped_payload_raw, dict) else {}
        reasons_raw = payload.get("reasons")
        reasons = reasons_raw if isinstance(reasons_raw, list) else []
        requested_raw = wrapped_payload.get("requested_payload")
        requested = requested_raw if isinstance(requested_raw, dict) else {}
        chapter_title = self._payload_text(requested, "chapter_title") or proposal.target_object_id
        query = self._route_query(project_id=project_id, novel_id=novel_id)
        reason_text = next((str(reason) for reason in reasons if isinstance(reason, str) and reason), "需要审核")
        return (
            "<li><div><strong>{title}</strong> <code>{proposal_id}</code></div>"
            "<p>{reason}</p>"
            "<span>{policy} · base revision <code>{base_revision}</code></span>"
            "<p><a class=\"back-link\" href=\"/review-desk{query}\">打开审核台</a></p></li>"
        ).format(
            title=html.escape(chapter_title),
            proposal_id=html.escape(proposal.proposal_id),
            reason=html.escape(reason_text),
            policy=html.escape(str(payload.get("policy_class", "review_required"))),
            base_revision=html.escape(proposal.base_revision_id or "none"),
            query=html.escape(query, quote=True),
        )

    def _render_sidebar_nav(self, current_route_id: str, project_id: str, novel_id: str | None) -> str:
        """Render sidebar navigation with active state highlighting."""
        query = self._route_query(project_id=project_id, novel_id=novel_id) if project_id else ""
        nav_items = [
            ("command-center", "全书总控台", f"/command-center{query}"),
            ("workbench", "流水线工作台", f"/workbench{query}"),
            ("review-desk", "审核台", f"/review-desk{query}"),
            ("skills", "技能工坊", f"/skills{query}"),
            ("publish", "发布导出", f"/publish{query}"),
            ("settings", "设置", f"/settings{query}"),
        ]
        parts: list[str] = []
        for route_id, label, href in nav_items:
            active = " nav-item-active" if route_id == current_route_id else ""
            parts.append(
                f'<a href="{html.escape(href, quote=True)}" class="nav-item{active}">'
                f'<span class="nav-label">{html.escape(label)}</span>'
                f'</a>'
            )
        return "".join(parts)

    def _render_layout(self, title: str, subtitle: str, content: str, *, current_route_id: str = "command-center", project_id: str = "", novel_id: str | None = None) -> str:
        return f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --color-bg: #ffffff;
      --color-bg-subtle: #f7f7f8;
      --color-bg-muted: #f3f4f6;
      --color-ink: #202123;
      --color-muted: #6b7280;
      --color-panel: #ffffff;
      --color-panel-strong: #f9fafb;
      --color-border: #e5e7eb;
      --color-accent: #d1d5db;
      --color-accent-strong: #374151;
      --color-danger: #b45309;
      --color-success: #166534;
      --color-warning: #92400e;
      --color-info: #1d4ed8;
      --space-1: 0.25rem;
      --space-2: 0.5rem;
      --space-3: 0.75rem;
      --space-4: 1rem;
      --space-5: 1.5rem;
      --space-6: 2rem;
      --space-7: 3rem;
      --radius-sm: 0.75rem;
      --radius-md: 1rem;
      --radius-lg: 1.5rem;
      --shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.04);
      --transition-base: 180ms ease;
      --font-display: \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif;
      --font-body: \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--color-ink);
      font-family: var(--font-body);
      background: var(--color-bg);
      min-height: 100vh;
      line-height: 1.6;
      display: grid;
      grid-template-columns: 16rem 1fr;
      grid-template-areas: "sidebar main";
    }}
    body::before {{
      content: none;
    }}
    .sidebar {{
      grid-area: sidebar;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      background: var(--color-bg-subtle);
      border-right: 1px solid var(--color-border);
      display: flex;
      flex-direction: column;
      padding: var(--space-5);
    }}
    .main-content {{
      grid-area: main;
      padding: var(--space-7) var(--space-6);
      overflow-y: auto;
      max-width: calc(100vw - 16rem);
    }}
    .layout-measure-anchor {{
      width: 100%;
      min-height: 1px;
      pointer-events: none;
    }}
    header {{ margin-bottom: var(--space-6); }}
    .eyebrow {{
      display: inline-flex;
      padding: var(--space-2) var(--space-3);
      border-radius: 999px;
      border: 1px solid var(--color-border);
      background: var(--color-bg-subtle);
      color: var(--color-muted);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 0.72rem;
      font-weight: 600;
    }}
    h1, h2, h3 {{ font-family: var(--font-display); margin: 0; }}
    h1 {{ font-size: clamp(2.35rem, 4vw, 3.5rem); line-height: 1.02; margin-top: var(--space-4); font-weight: 600; letter-spacing: -0.03em; }}
    h2 {{ font-size: 1.45rem; font-weight: 600; letter-spacing: -0.02em; }}
    h3 {{ font-size: 1rem; margin-bottom: var(--space-3); font-weight: 600; }}
    p {{ margin: 0; }}
    a {{ color: #2563eb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .sidebar-header {{
      margin-bottom: var(--space-6);
      padding-bottom: var(--space-5);
      border-bottom: 1px solid var(--color-border);
    }}
    .sidebar-title {{
      font-size: 1.5rem;
      font-weight: 600;
      margin-top: var(--space-2);
      letter-spacing: -0.02em;
      line-height: 1.3;
    }}
    .sidebar-nav {{
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: var(--space-2);
    }}
    .nav-item {{
      display: flex;
      flex-direction: column;
      gap: var(--space-1);
      padding: var(--space-3) var(--space-4);
      border-radius: var(--radius-sm);
      text-decoration: none;
      color: var(--color-ink);
      background: transparent;
      border: 1px solid transparent;
      transition: all var(--transition-base);
    }}
    .nav-item:hover {{
      background: var(--color-panel);
      border-color: var(--color-border);
      text-decoration: none;
    }}
    .nav-item-active {{
      background: var(--color-panel);
      border-color: var(--color-accent);
      font-weight: 600;
    }}
    .nav-label {{
      font-size: 0.95rem;
      font-family: var(--font-display);
    }}
    .sidebar-footer {{
      margin-top: auto;
      padding-top: var(--space-4);
      border-top: 1px solid var(--color-border);
      font-size: 0.85rem;
      color: var(--color-muted);
    }}
    code {{ color: var(--color-accent-strong); font-family: \"Cascadia Code\", \"SFMono-Regular\", Consolas, monospace; font-size: 0.9em; }}
    .lede {{ max-width: 52rem; color: var(--color-muted); font-size: 1rem; margin-top: var(--space-4); line-height: 1.7; }}
    .hero-panel, .panel {{
      border: 1px solid var(--color-border);
      background: var(--color-panel);
      box-shadow: var(--shadow-soft);
    }}
    .hero-panel {{
      border-radius: var(--radius-lg);
      padding: var(--space-6);
      display: grid;
      gap: var(--space-5);
      grid-template-columns: minmax(0, 1.3fr) minmax(18rem, 0.7fr);
      margin-bottom: var(--space-6);
    }}
    .hero-subtitle {{ color: #4b5563; font-size: 1rem; margin: var(--space-3) 0 var(--space-5); line-height: 1.7; }}
    .hero-stage {{
      border-left: 3px solid var(--color-border);
      padding-left: var(--space-4);
      color: var(--color-muted);
    }}
    .hero-stage strong {{ display: block; color: var(--color-ink); margin-bottom: var(--space-2); }}
    .queue-card {{
      padding: var(--space-5);
      border-radius: var(--radius-md);
      background: var(--color-panel-strong);
      border: 1px solid var(--color-border);
      margin-bottom: var(--space-4);
    }}
    .queue-card span, .metric-card span, .route-card span {{ color: var(--color-muted); display: block; font-size: 0.88rem; }}
    .queue-card strong {{ font-size: 2.5rem; color: var(--color-ink); }}
    .metric-grid, .route-grid, .content-grid {{ display: grid; gap: var(--space-4); }}
    .metric-grid {{ grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); }}
    .metric-card {{ padding: var(--space-4); border-radius: var(--radius-sm); background: var(--color-bg-subtle); border: 1px solid var(--color-border); }}
    .metric-card strong {{ display: block; margin-top: var(--space-2); font-size: 1.6rem; }}
    .content-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .panel {{ border-radius: var(--radius-md); padding: var(--space-5); }}
    .panel-wide {{ grid-column: 1 / -1; }}
    .panel-heading {{ margin-bottom: var(--space-4); }}
    .panel-heading p {{ color: var(--color-muted); margin: var(--space-2) 0 0; line-height: 1.6; }}
    .route-grid {{ grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); }}
    .route-card {{
      text-decoration: none;
      color: inherit;
      border-radius: var(--radius-sm);
      border: 1px solid var(--color-border);
      padding: var(--space-4);
      background: var(--color-bg-subtle);
      transition: transform var(--transition-base), border-color var(--transition-base), background var(--transition-base);
    }}
    .route-card:hover {{ transform: translateY(-1px); border-color: #d1d5db; background: #fcfcfd; text-decoration: none; }}
    .route-label {{ font-size: 1.1rem; font-family: var(--font-display); margin-bottom: var(--space-3); font-weight: 600; }}
    .route-card p {{ color: var(--color-muted); min-height: 4.5rem; margin: 0 0 var(--space-3); line-height: 1.55; }}
    .action-list, .signal-list, .audit-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: var(--space-3); }}
    .action-list li, .signal-list li, .audit-list li {{
      padding: var(--space-4);
      border-radius: var(--radius-sm);
      background: var(--color-panel);
      border: 1px solid var(--color-border);
    }}
    .action-list p, .signal-list p, .audit-list p {{ color: var(--color-muted); margin: var(--space-2) 0 0; line-height: 1.55; }}
    .action-list a, .back-link {{ color: #2563eb; }}
    .signal-kind {{ color: var(--color-muted); text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem; }}
    .audit-list code {{ color: var(--color-accent-strong); }}
    .audit-list span {{ display: block; margin-top: var(--space-2); color: var(--color-muted); font-size: 0.9rem; }}
    .review-desk-list {{ gap: var(--space-4); }}
    .review-card {{ display: grid; gap: var(--space-4); }}
    .status-banner {{ margin: var(--space-4) 0 0; padding: var(--space-3) var(--space-4); border-radius: var(--radius-sm); border: 1px solid var(--color-border); background: var(--color-bg-subtle); }}
    .status-banner-success {{ color: var(--color-success); }}
    .status-banner-danger {{ color: var(--color-danger); }}
    .review-card-header {{ display: flex; justify-content: space-between; gap: var(--space-4); align-items: flex-start; }}
    .review-state {{ display: inline-flex; align-items: center; padding: var(--space-2) var(--space-3); border-radius: 999px; border: 1px solid var(--color-border); background: var(--color-bg-subtle); text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.76rem; font-weight: 600; }}
    .review-state-success {{ color: var(--color-success); }}
    .review-state-danger {{ color: var(--color-danger); }}
    .review-state-warning {{ color: var(--color-warning); }}
    .review-state-pending {{ color: var(--color-info); }}
    .review-meta-grid, .review-grid {{ display: grid; gap: var(--space-3); }}
    .review-meta-grid {{ grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); }}
    .review-meta-grid div, .review-section {{ padding: var(--space-3); border-radius: var(--radius-sm); background: var(--color-bg-subtle); border: 1px solid var(--color-border); }}
    .review-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .review-loop-note {{ margin: 0; color: #4b5563; }}
    .nested-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: var(--space-2); }}
    .nested-list li {{ padding: var(--space-3); border-radius: var(--radius-sm); background: var(--color-panel); border: 1px solid var(--color-border); }}
    .nested-json pre, .review-section pre {{ margin: 0; padding: var(--space-3); border-radius: calc(var(--radius-sm) - 0.2rem); white-space: pre-wrap; word-break: break-word; color: #4b5563; background: var(--color-panel); border: 1px solid var(--color-border); font-family: "Cascadia Code", "SFMono-Regular", Consolas, monospace; font-size: 0.83rem; line-height: 1.45; }}
    .skill-form, .inline-form {{ display: grid; gap: var(--space-3); }}
    .skill-form label {{ display: grid; gap: var(--space-2); color: var(--color-muted); }}
    .skill-form input[type="text"], .skill-form textarea, .skill-form select {{ width: 100%; border-radius: var(--radius-sm); border: 1px solid #d1d5db; background: var(--color-panel); color: var(--color-ink); padding: var(--space-3); font: inherit; }}
    .skill-form input[type="text"]:focus, .skill-form textarea:focus, .skill-form select:focus {{ outline: none; border-color: #9ca3af; box-shadow: 0 0 0 3px rgba(229, 231, 235, 0.9); }}
    .skill-form textarea {{ min-height: 8rem; resize: vertical; }}
    .checkbox-row {{ grid-auto-flow: column; justify-content: start; align-items: center; }}
    .button-row, .inline-form {{ display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }}
    button {{ border: 1px solid #d1d5db; border-radius: 999px; background: #ffffff; color: var(--color-ink); padding: 0.8rem 1.1rem; font: inherit; font-weight: 600; cursor: pointer; transition: transform var(--transition-base), border-color var(--transition-base), background var(--transition-base); }}
    button:hover {{ transform: translateY(-1px); border-color: #9ca3af; background: var(--color-bg-subtle); }}
    button:disabled {{ opacity: 0.5; cursor: not-allowed; transform: none; }}
    .form-note {{ color: var(--color-muted); margin-top: var(--space-3); }}
    @media (max-width: 64rem) {{
      body {{ grid-template-columns: 12rem 1fr; }}
      .sidebar {{ padding: var(--space-3); }}
      .main-content {{ max-width: calc(100vw - 12rem); }}
    }}
    @media (max-width: 48rem) {{
      body {{ grid-template-columns: 1fr; grid-template-areas: "main"; }}
      .sidebar {{ display: none; }}
      .main-content {{ max-width: 100vw; padding: var(--space-5) var(--space-4); }}
      .hero-panel, .content-grid, .review-grid {{ grid-template-columns: 1fr; }}
      .review-card-header {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-header">
      <span class="eyebrow">SuperWriter</span>
      <h1 class="sidebar-title">总控台</h1>
    </div>
    <nav class="sidebar-nav" role="navigation" aria-label="Main navigation">
      {self._render_sidebar_nav(current_route_id, project_id, novel_id)}
    </nav>
    <div class="sidebar-footer">
      {f"Project: {html.escape(project_id)}" if project_id else ""}
    </div>
  </aside>
  <main class="main-content">
    <div id="layout-measure-anchor" class="layout-measure-anchor" data-measure-anchor="layout-measure-anchor" aria-hidden="true"></div>
    <header data-page-root="true">
      <span class="eyebrow">Book Command Center</span>
      <h2>{html.escape(title)}</h2>
      <p class="lede">{html.escape(subtitle)}</p>
    </header>
    {content}
  </main>
</body>
</html>
"""

    def _slugify_anchor(self, value: str) -> str:
        compact = "-".join(value.strip().lower().split())
        sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in compact)
        collapsed = "-".join(part for part in sanitized.split("-") if part)
        return collapsed or "page"

    def _render_signals(
        self,
        signals: tuple[CommandCenterSignal, ...],
        *,
        empty_copy: str,
    ) -> str:
        if not signals:
            return f"<li><strong>{html.escape(empty_copy)}</strong></li>"
        return "".join(
            (
                "<li><span class=\"signal-kind\">{kind}</span><strong>{title}</strong><p>{detail}</p></li>"
            ).format(
                kind=html.escape(signal.kind),
                title=html.escape(signal.title),
                detail=html.escape(signal.detail),
            )
            for signal in signals
        )

    def _route_query(self, *, project_id: str, novel_id: str | None) -> str:
        query_items = [f"project_id={project_id}"]
        if novel_id:
            query_items.append(f"novel_id={novel_id}")
        return "?" + "&".join(query_items)

    def _render_settings_page(self, *, project_id: str, novel_id: str | None) -> CommandCenterPage:
        """Render the AI provider settings page."""
        providers = self._service.list_provider_configs()
        provider_cards = "".join(self._render_provider_card(p, project_id, novel_id) for p in providers)

        content = f"""
        <section id="settings-page-root" class="settings-page" data-page="settings" data-measure-anchor="settings-page-root">
          <div id="settings-layout-anchor" class="settings-layout-anchor" aria-hidden="true"></div>
          <section class="panel panel-wide settings-panel" data-settings-section="provider-form">
            <div class="panel-heading">
              <h2>AI 提供者配置</h2>
              <p>配置 OpenAI 兼容的 API 提供者以启用 AI 生成功能。</p>
            </div>
            <form method="post" action="/api/providers{self._route_query(project_id=project_id, novel_id=novel_id)}" class="provider-form">
              <h3>添加新提供者</h3>
              <div class="form-grid">
                <div class="form-group">
                  <label for="provider_name">提供者名称</label>
                  <input type="text" id="provider_name" name="provider_name" placeholder="例如：openai、azure、local、custom 或自定义名称" required>
                  <small>可直接输入提供者标识或自定义名称。</small>
                </div>
                <div class="form-group">
                  <label for="base_url">API 地址</label>
                  <input type="url" id="base_url" name="base_url" placeholder="https://api.openai.com/v1" required>
                  <small>对于 OpenAI 使用: https://api.openai.com/v1</small>
                </div>
                <div class="form-group">
                  <label for="api_key">API 密钥</label>
                  <input type="password" id="api_key" name="api_key" placeholder="sk-..." required>
                </div>
                <div class="form-group">
                  <label for="model_name">模型名称</label>
                  <input type="text" id="model_name" name="model_name" placeholder="gpt-4o" required>
                  <small>例如: gpt-4o, gpt-4o-mini, claude-3-5-sonnet 等</small>
                </div>
                <div class="form-group">
                  <label for="temperature">温度 (0-2)</label>
                  <input type="number" id="temperature" name="temperature" min="0" max="2" step="0.1" value="0.7">
                </div>
                <div class="form-group">
                  <label for="max_tokens">最大令牌数</label>
                  <input type="number" id="max_tokens" name="max_tokens" min="1" value="4096">
                </div>
              </div>
              <div class="form-actions">
                <button type="submit" name="action" value="save">保存提供者</button>
                <button type="submit" name="action" value="save_and_activate">保存并设为活跃</button>
              </div>
            </form>
          </section>
          <section class="panel panel-wide settings-panel" data-settings-section="provider-list">
            <div class="panel-heading">
              <h3>已配置的提供者</h3>
            </div>
            <div class="provider-list" id="provider-list-root">
              {provider_cards if provider_cards else '<p class="empty-state">暂无配置的提供者</p>'}
            </div>
          </section>
        </section>
        <style>
          .settings-page {{
            display: grid;
            gap: var(--space-5);
            align-items: start;
          }}
          .settings-layout-anchor {{
            width: 100%;
            min-height: 1px;
          }}
          .settings-panel {{
            scroll-margin-top: var(--space-6);
          }}
          .form-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: var(--space-4);
            margin-bottom: var(--space-5);
          }}
          .form-group {{
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
          }}
          .form-group label {{
            font-weight: 600;
            font-size: 0.875rem;
          }}
          .form-group input, .form-group select {{
            padding: var(--space-2);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-sm);
            font-size: 1rem;
          }}
          .form-group small {{
            color: var(--color-muted);
            font-size: 0.75rem;
          }}
          .form-actions {{
            display: flex;
            gap: var(--space-3);
          }}
          .provider-list {{
            display: grid;
            gap: var(--space-4);
          }}
          .provider-card {{
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
            padding: var(--space-4);
            display: flex;
            justify-content: space-between;
            align-items: center;
          }}
          .provider-card.active {{
            border-color: var(--color-success);
            background: var(--color-bg-subtle);
          }}
          .provider-card h4 {{
            margin: 0 0 var(--space-2) 0;
          }}
          .provider-card-actions {{
            display: flex;
            gap: var(--space-2);
          }}
          .empty-state {{
            color: var(--color-muted);
            text-align: center;
            padding: var(--space-6);
          }}
        </style>
        """

        return CommandCenterPage(
            status_code=200,
            title="AI 提供者设置",
            body=self._render_layout(
                "AI 提供者设置",
                "配置 OpenAI 兼容的 API 用于 AI 内容生成",
                content,
                current_route_id="settings",
                project_id=project_id,
                novel_id=novel_id,
            ),
        )

    def _render_provider_card(self, provider: dict, project_id: str, novel_id: str | None) -> str:
        """Render a single provider configuration card."""
        is_active = provider.get("is_active", False)
        active_class = "active" if is_active else ""
        active_badge = '<span class="badge badge-success">活跃</span>' if is_active else ""

        return f"""
        <div class="provider-card {active_class}">
          <div>
            <h4>{html.escape(provider.get('provider_name', 'Unknown'))} {active_badge}</h4>
            <p><strong>模型:</strong> {html.escape(provider.get('model_name', 'N/A'))}</p>
            <p><strong>地址:</strong> {html.escape(provider.get('base_url', 'N/A'))}</p>
            <p><small>创建于: {html.escape(provider.get('created_at', 'N/A')[:10])}</small></p>
          </div>
          <div class="provider-card-actions">
            <form method="post" action="/api/providers{self._route_query(project_id=project_id, novel_id=novel_id)}" style="display:inline;">
              <input type="hidden" name="action" value="activate">
              <input type="hidden" name="provider_id" value="{html.escape(provider.get('provider_id', ''))}">
              <button type="submit" {'disabled' if is_active else ''}>设为活跃</button>
            </form>
            <form method="post" action="/api/providers{self._route_query(project_id=project_id, novel_id=novel_id)}" style="display:inline;">
              <input type="hidden" name="action" value="test">
              <input type="hidden" name="provider_id" value="{html.escape(provider.get('provider_id', ''))}">
              <button type="submit">测试连接</button>
            </form>
            <form method="post" action="/api/providers{self._route_query(project_id=project_id, novel_id=novel_id)}" style="display:inline;">
              <input type="hidden" name="action" value="delete">
              <input type="hidden" name="provider_id" value="{html.escape(provider.get('provider_id', ''))}">
              <button type="submit" class="button-danger">删除</button>
            </form>
          </div>
        </div>
        """

    def _handle_providers_api(self, *, project_id: str, novel_id: str | None) -> CommandCenterPage:
        return self.handle_api_request(
            path="/api/providers",
            method="GET",
            project_id=project_id,
            novel_id=novel_id,
            query={},
            payload={},
        )

    def _filter_artifacts(
        self,
        artifacts: tuple[DerivedArtifactSnapshot, ...],
        *,
        novel_id: str | None,
    ) -> tuple[DerivedArtifactSnapshot, ...]:
        if novel_id is None:
            return artifacts
        return tuple(artifact for artifact in artifacts if artifact.payload.get("novel_id") == novel_id)

    def _first_family(
        self,
        objects: Iterable[WorkspaceObjectSummary],
        family: str,
        object_id: str | None,
    ) -> WorkspaceObjectSummary | None:
        matches = [summary for summary in objects if summary.family == family]
        if object_id is not None:
            for summary in matches:
                if summary.object_id == object_id:
                    return summary
        return matches[0] if matches else None

    def _payload_text(self, payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
        return ""

    def _skill_matches_scene_to_chapter_scope(self, payload: Mapping[str, object]) -> bool:
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

    def _diff_excerpt(self, payload: Mapping[str, object]) -> str:
        preferred_keys = (
            "title",
            "chapter_title",
            "summary",
            "body",
            "reason",
            "note",
        )
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                compact = " ".join(value.split())
                return compact[:140] + ("…" if len(compact) > 140 else "")
        visible_keys = ", ".join(sorted(payload.keys())[:5])
        if visible_keys:
            return f"Diff fields: {visible_keys}"
        return json.dumps(payload, ensure_ascii=False)[:140]


class BookCommandCenterWSGIApp:
    __slots__: ClassVar[tuple[str, ...]] = ("_shell", "_frontend")
    _shell: BookCommandCenter
    _frontend: FrontendRuntimeConfig

    _FRONTEND_MODES: ClassVar[tuple[FrontendMode, ...]] = ("legacy", "hybrid", "spa")
    _LEGACY_ROUTE_PREFIX: ClassVar[str] = "/legacy"
    _HYBRID_FRONTEND_PREFIX: ClassVar[str] = "/app"

    def __init__(
        self,
        service: SuperwriterApplicationService,
        *,
        frontend_mode: FrontendMode = "legacy",
        frontend_dist_dir: Path | None = None,
    ):
        normalized_mode = frontend_mode.strip().lower()
        if normalized_mode not in self._FRONTEND_MODES:
            supported = ", ".join(self._FRONTEND_MODES)
            raise ValueError(f"Unsupported frontend mode: {frontend_mode}. Expected one of: {supported}")
        self._shell = BookCommandCenter(service)
        repo_root = Path(__file__).resolve().parents[2]
        dist_dir = (frontend_dist_dir or (repo_root / "apps" / "frontend" / "dist")).resolve()
        self._frontend = FrontendRuntimeConfig(mode=cast(FrontendMode, normalized_mode), dist_dir=dist_dir)

    def __call__(
        self,
        environ: Mapping[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> Iterable[bytes]:
        path = str(environ.get("PATH_INFO", "/") or "/")
        method = str(environ.get("REQUEST_METHOD", "GET") or "GET").upper()
        query = parse_qs(str(environ.get("QUERY_STRING", "") or ""))
        project_id = self._query_value(query, "project_id")
        novel_id = self._query_value(query, "novel_id")
        legacy_request_path = self._strip_legacy_prefix(path)

        page = self._serve_frontend_request(path=path, method=method, project_id=project_id)
        if page is None and legacy_request_path is not None:
            page = self._dispatch_shell_request(
                path=legacy_request_path,
                method=method,
                query=query,
                environ=environ,
                project_id=project_id,
                novel_id=novel_id,
            )
            page = self._prefix_legacy_shell_page(page)
        elif page is None and (path.startswith("/api/") or (method == "POST" and path.rstrip("/") == "/create-novel")):
            page = self._dispatch_shell_request(
                path=path,
                method=method,
                query=query,
                environ=environ,
                project_id=project_id,
                novel_id=novel_id,
            )
        elif page is None and not project_id:
            page = CommandCenterPage(
                status_code=200,
                title="Superwriter local shell",
                body=self._shell.render_missing_project_page(),
            )
        elif page is None:
            page = self._dispatch_shell_request(
                path=path,
                method=method,
                query=query,
                environ=environ,
                project_id=project_id,
                novel_id=novel_id,
            )
        payload = page.body.encode("utf-8") if isinstance(page.body, str) else page.body
        _ = start_response(
            f"{page.status_code} {self._status_reason(page.status_code)}",
            [("Content-Type", page.content_type)],
        )
        return [payload]

    def _dispatch_shell_request(
        self,
        *,
        path: str,
        method: str,
        query: Mapping[str, list[str]],
        environ: Mapping[str, object],
        project_id: str | None,
        novel_id: str | None,
    ) -> CommandCenterPage:
        normalized_path = path.rstrip("/") or "/"
        if normalized_path.startswith("/api/"):
            query_payload = {key: self._query_value(query, key) or "" for key in query}
            try:
                request_payload = self._parse_request_payload(environ, path=normalized_path)
            except ValueError as error:
                return self._shell._json_error("invalid_input", self._shell._error_message(error), status_code=400)
            return self._shell.handle_api_request(
                path=normalized_path,
                method=method,
                project_id=project_id,
                novel_id=novel_id,
                query=query_payload,
                payload=request_payload,
            )
        if method == "POST" and normalized_path == "/create-novel":
            body_query = parse_qs(self._request_body(environ))
            return self._shell.submit_create_novel_form(
                {key: self._query_value(body_query, key) or "" for key in body_query}
            )
        if project_id is None:
            return CommandCenterPage(
                status_code=200,
                title="Superwriter local shell",
                body=self._shell.render_missing_project_page(),
            )
        if method == "POST" and normalized_path == "/skills":
            body_query = parse_qs(self._request_body(environ))
            if novel_id is None:
                return CommandCenterPage(
                    status_code=400,
                    title="缺少 novel_id",
                    body=(
                        "<html><body><main><h1>缺少 novel_id</h1>"
                        "<p>Skill Studio mutations require a novel-scoped workshop context.</p>"
                        "<p>Provide both project_id and novel_id in the request URL.</p>"
                        "</main></body></html>"
                    ),
                )
            return self._shell.submit_skill_workshop_form(
                project_id=project_id,
                novel_id=novel_id,
                form={key: self._query_value(body_query, key) or "" for key in body_query},
            )
        if method == "POST" and normalized_path == "/publish":
            body_query = parse_qs(self._request_body(environ))
            if novel_id is None:
                return CommandCenterPage(
                    status_code=400,
                    title="缺少 novel_id",
                    body=(
                        "<html><body><main><h1>缺少 novel_id</h1>"
                        "<p>Publish mutations require a novel-scoped context.</p>"
                        "<p>Provide both project_id and novel_id in the request URL.</p>"
                        "</main></body></html>"
                    ),
                )
            return self._shell.submit_publish_form(
                project_id=project_id,
                novel_id=novel_id,
                form={key: self._query_value(body_query, key) or "" for key in body_query},
            )
        if method == "POST" and normalized_path == "/workbench":
            body_query = parse_qs(self._request_body(environ))
            if novel_id is None:
                return CommandCenterPage(
                    status_code=400,
                    title="缺少 novel_id",
                    body=(
                        "<html><body><main><h1>缺少 novel_id</h1>"
                        "<p>Workbench mutations require a novel-scoped context.</p>"
                        "<p>Provide both project_id and novel_id in the request URL.</p>"
                        "</main></body></html>"
                    ),
                )
            return self._shell.submit_workbench_form(
                project_id=project_id,
                novel_id=novel_id,
                form={key: self._query_value(body_query, key) or "" for key in body_query},
            )
        return self._shell.render_route(path, project_id=project_id, novel_id=novel_id)

    def _serve_frontend_request(
        self,
        *,
        path: str,
        method: str,
        project_id: str | None,
    ) -> CommandCenterPage | None:
        if method != "GET":
            return None
        if path.startswith(f"{self._LEGACY_ROUTE_PREFIX}/") or path == self._LEGACY_ROUTE_PREFIX:
            return None
        if self._frontend.mode == "legacy":
            return None
        if self._frontend.mode == "hybrid":
            return self._serve_hybrid_frontend_request(path)
        return self._serve_spa_frontend_request(path, project_id=project_id)

    def _serve_hybrid_frontend_request(self, path: str) -> CommandCenterPage | None:
        hybrid_prefix = self._HYBRID_FRONTEND_PREFIX
        normalized_path = path.rstrip("/") or "/"
        if normalized_path == hybrid_prefix:
            return self._serve_frontend_index(status_code=200)
        if not path.startswith(f"{hybrid_prefix}/"):
            return self._serve_frontend_asset(path)
        subpath = path[len(hybrid_prefix) :] or "/"
        asset_page = self._serve_frontend_asset(subpath)
        if asset_page is not None:
            return asset_page
        if self._has_frontend_dist():
            return self._serve_frontend_index(status_code=200)
        return self._missing_frontend_bundle_page(path, mode="hybrid")

    def _serve_spa_frontend_request(
        self,
        path: str,
        *,
        project_id: str | None,
    ) -> CommandCenterPage | None:
        asset_page = self._serve_frontend_asset(path)
        if asset_page is not None:
            return asset_page
        if path.startswith("/api/") or path == "/create-novel" or project_id is None:
            return None
        if self._has_frontend_dist():
            return self._serve_frontend_index(status_code=200)
        return self._missing_frontend_bundle_page(path, mode="spa")

    def _serve_frontend_index(self, *, status_code: int) -> CommandCenterPage:
        index_path = self._frontend.dist_dir / "index.html"
        if not index_path.is_file():
            return self._missing_frontend_bundle_page(index_path.as_posix(), mode=self._frontend.mode)
        return CommandCenterPage(
            status_code=status_code,
            title="Superwriter Frontend",
            body=index_path.read_bytes(),
            content_type="text/html; charset=utf-8",
        )

    def _serve_frontend_asset(self, path: str) -> CommandCenterPage | None:
        asset_path = self._frontend_asset_path(path)
        if asset_path is None:
            return None
        content_type, _ = mimetypes.guess_type(str(asset_path))
        if content_type is None:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
            "image/svg+xml",
        }:
            content_type = f"{content_type}; charset=utf-8"
        return CommandCenterPage(
            status_code=200,
            title=asset_path.name,
            body=asset_path.read_bytes(),
            content_type=content_type,
        )

    def _frontend_asset_path(self, path: str) -> Path | None:
        if not self._has_frontend_dist():
            return None
        normalized_path = path.rstrip("/") or "/"
        if normalized_path in {"/", "/create-novel"} or path.startswith("/api/"):
            return None
        relative_parts = [part for part in Path(path.lstrip("/")).parts if part not in {".", ""}]
        if not relative_parts or any(part == ".." for part in relative_parts):
            return None
        candidate = self._frontend.dist_dir.joinpath(*relative_parts).resolve()
        if candidate != self._frontend.dist_dir and self._frontend.dist_dir not in candidate.parents:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def _has_frontend_dist(self) -> bool:
        return (self._frontend.dist_dir / "index.html").is_file()

    def _missing_frontend_bundle_page(self, target: str, *, mode: FrontendMode) -> CommandCenterPage:
        dist = html.escape(str(self._frontend.dist_dir), quote=True)
        escaped_target = html.escape(target, quote=True)
        return CommandCenterPage(
            status_code=503,
            title="缺少前端构建产物",
            body=(
                "<html><body><main><h1>缺少前端构建产物</h1>"
                f"<p>{html.escape(mode)} 模式请求了 {escaped_target}，但未找到 {dist} 中的 index.html。</p>"
                "<p>请先构建前端产物，或切回 SUPERWRITER_FRONTEND_MODE=legacy。</p>"
                "</main></body></html>"
            ),
            content_type="text/html; charset=utf-8",
        )

    def _strip_legacy_prefix(self, path: str) -> str | None:
        normalized_path = path.rstrip("/") or "/"
        if normalized_path == self._LEGACY_ROUTE_PREFIX:
            return "/"
        legacy_prefix = f"{self._LEGACY_ROUTE_PREFIX}/"
        if not path.startswith(legacy_prefix):
            return None
        stripped = path[len(self._LEGACY_ROUTE_PREFIX) :]
        return stripped if stripped.startswith("/") else f"/{stripped}"

    def _prefix_legacy_shell_page(self, page: CommandCenterPage) -> CommandCenterPage:
        if not isinstance(page.body, str) or not page.content_type.startswith("text/html"):
            return page
        body = page.body
        for attribute in ('href="/', 'action="/', 'src="/'):
            body = body.replace(attribute, f'{attribute[:-1]}{self._LEGACY_ROUTE_PREFIX}/')
        return CommandCenterPage(
            status_code=page.status_code,
            title=page.title,
            body=body,
            content_type=page.content_type,
        )

    def _query_value(self, query: Mapping[str, list[str]], key: str) -> str | None:
        values = query.get(key) or []
        for value in values:
            stripped = value.strip()
            if stripped:
                return stripped
        return None

    def _status_reason(self, status_code: int) -> str:
        if status_code == 200:
            return "OK"
        if status_code == 503:
            return "Service Unavailable"
        if status_code == 400:
            return "错误请求"
        if status_code == 404:
            return "未找到"
        return "Response"

    def _request_body(self, environ: Mapping[str, object]) -> str:
        raw_input = environ.get("wsgi.input")
        if raw_input is None:
            return ""
        content_length_raw = str(environ.get("CONTENT_LENGTH", "") or "").strip()
        try:
            content_length = int(content_length_raw) if content_length_raw else 0
        except ValueError:
            content_length = 0
        if content_length <= 0:
            return ""
        if not isinstance(raw_input, _RequestBodyReader):
            return ""
        body = raw_input.read(content_length)
        if isinstance(body, bytes):
            return body.decode("utf-8")
        return str(body)

    def _parse_request_payload(self, environ: Mapping[str, object], *, path: str) -> dict[str, object]:
        raw_body = self._request_body(environ)
        if not raw_body.strip():
            return {}
        content_type = str(environ.get("CONTENT_TYPE", "") or "").split(";", 1)[0].strip().lower()
        if content_type == "application/json" or raw_body.lstrip().startswith("{"):
            decoded = json.loads(raw_body)
            if not isinstance(decoded, dict):
                raise ValueError(f"{path} request body must be a JSON object")
            return cast(dict[str, object], decoded)
        form_payload = parse_qs(raw_body)
        return {key: self._query_value(form_payload, key) or "" for key in form_payload}


__all__ = [
    "BookCommandCenter",
    "BookCommandCenterWSGIApp",
    "CommandCenterAuditEntry",
    "CommandCenterPage",
    "CommandCenterRoute",
    "CommandCenterSignal",
    "CommandCenterSnapshot",
    "NextAction",
]
