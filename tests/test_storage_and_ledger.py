from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.objects.contract import CANONICAL_FAMILIES, DERIVED_FAMILIES, FAMILY_REGISTRY
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest, DerivedRecordInput


def test_storage_schema_tracks_family_categories_and_non_authoritative_rows(
    tmp_path: Path,
) -> None:
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")

    assert storage.list_tables() == (
        "ai_provider_config",
        "approval_records",
        "canonical_objects",
        "canonical_revisions",
        "chat_message_links",
        "chat_sessions",
        "derived_records",
        "family_catalog",
        "import_records",
        "metadata_markers",
        "mutation_records",
        "proposal_comments",
        "proposals",
        "workbench_candidate_drafts",
        "workbench_feedback",
        "workbench_sessions",
    )

    catalog = storage.get_family_catalog()
    assert set(catalog) == {contract.family for contract in FAMILY_REGISTRY}
    assert {family for family, row in catalog.items() if row["category"] == "canonical"} == set(CANONICAL_FAMILIES)
    assert {family for family, row in catalog.items() if row["category"] == "derived"} == set(DERIVED_FAMILIES)
    assert catalog["mutation_record"]["is_append_only"] == 1
    assert catalog["chat_session"]["is_linkage_only"] == 1

    _ = storage.create_derived_record(
        DerivedRecordInput(
            family="chapter_artifact",
            payload={"chapter_title": "Draft One"},
            source_scene_revision_id="rev_scene_0001",
            created_by="author",
        )
    )
    derived_rows = storage.fetch_derived_records("chapter_artifact")
    assert len(derived_rows) == 1
    assert derived_rows[0]["is_authoritative"] == 0
    assert derived_rows[0]["is_rebuildable"] == 1
    assert derived_rows[0]["source_scene_revision_id"] == "rev_scene_0001"


def test_canonical_write_appends_exactly_one_mutation_per_revision(tmp_path: Path) -> None:
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")

    first_write = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="novel",
            payload={"project_id": "prj_demo", "title": "Stone Garden", "status": "draft"},
            actor="author-1",
            source_surface="review_desk",
            skill="continuity-check",
            policy_class="manual_edit",
            approval_state="approved",
            revision_reason="initial seed",
        )
    )
    second_write = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="novel",
            object_id=first_write.object_id,
            payload={"project_id": "prj_demo", "title": "Stone Garden", "status": "approved"},
            actor="author-1",
            source_surface="review_desk",
            skill="continuity-check",
            policy_class="manual_edit",
            approval_state="approved",
            revision_reason="status change",
        )
    )

    head = storage.fetch_canonical_head("novel", first_write.object_id)
    assert head is not None
    assert head["current_revision_id"] == second_write.revision_id
    assert head["current_revision_number"] == 2
    assert head["payload"] == {
        "project_id": "prj_demo",
        "title": "Stone Garden",
        "status": "approved",
    }

    revisions = storage.fetch_canonical_revisions(first_write.object_id)
    assert [revision["revision_number"] for revision in revisions] == [1, 2]
    assert revisions[1]["parent_revision_id"] == first_write.revision_id

    mutations = storage.fetch_mutation_records(first_write.object_id)
    assert len(mutations) == 2
    assert [mutation["resulting_revision_number"] for mutation in mutations] == [1, 2]
    assert mutations[0]["target_object_family"] == "novel"
    assert mutations[0]["actor_id"] == "author-1"
    assert mutations[0]["source_surface"] == "review_desk"
    assert mutations[0]["skill_name"] == "continuity-check"
    assert mutations[0]["policy_class"] == "manual_edit"
    assert mutations[0]["approval_state"] == "approved"
    assert mutations[1]["diff_payload"] == {
        "added": {},
        "removed": {},
        "changed": {"status": {"before": "draft", "after": "approved"}},
    }


def test_canonical_write_rejects_derived_family_and_does_not_emit_ledger(tmp_path: Path) -> None:
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")

    try:
        _ = storage.write_canonical_object(
            CanonicalWriteRequest(
                family="chapter_artifact",
                payload={"chapter_title": "Should Fail"},
                actor="author-1",
                source_surface="pipeline_workbench",
                skill="draft-generator",
                policy_class="derived_artifact",
                approval_state="not_applicable",
            )
        )
    except ValueError as error:
        assert "derived" in str(error)
    else:
        raise AssertionError("Derived families must be rejected as canonical writes")

    assert storage.fetch_mutation_records("cha_fake") == []
