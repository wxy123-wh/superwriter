from __future__ import annotations

from typing import TypeAlias

from core.storage._utils import JSONScalar, JSONValue
from core.storage.engine import CanonicalStorage
from core.storage._types import (
    ChatMessageLinkInput,
    ChatMessageLinkRow,
    ChatSessionInput,
    ChatSessionRow,
    MetadataMarkerInput,
    MetadataMarkerSnapshot,
)
from core.storage._utils import CONTENT_KEYS, utc_now_iso

JSONObject: TypeAlias = dict[str, JSONValue]

__all__ = [
    "CanonicalStorage",
    "CanonicalWriteRequest",
    "CanonicalWriteResult",
    "ChatMessageLinkInput",
    "ChatMessageLinkRow",
    "ChatSessionInput",
    "ChatSessionRow",
    "DerivedRecordInput",
    "ImportRecordInput",
    "JSONValue",
    "JSONObject",
    "MetadataMarkerSnapshot",
    "MetadataMarkerInput",
    "ProposalRecordInput",
    "CONTENT_KEYS",
    "utc_now_iso",
]
