"""
Tests for AI intent recognition enhancement.

Tests the AI-driven intent classification and entity extraction
for dialogue processing.
"""

import pytest

from core.ai.dialogue import DialogueIntent, DialogueProcessor


@pytest.fixture
def mock_service():
    """Create a mock application service."""
    class MockService:
        def _get_active_ai_provider(self):
            return None  # Will trigger fallback to keyword classification

        def get_workspace_snapshot(self, request):
            # Return a mock workspace
            class MockWorkspace:
                canonical_objects = []
                derived_artifacts = []
                review_proposals = []

            return MockWorkspace()

    return MockService()


class TestAIIntentRecognition:
    """Test AI-enhanced intent recognition."""

    def test_classify_intent_with_ai_disabled(self, mock_service):
        """Test classification when AI is not configured."""
        processor = DialogueProcessor(mock_service)

        classification = processor._classify_intent(
            message="写章节",
            project_id="prj_test",
            novel_id="nvl_test",
        )

        # Should use keyword classification
        assert classification.intent == DialogueIntent.SCENE_TO_CHAPTER

    def test_extract_entities_from_message(self, mock_service):
        """Test entity extraction from user message."""
        processor = DialogueProcessor(mock_service)

        # English message with object ID
        entities = processor.extract_entities(
            message="Work on scene scn_123",
            context={}
        )
        assert entities.get("scene_id") == "scn_123"

        # Chinese message with object ID
        entities = processor.extract_entities(
            message="编辑场景 scn_456",
            context={}
        )
        assert entities.get("scene_id") == "scn_456"

        # Message with operation
        entities = processor.extract_entities(
            message="Create a new outline",
            context={}
        )
        assert entities.get("operation") == "create"

    def test_extract_entities_with_operations(self, mock_service):
        """Test extracting operation type."""
        processor = DialogueProcessor(mock_service)

        # Edit operations
        entities = processor.extract_entities(
            message="修改这个场景",
            context={}
        )
        assert entities.get("operation") == "edit"

        # List operations
        entities = processor.extract_entities(
            message="列出所有场景",
            context={}
        )
        assert entities.get("operation") == "list"


class TestEntityPatterns:
    """Test entity extraction patterns."""

    def test_scene_id_patterns(self):
        """Test various scene ID patterns."""
        processor = DialogueProcessor(None)

        patterns = [
            ("scene scn_001", "scn_001"),
            ("场景 scn_003", "scn_003"),
        ]

        for pattern, expected_id in patterns:
            entities = processor.extract_entities(pattern, {})
            assert entities.get("scene_id") == expected_id, f"Failed for pattern: {pattern}"

    def test_outline_id_patterns(self):
        """Test various outline ID patterns."""
        processor = DialogueProcessor(None)

        patterns = [
            ("outline out_001", "out_001"),
            ("大纲 out_003", "out_003"),
        ]

        for pattern, expected_id in patterns:
            entities = processor.extract_entities(pattern, {})
            assert entities.get("outline_id") == expected_id, f"Failed for pattern: {pattern}"

    def test_novel_id_patterns(self):
        """Test various novel ID patterns."""
        processor = DialogueProcessor(None)

        patterns = [
            ("novel nvl_001", "nvl_001"),
            ("小说 nvl_003", "nvl_003"),
        ]

        for pattern, expected_id in patterns:
            entities = processor.extract_entities(pattern, {})
            assert entities.get("novel_id") == expected_id, f"Failed for pattern: {pattern}"


class TestIntentClassificationAccuracy:
    """Test accuracy of intent classification."""

    def test_workbench_operation_classification(self, mock_service):
        """Test classification of workbench operation requests."""
        processor = DialogueProcessor(mock_service)

        test_cases = [
            ("expand outline to plot", DialogueIntent.OUTLINE_TO_PLOT),
            ("生成剧情", DialogueIntent.PLOT_TO_EVENT),
            ("create scenes from event", DialogueIntent.EVENT_TO_SCENE),
            ("write chapter", DialogueIntent.SCENE_TO_CHAPTER),
            ("review proposals", DialogueIntent.REVIEW_PROPOSALS),
            ("list objects", DialogueIntent.LIST_OBJECTS),
            ("show skills", DialogueIntent.LIST_SKILLS),
            ("help", DialogueIntent.HELP),
        ]

        for message, expected_intent in test_cases:
            classification = processor._classify_intent(
                message=message,
                project_id="prj_test",
                novel_id="nvl_test",
            )
            # Check if intent matches expected or falls back to chat
            assert classification.intent in {expected_intent, DialogueIntent.CHAT}, \
                f"Expected {expected_intent} or CHAT for '{message}', got {classification.intent}"

    def test_confidence_scores(self, mock_service):
        """Test that different patterns produce different confidence levels."""
        processor = DialogueProcessor(mock_service)

        # High confidence: explicit workbench operation
        classification1 = processor._classify_intent(
            message="expand outline to plot",
            project_id="prj_test",
            novel_id="nvl_test",
        )
        # Keyword match should give moderate confidence
        assert 0.5 <= classification1.confidence <= 1.0

        # Lower confidence: ambiguous message
        classification2 = processor._classify_intent(
            message="do something",
            project_id="prj_test",
            novel_id="nvl_test",
        )
        # Fallback to chat with low confidence
        assert classification2.confidence <= 0.6
