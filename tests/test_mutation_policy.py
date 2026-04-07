from __future__ import annotations

import json
from sqlite3 import Row
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.runtime import CanonicalStorage, DerivedRecordInput
from core.runtime.mutation_policy import (
    ChapterMutationSignals,
    MutationDisposition,
    MutationPolicyClass,
    MutationPolicyEngine,
    MutationRequest,
)


def _seed_scene(storage: CanonicalStorage) -> tuple[str, str]:
    engine = MutationPolicyEngine(storage)
    result = engine.apply_mutation(
        MutationRequest(
            target_family="scene",
            payload={
                "novel_id": "nvl_demo",
                "event_id": "evt_demo",
                "title": "Lantern alley confrontation",
                "summary": "The heroine corners the courier before dawn.",
            },
            actor="author-1",
            source_surface="chat_agent",
            revision_reason="seed scene",
        )
    )
    if result.canonical_revision_id is None:
        raise AssertionError("scene seed should produce a canonical revision")
    return result.target_object_id, result.canonical_revision_id


def test_scene_structured_mutations_auto_apply_via_canonical_write_path(tmp_path: Path) -> None:
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")
    engine = MutationPolicyEngine(storage)

    result = engine.apply_mutation(
        MutationRequest(
            target_family="scene",
            payload={
                "novel_id": "nvl_demo",
                "event_id": "evt_demo",
                "title": "Bridge meeting",
                "summary": "The witness hands over the sealed ledger.",
            },
            actor="author-1",
            source_surface="chat_agent",
            revision_reason="create scene",
        )
    )

    assert result.disposition is MutationDisposition.AUTO_APPLIED
    assert result.policy_class is MutationPolicyClass.SCENE_STRUCTURED
    assert result.target_object_id.startswith("scn_")
    assert result.canonical_revision_id is not None
    assert result.mutation_record_id is not None

    head = storage.fetch_canonical_head("scene", result.target_object_id)
    assert head is not None
    assert head["payload"] == {
        "novel_id": "nvl_demo",
        "event_id": "evt_demo",
        "title": "Bridge meeting",
        "summary": "The witness hands over the sealed ledger.",
    }

    mutations = storage.fetch_mutation_records(result.target_object_id)
    assert len(mutations) == 1
    assert mutations[0]["policy_class"] == "scene_structured"
    assert mutations[0]["approval_state"] == "auto_applied"


def test_safe_chapter_prose_edits_auto_apply_as_derived_artifact_revision(tmp_path: Path) -> None:
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")
    scene_id, scene_revision_id = _seed_scene(storage)
    initial_artifact_revision_id = storage.create_derived_record(
        DerivedRecordInput(
            family="chapter_artifact",
            payload={
                "novel_id": "nvl_demo",
                "source_scene_id": scene_id,
                "source_scene_revision_id": scene_revision_id,
                "chapter_title": "Chapter 1",
                "body": "Lantern light washed over the stones.",
            },
            source_scene_revision_id=scene_revision_id,
            created_by="author-1",
        )
    )
    artifact_object_id = storage.fetch_derived_records("chapter_artifact")[0]["object_id"]
    engine = MutationPolicyEngine(storage)

    result = engine.apply_mutation(
        MutationRequest(
            target_family="chapter_artifact",
            target_object_id=str(artifact_object_id),
            base_revision_id=initial_artifact_revision_id,
            source_scene_revision_id=scene_revision_id,
            base_source_scene_revision_id=scene_revision_id,
            payload={
                "novel_id": "nvl_demo",
                "source_scene_id": scene_id,
                "source_scene_revision_id": scene_revision_id,
                "chapter_title": "Chapter 1",
                "body": "Lantern light poured over the stones, softening every sharp edge.",
            },
            actor="author-1",
            source_surface="chat_agent",
            chapter_signals=ChapterMutationSignals(
                prose_only=True,
                preserves_facts=True,
                preserves_event_order=True,
                preserves_reveal_order=True,
                preserves_character_decisions=True,
                preserves_continuity=True,
            ),
        )
    )

    assert result.disposition is MutationDisposition.AUTO_APPLIED
    assert result.policy_class is MutationPolicyClass.CHAPTER_PROSE_STYLE
    assert result.artifact_revision_id is not None
    assert result.target_object_id == artifact_object_id

    derived_rows = storage.fetch_derived_records("chapter_artifact")
    assert len(derived_rows) == 2
    assert [row["object_id"] for row in derived_rows] == [artifact_object_id, artifact_object_id]
    updated_row = next(
        row for row in derived_rows if row["artifact_revision_id"] == result.artifact_revision_id
    )
    assert updated_row["source_scene_revision_id"] == scene_revision_id
    assert updated_row["payload"] == {
        "novel_id": "nvl_demo",
        "source_scene_id": scene_id,
        "source_scene_revision_id": scene_revision_id,
        "chapter_title": "Chapter 1",
        "body": "Lantern light poured over the stones, softening every sharp edge.",
    }

    with storage.connect() as connection:
        proposal_count_row = cast(Row, connection.execute("SELECT COUNT(*) FROM proposals").fetchone())
        proposal_count_value = cast(int | float | str, proposal_count_row[0])
        proposal_count = int(proposal_count_value)
    assert proposal_count == 0


def test_ambiguous_chapter_edits_downgrade_to_review_proposal(tmp_path: Path) -> None:
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")
    scene_id, scene_revision_id = _seed_scene(storage)
    initial_artifact_revision_id = storage.create_derived_record(
        DerivedRecordInput(
            family="chapter_artifact",
            payload={
                "novel_id": "nvl_demo",
                "source_scene_id": scene_id,
                "source_scene_revision_id": scene_revision_id,
                "chapter_title": "Chapter 1",
                "body": "She accepts the bargain in silence.",
            },
            source_scene_revision_id=scene_revision_id,
            created_by="author-1",
        )
    )
    artifact_object_id = storage.fetch_derived_records("chapter_artifact")[0]["object_id"]
    engine = MutationPolicyEngine(storage)

    result = engine.apply_mutation(
        MutationRequest(
            target_family="chapter_artifact",
            target_object_id=str(artifact_object_id),
            base_revision_id=initial_artifact_revision_id,
            source_scene_revision_id=scene_revision_id,
            base_source_scene_revision_id=scene_revision_id,
            payload={
                "novel_id": "nvl_demo",
                "source_scene_id": scene_id,
                "source_scene_revision_id": scene_revision_id,
                "chapter_title": "Chapter 1",
                "body": "She rejects the bargain, storms away, and reveals the hidden key.",
            },
            actor="author-1",
            source_surface="chat_agent",
            chapter_signals=ChapterMutationSignals(
                prose_only=False,
                preserves_facts=False,
                preserves_event_order=True,
                preserves_reveal_order=False,
                preserves_character_decisions=False,
                preserves_continuity=False,
                mixed_with_structural_edit=True,
                ambiguous_intent=True,
            ),
        )
    )

    assert result.disposition is MutationDisposition.REVIEW_REQUIRED
    assert result.policy_class is MutationPolicyClass.CHAPTER_STRUCTURAL
    assert result.proposal_id is not None
    assert result.artifact_revision_id is None

    derived_rows = storage.fetch_derived_records("chapter_artifact")
    assert len(derived_rows) == 1

    with storage.connect() as connection:
        proposal_row = cast(
            Row,
            connection.execute(
            "SELECT target_family, target_object_id, base_revision_id, proposal_payload_json FROM proposals WHERE record_id = ?",
            (result.proposal_id,),
            ).fetchone(),
        )

    assert proposal_row["target_family"] == "chapter_artifact"
    assert proposal_row["target_object_id"] == artifact_object_id
    assert proposal_row["base_revision_id"] == initial_artifact_revision_id

    proposal_payload_raw = str(cast(object, proposal_row["proposal_payload_json"]))
    proposal_payload = cast(dict[str, object], json.loads(proposal_payload_raw))
    wrapped_payload = cast(dict[str, object], proposal_payload["payload"])
    chapter_signals = cast(dict[str, object], wrapped_payload["chapter_signals"])
    reasons = cast(list[str], proposal_payload["reasons"])
    assert proposal_payload["policy_class"] == "chapter_structural"
    assert proposal_payload["base_source_scene_revision_id"] == scene_revision_id
    assert proposal_payload["source_scene_revision_id"] == scene_revision_id
    assert chapter_signals["mixed_with_structural_edit"] is True
    assert "chapter edit may change facts" in reasons
    assert "chapter edit intent is ambiguous" in reasons
