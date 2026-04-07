from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

JSONObject = dict[str, Any]
MessageList = list[dict[str, str]]

# Pre-compiled regex patterns for entity extraction
_ENTITY_PATTERNS = [
    (re.compile(r'(?:scene|scn|场景)[\s_-]*([a-zA-Z0-9_]+)', re.IGNORECASE), 'scene_id'),
    (re.compile(r'(?:outline|out|大纲)[\s_-]*([a-zA-Z0-9_]+)', re.IGNORECASE), 'outline_id'),
    (re.compile(r'(?:novel|nvl|小说)[\s_-]*([a-zA-Z0-9_]+)', re.IGNORECASE), 'novel_id'),
    (re.compile(r'(?:project|prj|项目)[\s_-]*([a-zA-Z0-9_]+)', re.IGNORECASE), 'project_id'),
]

class DialogueIntent(str, Enum):
    """Intent classifications for user dialogue messages."""

    # Workbench operations
    OUTLINE_TO_PLOT = "outline_to_plot"
    PLOT_TO_EVENT = "plot_to_event"
    EVENT_TO_SCENE = "event_to_scene"
    SCENE_TO_CHAPTER = "scene_to_chapter"

    # Review operations
    REVIEW_PROPOSALS = "review_proposals"
    APPROVE_PROPOSAL = "approve_proposal"
    REJECT_PROPOSAL = "reject_proposal"

    # Query operations
    LIST_OBJECTS = "list_objects"
    SHOW_OBJECT = "show_object"
    SEARCH = "search"

    # Skill operations
    LIST_SKILLS = "list_skills"
    CREATE_SKILL = "create_skill"

    # General
    CHAT = "chat"
    HELP = "help"
    UNKNOWN = "unknown"


_VALID_INTENT_VALUES = frozenset(e.value for e in DialogueIntent)


class DialogueState(str, Enum):
    """States of the dialogue state machine."""

    IDLE = "idle"
    AWAITING_CONTEXT = "awaiting_context"
    PROCESSING = "processing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"


# Valid state transitions
_VALID_TRANSITIONS: dict[DialogueState, frozenset[DialogueState]] = {
    DialogueState.IDLE: frozenset({DialogueState.AWAITING_CONTEXT}),
    DialogueState.AWAITING_CONTEXT: frozenset({DialogueState.PROCESSING, DialogueState.IDLE}),
    DialogueState.PROCESSING: frozenset({DialogueState.AWAITING_CONFIRMATION, DialogueState.COMPLETED, DialogueState.IDLE}),
    DialogueState.AWAITING_CONFIRMATION: frozenset({DialogueState.COMPLETED, DialogueState.PROCESSING, DialogueState.IDLE}),
    DialogueState.COMPLETED: frozenset({DialogueState.IDLE}),
}


class DialogueStateMachine:
    """
    Tracks dialogue state per session.

    Manages state transitions for multi-turn dialogue flows,
    ensuring valid progression through the dialogue lifecycle.
    """

    def __init__(self) -> None:
        self._states: dict[str, DialogueState] = {}

    def get_state(self, session_id: str) -> DialogueState:
        """Get the current state for a session."""
        return self._states.get(session_id, DialogueState.IDLE)

    def transition(self, session_id: str, target: DialogueState) -> DialogueState:
        """
        Attempt a state transition.

        Args:
            session_id: The session to transition
            target: The target state

        Returns:
            The new state after transition

        Raises:
            ValueError: If the transition is invalid
        """
        current = self.get_state(session_id)
        valid_targets = _VALID_TRANSITIONS.get(current, frozenset())

        if target not in valid_targets:
            # Allow reset to IDLE from any state
            if target == DialogueState.IDLE:
                self._states[session_id] = DialogueState.IDLE
                return DialogueState.IDLE
            raise ValueError(
                f"Invalid transition from {current.value} to {target.value}"
            )

        self._states[session_id] = target
        return target

    def reset(self, session_id: str) -> DialogueState:
        """Reset a session to IDLE state."""
        self._states[session_id] = DialogueState.IDLE
        return DialogueState.IDLE

    def is_idle(self, session_id: str) -> bool:
        """Check if a session is in IDLE state."""
        return self.get_state(session_id) == DialogueState.IDLE


@dataclass(frozen=True, slots=True)
class DialogueRequest:
    """Request to process a dialogue turn."""

    session_id: str
    user_message: str
    project_id: str
    novel_id: str | None
    actor: str = "user"


@dataclass(frozen=True, slots=True)
class DialogueResponse:
    """Response from processing a dialogue turn."""

    response_text: str
    intent: DialogueIntent
    suggested_actions: list[JSONObject]
    mutations_proposed: list[JSONObject]
    context_provided: JSONObject


@dataclass(frozen=True, slots=True)
class IntentClassification:
    """Result of intent classification."""

    intent: DialogueIntent
    confidence: float
    extracted_params: JSONObject
    reasoning: str


class DialogueProcessor:
    """
    Process natural language dialogue and route to appropriate workbenches.

    This class provides the bridge between conversational input and the
    structured workbench operations of the Superwriter system.
    """

    def __init__(self, service: Any):  # SuperwriterApplicationService
        """Initialize with a reference to the application service."""
        self._service = service
        self._ai_client = service._get_active_ai_provider() if hasattr(service, "_get_active_ai_provider") else None
        self._state_machine = DialogueStateMachine()

    def process_turn(self, request: DialogueRequest) -> DialogueResponse:
        """
        Process a user's dialogue message and generate a response.

        Args:
            request: The dialogue request containing user message and context

        Returns:
            A response with AI-generated text and any suggested actions
        """
        # Transition state: idle → awaiting_context
        session_id = request.session_id
        current_state = self._state_machine.get_state(session_id)
        if current_state == DialogueState.IDLE:
            self._state_machine.transition(session_id, DialogueState.AWAITING_CONTEXT)

        # Classify the user's intent — use AI when available
        if self._ai_client is not None:
            context_for_ai = {
                "project_id": request.project_id,
                "novel_id": request.novel_id,
            }
            classification = self._classify_intent_with_ai(request.user_message, context_for_ai)
        else:
            classification = self._classify_intent(request.user_message, request.project_id, request.novel_id)

        # Transition: awaiting_context → processing
        self._state_machine.transition(session_id, DialogueState.PROCESSING)

        # Build context for the AI response
        context = self._build_dialogue_context(request, classification)

        # Generate response using AI if available
        if self._ai_client is not None:
            response_text = self._generate_ai_response(request, classification, context)
        else:
            response_text = self._generate_fallback_response(request, classification, context)

        # Determine suggested actions based on intent
        suggested_actions = self._determine_suggested_actions(classification, context)

        # Transition: processing → completed
        self._state_machine.transition(session_id, DialogueState.COMPLETED)
        # Reset back to idle for next turn
        self._state_machine.reset(session_id)

        return DialogueResponse(
            response_text=response_text,
            intent=classification.intent,
            suggested_actions=suggested_actions,
            mutations_proposed=[],
            context_provided=context,
        )

    def _classify_intent(
        self,
        message: str,
        project_id: str,
        novel_id: str | None,
    ) -> IntentClassification:
        """
        Classify the user's intent from their message.

        Uses simple keyword matching for MVP, can be enhanced with AI classification.
        """
        message_lower = message.lower()

        # Check for workbench operations
        if any(kw in message_lower for kw in ["大纲到剧情", "outline to plot", "展开大纲"]):
            return IntentClassification(
                intent=DialogueIntent.OUTLINE_TO_PLOT,
                confidence=0.8,
                extracted_params={},
                reasoning="User wants to expand outline into plot nodes",
            )

        if any(kw in message_lower for kw in ["剧情到事件", "plot to event", "展开剧情", "生成事件", "生成剧情"]):
            return IntentClassification(
                intent=DialogueIntent.PLOT_TO_EVENT,
                confidence=0.8,
                extracted_params={},
                reasoning="User wants to break down plot into events",
            )

        if any(kw in message_lower for kw in ["事件到场景", "event to scene", "展开事件", "生成场景"]):
            return IntentClassification(
                intent=DialogueIntent.EVENT_TO_SCENE,
                confidence=0.8,
                extracted_params={},
                reasoning="User wants to expand event into scenes",
            )

        if any(kw in message_lower for kw in ["场景到章节", "scene to chapter", "写章节", "生成章节", "写正文"]):
            return IntentClassification(
                intent=DialogueIntent.SCENE_TO_CHAPTER,
                confidence=0.8,
                extracted_params={},
                reasoning="User wants to write chapter from scene",
            )

        if any(kw in message_lower for kw in ["审核", "review", "待处理", "提议"]):
            return IntentClassification(
                intent=DialogueIntent.REVIEW_PROPOSALS,
                confidence=0.7,
                extracted_params={},
                reasoning="User wants to see review proposals",
            )

        # Check for skills before generic list/show (more specific pattern)
        if any(kw in message_lower for kw in ["技能", "skills", "风格"]):
            return IntentClassification(
                intent=DialogueIntent.LIST_SKILLS,
                confidence=0.7,
                extracted_params={},
                reasoning="User wants to see skills",
            )

        if any(kw in message_lower for kw in ["列出", "list", "显示", "show", "查看"]):
            return IntentClassification(
                intent=DialogueIntent.LIST_OBJECTS,
                confidence=0.6,
                extracted_params={},
                reasoning="User wants to list objects",
            )

        if any(kw in message_lower for kw in ["帮助", "help", "怎么用", "如何"]):
            return IntentClassification(
                intent=DialogueIntent.HELP,
                confidence=0.9,
                extracted_params={},
                reasoning="User is asking for help",
            )

        # Default to chat intent
        return IntentClassification(
            intent=DialogueIntent.CHAT,
            confidence=0.5,
            extracted_params={},
            reasoning="General chat, no specific intent detected",
        )

    def _build_dialogue_context(
        self,
        request: DialogueRequest,
        classification: IntentClassification,
    ) -> JSONObject:
        """Build context information for the dialogue response."""
        context: JSONObject = {
            "project_id": request.project_id,
            "novel_id": request.novel_id,
            "intent": classification.intent.value,
            "confidence": classification.confidence,
        }

        # Add workspace information
        try:
            workspace = self._service.get_workspace_snapshot(
                # type: ignore
                {
                    "project_id": request.project_id,
                    "novel_id": request.novel_id,
                }
            )

            # Count objects by family
            object_counts: dict[str, int] = {}
            for obj in workspace.canonical_objects:
                object_counts[obj.family] = object_counts.get(obj.family, 0) + 1

            context["workspace"] = {
                "canonical_count": len(workspace.canonical_objects),
                "derived_count": len(workspace.derived_artifacts),
                "proposal_count": len(workspace.review_proposals),
                "object_counts": object_counts,
            }
        except Exception:
            context["workspace"] = {"error": "Could not load workspace"}

        return context

    def _generate_ai_response(
        self,
        request: DialogueRequest,
        classification: IntentClassification,
        context: JSONObject,
    ) -> str:
        """Generate an AI response using the configured provider."""
        try:
            system_prompt = self._build_system_prompt(classification, context)
            user_prompt = self._build_user_prompt(request, classification, context)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            return self._ai_client.generate(messages=messages)  # type: ignore
        except Exception as e:
            return f"[AI generation error: {e}]"

    def _build_system_prompt(self, classification: IntentClassification, context: JSONObject) -> str:
        """Build the system prompt for AI response generation."""
        workspace_info = context.get("workspace", {})
        base_prompt = f"""You are Superwriter, an AI assistant for novel creation.

Current workspace context:
- Canonical objects: {workspace_info.get('canonical_count', 0)}
- Derived artifacts: {workspace_info.get('derived_count', 0)}
- Pending reviews: {workspace_info.get('proposal_count', 0)}

The user's intent appears to be: {classification.intent.value}

Provide helpful, concise responses. When appropriate, suggest next actions using the available workbenches:
- Outline → Plot: Expand outline nodes into plot structures
- Plot → Event: Break down plots into specific events
- Event → Scene: Create detailed scenes from events
- Scene → Chapter: Write prose chapters from scenes

Always be supportive of the author's creative process."""

        return base_prompt

    def _build_user_prompt(
        self,
        request: DialogueRequest,
        classification: IntentClassification,
        context: JSONObject,
    ) -> str:
        """Build the user prompt for AI response generation."""
        return f"""User message: {request.user_message}

Intent classification: {classification.intent.value} (confidence: {classification.confidence})
Reasoning: {classification.reasoning}

Please provide a helpful response."""

    def _generate_fallback_response(
        self,
        request: DialogueRequest,
        classification: IntentClassification,
        context: JSONObject,
    ) -> str:
        """Generate a fallback response when AI is not available."""
        intent_responses = {
            DialogueIntent.OUTLINE_TO_PLOT: "我可以帮你将大纲节点扩展为剧情结构。请提供要扩展的大纲节点 ID，或使用工作台界面进行操作。",
            DialogueIntent.PLOT_TO_EVENT: "我可以帮你将剧情节点分解为具体事件。请提供要分解的剧情节点 ID。",
            DialogueIntent.EVENT_TO_SCENE: "我可以帮你将事件展开为场景。请提供要展开的事件 ID。",
            DialogueIntent.SCENE_TO_CHAPTER: "我可以帮你将场景写成章节正文。请提供要写的场景 ID。",
            DialogueIntent.REVIEW_PROPOSALS: f"当前有 {context.get('workspace', {}).get('proposal_count', 0)} 个待审核的提议。请使用审核台查看详情。",
            DialogueIntent.LIST_OBJECTS: f"当前工作区有 {context.get('workspace', {}).get('canonical_count', 0)} 个规范对象。",
            DialogueIntent.LIST_SKILLS: "请使用技能工坊查看和管理当前技能。",
            DialogueIntent.HELP: "我可以帮助你:\n- 扩展大纲为剧情\n- 分解剧情为事件\n- 展开事件为场景\n- 写作章节正文\n- 查看审核提议\n\n请告诉我你想要做什么。",
            DialogueIntent.CHAT: f"你说: {request.user_message}\n\n(注意: AI 提供者未配置，高级对话功能不可用。请先在设置中配置 AI 提供者。)",
            DialogueIntent.UNKNOWN: "我不太确定你的意图。你可以说'帮助'来查看可用的操作。",
        }

        return intent_responses.get(
            classification.intent,
            "我理解了你的请求。请配置 AI 提供者以获得更好的对话体验。",
        )

    def _determine_suggested_actions(
        self,
        classification: IntentClassification,
        context: JSONObject,
    ) -> list[JSONObject]:
        """Determine suggested actions based on intent and context."""
        actions: list[JSONObject] = []

        workspace_info = context.get("workspace", {})

        match classification.intent:
            case DialogueIntent.OUTLINE_TO_PLOT:
                actions.append({
                    "label": "打开大纲→剧情工作台",
                    "route": "/workbench",
                    "description": "在工作台中选择大纲节点进行扩展",
                })
            case DialogueIntent.PLOT_TO_EVENT:
                actions.append({
                    "label": "打开剧情→事件工作台",
                    "route": "/workbench",
                    "description": "在工作台中选择剧情节点进行分解",
                })
            case DialogueIntent.EVENT_TO_SCENE:
                actions.append({
                    "label": "打开事件→场景工作台",
                    "route": "/workbench",
                    "description": "在工作台中选择事件进行展开",
                })
            case DialogueIntent.SCENE_TO_CHAPTER:
                actions.append({
                    "label": "打开场景→章节工作台",
                    "route": "/workbench",
                    "description": "在工作台中选择场景进行写作",
                })
            case DialogueIntent.REVIEW_PROPOSALS:
                if workspace_info.get("proposal_count", 0) > 0:
                    actions.append({
                        "label": "查看审核台",
                        "route": "/review-desk",
                        "description": f"有 {workspace_info['proposal_count']} 个待审核提议",
                    })
            case DialogueIntent.LIST_SKILLS:
                actions.append({
                    "label": "打开技能工坊",
                    "route": "/skills",
                    "description": "查看和管理技能配置",
                })

        # Always add settings action if AI is not configured
        if self._ai_client is None:
            actions.append({
                "label": "配置 AI 提供者",
                "route": "/settings",
                "description": "配置 OpenAI 兼容 API 以启用 AI 功能",
            })

        return actions

    def _classify_intent_with_ai(
        self,
        message: str,
        context: dict,
    ) -> IntentClassification:
        """
        Classify intent using AI for better accuracy.

        Uses the AI client to analyze the user message and determine
        their intent along with extracting relevant entities.

        Args:
            message: The user's message
            context: Dialogue context with workspace info

        Returns:
            IntentClassification with AI-determined intent and entities
        """
        if self._ai_client is None:
            # Fall back to keyword-based classification
            return self._classify_intent(
                message,
                context.get("project_id", ""),
                context.get("novel_id"),
            )

        # Build the classification prompt
        system_prompt = """You are an intent classifier for a novel creation system.

Classify the user's intent into one of the following categories:

- outline_to_plot: Expanding outline nodes into plot structures
- plot_to_event: Breaking down plot nodes into specific events
- event_to_scene: Creating detailed scenes from events
- scene_to_chapter: Writing prose chapters from scenes
- review_proposals: Reviewing and approving/rejecting proposals
- list_objects: Listing or showing objects
- list_skills: Managing skills and styles
- help: Requesting help or instructions
- chat: General conversational chat

Extract relevant entities from the message:
- Object IDs (e.g., scene_id, novel_id, project_id)
- Operations (e.g., "create", "edit", "delete", "list")
- Parameters (e.g., number, count, limit)

Return a JSON object with:
{
    "intent": "category_name",
    "confidence": 0.0-1.0,
    "entities": {...}
}
"""

        # Add context about the workspace
        workspace_info = context.get("workspace", {})
        context_str = ""
        if workspace_info:
            context_str = f"\nWorkspace has {workspace_info.get('canonical_count', 0)} canonical objects."
            if workspace_info.get("object_counts"):
                obj_counts = workspace_info["object_counts"]
                if obj_counts.get("scene", 0) > 0:
                    context_str += f" {obj_counts['scene']} scenes."
                if obj_counts.get("outline_node", 0) > 0:
                    context_str += f" {obj_counts['outline_node']} outline nodes."

        user_prompt = f"""Classify the intent for this user message:

"{message}"

{context_str}

Return only JSON, no explanations."""

        try:
            response = self._ai_client.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )

            # Parse the JSON response
            if isinstance(response, str):
                result = json.loads(response)
            else:
                result = response

            # Validate and return
            if isinstance(result, dict):
                intent_value = result.get("intent", "chat")
                confidence = float(result.get("confidence", 0.5))
                entities = result.get("entities", {})

                # Normalize intent value
                valid_intents = _VALID_INTENT_VALUES
                if intent_value not in valid_intents:
                    intent_value = "chat"

                return IntentClassification(
                    intent=DialogueIntent(intent_value) if intent_value in _VALID_INTENT_VALUES else DialogueIntent.CHAT,
                    confidence=max(0.0, min(1.0, confidence)),
                    extracted_params=entities,
                    reasoning="AI-classified intent",
                )

        except (json.JSONDecodeError, TypeError, ValueError) as e:
            # Fall back to keyword classification on error
            pass

        # Fallback to keyword classification
        return self._classify_intent(
            message,
            context.get("project_id", ""),
            context.get("novel_id"),
        )

    def extract_entities(
        self,
        message: str,
        context: dict,
    ) -> dict:
        """
        Extract entities from user message.

        Looks for object IDs, operations, and other relevant information
        that can be used to parameterize workbench operations.

        Args:
            message: The user's message
            context: Dialogue context with workspace info

        Returns:
            Dictionary of extracted entities
        """
        entities = {}
        message_lower = message.lower()

        # Extract object IDs using pre-compiled patterns
        for pattern, entity_type in _ENTITY_PATTERNS:
            match = pattern.search(message_lower)
            if match and match.groups():
                entities[entity_type] = match.group(1)

        # Extract operations
        operations = {
            "create": ["create", "创建", "新建", "add", "添加", "增加"],
            "edit": ["edit", "修改", "编辑", "revise", "修订"],
            "delete": ["delete", "删除", "remove", "移除"],
            "list": ["list", "列出", "显示", "show", "查看"],
        }

        for op, keywords in operations.items():
            if any(kw in message_lower for kw in keywords):
                entities["operation"] = op
                break

        return entities


__all__ = [
    "DialogueIntent",
    "DialogueRequest",
    "DialogueResponse",
    "DialogueProcessor",
    "DialogueState",
    "DialogueStateMachine",
    "extract_entities",
]
