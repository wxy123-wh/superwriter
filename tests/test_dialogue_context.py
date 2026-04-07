"""
Tests for dialogue context management.

Tests the multi-turn conversation context support, including:
- Creating dialogue contexts
- Adding conversation turns
- Building context prompts
- Inferring current topic
"""

import tempfile
from pathlib import Path

import pytest

from core.ai.dialogue import DialogueIntent
from core.ai.dialogue_context import (
    ContextScope,
    ContextUpdate,
    DialogueContext,
    DialogueContextManager,
    DialogueTurnRecord,
)
from core.runtime.storage import CanonicalStorage


@pytest.fixture
def temp_storage():
    """Create a temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = CanonicalStorage(db_path)
        yield storage


@pytest.fixture
def context_manager(temp_storage: CanonicalStorage):
    """Create a DialogueContextManager for testing."""
    return DialogueContextManager(temp_storage)


class TestDialogueTurnRecord:
    """Test DialogueTurnRecord model."""

    def test_turn_creation(self):
        """Test creating a turn record."""
        turn = DialogueTurnRecord(
            turn_id="trn_001",
            session_id="sess_001",
            user_message="Hello",
            assistant_response="Hi there!",
            intent=DialogueIntent.CHAT.value,
            extracted_entities={},
            timestamp="2024-01-01T00:00:00Z",
        )
        assert turn.turn_id == "trn_001"
        assert turn.user_message == "Hello"
        assert turn.assistant_response == "Hi there!"
        assert turn.intent == "chat"  # The value, not enum
        # Note: intent_enum may not match if we store value instead of enum name
        # This is expected - we store the value string

    def test_turn_with_entities(self):
        """Test turn with extracted entities."""
        turn = DialogueTurnRecord(
            turn_id="trn_002",
            session_id="sess_001",
            user_message="Work on scene scn_123",
            assistant_response="OK",
            intent=DialogueIntent.EVENT_TO_SCENE.value,
            extracted_entities={"scene_id": "scn_123"},
            timestamp="2024-01-01T00:00:00Z",
        )
        assert turn.extracted_entities["scene_id"] == "scn_123"


class TestDialogueContext:
    """Test DialogueContext model."""

    def test_empty_context(self):
        """Test creating an empty context."""
        context = DialogueContext(
            session_id="sess_001",
            turns=[],
            current_topic=None,
            active_objects={},
            user_preferences={},
            started_at="2024-01-01T00:00:00Z",
            last_updated_at="2024-01-01T00:00:00Z",
        )
        assert context.is_empty
        assert context.turn_count == 0
        assert context.recent_turns(5) == []

    def test_context_with_turns(self):
        """Test context with conversation turns."""
        turns = [
            DialogueTurnRecord(
                turn_id="trn_001",
                session_id="sess_001",
                user_message="First message",
                assistant_response="First response",
                intent=DialogueIntent.CHAT.value,
                extracted_entities={},
                timestamp="2024-01-01T00:00:00Z",
            ),
            DialogueTurnRecord(
                turn_id="trn_002",
                session_id="sess_001",
                user_message="Second message",
                assistant_response="Second response",
                intent=DialogueIntent.SCENE_TO_CHAPTER.value,
                extracted_entities={"scene_id": "scn_123"},
                timestamp="2024-01-01T00:01:00Z",
            ),
        ]

        context = DialogueContext(
            session_id="sess_001",
            turns=turns,
            current_topic="writing",
            active_objects={"scene": "scn_123"},
            user_preferences={},
            started_at="2024-01-01T00:00:00Z",
            last_updated_at="2024-01-01T00:01:00Z",
        )
        assert context.turn_count == 2
        assert context.current_topic == "writing"
        assert context.active_objects == {"scene": "scn_123"}

    def test_recent_turns(self):
        """Test getting recent turns."""
        turns = [
            DialogueTurnRecord(
                turn_id=f"trn_{i:03d}",
                session_id="sess_001",
                user_message=f"Message {i}",
                assistant_response=f"Response {i}",
                intent=DialogueIntent.CHAT.value,
                extracted_entities={},
                timestamp="2024-01-01T00:00:00Z",
            )
            for i in range(10)
        ]

        context = DialogueContext(
            session_id="sess_001",
            turns=turns,
            current_topic=None,
            active_objects={},
            user_preferences={},
            started_at="2024-01-01T00:00:00Z",
            last_updated_at="2024-01-01T00:00:00Z",
        )

        recent_3 = context.recent_turns(3)
        assert len(recent_3) == 3
        assert recent_3[0].turn_id == "trn_007"
        assert recent_3[2].turn_id == "trn_009"

    def test_active_object_ids(self):
        """Test getting active object IDs."""
        context = DialogueContext(
            session_id="sess_001",
            turns=[],
            current_topic=None,
            active_objects={"scene": "scn_123", "novel": "nvl_456"},
            user_preferences={},
            started_at="2024-01-01T00:00:00Z",
            last_updated_at="2024-01-01T00:00:00Z",
        )
        assert set(context.active_object_ids) == {"scn_123", "nvl_456"}


class TestDialogueContextManager:
    """Test DialogueContextManager class."""

    def test_create_context(self, context_manager: DialogueContextManager):
        """Test creating a new dialogue context."""
        context = context_manager.create_context(
            session_id="sess_001",
            project_id="prj_test",
            novel_id="nvl_test",
            actor="test_user",
        )
        assert context.session_id == "sess_001"
        assert context.is_empty
        assert context.turn_count == 0

    def test_add_turn(self, context_manager: DialogueContextManager):
        """Test adding a turn to context."""
        context = context_manager.create_context(
            session_id="sess_001",
            project_id="prj_test",
            actor="test_user",
        )

        updated = context_manager.add_turn(
            context=context,
            user_message="Hello",
            assistant_response="Hi!",
            intent=DialogueIntent.CHAT,
            extracted_entities={},
        )

        assert updated.turn_count == 1
        assert updated.turns[0].user_message == "Hello"

    def test_add_turn_with_update(self, context_manager: DialogueContextManager):
        """Test adding a turn with context update."""
        context = context_manager.create_context(
            session_id="sess_001",
            project_id="prj_test",
            actor="test_user",
        )

        update = ContextUpdate(
            topic="writing chapter",
            active_objects={"scene": "scn_123"},
        )

        updated = context_manager.add_turn(
            context=context,
            user_message="Work on scene scn_123",
            assistant_response="OK",
            intent=DialogueIntent.SCENE_TO_CHAPTER,
            extracted_entities={},
            update=update,
        )

        assert updated.current_topic == "writing chapter"
        assert updated.active_objects["scene"] == "scn_123"

    def test_add_turn_auto_extract_entities(self, context_manager: DialogueContextManager):
        """Test that entities are auto-extracted to active objects."""
        context = context_manager.create_context(
            session_id="sess_001",
            project_id="prj_test",
            actor="test_user",
        )

        updated = context_manager.add_turn(
            context=context,
            user_message="Edit scene scn_456",
            assistant_response="OK",
            intent=DialogueIntent.EVENT_TO_SCENE,
            extracted_entities={"scene_id": "scn_456", "novel_id": "nvl_789"},
        )

        assert updated.active_objects["scene"] == "scn_456"
        assert updated.active_objects["novel"] == "nvl_789"

    def test_build_context_prompt(self, context_manager: DialogueContextManager):
        """Test building context prompt for AI."""
        context = context_manager.create_context(
            session_id="sess_001",
            project_id="prj_test",
            actor="test_user",
        )

        # Add some turns
        context = context_manager.add_turn(
            context=context,
            user_message="I want to write a chapter",
            assistant_response="OK, which scene?",
            intent=DialogueIntent.SCENE_TO_CHAPTER,
            extracted_entities={"scene_id": "scn_001"},
        )

        prompt = context_manager.build_context_prompt(context, max_turns=5)

        assert "Current topic:" in prompt or "Active objects:" in prompt or "Recent conversation:" in prompt
        assert "I want to write a chapter" in prompt
        assert "scene_to_chapter" in prompt

    def test_build_context_prompt_truncation(self, context_manager: DialogueContextManager):
        """Test that long messages are truncated in context prompt."""
        context = context_manager.create_context(
            session_id="sess_001",
            project_id="prj_test",
            actor="test_user",
        )

        # Add a turn with very long message
        long_message = "A" * 500
        long_response = "B" * 1000

        context = context_manager.add_turn(
            context=context,
            user_message=long_message,
            assistant_response=long_response,
            intent=DialogueIntent.CHAT,
            extracted_entities={},
        )

        prompt = context_manager.build_context_prompt(context, max_tokens=500)

        # Check truncation
        # User message should be truncated to ~200 chars
        # Response should be truncated to ~400 chars
        assert len(prompt) < 1000  # Rough check

    def test_load_nonexistent_context(self, context_manager: DialogueContextManager):
        """Test loading a context that doesn't exist."""
        context = context_manager.load_context("sess_nonexistent")
        assert context is None


class TestContextUpdate:
    """Test ContextUpdate model."""

    def test_update_with_topic(self):
        """Test context update with topic change."""
        update = ContextUpdate(topic="new topic")
        assert update.topic == "new topic"
        assert update.active_objects is None
        assert update.user_preferences is None

    def test_update_with_all_fields(self):
        """Test context update with all fields."""
        update = ContextUpdate(
            topic="revising",
            active_objects={"scene": "scn_new"},
            user_preferences={"style": "dramatic"},
            context_scope="session",
        )
        assert update.topic == "revising"
        assert update.active_objects == {"scene": "scn_new"}
        assert update.user_preferences == {"style": "dramatic"}
        assert update.context_scope == "session"


class TestContextScope:
    """Test ContextScope enum."""

    def test_scope_values(self):
        """Test that all scope values are defined."""
        assert ContextScope.SESSION.value == "session"
        assert ContextScope.RECENT.value == "recent"
        assert ContextScope.ACTIVE.value == "active"
