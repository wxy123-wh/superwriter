"""Chat Service.

Manages chat sessions, message processing, and AI-driven content generation
through chat interactions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from core.ai.dialogue import DialogueIntent, DialogueProcessor, DialogueRequest as DialogueDialogueRequest
from core.ai.prompts import build_partial_revision_prompt
from core.runtime.storage import CanonicalStorage, ChatMessageLinkInput, ChatSessionInput
from core.runtime.mutation_policy import MutationPolicyEngine
from core.runtime.utils import _payload_text

if TYPE_CHECKING:
    from core.ai import AIProviderClient
    from core.runtime.services.ai_config_service import AIConfigService
    from core.runtime.types import (
        ChatSessionSnapshot,
        ChatTurnRequest,
        ChatTurnResult,
        GetChatSessionRequest,
        OpenChatSessionRequest,
        OpenChatSessionResult,
        ServiceMutationRequest,
        ServiceMutationResult,
        ReadObjectRequest,
        ReadObjectResult,
        OutlineToPlotWorkbenchRequest,
        OutlineToPlotWorkbenchResult,
        PlotToEventWorkbenchRequest,
        PlotToEventWorkbenchResult,
        EventToSceneWorkbenchRequest,
        EventToSceneWorkbenchResult,
        SceneToChapterWorkbenchRequest,
        SceneToChapterWorkbenchResult,
        ExportArtifactRequest,
        ExportArtifactResult,
        SkillExecutionRequest,
        SkillExecutionResult,
    )
    from core.runtime.storage import JSONObject


class ChatService:
    """Service for managing chat sessions and AI-driven dialogue."""

    def __init__(
        self,
        storage: CanonicalStorage,
        mutation_engine: MutationPolicyEngine,
        ai_config_service: "AIConfigService",
    ):
        """Initialize the chat service.

        Args:
            storage: The canonical storage instance.
            mutation_engine: The mutation policy engine.
            ai_config_service: The AI configuration service for provider access.
        """
        self.__storage = storage
        self.__mutation_engine = mutation_engine
        self.__ai_config_service = ai_config_service
        # Callbacks for delegating to application service
        self._apply_mutation_func: callable | None = None
        self._read_object_func: callable | None = None
        self._generate_outline_to_plot_func: callable | None = None
        self._generate_plot_to_event_func: callable | None = None
        self._generate_event_to_scene_func: callable | None = None
        self._generate_scene_to_chapter_func: callable | None = None
        self._create_export_artifact_func: callable | None = None
        self._execute_skill_func: callable | None = None

    def set_callbacks(
        self,
        *,
        apply_mutation_func: callable,
        read_object_func: callable,
        generate_outline_to_plot_func: callable,
        generate_plot_to_event_func: callable,
        generate_event_to_scene_func: callable,
        generate_scene_to_chapter_func: callable,
        create_export_artifact_func: callable,
        execute_skill_func: callable,
    ) -> None:
        """Set callback functions for delegating to application service."""
        self._apply_mutation_func = apply_mutation_func
        self._read_object_func = read_object_func
        self._generate_outline_to_plot_func = generate_outline_to_plot_func
        self._generate_plot_to_event_func = generate_plot_to_event_func
        self._generate_event_to_scene_func = generate_event_to_scene_func
        self._generate_scene_to_chapter_func = generate_scene_to_chapter_func
        self._create_export_artifact_func = create_export_artifact_func
        self._execute_skill_func = execute_skill_func

    def _get_active_ai_provider(self) -> "AIProviderClient | None":
        """Get the active AI provider client, or None if not configured."""
        return self.__ai_config_service.get_active_ai_provider()

    def _get_dialogue_processor(self) -> DialogueProcessor | None:
        """Get or create a dialogue processor instance."""
        try:
            # DialogueProcessor needs access to application service methods
            # We'll need to pass a reference or use callbacks
            return None  # Placeholder - needs proper initialization
        except Exception:
            return None

    def open_chat_session(self, request: "OpenChatSessionRequest") -> "OpenChatSessionResult":
        """Open a new chat session."""
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
        from core.runtime.types import OpenChatSessionResult
        return OpenChatSessionResult(
            session_id=session_id,
            project_id=request.project_id,
            novel_id=request.novel_id,
            title=request.title,
            runtime_origin=request.runtime_origin,
        )

    def get_chat_session(self, request: "GetChatSessionRequest") -> "ChatSessionSnapshot":
        """Get a chat session snapshot."""
        session_row = self.__storage.fetch_chat_session_row(request.session_id)
        if session_row is None:
            raise KeyError(request.session_id)
        message_rows = self.__storage.fetch_chat_message_link_rows(request.session_id)
        from core.runtime.types import ChatSessionSnapshot, ChatMessageSnapshot
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

    def process_chat_turn(self, request: "ChatTurnRequest") -> "ChatTurnResult":
        """Process a chat turn with user and assistant messages."""
        session_id = request.session_id
        if session_id is None:
            session_id = self.open_chat_session(
                self._build_open_chat_session_request(request)
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
            self._apply_mutation_func(
                self._build_service_mutation_request(mutation, request)
            )
            for mutation in request.mutation_requests
        ) if self._apply_mutation_func else ()

        export_results = tuple(
            self._create_export_artifact_func(export_request)
            for export_request in request.export_requests
        ) if self._create_export_artifact_func else ()

        skill_results = tuple(
            self._execute_skill_func(skill_request)
            for skill_request in request.skill_requests
        ) if self._execute_skill_func else ()

        chat_linked_object_id: str | None = None
        chat_linked_revision_id: str | None = None

        # Generate AI response if no explicit operations were requested
        assistant_payload: "JSONObject" = cast("JSONObject", dict(request.assistant_message.payload))
        if not mutation_results and not export_results and not skill_results:
            # Extract user message text
            user_text = _payload_text(request.user_message.payload, "content") or _payload_text(request.user_message.payload, "text") or ""
            if not user_text:
                user_text = str(request.user_message.payload.get("message", ""))

            if user_text:
                _intent = self.classify_chat_intent(user_text, request)
                if _intent == "edit_content":
                    generation_payload = self.apply_chat_edit(
                        request=request, user_instruction=user_text
                    )
                elif _intent is not None:
                    generation_payload = self.generate_downstream_content_from_chat(request=request)
                else:
                    generation_payload = None
                if generation_payload is not None:
                    assistant_payload, chat_linked_object_id, chat_linked_revision_id = generation_payload
                else:
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
                            assistant_payload = cast("JSONObject", {
                                "content": dialogue_response.response_text,
                                "intent": dialogue_response.intent.value,
                                "suggested_actions": dialogue_response.suggested_actions,
                            })
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
        elif chat_linked_object_id is not None and chat_linked_revision_id is not None:
            linked_object_id = chat_linked_object_id
            linked_revision_id = chat_linked_revision_id
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
        assistant_content = _payload_text(assistant_payload, "content") or _payload_text(assistant_payload, "text")
        from core.runtime.types import ChatTurnResult
        return ChatTurnResult(
            session_id=session_id,
            user_message_state_id=user_message_state_id,
            assistant_message_state_id=assistant_message_state_id,
            assistant_content=assistant_content,
            mutation_results=mutation_results,
            export_results=export_results,
            skill_results=skill_results,
        )

    def classify_chat_intent(self, user_text: str, request: "ChatTurnRequest") -> str | None:
        """Classify chat intent: 'edit_content', a workbench_type string, or None (fallback to dialogue)."""
        processor = self._get_dialogue_processor()
        if processor is None:
            return request.workbench_type if request.workbench_type else None
        classification = processor._classify_intent(user_text, request.project_id, request.novel_id)
        if classification.intent == DialogueIntent.EDIT_CONTENT:
            return "edit_content"
        _intent_to_workbench = {
            DialogueIntent.OUTLINE_TO_PLOT: "outline_to_plot",
            DialogueIntent.PLOT_TO_EVENT: "plot_to_event",
            DialogueIntent.EVENT_TO_SCENE: "event_to_scene",
            DialogueIntent.SCENE_TO_CHAPTER: "scene_to_chapter",
        }
        if classification.intent in _intent_to_workbench:
            return _intent_to_workbench[classification.intent]
        # For CHAT/UNKNOWN with a workbench_type set, default to generation
        if classification.intent in (DialogueIntent.CHAT, DialogueIntent.UNKNOWN):
            return request.workbench_type if request.workbench_type else None
        return None

    def apply_chat_edit(
        self,
        *,
        request: "ChatTurnRequest",
        user_instruction: str,
    ) -> "tuple[JSONObject, str, str] | None":
        """Apply an AI-driven content edit to the source object via chat."""
        if not request.source_object_id or not request.novel_id:
            return None
        ai_client = self._get_active_ai_provider()
        if ai_client is None:
            return None

        _family_map = {
            "outline_to_plot": "outline_node",
            "plot_to_event": "plot_node",
            "event_to_scene": "event",
            "scene_to_chapter": "scene",
        }
        target_family = _family_map.get(request.workbench_type or "", "outline_node")

        if not self._read_object_func:
            return None

        from core.runtime.types import ReadObjectRequest
        current = self._read_object_func(ReadObjectRequest(family=target_family, object_id=request.source_object_id))
        if current.head is None:
            return None
        current_payload = dict(current.head.payload)

        content_key = next(
            (k for k in ("content", "body", "summary", "description", "text") if k in current_payload),
            None,
        )
        section_content = str(current_payload.get(content_key or "summary", str(current_payload)))

        prompt_str = build_partial_revision_prompt(
            section_content=section_content,
            section_type=target_family,
            revision_instruction=user_instruction,
            context={"title": str(current_payload.get("title", ""))},
        )
        revised_text = ai_client.generate([{"role": "user", "content": prompt_str}])

        revised_payload = dict(current_payload)
        if content_key:
            revised_payload[content_key] = revised_text
        else:
            revised_payload["content"] = revised_text

        if not self._apply_mutation_func:
            return None

        from core.runtime.types import ServiceMutationRequest
        mutation_result = self._apply_mutation_func(
            ServiceMutationRequest(
                target_family=target_family,
                target_object_id=request.source_object_id,
                base_revision_id=request.source_revision_id or current.head.current_revision_id,
                payload=revised_payload,
                actor=request.created_by,
                source_surface="workbench_chat",
                source_ref=request.source_ref,
                revision_reason=f"Chat edit: {user_instruction[:80]}",
                revision_source_message_id=request.user_message.chat_message_id,
            )
        )

        object_id = mutation_result.target_object_id or request.source_object_id
        revision_id = mutation_result.canonical_revision_id or mutation_result.artifact_revision_id or ""
        return (
            {"content": f"已修改内容：{user_instruction[:50]}", "edited": True},
            object_id,
            revision_id,
        )

    def generate_downstream_content_from_chat(
        self,
        *,
        request: "ChatTurnRequest",
    ) -> "tuple[JSONObject, str, str] | None":
        """Generate downstream content based on chat context."""
        if request.novel_id is None or request.workbench_type is None or request.source_object_id is None:
            return None

        if request.workbench_type == "outline_to_plot":
            if not self._generate_outline_to_plot_func:
                return None
            from core.runtime.types import OutlineToPlotWorkbenchRequest
            result = self._generate_outline_to_plot_func(
                OutlineToPlotWorkbenchRequest(
                    project_id=request.project_id,
                    novel_id=request.novel_id,
                    outline_node_object_id=request.source_object_id,
                    actor=request.created_by,
                    expected_parent_revision_id=request.source_revision_id,
                    require_ai=True,
                    source_surface="workbench_chat",
                    source_ref=request.source_ref,
                )
            )
            plot_title = _payload_text(result.plot_payload, "title") or result.child_object_id or "剧情节点"
            return {"content": f"已生成下游剧情节点《{plot_title}》。", "generated": result.plot_payload}, result.child_object_id or "", result.child_revision_id or ""

        if request.workbench_type == "plot_to_event":
            if not self._generate_plot_to_event_func:
                return None
            from core.runtime.types import PlotToEventWorkbenchRequest
            result = self._generate_plot_to_event_func(
                PlotToEventWorkbenchRequest(
                    project_id=request.project_id,
                    novel_id=request.novel_id,
                    plot_node_object_id=request.source_object_id,
                    actor=request.created_by,
                    expected_parent_revision_id=request.source_revision_id,
                    require_ai=True,
                    source_surface="workbench_chat",
                    source_ref=request.source_ref,
                )
            )
            event_title = _payload_text(result.event_payload, "title") or result.child_object_id or "事件"
            return {"content": f"已生成下游事件《{event_title}》。", "generated": result.event_payload}, result.child_object_id or "", result.child_revision_id or ""

        if request.workbench_type == "event_to_scene":
            if not self._generate_event_to_scene_func:
                return None
            from core.runtime.types import EventToSceneWorkbenchRequest
            result = self._generate_event_to_scene_func(
                EventToSceneWorkbenchRequest(
                    project_id=request.project_id,
                    novel_id=request.novel_id,
                    event_object_id=request.source_object_id,
                    actor=request.created_by,
                    expected_parent_revision_id=request.source_revision_id,
                    require_ai=True,
                    source_surface="workbench_chat",
                    source_ref=request.source_ref,
                )
            )
            scene_title = _payload_text(result.scene_payload, "title") or result.child_object_id or "场景"
            return {"content": f"已生成下游场景《{scene_title}》。", "generated": result.scene_payload}, result.child_object_id or "", result.child_revision_id or ""

        if request.workbench_type == "scene_to_chapter":
            if not self._generate_scene_to_chapter_func:
                return None
            from core.runtime.types import SceneToChapterWorkbenchRequest
            result = self._generate_scene_to_chapter_func(
                SceneToChapterWorkbenchRequest(
                    project_id=request.project_id,
                    novel_id=request.novel_id,
                    scene_object_id=request.source_object_id,
                    actor=request.created_by,
                    expected_source_scene_revision_id=request.source_revision_id,
                    source_surface="workbench_chat",
                    source_ref=request.source_ref,
                )
            )
            chapter_title = _payload_text(result.chapter_payload, "chapter_title") or result.artifact_object_id or "章节"
            return {"content": f"已生成下游章节《{chapter_title}》。", "generated": result.chapter_payload}, result.artifact_object_id or "", result.artifact_revision_id or ""

        return None

    def _build_open_chat_session_request(self, request: "ChatTurnRequest") -> "OpenChatSessionRequest":
        """Build OpenChatSessionRequest from ChatTurnRequest."""
        from core.runtime.types import OpenChatSessionRequest
        return OpenChatSessionRequest(
            project_id=request.project_id,
            novel_id=request.novel_id,
            title=request.title,
            runtime_origin=request.runtime_origin,
            created_by=request.created_by,
            source_ref=request.source_ref,
        )

    def _build_service_mutation_request(self, mutation, request: "ChatTurnRequest") -> "ServiceMutationRequest":
        """Build ServiceMutationRequest from mutation and ChatTurnRequest."""
        from core.runtime.types import ServiceMutationRequest
        return ServiceMutationRequest(
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
