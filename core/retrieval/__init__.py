from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TypeAlias, cast

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]

_LATIN_PATTERN = re.compile(r"[a-z0-9]+")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")
_TEXT_FIELDS = (
    "title",
    "chapter_title",
    "summary",
    "body",
    "fact",
    "rule",
    "instruction",
    "state",
    "name",
    "genre",
)


@dataclass(frozen=True, slots=True)
class RetrievalSourceRecord:
    family: str
    object_id: str
    revision_id: str
    revision_number: int
    project_id: str | None
    novel_id: str | None
    payload: JSONObject
    revision_count: int


@dataclass(frozen=True, slots=True)
class RetrievalSupportDocument:
    target_family: str
    target_object_id: str
    target_revision_id: str
    marker_payload: JSONObject


@dataclass(frozen=True, slots=True)
class RetrievalBuildReport:
    build_consistency_stamp: str
    canonical_object_count: int
    canonical_revision_count: int
    warning_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalIndexedDocument:
    target_family: str
    target_object_id: str
    target_revision_id: str
    search_text: str
    terms: tuple[str, ...]
    summary_text: str
    ranking_metadata: JSONObject


@dataclass(frozen=True, slots=True)
class RetrievalRankedDocument:
    target_family: str
    target_object_id: str
    target_revision_id: str
    score: float
    summary_text: str
    ranking_reasons: tuple[str, ...]
    ranking_metadata: JSONObject


def build_support_documents(
    sources: tuple[RetrievalSourceRecord, ...],
    *,
    scope_project_id: str,
    scope_novel_id: str | None,
) -> tuple[tuple[RetrievalSupportDocument, ...], RetrievalBuildReport]:
    warnings: list[str] = []
    documents: list[RetrievalSupportDocument] = []
    canonical_revision_count = 0

    for source in sources:
        canonical_revision_count += source.revision_count
        consistency_stamp = source_consistency_stamp(source)
        summary_text = summarize_payload(source.payload, source.object_id)
        search_text = build_search_text(source.family, source.object_id, source.payload)
        terms = tuple(sorted(set(_tokenize(search_text))))
        if not terms:
            warnings.append(f"{source.family}:{source.object_id} has no indexed terms; retrieval falls back to object identity only")
        documents.append(
            RetrievalSupportDocument(
                target_family=source.family,
                target_object_id=source.object_id,
                target_revision_id=source.revision_id,
                marker_payload={
                    "project_id": scope_project_id,
                    "novel_id": scope_novel_id,
                    "target_family": source.family,
                    "target_object_id": source.object_id,
                    "target_revision_id": source.revision_id,
                    "target_revision_number": source.revision_number,
                    "support_only": True,
                    "rebuildable": True,
                    "source_kind": "canonical_objects_and_revisions",
                    "revision_count": source.revision_count,
                    "consistency_stamp": consistency_stamp,
                    "summary_text": summary_text,
                    "search_text": search_text,
                    "terms": list(terms),
                    "ranking_metadata": {
                        "family": source.family,
                        "revision_number": source.revision_number,
                    },
                },
            )
        )

    report = RetrievalBuildReport(
        build_consistency_stamp=scope_consistency_stamp(sources),
        canonical_object_count=len(sources),
        canonical_revision_count=canonical_revision_count,
        warning_count=len(warnings),
        warnings=tuple(dict.fromkeys(warnings)),
    )
    return tuple(documents), report


def build_indexed_documents(marker_payloads: tuple[JSONObject, ...]) -> tuple[RetrievalIndexedDocument, ...]:
    documents: list[RetrievalIndexedDocument] = []
    for payload in marker_payloads:
        search_text = _raw_string_value(payload.get("search_text"))
        raw_terms = payload.get("terms")
        terms = tuple(
            sorted(
                {
                    str(item).strip().lower()
                    for item in raw_terms
                    if isinstance(item, str) and item.strip()
                }
            )
        ) if isinstance(raw_terms, list) else tuple(_tokenize(search_text))
        ranking_metadata = payload.get("ranking_metadata")
        documents.append(
            RetrievalIndexedDocument(
                target_family=_raw_string_value(payload.get("target_family")),
                target_object_id=_raw_string_value(payload.get("target_object_id")),
                target_revision_id=_raw_string_value(payload.get("target_revision_id")),
                search_text=search_text.lower(),
                terms=terms,
                summary_text=_raw_string_value(payload.get("summary_text")),
                ranking_metadata=ranking_metadata if isinstance(ranking_metadata, dict) else {},
            )
        )
    return tuple(documents)


def rank_support_documents(
    query: str,
    documents: tuple[RetrievalIndexedDocument, ...],
) -> tuple[RetrievalRankedDocument, ...]:
    normalized_query = query.strip().lower()
    query_terms = set(_tokenize(normalized_query))
    ranked: list[RetrievalRankedDocument] = []
    for document in documents:
        keyword_overlap = len(query_terms & set(document.terms))
        phrase_match = 1 if normalized_query and normalized_query in document.search_text else 0
        prefix_hits = sum(1 for term in document.terms if any(term.startswith(query_term) for query_term in query_terms))
        score = float(keyword_overlap * 100 + phrase_match * 40 + prefix_hits * 10)
        reasons: list[str] = []
        if keyword_overlap:
            reasons.append(f"{keyword_overlap} query term(s) matched indexed support terms")
        if phrase_match:
            reasons.append("exact query phrase matched indexed support text")
        if prefix_hits and not phrase_match:
            reasons.append(f"{prefix_hits} prefix match(es) helped rank the result")
        if not reasons:
            reasons.append("kept as a low-confidence fallback from support-only recall")
        ranking_metadata = dict(document.ranking_metadata)
        ranking_metadata["keyword_overlap"] = keyword_overlap
        ranking_metadata["phrase_match"] = phrase_match
        ranking_metadata["prefix_hits"] = prefix_hits
        ranking_metadata["query_terms"] = cast(list[JSONValue], list(sorted(query_terms)))
        ranking_metadata["support_only"] = True
        ranked.append(
            RetrievalRankedDocument(
                target_family=document.target_family,
                target_object_id=document.target_object_id,
                target_revision_id=document.target_revision_id,
                score=score,
                summary_text=document.summary_text,
                ranking_reasons=tuple(reasons),
                ranking_metadata=ranking_metadata,
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.target_family, item.target_object_id, item.target_revision_id))
    return tuple(ranked)


def scope_consistency_stamp(sources: tuple[RetrievalSourceRecord, ...]) -> str:
    digest = hashlib.sha1()
    for source in sorted(sources, key=lambda item: (item.family, item.object_id, item.revision_id)):
        digest.update(source_consistency_stamp(source).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]


def source_consistency_stamp(source: RetrievalSourceRecord) -> str:
    return f"{source.family}:{source.object_id}:{source.revision_id}:{source.revision_number}:{source.revision_count}"


def summarize_payload(payload: JSONObject, object_id: str) -> str:
    for field_name in _TEXT_FIELDS:
        value = payload.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return object_id


def build_search_text(family: str, object_id: str, payload: JSONObject) -> str:
    fragments = [family, object_id]
    for field_name in _TEXT_FIELDS:
        value = payload.get(field_name)
        if isinstance(value, str) and value.strip():
            fragments.append(value.strip())
    return " ".join(fragments).strip().lower()


def _tokenize(text: str) -> tuple[str, ...]:
    """Tokenize text into searchable terms supporting CJK and Latin scripts.

    For CJK characters: produces unigrams and bigrams for better recall.
    For Latin text: produces lowercase alphanumeric tokens.
    """
    lowered = text.lower()
    tokens: set[str] = set()

    # Latin tokens
    for match in _LATIN_PATTERN.finditer(lowered):
        tokens.add(match.group(0))

    # CJK unigrams and bigrams
    for match in _CJK_PATTERN.finditer(lowered):
        segment = match.group(0)
        for i, ch in enumerate(segment):
            tokens.add(ch)  # unigram
            if i + 1 < len(segment):
                tokens.add(segment[i : i + 2])  # bigram

    return tuple(sorted(tokens))


def _raw_string_value(value: JSONValue) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "RetrievalBuildReport",
    "RetrievalIndexedDocument",
    "RetrievalRankedDocument",
    "RetrievalSourceRecord",
    "RetrievalSupportDocument",
    "build_indexed_documents",
    "build_search_text",
    "build_support_documents",
    "scope_consistency_stamp",
    "source_consistency_stamp",
    "summarize_payload",
    "rank_support_documents",
]
