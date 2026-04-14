"""API-only WSGI server for SuperWriter SPA frontend.

Refactored to use 4 independent core services:
- AIConfigService (provider适配层)
- ChatService (chat对话台)
- SkillService (skill管理)
- RetrievalService (rag索引)
"""

from __future__ import annotations

import json
import mimetypes
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable
from urllib.parse import parse_qs

from core.ai import AIProviderClient
from core.runtime.mutation_policy import MutationPolicyEngine
from core.runtime.services.ai_config_service import AIConfigService
from core.runtime.services.chat_service import ChatService
from core.runtime.services.retrieval_service import RetrievalService
from core.runtime.services.skill_service import SkillService
from core.runtime.storage import CanonicalStorage, JSONValue
from core.runtime.types import (
    ChatMessageRequest,
    ChatTurnRequest,
    ChatTurnResult,
    GetChatSessionRequest,
    OpenChatSessionRequest,
    ReadObjectRequest,
    RetrievalRebuildRequest,
    RetrievalSearchRequest,
    ServiceMutationRequest,
    SkillWorkshopCompareRequest,
    SkillWorkshopImportRequest,
    SkillWorkshopRequest,
    SkillWorkshopRollbackRequest,
    SkillWorkshopUpsertRequest,
    WorkspaceObjectSummary,
    WorkspaceSnapshotRequest,
    WorkspaceSnapshotResult,
    CanonicalObjectSnapshot,
    ReadObjectResult,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

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
# SuperwriterAPIApp — API request handler
# ---------------------------------------------------------------------------

class SuperwriterAPIApp:
    __slots__ = (
        "_storage",
        "_ai_config_service",
        "_chat_service",
        "_skill_service",
        "_retrieval_service",
        "_mutation_engine",
    )

    def __init__(self, storage: CanonicalStorage):
        self._storage = storage
        self._mutation_engine = MutationPolicyEngine()

        # Initialize services
        self._ai_config_service = AIConfigService(storage)

        # ChatService needs mutation_engine and ai_config_service
        self._chat_service = ChatService(
            storage=storage,
            mutation_engine=self._mutation_engine,
            ai_config_service=self._ai_config_service,
        )

        self._skill_service = SkillService(
            storage=storage,
            mutation_engine=self._mutation_engine,
        )

        self._retrieval_service = RetrievalService(storage=storage)

    # -- service accessors for callbacks ---------------------------------

    def _get_active_ai_provider(self) -> AIProviderClient | None:
        return self._ai_config_service.get_active_ai_provider()

    def _get_workspace_snapshot(self, request: WorkspaceSnapshotRequest) -> WorkspaceSnapshotResult:
        """Get workspace snapshot - returns empty for now."""
        return WorkspaceSnapshotResult(canonical_objects=())

    def _read_object(self, request: ReadObjectRequest):
        """Read a canonical object - returns empty for now."""
        return ReadObjectResult(head=None, revisions=())

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
            # /api/skills - GET/POST (skill管理) -> SkillService
            if normalized_path == "/api/skills":
                pid = _require_project_id(project_id)
                nid = _require_novel_id(novel_id)
                if method == "GET":
                    result = self._skill_service.get_skill_workshop(
                        SkillWorkshopRequest(
                            project_id=pid,
                            novel_id=nid,
                            selected_skill_id=_string_or_none(query.get("selected_skill_id")),
                            left_revision_id=_string_or_none(query.get("left_revision_id")),
                            right_revision_id=_string_or_none(query.get("right_revision_id")),
                        ),
                        get_workspace_snapshot_func=self._get_workspace_snapshot,
                        compare_skill_versions_func=self._skill_service.compare_skill_versions,
                    )
                    return _json_ok({"workshop": _serialize_json(result)})
                _require_method(method, {"POST"})
                return _json_ok({"result": _serialize_json(self._submit_skill_workshop(novel_id=nid, payload=payload))})

            # /api/providers or /api/settings - GET/POST (provider配置) -> AIConfigService
            if normalized_path in {"/api/providers", "/api/settings"}:
                if method == "GET":
                    return _json_ok({"settings": self._build_provider_settings_snapshot()})
                _require_method(method, {"POST"})
                return _json_ok({"result": _serialize_json(self._submit_provider(payload))})

            # /api/chat - GET/POST (chat对话台) -> ChatService
            if normalized_path == "/api/chat":
                if method == "GET":
                    session_id = _optional_string(dict(query), "session_id")
                    if session_id:
                        session = self._chat_service.get_chat_session(
                            GetChatSessionRequest(session_id=session_id)
                        )
                        return _json_ok({"session": _serialize_json(session)})
                    return _json_ok({"sessions": []})
                _require_method(method, {"POST"})
                return _json_ok({"result": _serialize_json(self._submit_chat(payload))})

            # /api/rag/rebuild - POST (rag索引重建) -> RetrievalService
            if normalized_path == "/api/rag/rebuild":
                _require_method(method, {"POST"})
                pid = _require_project_id(project_id)
                result = self._retrieval_service.rebuild_retrieval_support(
                    RetrievalRebuildRequest(
                        project_id=pid,
                        actor=_optional_string(payload, "actor") or "web-shell",
                        novel_id=novel_id,
                    ),
                    workspace_canonical_objects=self._get_workspace_canonical_objects(pid, novel_id),
                    read_object_func=self._read_object,
                )
                return _json_ok({"result": _serialize_json(result)})

            # /api/rag/search - POST (rag搜索) -> RetrievalService
            if normalized_path == "/api/rag/search":
                _require_method(method, {"POST"})
                pid = _require_project_id(project_id)
                result = self._retrieval_service.search_retrieval_support(
                    RetrievalSearchRequest(
                        project_id=pid,
                        query=_required_string(payload, "query"),
                        novel_id=novel_id,
                        limit=_optional_int(payload, "limit") or 5,
                    ),
                    workspace_canonical_objects=self._get_workspace_canonical_objects(pid, novel_id),
                    read_object_func=self._read_object,
                )
                return _json_ok({"result": _serialize_json(result)})

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

    # -- skill handlers ------------------------------------------------------

    def _submit_skill_workshop(self, *, novel_id: str, payload: Mapping[str, object]) -> object:
        action = _required_string(payload, "action").lower()
        if action == "create":
            return self._skill_service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id, actor="web-shell", source_surface="skill_workshop_form",
                    name=_required_string(payload, "name"),
                    description=_string_value(payload.get("description", "")),
                    instruction=_required_string(payload, "instruction"),
                    style_scope=_optional_string(payload, "style_scope") or "scene_to_chapter",
                    is_active=_bool_from_value(payload.get("is_active"), default=True),
                    revision_reason="从 API 创建受约束技能",
                    source_ref="web-shell:/api/skills",
                ),
                read_object_func=self._read_object,
                apply_mutation_func=self._apply_mutation,
            )
        if action == "update":
            return self._skill_service.upsert_skill_workshop_skill(
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
                ),
                read_object_func=self._read_object,
                apply_mutation_func=self._apply_mutation,
            )
        if action == "toggle":
            return self._skill_service.upsert_skill_workshop_skill(
                SkillWorkshopUpsertRequest(
                    novel_id=novel_id, actor="web-shell", source_surface="skill_workshop_form",
                    skill_object_id=_required_string(payload, "skill_object_id"),
                    is_active=_bool_from_value(payload.get("is_active"), default=False),
                    base_revision_id=_optional_string(payload, "base_revision_id"),
                    revision_reason="从 API 切换受约束技能激活状态",
                    source_ref="web-shell:/api/skills",
                ),
                read_object_func=self._read_object,
                apply_mutation_func=self._apply_mutation,
            )
        if action == "rollback":
            return self._skill_service.rollback_skill_workshop_skill(
                SkillWorkshopRollbackRequest(
                    skill_object_id=_required_string(payload, "skill_object_id"),
                    target_revision_id=_required_string(payload, "target_revision_id"),
                    actor="web-shell", source_surface="skill_workshop_form",
                    revision_reason="从 API 回滚受约束技能",
                ),
                read_object_func=self._read_object,
                upsert_skill_workshop_skill_func=self._skill_service.upsert_skill_workshop_skill,
            )
        if action == "import":
            return self._skill_service.import_skill_workshop_skill(
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
                ),
                upsert_skill_workshop_skill_func=self._skill_service.upsert_skill_workshop_skill,
            )
        raise ValueError("unsupported skill workshop action")

    # -- chat handlers -------------------------------------------------------

    def _submit_chat(self, payload: Mapping[str, object]) -> ChatTurnResult:
        """Submit a chat turn request."""
        user_message = ChatMessageRequest(
            chat_message_id=_required_string(payload, "user_message_id"),
            chat_role="user",
            payload=dict(payload.get("user_message_payload", {})),
        )
        assistant_message = ChatMessageRequest(
            chat_message_id=_required_string(payload, "assistant_message_id"),
            chat_role="assistant",
            payload={},
        )
        request = ChatTurnRequest(
            project_id=_require_project_id(payload.get("project_id")),
            created_by=_optional_string(payload, "created_by") or "web-shell",
            runtime_origin="api",
            user_message=user_message,
            assistant_message=assistant_message,
            session_id=_optional_string(payload, "session_id"),
            novel_id=_optional_string(payload, "novel_id"),
            title=_optional_string(payload, "title"),
            source_ref="web-shell:/api/chat",
        )
        return self._chat_service.process_chat_turn(request)

    # -- provider handlers ---------------------------------------------------

    def _submit_provider(self, payload: Mapping[str, object]) -> dict[str, object]:
        action = _optional_string(payload, "action") or "save"
        if action == "save":
            provider_id = self._ai_config_service.save_provider_config(
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
                    "providers": self._sanitize_providers(self._ai_config_service.list_provider_configs())}
        provider_id = _required_string(payload, "provider_id")
        if action == "activate":
            if not self._ai_config_service.set_active_provider(provider_id):
                raise KeyError(provider_id)
            return {"action": "activate", "provider_id": provider_id,
                    "providers": self._sanitize_providers(self._ai_config_service.list_provider_configs())}
        if action == "delete":
            if not self._ai_config_service.delete_provider_config(provider_id):
                raise KeyError(provider_id)
            return {"action": "delete", "provider_id": provider_id,
                    "providers": self._sanitize_providers(self._ai_config_service.list_provider_configs())}
        if action == "test":
            return {"action": "test", "provider_id": provider_id,
                    "test_result": self._ai_config_service.test_provider_config(provider_id)}
        raise ValueError(f"unsupported provider action: {action}")

    # -- snapshot builders --------------------------------------------------

    def _build_provider_settings_snapshot(self) -> dict[str, object]:
        providers = self._sanitize_providers(self._ai_config_service.list_provider_configs())
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

    # -- helper methods -----------------------------------------------------

    def _get_workspace_canonical_objects(
        self, project_id: str, novel_id: str | None
    ) -> tuple[WorkspaceObjectSummary, ...]:
        """Get workspace canonical objects for retrieval operations."""
        workspace = self._get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        return workspace.canonical_objects

    def _apply_mutation(self, request: ServiceMutationRequest):
        """Apply a service mutation via storage.

        Note: Full mutation implementation requires canonical storage which is pending.
        This is a stub that raises an error indicating the feature is not yet available.
        """
        raise RuntimeError("Canonical mutation storage not yet implemented in this API server version")


# ---------------------------------------------------------------------------
# WSGI application — serves SPA static files + dispatches API requests
# ---------------------------------------------------------------------------

class SuperwriterWSGIApp:
    __slots__ = ("_api", "_frontend")

    def __init__(
        self,
        storage: CanonicalStorage,
        *,
        frontend_dist_dir: Path | None = None,
    ):
        self._api = SuperwriterAPIApp(storage)
        repo_root = Path(__file__).resolve().parents[2]
        dist_dir = (frontend_dist_dir or (repo_root / "apps" / "frontend" / "dist")).resolve()
        self._frontend = FrontendRuntimeConfig(dist_dir=dist_dir)

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

        # 2. API routes
        if path.startswith("/api/"):
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

        return self._api.handle_request(
            path=path, method=method, project_id=project_id, novel_id=novel_id,
            query=query_payload, payload=request_payload,
        )

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
