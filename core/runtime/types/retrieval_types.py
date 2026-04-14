from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from core.runtime.storage import JSONValue

JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class RetrievalStatusSnapshot:
    scope_family: str
    scope_object_id: str
    support_only: bool
    rebuildable: bool
    build_consistency_stamp: str
    indexed_object_count: int
    indexed_revision_count: int
    degraded: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalRebuildRequest:
    project_id: str
    actor: str
    novel_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalRebuildResult:
    status: RetrievalStatusSnapshot
    document_count: int
    replaced_marker_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalSearchRequest:
    project_id: str
    query: str
    novel_id: str | None = None
    limit: int = 5


@dataclass(frozen=True, slots=True)
class RetrievalMatchSnapshot:
    target_family: str
    target_object_id: str
    target_revision_id: str
    score: float
    summary_text: str
    ranking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    review_hints: tuple[str, ...]
    ranking_metadata: JSONObject


@dataclass(frozen=True, slots=True)
class RetrievalSearchResult:
    status: RetrievalStatusSnapshot
    matches: tuple[RetrievalMatchSnapshot, ...]
    warnings: tuple[str, ...]
    review_hints: tuple[str, ...]
