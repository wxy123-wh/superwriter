"""
Tests for partial modification functionality.

Tests the ability to modify specific sections of generated content,
such as "modify paragraph 3" or "change the dialogue in scene 2".
"""

import pytest

from core.ai.partial_modifier import (
    PartialModificationResult,
    PartialModifier,
    SectionContent,
    SectionTarget,
)


class TestSectionTarget:
    """Test SectionTarget model."""

    def test_section_target_with_numeric_index(self):
        """Test section target with numeric index."""
        target = SectionTarget(
            section_type="paragraph",
            index=3,
            identifier=None,
            raw_match="paragraph 3",
        )
        assert target.section_type == "paragraph"
        assert target.index == 3
        assert target.is_numeric
        assert str(target) == "paragraph 3"

    def test_section_target_with_identifier(self):
        """Test section target with identifier."""
        target = SectionTarget(
            section_type="scene",
            index=None,
            identifier="intro",
            raw_match="the intro",
        )
        assert target.section_type == "scene"
        assert target.identifier == "intro"
        assert not target.is_numeric
        assert str(target) == "scene 'intro'"


class TestPartialModifier:
    """Test PartialModifier class."""

    @pytest.fixture
    def modifier(self):
        """Create a PartialModifier instance."""
        return PartialModifier(ai_client=None)

    def test_parse_paragraph_target(self, modifier: PartialModifier):
        """Test parsing paragraph targets."""
        # English
        target = modifier.parse_section_target("modify paragraph 3")
        assert target is not None
        assert target.section_type == "paragraph"
        assert target.index == 3

        target = modifier.parse_section_target("fix the third paragraph")
        assert target is not None
        assert target.index == 3

        # Chinese
        target = modifier.parse_section_target("修改第三段")
        assert target is not None
        assert target.section_type == "paragraph"
        assert target.index == 3

    def test_parse_scene_target(self, modifier: PartialModifier):
        """Test parsing scene targets."""
        target = modifier.parse_section_target("change scene 2")
        assert target is not None
        assert target.section_type == "scene"
        assert target.index == 2

        target = modifier.parse_section_target("修改场景1")
        assert target is not None
        assert target.section_type == "scene"
        assert target.index == 1

    def test_parse_chapter_target(self, modifier: PartialModifier):
        """Test parsing chapter targets."""
        target = modifier.parse_section_target("revise chapter 5")
        assert target is not None
        assert target.section_type == "chapter"
        assert target.index == 5

        # Chinese chapter numbers
        target = modifier.parse_section_target("修改第三章")
        assert target is not None
        assert target.section_type == "chapter"
        assert target.index == 3

    def test_parse_named_section(self, modifier: PartialModifier):
        """Test parsing named sections like intro/ending."""
        target = modifier.parse_section_target("fix the intro")
        assert target is not None
        assert target.section_type in ("section", "intro")
        assert target.identifier == "intro"

        target = modifier.parse_section_target("修改开头")
        assert target is not None
        assert target.identifier == "开头"

    def test_parse_no_target(self, modifier: PartialModifier):
        """Test feedback with no section target."""
        target = modifier.parse_section_target("make it more dramatic")
        assert target is None

        target = modifier.parse_section_target("improve the writing")
        assert target is None

    def test_chinese_number_conversion(self, modifier: PartialModifier):
        """Test Chinese number to int conversion."""
        assert modifier._chinese_number_to_int("一") == 1
        assert modifier._chinese_number_to_int("三") == 3
        assert modifier._chinese_number_to_int("十") == 10
        assert modifier._chinese_number_to_int("123") == 123
        assert modifier._chinese_number_to_int("invalid") is None

    def test_extract_content_from_payload(self, modifier: PartialModifier):
        """Test extracting content from various payload structures."""
        # Content field
        payload = {"content": "This is the content", "title": "Test"}
        assert modifier._get_content_from_payload(payload) == "This is the content"

        # Body field
        payload = {"body": "Body content", "title": "Test"}
        assert modifier._get_content_from_payload(payload) == "Body content"

        # Text field
        payload = {"text": "Text content", "title": "Test"}
        assert modifier._get_content_from_payload(payload) == "Text content"

        # Nested content
        payload = {"content": {"body": "Nested body"}}
        assert modifier._get_content_from_payload(payload) == "Nested body"

        # No content
        payload = {"title": "Only title"}
        assert modifier._get_content_from_payload(payload) is None

    def test_split_into_paragraphs(self, modifier: PartialModifier):
        """Test splitting content into paragraphs."""
        content = """First paragraph here.

Second paragraph with more text.

Third paragraph to conclude."""

        sections = modifier._split_into_sections(content, "paragraph")
        assert len(sections) == 3
        assert "First paragraph" in sections[0]
        assert "Second paragraph" in sections[1]
        assert "Third paragraph" in sections[2]

    def test_split_into_scenes(self, modifier: PartialModifier):
        """Test splitting content into scenes."""
        content = """## Scene 1
Opening scene content.

## Scene 2
Following scene content.

## Scene 3
Final scene."""

        sections = modifier._split_into_sections(content, "scene")
        assert len(sections) == 3
        assert "Opening scene" in sections[0]
        assert "Following scene" in sections[1]
        assert "Final scene" in sections[2]

    def test_extract_section_by_index(self, modifier: PartialModifier):
        """Test extracting a section by index."""
        content = """First paragraph.

Second paragraph.

Third paragraph."""

        payload = {"content": content}
        target = SectionTarget(section_type="paragraph", index=2, identifier=None, raw_match="paragraph 2")

        section = modifier.extract_section(payload, target)
        assert section is not None
        assert section.index == 2
        assert "Second paragraph" in section.content

    def test_extract_section_by_identifier(self, modifier: PartialModifier):
        """Test extracting a section by identifier."""
        content = """## Intro
This is the intro section.

## Main
This is the main section."""

        payload = {"content": content}
        target = SectionTarget(section_type="scene", index=None, identifier="intro", raw_match="the intro")

        section = modifier.extract_section(payload, target)
        assert section is not None
        assert section.identifier == "intro"
        assert "This is the intro" in section.content

    def test_apply_partial_revision_by_index(self, modifier: PartialModifier):
        """Test applying a partial revision by index."""
        original_content = """First paragraph.

Second paragraph.

Third paragraph."""

        payload = {"content": original_content}
        target = SectionTarget(section_type="paragraph", index=2, identifier=None, raw_match="paragraph 2")
        revised_content = "Modified second paragraph."

        result = modifier.apply_partial_revision(payload, target, revised_content)

        assert result.success
        assert "Modified second paragraph" in result.modified_payload["content"]
        assert "First paragraph" in result.modified_payload["content"]
        assert "Third paragraph" in result.modified_payload["content"]
        assert result.modified_sections == ["paragraph 2"]

    def test_apply_partial_revision_by_identifier(self, modifier: PartialModifier):
        """Test applying a partial revision by identifier."""
        original_content = """## Intro
Original intro content.

## Main
Main content here."""

        payload = {"content": original_content}
        target = SectionTarget(section_type="scene", index=None, identifier="intro", raw_match="the intro")
        revised_content = "Revised intro content."

        result = modifier.apply_partial_revision(payload, target, revised_content)

        assert result.success
        assert "Revised intro" in result.modified_payload["content"]
        assert "Main content" in result.modified_payload["content"]

    def test_apply_revision_invalid_target(self, modifier: PartialModifier):
        """Test applying revision to non-existent section."""
        content = """Only one paragraph here."""

        payload = {"content": content}
        target = SectionTarget(section_type="paragraph", index=5, identifier=None, raw_match="paragraph 5")
        revised_content = "This won't be applied."

        result = modifier.apply_partial_revision(payload, target, revised_content)

        assert not result.success
        assert result.error_message is not None
        assert result.modified_payload == payload

    def test_find_content_key(self, modifier: PartialModifier):
        """Test finding the content key in a payload."""
        # Content field
        assert modifier._find_content_key({"content": "text"}) == "content"
        # Body field
        assert modifier._find_content_key({"body": "text"}) == "body"
        # Text field
        assert modifier._find_content_key({"text": "text"}) == "text"
        # Unknown
        assert modifier._find_content_key({"title": "text"}) is None

    def test_partial_modification_result_structure(self):
        """Test PartialModificationResult structure."""
        result = PartialModificationResult(
            success=True,
            modified_payload={"content": "modified"},
            modified_sections=["paragraph 1"],
            error_message=None,
            applied_changes={"target": "paragraph 1"},
        )
        assert result.success
        assert result.modified_payload["content"] == "modified"
        assert result.modified_sections == ["paragraph 1"]
        assert result.error_message is None

        failure_result = PartialModificationResult(
            success=False,
            modified_payload={"content": "original"},
            modified_sections=[],
            error_message="Section not found",
            applied_changes=None,
        )
        assert not failure_result.success
        assert failure_result.error_message == "Section not found"


class TestSectionContent:
    """Test SectionContent model."""

    def test_section_content_creation(self):
        """Test creating a SectionContent instance."""
        content = SectionContent(
            section_type="paragraph",
            index=1,
            identifier=None,
            content="Paragraph content here.",
            metadata={"word_count": 3},
        )
        assert content.section_type == "paragraph"
        assert content.index == 1
        assert content.content == "Paragraph content here."
        assert content.metadata["word_count"] == 3
