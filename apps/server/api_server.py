"""API-only WSGI server for SuperWriter SPA frontend.

Stripped from the original 3401-line command_center.py — no HTML rendering, only JSON API + SPA static file serving.
"""

from __future__ import annotations

import json
import mimetypes
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol, cast, runtime_checkable
from urllib.parse import parse_qs

from apps.server.pipeline_api import FileStore, FileWatcher, PipelineAPI

from core.runtime import (
    ChapterMutationSignals,
    ChatMessageRequest,
    ChatTurnRequest,
    CreateWorkspaceRequest,
    DerivedArtifactSnapshot,
    EventToSceneWorkbenchRequest,
    GetChatSessionRequest,
    ImportOutlineRequest,
    ImportRequest,
    OpenChatSessionRequest,
    OutlineToPlotWorkbenchRequest,
    PlotToEventWorkbenchRequest,
    PublishExportArtifactRequest,
    PublishExportRequest,
    ReadObjectRequest,
    RetrievalRebuildRequest,
    RetrievalSearchRequest,
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
    SupportedDonor,
    WorkspaceContextSnapshot,
    WorkspaceObjectSummary,
    WorkspaceSnapshotRequest,
)
from core.skills import ALLOWED_STYLE_SCOPES


# ---------------------------------------------------------------------------
# Data classes (shared with frontend contract)
# ---------------------------------------------------------------------------

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
class ApiResponse:
    status_code: int
    body: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class FrontendRuntimeConfig:
    dist_dir: Path


@runtime_checkable
class _RequestBodyReader(Protocol):
    def read(self, size: int = ...) -> bytes | str: ...


# ---------------------------------------------------------------------------
# JSON response helpers
# ---------------------------------------------------------------------------

def _json_response(data: Mapping[str, object], *, status_code: int = 200) -> ApiResponse:
    payload = json.dumps(_serialize_json(data), ensure_ascii=False, sort_keys=True)
    return ApiResponse(
        status_code=status_code,
        body=payload.encode("utf-8"),
        content_type="application/json; charset=utf-8",
    )


def _json_ok(data: Mapping[str, object], *, status_code: int = 200) -> ApiResponse:
    return _json_response({"ok": True, "data": _serialize_json(data)}, status_code=status_code)


def _json_error(code: str, message: str, *, status_code: int, details: Mapping[str, object] | None = None) -> ApiResponse:
    return _json_response(
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": _serialize_json(details or {}),
            },
        },
        status_code=status_code,
    )


def _serialize_json(value: object) -> object:
    if is_dataclass(value):
        return _serialize_json(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _serialize_json(child) for key, child in value.items()}
    if isinstance(value, tuple | list):
        return [_serialize_json(child) for child in value]
    if isinstance(value, Path):
        return str(value)
    return value


# ---------------------------------------------------------------------------
# Value parsing helpers
# ---------------------------------------------------------------------------

def _require_method(method: str, allowed: set[str]) -> None:
    if method not in allowed:
        raise ValueError(f"method {method} is not allowed for this route")


def _require_project_id(project_id: str | None) -> str:
    if project_id is None:
        raise ValueError("project_id is required")
    return project_id


def _require_novel_id(novel_id: str | None) -> str:
    if novel_id is None:
        raise ValueError("novel_id is required")
    return novel_id


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    return _string_value(value)


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    return _string_or_none(payload.get(key))


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    raise ValueError("expected string value")


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return None


def _bool_from_value(value: object, *, default: bool) -> bool:
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


def _bool_from_optional_value(value: object) -> bool | None:
    if value is None:
        return None
    return _bool_from_value(value, default=False)


def _optional_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    return _int_from_value(value, default=0)


def _int_from_value(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip():
        return int(value.strip())
    raise ValueError("expected integer value")


def _float_from_value(value: object, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value.strip())
    raise ValueError("expected number value")


def _value_error_status(message: str) -> tuple[int, str]:
    lowered = message.lower()
    if "method " in lowered and " is not allowed" in lowered:
        return 405, "method_not_allowed"
    if any(token in lowered for token in ("illegal transition", "invalid transition", "unsupported approval_state")):
        return 409, "illegal_transition"
    if any(token in lowered for token in ("stale", "drift", "mismatch")):
        return 409, "conflict"
    return 400, "invalid_input"


def _error_message(error: BaseException) -> str:
    return str(error.args[0]) if error.args else str(error)


# ---------------------------------------------------------------------------
# SuperwriterAPIApp — API request handler (no HTML)
# ---------------------------------------------------------------------------

class SuperwriterAPIApp:
    __slots__ = ("_service",)
    _service: SuperwriterApplicationService

    def __init__(self, service: SuperwriterApplicationService):
        self._service = service

    # -- main dispatch -------------------------------------------------------

    def handle_request(
        self,
        *,
        path: str,
        method: str,
        project_id: str | None,
        novel_id: str | None,
        query: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> ApiResponse:
        normalized_path = path.rstrip("/") or "/"
        try:
            if normalized_path == "/api/startup":
                _require_method(method, {"GET"})
                return _json_ok({"startup": self._build_startup_snapshot()})

            if normalized_path == "/api/create-novel":
                _require_method(method, {"POST"})
                return self._handle_create_novel(payload)

            if normalized_path == "/api/skills":
                pid = _require_project_id(project_id)
                nid = _require_novel_id(novel_id)
                if method == "GET":
                    workshop = self._service.get_skill_workshop(
                        SkillWorkshopRequest(
                            project_id=pid,
                            novel_id=nid,
                            selected_skill_id=_string_or_none(query.get("selected_skill_id")),
                            left_revision_id=_string_or_none(query.get("left_revision_id")),
                            right_revision_id=_string_or_none(query.get("right_revision_id")),
                        )
                    )
                    return _json_ok({"workshop": _serialize_json(workshop)})
                _require_method(method, {"POST"})
                return _json_ok({"result": _serialize_json(self._submit_skill_workshop(novel_id=nid, payload=payload))})

            if normalized_path in {"/api/providers", "/api/settings"}:
                if method == "GET":
                    return _json_ok({"settings": self._build_provider_settings_snapshot()})
                _require_method(method, {"POST"})
                return _json_ok({"result": _serialize_json(self._submit_provider(payload))})

            return _json_error("not_found", f"Unknown API route: {normalized_path}", status_code=404)

        except KeyError as error:
            return _json_error("not_found", _error_message(error), status_code=404)
        except ValueError as error:
            message = _error_message(error)
            status_code, code = _value_error_status(message)
            return _json_error(code, message, status_code=status_code)
        except sqlite3.Error as error:
            import traceback
            traceback.print_exc()
            return _json_error("dependency_failure", _error_message(error), status_code=502)
        except (OSError, RuntimeError) as error:
            return _json_error("dependency_failure", _error_message(error), status_code=502)
        except Exception as error:
            import traceback
            traceback.print_exc()
            return _json_error("internal_error", _error_message(error), status_code=500)

    # -- command center snapshot ----------------------------------------------

    def build_snapshot(self, *, project_id: str, novel_id: str | None = None) -> CommandCenterSnapshot:
        workspace = self._service.get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        project = self._first_family(workspace.canonical_objects, "project", project_id)
        novel = self._first_family(workspace.canonical_objects, "novel", novel_id)
        project_title = self._payload_text(project.payload, "title") if project else "未绑定项目"
        novel_title = self._payload_text(novel.payload, "title") if novel else "未选择小说"

        canonical_counts = Counter(s.family for s in workspace.canonical_objects)
        chapter_artifacts = self._filter_artifacts(self._service.list_derived_artifacts("chapter_artifact"), novel_id=novel_id)
        export_artifacts = self._filter_artifacts(self._service.list_derived_artifacts("export_artifact"), novel_id=novel_id)
        object_counts = dict(canonical_counts)
        object_counts["chapter_artifact"] = len(chapter_artifacts)
        object_counts["export_artifact"] = len(export_artifacts)

        scenes = [s for s in workspace.canonical_objects if s.family == "scene"]
        events = [s for s in workspace.canonical_objects if s.family == "event"]
        outlines = [s for s in workspace.canonical_objects if s.family == "outline_node"]
        plots = [s for s in workspace.canonical_objects if s.family == "plot_node"]
        skills = [s for s in workspace.canonical_objects if s.family == "skill"]
        scene_ids_with_chapters = {
            self._payload_text(a.payload, "source_scene_id")
            for a in chapter_artifacts
            if self._payload_text(a.payload, "source_scene_id")
        }
        scenes_without_chapters = [s for s in scenes if s.object_id not in scene_ids_with_chapters]

        blocked_signals = self._build_blocked_signals(project=project, novel=novel)
        stale_signals = self._build_stale_signals(
            outlines=outlines, plots=plots, events=events, scenes=scenes,
            scenes_without_chapters=scenes_without_chapters, skills=skills,
        )
        routes = self._build_routes(
            project_id=project_id, novel_id=novel_id,
            outlines=outlines, plots=plots, events=events, scenes=scenes,
            scenes_without_chapters=scenes_without_chapters, review_queue_count=0,
            skills_count=len(skills), chapter_artifact_count=len(chapter_artifacts),
            export_artifact_count=len(export_artifacts),
        )
        next_actions = self._build_next_actions(
            routes=routes, blocked_signals=blocked_signals, stale_signals=stale_signals,
            scenes_without_chapters=scenes_without_chapters,
            skills=skills, chapter_artifacts=chapter_artifacts, export_artifacts=export_artifacts,
        )
        audit_entries = self._build_audit_entries(workspace.canonical_objects)
        stage_label, stage_detail = self._stage_summary(
            novel=novel, scenes=scenes, chapter_artifacts=chapter_artifacts,
            export_artifacts=export_artifacts,
            scenes_without_chapters=scenes_without_chapters,
        )
        return CommandCenterSnapshot(
            project_id=project_id, novel_id=novel_id,
            project_title=project_title, novel_title=novel_title,
            stage_label=stage_label, stage_detail=stage_detail,
            object_counts=object_counts,
            blocked_signals=blocked_signals, stale_signals=stale_signals,
            next_actions=next_actions, routes=routes,
            audit_entries=audit_entries, review_queue_count=0,
        )

    # -- mutation handlers ---------------------------------------------------

    def _handle_create_novel(self, payload: Mapping[str, object]) -> ApiResponse:
        folder_path = (_string_value(payload.get("folder_path", ""))).strip()
        novel_title = (_string_value(payload.get("novel_title", ""))).strip()
        project_title = (_string_value(payload.get("project_title", ""))).strip() or novel_title
        if not folder_path:
            raise ValueError("请选择用于初始化小说的本地文件夹。")
        if not novel_title:
            raise ValueError("请填写小说名称。")
        workspace_root = Path(folder_path).expanduser().resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        workspace_result = self._service.create_workspace(
            CreateWorkspaceRequest(
                project_title=project_title, novel_title=novel_title,
                actor="web-shell", source_surface="command_center_start",
                source_ref="web-shell:/api/create-novel",
            )
        )
        manifest_dir = workspace_root / ".superwriter"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "workspace.json"
        manifest_payload = {
            "project": {"id": workspace_result.project_id, "title": project_title},
            "novel": {"id": workspace_result.novel_id, "title": novel_title},
        }
        manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json_ok(
            {"workspace": {
                "project_id": workspace_result.project_id,
                "novel_id": workspace_result.novel_id,
                "manifest_path": str(manifest_path),
            }},
            status_code=201,
        )

    def _submit_workbench(self, *, project_id: str, novel_id: str, payload: Mapping[str, object]) -> object:
        link_type = _required_string(payload, "link_type")
        action = _optional_string(payload, "action") or "generate"
        if action == "delete_object":
            family = _required_string(payload, "family")
            object_id = _required_string(payload, "object_id")
            self._service.delete_workspace_object(family=family, object_id=object_id)
            return {"action": "delete_object", "family": family, "object_id": object_id}
        if link_type == "import_outline":
            return self._service.import_outline(
                ImportOutlineRequest(
                    novel_id=novel_id,
                    title=_required_string(payload, "outline_title"),
                    body=_required_string(payload, "outline_body"),
                    actor="web-shell", source_surface="workbench_outline_import",
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "outline_to_plot":
            return self._service.generate_outline_to_plot_workbench(
                OutlineToPlotWorkbenchRequest(
                    project_id=project_id, novel_id=novel_id,
                    outline_node_object_id=_required_string(payload, "parent_object_id"),
                    actor="web-shell",
                    expected_parent_revision_id=_optional_string(payload, "expected_parent_revision_id"),
                    target_child_object_id=_optional_string(payload, "target_child_object_id"),
                    base_child_revision_id=_optional_string(payload, "base_child_revision_id"),
                    require_ai=True,
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "plot_to_event":
            return self._service.generate_plot_to_event_workbench(
                PlotToEventWorkbenchRequest(
                    project_id=project_id, novel_id=novel_id,
                    plot_node_object_id=_required_string(payload, "parent_object_id"),
                    actor="web-shell",
                    expected_parent_revision_id=_optional_string(payload, "expected_parent_revision_id"),
                    target_child_object_id=_optional_string(payload, "target_child_object_id"),
                    base_child_revision_id=_optional_string(payload, "base_child_revision_id"),
                    require_ai=True,
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "event_to_scene":
            return self._service.generate_event_to_scene_workbench(
                EventToSceneWorkbenchRequest(
                    project_id=project_id, novel_id=novel_id,
                    event_object_id=_required_string(payload, "parent_object_id"),
                    actor="web-shell",
                    expected_parent_revision_id=_optional_string(payload, "expected_parent_revision_id"),
                    target_child_object_id=_optional_string(payload, "target_child_object_id"),
                    base_child_revision_id=_optional_string(payload, "base_child_revision_id"),
                    require_ai=True,
                    source_ref="web-shell:/api/workbench",
                )
            )
        if link_type == "scene_to_chapter":
            scene_object_id = _optional_string(payload, "scene_object_id") or _optional_string(payload, "parent_object_id")
            if scene_object_id is None:
                raise ValueError("scene_object_id is required")
            chapter_signals_payload = payload.get("chapter_signals")
            chapter_signals = None
            if isinstance(chapter_signals_payload, dict):
                chapter_signals = ChapterMutationSignals(**chapter_signals_payload)
            return self._service.generate_scene_to_chapter_workbench(
                SceneToChapterWorkbenchRequest(
                    project_id=project_id, novel_id=novel_id,
                    scene_object_id=scene_object_id, actor="web-shell",
                    expected_source_scene_revision_id=_optional_string(payload, "expected_source_scene_revision_id"),
                    target_artifact_object_id=_optional_string(payload, "target_artifact_object_id"),
                    base_artifact_revision_id=_optional_string(payload, "base_artifact_revision_id"),
                    chapter_signals=chapter_signals,
                    source_ref="web-shell:/api/workbench",
                    skill_name=_optional_string(payload, "skill_name"),
                )
            )
        raise ValueError(f"unsupported workbench link_type: {link_type}")

    def _submit_skill_workshop(self, *, novel_id: str, payload: Mapping[str, object]) -> object:
        action = _required_string(payload, "action").lower()
        if action == "create":
            return self._service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id, actor="web-shell", source_surface="skill_workshop_form",
                    name=_required_string(payload, "name"),
                    description=_string_value(payload.get("description", "")),
                    instruction=_required_string(payload, "instruction"),
                    style_scope=_optional_string(payload, "style_scope") or "scene_to_chapter",
                    is_active=_bool_from_value(payload.get("is_active"), default=True),
                    revision_reason="从 API 创建受约束技能",
                    source_ref="web-shell:/api/skills",
                )
            )
        if action == "update":
            return self._service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id, actor="web-shell", source_surface="skill_workshop_form",
                    skill_object_id=_required_string(payload, "skill_object_id"),
                    name=_optional_string(payload, "name"),
                    description=_optional_string(payload, "description"),
                    instruction=_optional_string(payload, "instruction"),
                    style_scope=_optional_string(payload, "style_scope"),
                    is_active=_bool_from_optional_value(payload.get("is_active")),
                    base_revision_id=_optional_string(payload, "base_revision_id"),
                    revision_reason="从 API 更新受约束技能",
                    source_ref="web-shell:/api/skills",
                )
            )
        if action == "toggle":
            return self._service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id, actor="web-shell", source_surface="skill_workshop_form",
                    skill_object_id=_required_string(payload, "skill_object_id"),
                    is_active=_bool_from_value(payload.get("is_active"), default=False),
                    base_revision_id=_optional_string(payload, "base_revision_id"),
                    revision_reason="从 API 切换受约束技能激活状态",
                    source_ref="web-shell:/api/skills",
                )
            )
        if action == "rollback":
            return self._service.rollback_skill_workshop_skill(
                SkillWorkshopRollbackRequest(
                    skill_object_id=_required_string(payload, "skill_object_id"),
                    target_revision_id=_required_string(payload, "target_revision_id"),
                    actor="web-shell", source_surface="skill_workshop_form",
                    revision_reason="从 API 回滚受约束技能",
                )
            )
        if action == "import":
            return self._service.import_skill_workshop_skill(
                SkillWorkshopImportRequest(
                    donor_kind=_optional_string(payload, "donor_kind") or "prompt_template",
                    novel_id=novel_id, actor="web-shell", source_surface="skill_workshop_form",
                    donor_payload={
                        "name": _string_value(payload.get("name", "")),
                        "title": _string_value(payload.get("name", "")),
                        "description": _string_value(payload.get("description", "")),
                        "instruction": _string_value(payload.get("instruction", "")),
                        "prompt": _string_value(payload.get("instruction", "")),
                        "role": _string_value(payload.get("name", "")),
                    },
                    style_scope=_optional_string(payload, "style_scope") or "scene_to_chapter",
                    is_active=_bool_from_value(payload.get("is_active"), default=True),
                    source_ref="web-shell:/api/skills",
                )
            )
        raise ValueError("unsupported skill workshop action")

    def _submit_publish(self, *, project_id: str, novel_id: str, payload: Mapping[str, object]) -> object:
        action = _optional_string(payload, "action") or "publish"
        if action == "publish_export_artifact":
            return self._service.publish_export_artifact(
                PublishExportArtifactRequest(
                    artifact_revision_id=_required_string(payload, "artifact_revision_id"),
                    actor="web-shell",
                    output_root=Path(_required_string(payload, "output_root")).expanduser(),
                    source_surface="publish_surface",
                    fail_after_file_count=_optional_int(payload, "fail_after_file_count"),
                )
            )
        if action != "publish":
            raise ValueError(f"unsupported publish action: {action}")
        return self._service.publish_export(
            PublishExportRequest(
                project_id=project_id, novel_id=novel_id, actor="web-shell",
                output_root=Path(_required_string(payload, "output_root")).expanduser(),
                chapter_artifact_object_id=_optional_string(payload, "chapter_artifact_object_id"),
                base_chapter_artifact_revision_id=(
                    _optional_string(payload, "base_artifact_revision_id")
                    or _optional_string(payload, "base_chapter_artifact_revision_id")
                ),
                expected_source_scene_revision_id=_optional_string(payload, "expected_source_scene_revision_id"),
                export_object_id=_optional_string(payload, "export_object_id"),
                expected_import_source=_optional_string(payload, "expected_import_source") or "webnovel-writer",
                source_surface="publish_surface",
                source_ref="web-shell:/api/publish",
                fail_after_file_count=_optional_int(payload, "fail_after_file_count"),
            )
        )

    def _submit_provider(self, payload: Mapping[str, object]) -> dict[str, object]:
        action = _optional_string(payload, "action") or "save"
        if action == "save":
            provider_id = self._service.save_provider_config(
                provider_name=_required_string(payload, "provider_name"),
                base_url=_required_string(payload, "base_url"),
                api_key=_required_string(payload, "api_key"),
                model_name=_required_string(payload, "model_name"),
                temperature=_float_from_value(payload.get("temperature"), default=0.7),
                max_tokens=_int_from_value(payload.get("max_tokens"), default=4096),
                is_active=_bool_from_value(payload.get("is_active"), default=False),
                created_by="web-shell",
            )
            return {"action": "save", "provider_id": provider_id,
                    "providers": self._sanitize_providers(self._service.list_provider_configs())}
        provider_id = _required_string(payload, "provider_id")
        if action == "activate":
            if not self._service.set_active_provider(provider_id):
                raise KeyError(provider_id)
            return {"action": "activate", "provider_id": provider_id,
                    "providers": self._sanitize_providers(self._service.list_provider_configs())}
        if action == "delete":
            if not self._service.delete_provider_config(provider_id):
                raise KeyError(provider_id)
            return {"action": "delete", "provider_id": provider_id,
                    "providers": self._sanitize_providers(self._service.list_provider_configs())}
        if action == "test":
            return {"action": "test", "provider_id": provider_id,
                    "test_result": self._service.test_provider_config(provider_id)}
        raise ValueError(f"unsupported provider action: {action}")

    # -- snapshot builders ----------------------------------------------------

    def _build_startup_snapshot(self) -> dict[str, object]:
        contexts = self._service.list_workspace_contexts()
        return {"workspace_contexts": _serialize_json(contexts), "has_workspace_contexts": bool(contexts)}

    def _build_workbench_snapshot(self, *, project_id: str, novel_id: str) -> dict[str, object]:
        workspace = self._service.get_workspace_snapshot(WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id))
        chapter_artifacts = self._filter_artifacts(self._service.list_derived_artifacts("chapter_artifact"), novel_id=novel_id)
        return {
            "project_id": project_id, "novel_id": novel_id,
            "canonical_objects": _serialize_json(workspace.canonical_objects),
            "chapter_artifacts": _serialize_json(chapter_artifacts),
            "chapter_review_proposals": [],
        }

    _PIPELINE_FAMILIES: ClassVar[dict[str, tuple[str, str]]] = {
        "outline_to_plot": ("outline_node", "plot_node"),
        "plot_to_event": ("plot_node", "event"),
        "event_to_scene": ("event", "scene"),
        "scene_to_chapter": ("scene", "chapter_artifact"),
    }

    def _build_pipeline_snapshot(self, *, project_id: str, novel_id: str, link_type: str) -> dict[str, object]:
        source_family, target_family = self._PIPELINE_FAMILIES[link_type]
        workspace = self._service.get_workspace_snapshot(WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id))
        source_objects = [o for o in workspace.canonical_objects if o.family == source_family]
        if target_family == "chapter_artifact":
            target_objects = self._filter_artifacts(self._service.list_derived_artifacts("chapter_artifact"), novel_id=novel_id)
        else:
            target_objects = [o for o in workspace.canonical_objects if o.family == target_family]
        return {
            "pipeline_stage": link_type,
            "source_family": source_family,
            "target_family": target_family,
            "source_objects": _serialize_json(source_objects),
            "target_objects": _serialize_json(target_objects),
            "upstream_ready": len(source_objects) > 0,
        }

    def _build_publish_snapshot(self, *, project_id: str, novel_id: str) -> dict[str, object]:
        return {
            "project_id": project_id, "novel_id": novel_id,
            "chapter_artifacts": _serialize_json(
                self._filter_artifacts(self._service.list_derived_artifacts("chapter_artifact"), novel_id=novel_id)
            ),
            "export_artifacts": _serialize_json(
                self._filter_artifacts(self._service.list_derived_artifacts("export_artifact"), novel_id=novel_id)
            ),
        }

    def _build_provider_settings_snapshot(self) -> dict[str, object]:
        providers = self._sanitize_providers(self._service.list_provider_configs())
        active = next((p for p in providers if p.get("is_active") is True), None)
        return {"providers": providers, "active_provider": active}

    def _sanitize_providers(self, providers: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
        sanitized: list[dict[str, object]] = []
        for provider in providers:
            d = dict(provider)
            if "api_key" in d and isinstance(d["api_key"], str):
                key = cast(str, d["api_key"])
                d["api_key_masked"] = f"{key[:2]}{'*' * max(4, len(key) - 4)}{key[-2:]}" if len(key) > 4 else "*" * len(key)
                del d["api_key"]
            sanitized.append(d)
        return sanitized

    # -- signal/action/audit builders ----------------------------------------

    def _build_blocked_signals(
        self, *, project: WorkspaceObjectSummary | None, novel: WorkspaceObjectSummary | None,
    ) -> tuple[CommandCenterSignal, ...]:
        signals: list[CommandCenterSignal] = []
        if project is None:
            signals.append(CommandCenterSignal(kind="blocked", title="项目上下文缺失",
                detail="总控台在规范项目存在之前无法派发下游工作。", route_id="command-center"))
        if novel is None:
            signals.append(CommandCenterSignal(kind="blocked", title="小说范围未选择",
                detail="工作台、审核和技能路由依赖于规范小说上下文。", route_id="command-center"))
        return tuple(signals)

    def _build_stale_signals(
        self, *, outlines: list[WorkspaceObjectSummary], plots: list[WorkspaceObjectSummary],
        events: list[WorkspaceObjectSummary], scenes: list[WorkspaceObjectSummary],
        scenes_without_chapters: list[WorkspaceObjectSummary], skills: list[WorkspaceObjectSummary],
    ) -> tuple[CommandCenterSignal, ...]:
        signals: list[CommandCenterSignal] = []
        if outlines and not plots:
            signals.append(CommandCenterSignal(kind="stale", title="大纲尚未推进到剧情节点",
                detail="书籍已有结构种子，但尚无剧情层扩展可见。", route_id="wb-outline"))
        if plots and not events:
            signals.append(CommandCenterSignal(kind="stale", title="剧情节点正在等待事件拆解",
                detail="叙事线在上游已存在，但事件级执行尚未跟上。", route_id="wb-plot"))
        if events and not scenes:
            signals.append(CommandCenterSignal(kind="stale", title="事件存在但场景未执行",
                detail="流水线正在承载事件真相，但场景载荷尚未生成。", route_id="wb-event"))
        if scenes_without_chapters:
            lead = scenes_without_chapters[0]
            lead_title = self._payload_text(lead.payload, "title") or lead.object_id
            signals.append(CommandCenterSignal(kind="stale", title="场景正在等待成为章节",
                detail=f"{len(scenes_without_chapters)} 个场景缺少章节制品；下一个是 {lead_title}。", route_id="wb-scene"))
        if scenes and not skills:
            signals.append(CommandCenterSignal(kind="stale", title="叙事工作正在无技能指导下进行",
                detail="总控台可以看到场景进展，但没有规范技能对象附加以塑造后续处理。", route_id="skills"))
        return tuple(signals)

    def _build_routes(
        self, *, project_id: str, novel_id: str | None,
        outlines: list[WorkspaceObjectSummary], plots: list[WorkspaceObjectSummary],
        events: list[WorkspaceObjectSummary], scenes: list[WorkspaceObjectSummary],
        scenes_without_chapters: list[WorkspaceObjectSummary],
        review_queue_count: int, skills_count: int,
        chapter_artifact_count: int, export_artifact_count: int,
    ) -> tuple[CommandCenterRoute, ...]:
        query = self._route_query(project_id=project_id, novel_id=novel_id)
        return (
            CommandCenterRoute(route_id="wb-outline", label="大纲→剧情", href=f"/workbench/outline-to-plot{query}",
                description="将大纲节点扩展为剧情结构。",
                readiness=f"{len(outlines)} 个大纲节点就绪" if outlines else "尚无大纲"),
            CommandCenterRoute(route_id="wb-plot", label="剧情→事件", href=f"/workbench/plot-to-event{query}",
                description="将剧情节点分解为具体事件。",
                readiness=f"{len(plots)} 个剧情节点" if plots else "尚无剧情节点"),
            CommandCenterRoute(route_id="wb-event", label="事件→场景", href=f"/workbench/event-to-scene{query}",
                description="将事件展开为详细场景。",
                readiness=f"{len(events)} 个事件" if events else "尚无事件"),
            CommandCenterRoute(route_id="wb-scene", label="场景→章节", href=f"/workbench/scene-to-chapter{query}",
                description="将场景写成章节正文。",
                readiness=f"{len(scenes_without_chapters)} 个场景排队" if scenes_without_chapters else "无排队场景"),
            CommandCenterRoute(route_id="review-desk", label="审核台", href=f"/review-desk{query}",
                description="通过服务层拥有的审批流程解决需要审核的提案。",
                readiness=f"{review_queue_count} 个提案等待中" if review_queue_count else "队列清空"),
            CommandCenterRoute(route_id="skills", label="技能工坊", href=f"/skills{query}",
                description="调整影响后续生产界面的作者控制技能。",
                readiness=f"{skills_count} 个技能已附加" if skills_count else "尚未附加技能"),
            CommandCenterRoute(route_id="publish", label="发布导出", href=f"/publish{query}",
                description="从已批准的规范和章节谱系投影显式导出包。",
                readiness=f"{chapter_artifact_count} 个章节制品就绪 · {export_artifact_count} 个导出制品已记录"
                    if chapter_artifact_count else "尚无章节制品就绪"),
        )

    def _build_next_actions(
        self, *, routes: tuple[CommandCenterRoute, ...],
        blocked_signals: tuple[CommandCenterSignal, ...],
        stale_signals: tuple[CommandCenterSignal, ...],
        scenes_without_chapters: list[WorkspaceObjectSummary],
        skills: list[WorkspaceObjectSummary],
        chapter_artifacts: tuple[DerivedArtifactSnapshot, ...],
        export_artifacts: tuple[DerivedArtifactSnapshot, ...],
    ) -> tuple[NextAction, ...]:
        route_by_id = {r.route_id: r for r in routes}
        actions: list[NextAction] = []
        if scenes_without_chapters and "wb-scene" in route_by_id:
            scene = scenes_without_chapters[0]
            scene_title = self._payload_text(scene.payload, "title") or scene.object_id
            actions.append(NextAction(
                priority="high" if not blocked_signals else "medium",
                title="将下一个场景推进为章节制品",
                reason=f"{scene_title} 已是结构化真相，因此工作台是散文生产的正确下游界面。",
                route_id="wb-scene"))
        if not skills and "skills" in route_by_id:
            actions.append(NextAction(priority="medium",
                title="附加至少一个规范技能",
                reason="外壳可以在没有技能的情况下路由生产，但作者控制规则在可见工作区状态中仍然缺失。",
                route_id="skills"))
        if (chapter_artifacts and "publish" in route_by_id
                and len(export_artifacts) < len(chapter_artifacts)):
            actions.append(NextAction(priority="medium",
                title="将最新批准的章节投影为导出包",
                reason="章节散文已在下游派生并批准，因此发布应仅从该谱系中具象化显式文件系统投影。",
                route_id="publish"))
        if not actions:
            fallback_route = "wb-outline"
            actions.append(NextAction(priority="medium", title="从外壳的活动界面继续",
                reason="审核队列已清空且章节覆盖已更新；从生产工作台继续。",
                route_id=fallback_route))
        if stale_signals and len(actions) < 3:
            seen = {a.route_id for a in actions}
            for signal in stale_signals:
                if signal.route_id in seen or signal.route_id == "command-center":
                    continue
                actions.append(NextAction(priority="medium", title=signal.title,
                    reason=signal.detail, route_id=signal.route_id))
                seen.add(signal.route_id)
                if len(actions) >= 3:
                    break
        return tuple(actions)

    def _build_audit_entries(self, objects: Iterable[WorkspaceObjectSummary]) -> tuple[CommandCenterAuditEntry, ...]:
        entries: list[CommandCenterAuditEntry] = []
        for summary in objects:
            result = self._service.read_object(
                ReadObjectRequest(family=summary.family, object_id=summary.object_id, include_mutations=True))
            if not result.mutations:
                continue
            latest = result.mutations[-1]
            entries.append(CommandCenterAuditEntry(
                target_family=latest.target_object_family,
                target_object_id=latest.target_object_id,
                revision_id=latest.result_revision_id,
                revision_number=latest.resulting_revision_number,
                policy_class=latest.policy_class,
                approval_state=latest.approval_state,
                source_surface=latest.source_surface,
                skill_name=latest.skill_name,
                diff_excerpt=self._diff_excerpt(latest.diff_payload),
            ))
        entries.sort(key=lambda e: (e.revision_number, e.target_family, e.target_object_id), reverse=True)
        return tuple(entries[:8])

    def _stage_summary(
        self, *, novel: WorkspaceObjectSummary | None, scenes: list[WorkspaceObjectSummary],
        chapter_artifacts: tuple[DerivedArtifactSnapshot, ...],
        export_artifacts: tuple[DerivedArtifactSnapshot, ...],
        scenes_without_chapters: list[WorkspaceObjectSummary],
    ) -> tuple[str, str]:
        if novel is None:
            return "项目接入", "规范项目数据已存在，但外壳仍需要一个活动小说才能派发生产工作。"
        if not scenes:
            return "结构引导", "小说已注册，但场景级真相尚未建立。"
        if scenes_without_chapters:
            return "场景积压", f"{len(chapter_artifacts)} 个章节制品已存在，但 {len(scenes_without_chapters)} 个场景仍需下游散文工作。"
        if chapter_artifacts and len(export_artifacts) < len(chapter_artifacts):
            return "发布就绪", f"{len(chapter_artifacts)} 个章节制品可用，目前已投影 {len(export_artifacts)} 个导出制品。"
        return "外壳运转正常", "规范场景、章节制品和审核队列已足够对齐，总控台可以作为清晰的调度器运作。"

    # -- utility methods ------------------------------------------------------

    def _filter_artifacts(
        self, artifacts: tuple[DerivedArtifactSnapshot, ...], *, novel_id: str | None,
    ) -> tuple[DerivedArtifactSnapshot, ...]:
        if novel_id is None:
            return artifacts
        return tuple(a for a in artifacts if a.payload.get("novel_id") == novel_id)

    def _first_family(
        self, objects: Iterable[WorkspaceObjectSummary], family: str, object_id: str | None,
    ) -> WorkspaceObjectSummary | None:
        matches = [s for s in objects if s.family == family]
        if object_id is not None:
            for s in matches:
                if s.object_id == object_id:
                    return s
        return matches[0] if matches else None

    def _payload_text(self, payload: Mapping[str, object], key: str) -> str:
        value = payload.get(key)
        return value.strip() if isinstance(value, str) else ""

    def _diff_excerpt(self, payload: Mapping[str, object]) -> str:
        for key in ("title", "chapter_title", "summary", "body", "reason", "note"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                compact = " ".join(value.split())
                return compact[:140] + ("\u2026" if len(compact) > 140 else "")
        visible = ", ".join(sorted(payload.keys())[:5])
        return f"Diff fields: {visible}" if visible else json.dumps(payload, ensure_ascii=False)[:140]

    def _route_query(self, *, project_id: str, novel_id: str | None) -> str:
        parts = [f"project_id={project_id}"]
        if novel_id:
            parts.append(f"novel_id={novel_id}")
        return "?" + "&".join(parts)


# ---------------------------------------------------------------------------
# WSGI application — serves SPA static files + dispatches API requests
# ---------------------------------------------------------------------------

class SuperwriterWSGIApp:
    __slots__ = ("_api", "_frontend", "_pipeline", "_watcher")

    def __init__(
        self,
        service: SuperwriterApplicationService,
        *,
        frontend_dist_dir: Path | None = None,
        nodes_root: Path | None = None,
    ):
        self._api = SuperwriterAPIApp(service)
        repo_root = Path(__file__).resolve().parents[2]
        dist_dir = (frontend_dist_dir or (repo_root / "apps" / "frontend" / "dist")).resolve()
        self._frontend = FrontendRuntimeConfig(dist_dir=dist_dir)
        _nodes_root = nodes_root or (repo_root / ".superwriter")
        file_store = FileStore(_nodes_root)
        self._watcher = FileWatcher(file_store)
        self._watcher.start()
        self._pipeline = PipelineAPI(file_store, service._get_active_ai_provider, self._watcher)

    def __call__(
        self,
        environ: Mapping[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> Iterable[bytes]:
        try:
            return self._handle_request(environ, start_response)
        except Exception as error:
            response = _json_error("internal_error", _error_message(error), status_code=500)
            return self._respond(response, start_response)

    def _handle_request(
        self,
        environ: Mapping[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> Iterable[bytes]:
        path = str(environ.get("PATH_INFO", "/") or "/")
        method = str(environ.get("REQUEST_METHOD", "GET") or "GET").upper()
        query = parse_qs(str(environ.get("QUERY_STRING", "") or ""))
        project_id = self._query_value(query, "project_id")
        novel_id = self._query_value(query, "novel_id")

        # 1. Try static asset from frontend dist
        if method == "GET" and not path.startswith("/api/"):
            asset = self._serve_asset(path)
            if asset is not None:
                return self._respond(asset, start_response)

        # 2. API routes — SSE must bypass normal response path
        if path.startswith("/api/"):
            if path == "/api/pipeline/events" and method == "GET":
                return self._sse_response(start_response)
            response = self._dispatch_api(path=path, method=method, query=query,
                                          project_id=project_id, novel_id=novel_id, environ=environ)
            return self._respond(response, start_response)

        # 3. SPA fallback — serve index.html for all non-API GET requests
        if method == "GET" and self._has_dist():
            index = self._serve_index()
            if index is not None:
                return self._respond(index, start_response)

        # 4. Nothing matched
        response = _json_error("not_found", f"No route for {method} {path}", status_code=404)
        return self._respond(response, start_response)

    def _dispatch_api(
        self, *, path: str, method: str, query: Mapping[str, list[str]],
        project_id: str | None, novel_id: str | None, environ: Mapping[str, object],
    ) -> ApiResponse:
        query_payload = {key: self._query_value(query, key) or "" for key in query}
        try:
            request_payload = self._parse_body(environ)
        except Exception as error:
            return _json_error("invalid_input", _error_message(error), status_code=400)

        # Pipeline file-system API
        if path.startswith("/api/pipeline/"):
            path_parts = path[len("/api/pipeline/"):].strip("/").split("/")

            try:
                result = self._pipeline.handle(method, path_parts, dict(request_payload), query_payload)
                if "error" in result:
                    return _json_error(str(result["error"]), str(result.get("message", "")), status_code=404)
                return _json_ok(result)
            except Exception as error:
                return _json_error("pipeline_error", _error_message(error), status_code=500)

        return self._api.handle_request(
            path=path, method=method, project_id=project_id, novel_id=novel_id,
            query=query_payload, payload=request_payload,
        )

    def _sse_response(self, start_response: Callable[[str, list[tuple[str, str]]], object]) -> Iterable[bytes]:
        start_response("200 OK", [
            ("Content-Type", "text/event-stream; charset=utf-8"),
            ("Cache-Control", "no-cache"),
            ("X-Accel-Buffering", "no"),
        ])
        return self._pipeline.sse_events()

    def _respond(self, response: ApiResponse, start_response: Callable[[str, list[tuple[str, str]]], object]) -> Iterable[bytes]:
        reason = {200: "OK", 201: "Created", 400: "Bad Request", 404: "Not Found",
                  405: "Method Not Allowed", 409: "Conflict", 500: "Internal Server Error",
                  502: "Bad Gateway", 503: "Service Unavailable"}.get(response.status_code, "Response")
        start_response(f"{response.status_code} {reason}", [
            ("Content-Type", response.content_type),
            ("Connection", "close"),
        ])
        return [response.body]

    # -- static file serving -------------------------------------------------

    def _has_dist(self) -> bool:
        return (self._frontend.dist_dir / "index.html").is_file()

    def _serve_index(self) -> ApiResponse | None:
        index_path = self._frontend.dist_dir / "index.html"
        if not index_path.is_file():
            return None
        return ApiResponse(status_code=200, body=index_path.read_bytes(),
                           content_type="text/html; charset=utf-8")

    def _serve_asset(self, path: str) -> ApiResponse | None:
        if not self._has_dist():
            return None
        normalized = path.rstrip("/") or "/"
        if normalized in {"/", "/api/"} or path.startswith("/api/"):
            return None
        parts = [p for p in Path(path.lstrip("/")).parts if p not in {".", ""}]
        if not parts or ".." in parts:
            return None
        candidate = self._frontend.dist_dir.joinpath(*parts).resolve()
        if candidate == self._frontend.dist_dir or self._frontend.dist_dir not in candidate.parents:
            return None
        if not candidate.is_file():
            return None
        content_type, _ = mimetypes.guess_type(str(candidate))
        if content_type is None:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript", "application/json", "image/svg+xml",
        }:
            content_type = f"{content_type}; charset=utf-8"
        return ApiResponse(status_code=200, body=candidate.read_bytes(), content_type=content_type)

    # -- request parsing -----------------------------------------------------

    def _parse_body(self, environ: Mapping[str, object]) -> dict[str, object]:
        raw_input = environ.get("wsgi.input")
        if raw_input is None:
            return {}
        length_raw = str(environ.get("CONTENT_LENGTH", "") or "").strip()
        try:
            content_length = int(length_raw) if length_raw else 0
        except ValueError:
            content_length = 0
        if content_length <= 0 or not isinstance(raw_input, _RequestBodyReader):
            return {}
        body = raw_input.read(content_length)
        raw_body = body.decode("utf-8") if isinstance(body, bytes) else str(body)
        if not raw_body.strip():
            return {}
        content_type = str(environ.get("CONTENT_TYPE", "") or "").split(";", 1)[0].strip().lower()
        if content_type == "application/json" or raw_body.lstrip().startswith("{"):
            decoded = json.loads(raw_body)
            if not isinstance(decoded, dict):
                raise ValueError("request body must be a JSON object")
            return cast(dict[str, object], decoded)
        form = parse_qs(raw_body)
        return {key: self._query_value(form, key) or "" for key in form}

    @staticmethod
    def _query_value(query: Mapping[str, list[str]], key: str) -> str | None:
        values = query.get(key) or []
        for v in values:
            stripped = v.strip()
            if stripped:
                return stripped
        return None
