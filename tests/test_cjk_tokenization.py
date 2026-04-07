"""Tests for CJK tokenization in the retrieval system."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.retrieval import (
    _tokenize,
    build_search_text,
    rank_support_documents,
    build_indexed_documents,
    RetrievalSourceRecord,
    RetrievalIndexedDocument,
    build_support_documents,
)


def test_tokenize_pure_chinese() -> None:
    """Chinese characters produce unigrams and bigrams."""
    tokens = _tokenize("大唐盛世")
    # Unigrams: 大, 唐, 盛, 世
    # Bigrams: 大唐, 唐盛, 盛世
    assert "大" in tokens
    assert "唐" in tokens
    assert "盛" in tokens
    assert "世" in tokens
    assert "大唐" in tokens
    assert "唐盛" in tokens
    assert "盛世" in tokens


def test_tokenize_mixed_chinese_english() -> None:
    """Mixed CJK and Latin text is tokenized correctly."""
    tokens = _tokenize("scene1 大纲节点 outline")
    # Latin tokens
    assert "scene1" in tokens
    assert "outline" in tokens
    # CJK unigrams
    assert "大" in tokens
    assert "纲" in tokens
    assert "节" in tokens
    assert "点" in tokens
    # CJK bigrams
    assert "大纲" in tokens
    assert "纲节" in tokens
    assert "节点" in tokens


def test_tokenize_pure_latin_unchanged() -> None:
    """Latin-only text behaves like the original tokenizer."""
    tokens = _tokenize("broken seal at the quay")
    assert "broken" in tokens
    assert "seal" in tokens
    assert "at" in tokens
    assert "the" in tokens
    assert "quay" in tokens


def test_tokenize_single_chinese_char() -> None:
    """Single CJK character produces only a unigram, no bigram."""
    tokens = _tokenize("书")
    assert "书" in tokens
    assert len(tokens) == 1


def test_tokenize_empty_string() -> None:
    """Empty string produces no tokens."""
    tokens = _tokenize("")
    assert len(tokens) == 0


def test_build_search_text_includes_chinese() -> None:
    """Chinese content from payloads is included in search text."""
    search_text = build_search_text(
        "scene", "scn_001",
        {"title": "月下独行", "summary": "在月光下独自走过长街"},
    )
    assert "月" in search_text
    assert "月下" in search_text
    assert "独行" in search_text


def test_chinese_ranking() -> None:
    """Chinese queries match against Chinese-indexed documents."""
    source = RetrievalSourceRecord(
        family="scene",
        object_id="scn_cjk_001",
        revision_id="rev_001",
        revision_number=1,
        project_id="prj_001",
        novel_id="nvl_001",
        payload={"title": "月下独行", "summary": "在月光下独自走过长街"},
        revision_count=1,
    )
    documents, _ = build_support_documents(
        (source,),
        scope_project_id="prj_001",
        scope_novel_id="nvl_001",
    )
    marker_payloads = tuple(d.marker_payload for d in documents)
    indexed = build_indexed_documents(marker_payloads)

    results = rank_support_documents("月光长街", indexed)
    assert len(results) > 0
    assert results[0].target_object_id == "scn_cjk_001"
    assert results[0].score > 0


def test_chinese_ranking_beats_irrelevant() -> None:
    """Chinese query ranks relevant Chinese content higher than irrelevant."""
    source_relevant = RetrievalSourceRecord(
        family="scene",
        object_id="scn_relevant",
        revision_id="rev_r",
        revision_number=1,
        project_id="prj_001",
        novel_id="nvl_001",
        payload={"title": "密室之谜", "summary": "在密室中发现了一封密信"},
        revision_count=1,
    )
    source_irrelevant = RetrievalSourceRecord(
        family="scene",
        object_id="scn_irrelevant",
        revision_id="rev_i",
        revision_number=1,
        project_id="prj_001",
        novel_id="nvl_001",
        payload={"title": "海边日落", "summary": "夕阳下的海边渔船"},
        revision_count=1,
    )
    documents, _ = build_support_documents(
        (source_relevant, source_irrelevant),
        scope_project_id="prj_001",
        scope_novel_id="nvl_001",
    )
    marker_payloads = tuple(d.marker_payload for d in documents)
    indexed = build_indexed_documents(marker_payloads)

    results = rank_support_documents("密室密信", indexed)
    assert len(results) >= 2
    assert results[0].target_object_id == "scn_relevant"
    assert results[0].score > results[1].score
