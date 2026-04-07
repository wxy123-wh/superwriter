"""Tests for dialogue state machine and AI-driven intent integration."""

from __future__ import annotations

import pytest

from core.ai.dialogue import (
    DialogueIntent,
    DialogueRequest,
    DialogueResponse,
    DialogueState,
    DialogueStateMachine,
    IntentClassification,
)


class TestDialogueState:
    def test_all_states_defined(self):
        expected = {"idle", "awaiting_context", "processing", "awaiting_confirmation", "completed"}
        assert set(e.value for e in DialogueState) == expected

    def test_state_values_are_strings(self):
        for state in DialogueState:
            assert isinstance(state.value, str)


class TestDialogueStateMachine:
    def test_initial_state_is_idle(self):
        sm = DialogueStateMachine()
        assert sm.get_state("new_session") == DialogueState.IDLE

    def test_valid_transition_idle_to_awaiting_context(self):
        sm = DialogueStateMachine()
        result = sm.transition("s1", DialogueState.AWAITING_CONTEXT)
        assert result == DialogueState.AWAITING_CONTEXT

    def test_valid_transition_awaiting_context_to_processing(self):
        sm = DialogueStateMachine()
        sm.transition("s1", DialogueState.AWAITING_CONTEXT)
        result = sm.transition("s1", DialogueState.PROCESSING)
        assert result == DialogueState.PROCESSING

    def test_valid_transition_processing_to_completed(self):
        sm = DialogueStateMachine()
        sm.transition("s1", DialogueState.AWAITING_CONTEXT)
        sm.transition("s1", DialogueState.PROCESSING)
        result = sm.transition("s1", DialogueState.COMPLETED)
        assert result == DialogueState.COMPLETED

    def test_valid_transition_completed_to_idle(self):
        sm = DialogueStateMachine()
        sm.transition("s1", DialogueState.AWAITING_CONTEXT)
        sm.transition("s1", DialogueState.PROCESSING)
        sm.transition("s1", DialogueState.COMPLETED)
        result = sm.transition("s1", DialogueState.IDLE)
        assert result == DialogueState.IDLE

    def test_invalid_transition_idle_to_processing(self):
        sm = DialogueStateMachine()
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition("s1", DialogueState.PROCESSING)

    def test_invalid_transition_idle_to_completed(self):
        sm = DialogueStateMachine()
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition("s1", DialogueState.COMPLETED)

    def test_reset_always_goes_to_idle(self):
        sm = DialogueStateMachine()
        sm.transition("s1", DialogueState.AWAITING_CONTEXT)
        result = sm.reset("s1")
        assert result == DialogueState.IDLE
        assert sm.get_state("s1") == DialogueState.IDLE

    def test_reset_from_any_state(self):
        sm = DialogueStateMachine()
        for state in DialogueState:
            sm.reset("s1")  # Start fresh
            if state != DialogueState.IDLE:
                # Force set a state for testing
                sm._states["s1"] = state
            result = sm.reset("s1")
            assert result == DialogueState.IDLE

    def test_is_idle(self):
        sm = DialogueStateMachine()
        assert sm.is_idle("s1") is True
        sm.transition("s1", DialogueState.AWAITING_CONTEXT)
        assert sm.is_idle("s1") is False

    def test_sessions_are_independent(self):
        sm = DialogueStateMachine()
        sm.transition("s1", DialogueState.AWAITING_CONTEXT)
        assert sm.get_state("s1") == DialogueState.AWAITING_CONTEXT
        assert sm.get_state("s2") == DialogueState.IDLE

    def test_full_lifecycle(self):
        """Test a complete dialogue lifecycle through all states."""
        sm = DialogueStateMachine()
        session = "lifecycle_test"

        assert sm.get_state(session) == DialogueState.IDLE
        sm.transition(session, DialogueState.AWAITING_CONTEXT)
        sm.transition(session, DialogueState.PROCESSING)
        sm.transition(session, DialogueState.COMPLETED)
        sm.transition(session, DialogueState.IDLE)
        assert sm.get_state(session) == DialogueState.IDLE


class TestAIIntentPreferred:
    """Test that AI intent classification is preferred when AI client is available."""

    def test_ai_client_check_in_processor(self):
        """Verify the processor checks for AI client before classification."""
        from core.ai.dialogue import DialogueProcessor

        # Create a mock service with AI provider
        class MockAIProvider:
            def generate(self, messages):
                return '{"intent": "help", "confidence": 0.9, "entities": {}}'

        class MockService:
            def _get_active_ai_provider(self):
                return MockAIProvider()

            def get_workspace_snapshot(self, _):
                class WS:
                    canonical_objects = []
                    derived_artifacts = []
                    review_proposals = []
                return WS()

        processor = DialogueProcessor(MockService())
        assert processor._ai_client is not None

    def test_no_ai_client_uses_keyword_fallback(self):
        """Verify keyword classification is used when no AI client."""
        from core.ai.dialogue import DialogueProcessor

        class MockServiceNoAI:
            def _get_active_ai_provider(self):
                return None

        processor = DialogueProcessor(MockServiceNoAI())
        assert processor._ai_client is None

        # Keyword classification should still work
        classification = processor._classify_intent("帮助", "prj_001", None)
        assert classification.intent == DialogueIntent.HELP
        assert classification.confidence >= 0.9

    def test_state_machine_integrated_in_processor(self):
        """Verify processor has a state machine instance."""
        from core.ai.dialogue import DialogueProcessor

        class MockServiceNoAI:
            def _get_active_ai_provider(self):
                return None

        processor = DialogueProcessor(MockServiceNoAI())
        assert hasattr(processor, "_state_machine")
        assert isinstance(processor._state_machine, DialogueStateMachine)


class TestIntentClassification:
    def test_keyword_classification_workbench_intents(self):
        from core.ai.dialogue import DialogueProcessor

        class MockServiceNoAI:
            def _get_active_ai_provider(self):
                return None

        processor = DialogueProcessor(MockServiceNoAI())

        test_cases = [
            ("展开大纲", DialogueIntent.OUTLINE_TO_PLOT),
            ("生成事件", DialogueIntent.PLOT_TO_EVENT),
            ("展开事件", DialogueIntent.EVENT_TO_SCENE),
            ("写章节", DialogueIntent.SCENE_TO_CHAPTER),
            ("帮助", DialogueIntent.HELP),
        ]

        for message, expected_intent in test_cases:
            result = processor._classify_intent(message, "prj_001", None)
            assert result.intent == expected_intent, f"Failed for '{message}'"
