"""Stub mutation policy engine — core editing features removed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

JSONObject: TypeAlias = dict[str, "JSONValue"]


@dataclass(frozen=True, slots=True)
class ChapterMutationSignals:
    """Stub — real signals removed with core editing features."""
    signals: JSONObject


@dataclass(frozen=True, slots=True)
class MutationRequest:
    """Stub — real mutation request removed with core editing features."""
    target_family: str
    payload: JSONObject
    actor: str
    source_surface: str
    target_object_id: str | None = None
    base_revision_id: str | None = None
    source_scene_revision_id: str | None = None
    base_source_scene_revision_id: str | None = None
    skill: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None
    revision_reason: str | None = None
    revision_source_message_id: str | None = None
    chapter_signals: ChapterMutationSignals | None = None


class MutationPolicyEngine:
    """Stub engine. Full editing/mutation policy removed per user request."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass
