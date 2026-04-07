"""
Dialogue context management for multi-turn conversations.

This module provides the ability to maintain conversation context across
multiple dialogue turns, enabling the AI to remember previous exchanges,
track active objects, and provide more coherent responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias, cast

from core.ai.dialogue import DialogueIntent
from core.runtime.storage import JSONValue, utc_now_iso

JSONObject: TypeAlias = dict[str, JSONValue]


class ContextScope(str, Enum):
    """Scope of context relevance."""

    SESSION = "session"  # Relevant for the entire session
    RECENT = "recent"  # Recently used, may fade
    ACTIVE = "active"  # Currently active/primary


@dataclass(frozen=True, slots=True)
class DialogueTurnRecord:
    """A single turn in a dialogue conversation.

    Each turn represents one user message and the assistant's response,
    along with the classified intent and any extracted entities.
    """

    turn_id: str
    session_id: str
    user_message: str
    assistant_response: str
    intent: str  # DialogueIntent value
    extracted_entities: JSONObject
    timestamp: str
    context_scope: str = ContextScope.RECENT.value

    @property
    def intent_enum(self) -> DialogueIntent:
        """Get the intent as an enum."""
        return DialogueIntent(self.intent) if self.intent in DialogueIntent.__members__ else DialogueIntent.UNKNOWN


@dataclass(frozen=True, slots=True)
class DialogueContext:
    """Context for a dialogue session.

    Tracks the conversation history, current topic, active objects,
    and user preferences across multiple turns.
    """

    session_id: str
    turns: list[DialogueTurnRecord]
    current_topic: str | None
    active_objects: dict[str, str]  # {"scene": "scn_123", "novel": "nvl_456"}
    user_preferences: JSONObject
    started_at: str
    last_updated_at: str

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def is_empty(self) -> bool:
        return self.turn_count == 0

    def recent_turns(self, count: int = 5) -> list[DialogueTurnRecord]:
        """Get the most recent turns."""
        return self.turns[-count:] if self.turns else []

    @property
    def active_object_ids(self) -> list[str]:
        """Get list of active object IDs."""
        return list(self.active_objects.values())


@dataclass(frozen=True, slots=True)
class ContextUpdate:
    """An update to be applied to dialogue context."""

    topic: str | None = None
    active_objects: dict[str, str] | None = None
    user_preferences: JSONObject | None = None
    context_scope: str | None = None


class DialogueContextManager:
    """Manages dialogue context for multi-turn conversations.

    This class provides:
    - Loading and saving context
    - Adding conversation turns
    - Updating context based on conversation
    - Building context prompts for AI generation
    """

    def __init__(self, storage):
        """Initialize the context manager.

        Args:
            storage: CanonicalStorage instance for persistence
        """
        self._storage = storage

    def create_context(
        self,
        session_id: str,
        project_id: str,
        novel_id: str | None = None,
        actor: str = "user",
        runtime_origin: str = "dialogue",
    ) -> DialogueContext:
        """Create a new dialogue context.

        Args:
            session_id: Unique session identifier
            project_id: Project ID
            novel_id: Optional novel ID
            actor: User who created the session
            runtime_origin: Origin of the dialogue

        Returns:
            New DialogueContext instance
        """
        from core.runtime.storage import ChatSessionInput

        timestamp = utc_now_iso()

        # Create chat session for tracking
        # Note: We use the session_id as the chat session_state_id
        # In a full implementation, these might be separate
        # For now, we'll skip creating a chat session to avoid the complexity
        # and just create the DialogueContext directly

        return DialogueContext(
            session_id=session_id,
            turns=[],
            current_topic=None,
            active_objects={},
            user_preferences={},
            started_at=timestamp,
            last_updated_at=timestamp,
        )

    def load_context(self, session_id: str) -> DialogueContext | None:
        """Load dialogue context from storage.

        Args:
            session_id: Session ID to load

        Returns:
            DialogueContext if found, None otherwise
        """
        # Load chat session
        chat_session = self._storage.fetch_chat_session_row(session_id)
        if chat_session is None:
            return None

        # Load message links
        message_rows = self._storage.fetch_chat_message_link_rows(session_id)

        # Build turn records (single pass: pair each user message with next assistant message)
        turns = []
        i = 0
        while i < len(message_rows):
            msg_row = message_rows[i]
            if msg_row.chat_role == "user":
                assistant_response = ""
                if i + 1 < len(message_rows) and message_rows[i + 1].chat_role == "assistant":
                    assistant_response = message_rows[i + 1].payload.get("content", "")

                payload = msg_row.payload or {}
                intent = payload.get("intent", DialogueIntent.UNKNOWN.value)
                entities = payload.get("entities", {})

                turns.append(DialogueTurnRecord(
                    turn_id=msg_row.message_state_id,
                    session_id=session_id,
                    user_message=msg_row.payload.get("content", ""),
                    assistant_response=assistant_response,
                    intent=intent,
                    extracted_entities=entities,
                    timestamp=msg_row.payload.get("timestamp", ""),
                ))
            i += 1

        # Build active objects from recent turns
        active_objects = self._extract_active_objects(turns)

        # Determine current topic
        current_topic = self._infer_current_topic(turns)

        # Get user preferences from session or use defaults
        user_preferences = chat_session.payload.get("preferences") if chat_session.payload else {}

        return DialogueContext(
            session_id=session_id,
            turns=turns,
            current_topic=current_topic,
            active_objects=active_objects,
            user_preferences=user_preferences,
            started_at=chat_session.payload.get("started_at", ""),
            last_updated_at=chat_session.payload.get("updated_at", ""),
        )

    def add_turn(
        self,
        context: DialogueContext,
        user_message: str,
        assistant_response: str,
        intent: DialogueIntent,
        extracted_entities: JSONObject,
        update: ContextUpdate | None = None,
    ) -> DialogueContext:
        """Add a dialogue turn to the context.

        Args:
            context: Current dialogue context
            user_message: User's message
            assistant_response: Assistant's response
            intent: Classified intent
            extracted_entities: Entities extracted from message
            update: Optional context update

        Returns:
            Updated DialogueContext
        """
        timestamp = utc_now_iso()

        # Create turn record
        turn = DialogueTurnRecord(
            turn_id=f"trn_{timestamp}_{len(context.turns)}",
            session_id=context.session_id,
            user_message=user_message,
            assistant_response=assistant_response,
            intent=intent.value,
            extracted_entities=extracted_entities,
            timestamp=timestamp,
        )

        # Add to context
        updated_turns = list(context.turns) + [turn]

        # Apply updates if provided
        active_objects = dict(context.active_objects)
        current_topic = context.current_topic
        user_preferences = dict(context.user_preferences)

        if update:
            if update.active_objects:
                active_objects.update(update.active_objects)
            if update.topic:
                current_topic = update.topic
            if update.user_preferences:
                user_preferences.update(update.user_preferences)

        # Auto-update active objects from entities
        if extracted_entities:
            active_objects.update(self._entities_to_active_objects(extracted_entities))

        return DialogueContext(
            session_id=context.session_id,
            turns=updated_turns,
            current_topic=current_topic,
            active_objects=active_objects,
            user_preferences=user_preferences,
            started_at=context.started_at,
            last_updated_at=timestamp,
        )

    def build_context_prompt(
        self,
        context: DialogueContext,
        max_turns: int = 10,
        max_tokens: int = 2000,
    ) -> str:
        """Build a context prompt for AI generation.

        Args:
            context: The dialogue context
            max_turns: Maximum number of recent turns to include
            max_tokens: Approximate maximum tokens for context

        Returns:
            Formatted context prompt string
        """
        parts = []

        # Add current topic
        if context.current_topic:
            parts.append(f"Current topic: {context.current_topic}")

        # Add active objects
        if context.active_objects:
            obj_str = ", ".join(f"{k}:{v}" for k, v in context.active_objects.items())
            parts.append(f"Active objects: {obj_str}")

        # Add recent conversation turns
        if context.turns:
            parts.append("\nRecent conversation:")
            recent_turns = context.recent_turns(max_turns)

            for turn in recent_turns:
                # Truncate long messages to save tokens
                user_msg = self._truncate_text(turn.user_message, 200)
                response = self._truncate_text(turn.assistant_response, 400)

                parts.append(f"User: {user_msg}")
                if response:
                    parts.append(f"Assistant: {response}")

                # Add intent for context
                if turn.intent != DialogueIntent.CHAT.value:
                    parts.append(f"[Intent: {turn.intent}]")

        return "\n".join(parts)

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    def _extract_active_objects(self, turns: list[DialogueTurnRecord]) -> dict[str, str]:
        """Extract active objects from conversation turns."""
        active = {}
        seen = set()

        # Scan turns in reverse order (most recent first)
        for turn in reversed(turns):
            entities = turn.extracted_entities
            if isinstance(entities, dict):
                for key, value in entities.items():
                    # Common entity patterns
                    if key.endswith("_id") and isinstance(value, str):
                        obj_type = key.replace("_id", "")
                        if obj_type not in seen:
                            active[obj_type] = value
                            seen.add(obj_type)

        return active

    def _infer_current_topic(self, turns: list[DialogueTurnRecord]) -> str | None:
        """Infer the current topic from conversation turns."""
        if not turns:
            return None

        # Use the intent of the most recent turn
        last_turn = turns[-1]
        intent = last_turn.intent_enum

        # Map intents to topics
        intent_topics = {
            DialogueIntent.OUTLINE_TO_PLOT: "expanding outline into plot",
            DialogueIntent.PLOT_TO_EVENT: "breaking down plot into events",
            DialogueIntent.EVENT_TO_SCENE: "expanding event into scenes",
            DialogueIntent.SCENE_TO_CHAPTER: "writing chapter from scene",
            DialogueIntent.REVIEW_PROPOSALS: "reviewing proposals",
        }

        return intent_topics.get(intent)

    def _entities_to_active_objects(self, entities: JSONObject) -> dict[str, str]:
        """Convert extracted entities to active objects format."""
        active = {}
        for key, value in entities.items():
            if key.endswith("_id") and isinstance(value, str):
                obj_type = key.replace("_id", "")
                active[obj_type] = value
        return active


__all__ = [
    "ContextScope",
    "DialogueTurnRecord",
    "DialogueContext",
    "ContextUpdate",
    "DialogueContextManager",
]
