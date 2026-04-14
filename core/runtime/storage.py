"""Simplified runtime storage re-exports — chat, provider, and metadata only."""

from __future__ import annotations

from typing import TypeAlias

from core.storage.engine import CanonicalStorage
from core.storage._types import (
    ChatMessageLinkInput,
    ChatMessageLinkRow,
    ChatSessionInput,
    ChatSessionRow,
    MetadataMarkerInput,
    MetadataMarkerSnapshot,
)
from core.storage._utils import JSONValue, CONTENT_KEYS, utc_now_iso

JSONObject: TypeAlias = dict[str, JSONValue]

__all__ = [
    "CanonicalStorage",
    "ChatMessageLinkInput",
    "ChatMessageLinkRow",
    "ChatSessionInput",
    "ChatSessionRow",
    "JSONValue",
    "JSONObject",
    "MetadataMarkerInput",
    "MetadataMarkerSnapshot",
    "CONTENT_KEYS",
    "utc_now_iso",
]
