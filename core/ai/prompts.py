"""Stub prompts module — full prompt building removed with core editing features."""

from __future__ import annotations


def build_partial_revision_prompt(
    section_content: str,
    section_type: str,
    revision_instruction: str,
    context: dict | None = None,
) -> str:
    """Stub: builds a partial revision prompt."""
    title = (context or {}).get("title", "")
    return (
        f"Revision request for {section_type}" + (f" '{title}'" if title else "") + ":\n\n"
        f"Content:\n{section_content}\n\n"
        f"Instruction: {revision_instruction}"
    )
