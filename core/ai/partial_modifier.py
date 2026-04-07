"""
Partial modifier for workbench iteration.

This module provides the ability to modify specific sections of generated
content, such as "modify paragraph 3" or "change the dialogue in scene 2".

The parser extracts section targets from user feedback, and the modifier
applies changes to only the specified sections while preserving the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias, cast

from core.ai.prompts import build_partial_revision_prompt
from core.runtime.storage import CONTENT_KEYS, JSONValue

JSONObject: TypeAlias = dict[str, JSONValue]


# Patterns for extracting section targets from user feedback (pre-compiled)
_SECTION_PATTERNS_RAW = [
    # Named sections first (intro, ending, etc.) - must come before general patterns
    r"(?:the\s+)?(intro|开头|序章|序幕)(?:\s+section|$|\s)",
    r"(?:the\s+)?(ending|结尾|尾声)(?:\s+section|$|\s)",
    # "paragraph 3", "第三段", "para 3", "段3" (with optional space)
    r"(?:paragraph|para|段)\s*(\d+)",
    # "section 2", "第二部分"
    r"(?:section|部分)\s+(\d+)",
    # "scene 1", "场景1", "场景 1" (scene followed by optional space and number)
    r"(?:scene|场景)\s*(\d+)",
    # "chapter 5", "第五章", "章5"
    r"(?:chapter)\s+(\d+)",
    r"第\s*([一二三四五六七八九十百千\d]+)\s*章",
    r"章\s*([一二三四五六七八九十百千\d]+)",
    # Chinese patterns like "第三段" (Chinese number + 段/章/等)
    r"([一二三四五六七八九十百千]+)\s*(?:段|章|部分|节)",
]
_SECTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SECTION_PATTERNS_RAW]

# Ordinal number mapping (third -> 3, etc.)
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

_CONTENT_KEYS = CONTENT_KEYS

# Chinese number mapping for section parsing
_BASIC_CHINESE_NUMS: dict[str, int] = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "零": 0,
}

# Pre-compiled regex for splitting content into scenes and chapters
_SCENE_SPLIT = re.compile(r"\n(?=#{1,3}\s*(?:场景|Scene|SCENE)\s)", re.IGNORECASE)
_CHAPTER_SPLIT = re.compile(r"\n(?=#{1,2}\s*(?:第.{1,3}章|Chapter|CHAPTER)\s)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SectionTarget:
    """A specific section within a candidate payload.

    Used for partial revision requests like "modify paragraph 3".
    """

    section_type: str  # "paragraph", "scene", "chapter", "intro", "ending", etc.
    index: int | None  # 1-based index, or None for named sections
    identifier: str | None  # Optional identifier like "intro_scene"
    raw_match: str  # The original text that matched

    def __str__(self) -> str:
        if self.identifier:
            return f"{self.section_type} '{self.identifier}'"
        if self.index is not None:
            return f"{self.section_type} {self.index}"
        return self.section_type

    @property
    def is_numeric(self) -> bool:
        """Check if this target uses a numeric index."""
        return self.index is not None


@dataclass(frozen=True, slots=True)
class SectionContent:
    """Content extracted from a specific section."""

    section_type: str
    index: int | None
    identifier: str | None
    content: str
    metadata: JSONObject


@dataclass(frozen=True, slots=True)
class PartialModificationResult:
    """Result of a partial modification operation."""

    success: bool
    modified_payload: JSONObject
    modified_sections: list[str]
    error_message: str | None = None
    applied_changes: JSONObject | None = None


class PartialModifier:
    """Handles partial modification of generated content.

    This class provides:
    1. Parsing of user feedback to extract section targets
    2. Extraction of specific sections from payloads
    3. Application of AI-generated revisions to specific sections
    4. Reassembly of modified content with unchanged sections
    """

    def __init__(self, ai_client=None):
        """Initialize the partial modifier.

        Args:
            ai_client: Optional AI client for generating revisions
        """
        self._ai_client = ai_client

    def parse_section_target(self, feedback: str) -> SectionTarget | None:
        """Parse a section target from user feedback.

        Args:
            feedback: User feedback text like "modify paragraph 3"

        Returns:
            SectionTarget if found, None otherwise
        """
        feedback_lower = feedback.lower()

        # First check for ordinal numbers (third, fourth, etc.)
        for word, number in _ORDINALS.items():
            if word in feedback_lower:
                # Try to find the section type after the ordinal
                # e.g., "third paragraph", "fourth scene"
                for pattern in ["paragraph", "para", "scene", "section", "chapter"]:
                    if pattern in feedback_lower:
                        return SectionTarget(
                            section_type=pattern,
                            index=number,
                            identifier=None,
                            raw_match=f"{word} {pattern}",
                        )
                # If no specific type found, default to paragraph
                return SectionTarget(
                    section_type="paragraph",
                    index=number,
                    identifier=None,
                    raw_match=word,
                )

        # Then check for numbered sections
        for pattern, pattern_str in zip(_SECTION_PATTERNS, _SECTION_PATTERNS_RAW):
            match = pattern.search(feedback_lower)
            if match:
                raw_match = match.group(0)
                groups = match.groups()

                # Determine section type from pattern string
                if "intro" in pattern_str or "开头" in pattern_str or "序章" in pattern_str or "序幕" in pattern_str:
                    section_type = "intro"
                elif "ending" in pattern_str or "结尾" in pattern_str or "尾声" in pattern_str:
                    section_type = "ending"
                elif "paragraph" in pattern_str or "para" in pattern_str or "段" in pattern_str:
                    section_type = "paragraph"
                elif "section" in pattern_str or "部分" in pattern_str:
                    section_type = "section"
                elif "scene" in pattern_str or "场景" in pattern_str:
                    section_type = "scene"
                elif "chapter" in pattern_str or "章" in pattern_str:
                    section_type = "chapter"
                else:
                    section_type = "section"

                # Extract index or identifier
                index = None
                identifier = None

                for group in groups:
                    if group:
                        # Try to convert to number (including Chinese numbers)
                        if group.isdigit():
                            index = int(group)
                            break
                        # Try Chinese number conversion BEFORE isalpha check
                        # because Chinese characters are considered alpha
                        converted = self._chinese_number_to_int(group)
                        if converted is not None:
                            index = converted
                            break
                        # Only set as identifier if not a number
                        elif not any(c.isdigit() for c in group):
                            identifier = group
                            break

                return SectionTarget(
                    section_type=section_type,
                    index=index,
                    identifier=identifier,
                    raw_match=raw_match,
                )

        return None

    def _chinese_number_to_int(self, text: str) -> int | None:
        """Convert Chinese numbers to integers.

        Args:
            text: Chinese number text like "三" or "十五"

        Returns:
            Integer value or None if not a valid number
        """
        # Simple mapping for basic numbers
        # Direct lookup first
        if text in _BASIC_CHINESE_NUMS:
            return _BASIC_CHINESE_NUMS[text]
        if text.isdigit():
            return int(text)

        # Handle compound numbers like "十五" (15), "二十三" (23)
        if "十" in text:
            if text == "十":
                return 10
            if text.startswith("十"):
                rest = text[1:]
                rest_val = _BASIC_CHINESE_NUMS.get(rest, 0)
                return 10 + rest_val
            if text.endswith("十"):
                first = _BASIC_CHINESE_NUMS.get(text[0], 0)
                return first * 10
            first = _BASIC_CHINESE_NUMS.get(text[0], 0)
            rest = text[text.index("十") + 1:]
            rest_val = _BASIC_CHINESE_NUMS.get(rest, 0)
            return first * 10 + rest_val

        # Handle numbers like "百" (hundred), "千" (thousand)
        if "百" in text:
            if text == "百":
                return 100
            first = _BASIC_CHINESE_NUMS.get(text[0], 1)
            return first * 100
        if "千" in text:
            if text == "千":
                return 1000
            first = _BASIC_CHINESE_NUMS.get(text[0], 1)
            return first * 1000

        return None

    def extract_section(
        self,
        payload: JSONObject,
        target: SectionTarget,
    ) -> SectionContent | None:
        """Extract a specific section from a payload.

        Args:
            payload: The full payload object
            target: The section target to extract

        Returns:
            SectionContent if found, None otherwise
        """
        # Handle different payload structures
        content = self._get_content_from_payload(payload)
        if not content:
            return None

        # Split content into sections based on type
        sections = self._split_into_sections(content, target.section_type)

        if target.is_numeric:
            idx = (target.index or 1) - 1  # Convert to 0-based
            if 0 <= idx < len(sections):
                return SectionContent(
                    section_type=target.section_type,
                    index=target.index,
                    identifier=None,
                    content=sections[idx],
                    metadata={"section_index": idx},
                )
        elif target.identifier:
            # Find section by identifier
            for i, section in enumerate(sections):
                if target.identifier.lower() in section.lower()[:50]:
                    return SectionContent(
                        section_type=target.section_type,
                        index=None,
                        identifier=target.identifier,
                        content=section,
                        metadata={"section_index": i},
                    )

        return None

    def _get_content_from_payload(self, payload: JSONObject) -> str | None:
        """Extract the main content from a payload."""
        # Try common content fields
        for key in _CONTENT_KEYS:
            value = payload.get(key)
            if isinstance(value, str):
                return value

        # Try nested content
        if "content" in payload:
            content = payload["content"]
            if isinstance(content, dict):
                return content.get("body") or content.get("text")
            elif isinstance(content, str):
                return content

        return None

    def _split_into_sections(self, content: str, section_type: str) -> list[str]:
        """Split content into sections based on type.

        Args:
            content: The full content
            section_type: The type of section to split by

        Returns:
            List of section strings
        """
        if section_type == "paragraph":
            sections = [s.strip() for s in content.split("\n\n") if s.strip()]
        elif section_type == "scene":
            sections = [s.strip() for s in _SCENE_SPLIT.split(content) if s.strip()]
        elif section_type == "chapter":
            sections = [s.strip() for s in _CHAPTER_SPLIT.split(content) if s.strip()]
        else:
            sections = [s.strip() for s in content.split("\n\n") if s.strip()]

        return sections

    def apply_partial_revision(
        self,
        base_payload: JSONObject,
        target: SectionTarget,
        revised_content: str,
    ) -> PartialModificationResult:
        """Apply a partial revision to a payload.

        Args:
            base_payload: The original payload
            target: The section target to modify
            revised_content: The new content for the section

        Returns:
            PartialModificationResult with the modified payload
        """
        # Extract the original content
        original_content = self._get_content_from_payload(base_payload)
        if not original_content:
            return PartialModificationResult(
                success=False,
                modified_payload=base_payload,
                modified_sections=[],
                error_message="Could not extract content from payload",
            )

        # Split into sections
        sections = self._split_into_sections(original_content, target.section_type)

        # Find and replace the target section
        modified = False
        modified_sections = []

        if target.is_numeric:
            idx = (target.index or 1) - 1
            if 0 <= idx < len(sections):
                sections[idx] = revised_content
                modified = True
                modified_sections.append(str(target))
        elif target.identifier:
            for i, section in enumerate(sections):
                if target.identifier.lower() in section.lower()[:50]:
                    sections[i] = revised_content
                    modified = True
                    modified_sections.append(f"{target.section_type} '{target.identifier}'")
                    break

        if not modified:
            return PartialModificationResult(
                success=False,
                modified_payload=base_payload,
                modified_sections=[],
                error_message=f"Could not find section: {target}",
            )

        # Reassemble content
        new_content = "\n\n".join(sections)

        # Create modified payload
        modified_payload = dict(base_payload)
        content_key = self._find_content_key(base_payload)
        if content_key:
            modified_payload[content_key] = new_content
        else:
            # Add content field if none existed
            modified_payload["content"] = new_content

        return PartialModificationResult(
            success=True,
            modified_payload=cast(JSONObject, modified_payload),
            modified_sections=modified_sections,
            applied_changes={
                "target": str(target),
                "original_sections": len(sections),
                "modified_sections": modified_sections,
            },
        )

    def _find_content_key(self, payload: JSONObject) -> str | None:
        """Find the key that contains the main content."""
        for key in _CONTENT_KEYS:
            if key in payload and isinstance(payload[key], str):
                return key
        return None

    async def generate_partial_revision(
        self,
        base_payload: JSONObject,
        target: SectionTarget,
        revision_instruction: str,
        context: JSONObject | None = None,
    ) -> PartialModificationResult:
        """Generate and apply a partial revision using AI.

        Args:
            base_payload: The original payload
            target: The section target to modify
            revision_instruction: The user's revision instruction
            context: Additional context for generation

        Returns:
            PartialModificationResult with the AI-generated revision
        """
        if self._ai_client is None:
            return PartialModificationResult(
                success=False,
                modified_payload=base_payload,
                modified_sections=[],
                error_message="AI client not configured for partial revision",
            )

        # Extract the section content
        section_content = self.extract_section(base_payload, target)
        if not section_content:
            return PartialModificationResult(
                success=False,
                modified_payload=base_payload,
                modified_sections=[],
                error_message=f"Could not extract section: {target}",
            )

        # Build the revision prompt
        prompt = build_partial_revision_prompt(
            section_content=section_content.content,
            section_type=target.section_type,
            revision_instruction=revision_instruction,
            context=context or {},
        )

        # Generate revision (synchronous for now, would be async with real AI)
        try:
            response = self._ai_client.generate(
                messages=[
                    {"role": "system", "content": "You are a novel editing assistant. Rewrite the specified section according to the user's instructions."},
                    {"role": "user", "content": prompt},
                ]
            )
            revised_content = response.strip() if isinstance(response, str) else str(response)
        except Exception as e:
            return PartialModificationResult(
                success=False,
                modified_payload=base_payload,
                modified_sections=[],
                error_message=f"AI generation failed: {e}",
            )

        # Apply the revision
        return self.apply_partial_revision(base_payload, target, revised_content)


__all__ = [
    "SectionTarget",
    "SectionContent",
    "PartialModificationResult",
    "PartialModifier",
]
