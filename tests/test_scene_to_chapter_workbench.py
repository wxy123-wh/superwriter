from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import BookCommandCenter  # noqa: E402
from core.runtime import (  # noqa: E402
    ChapterMutationSignals,
    ListReviewProposalsRequest,
    SceneToChapterWorkbenchRequest,
    ServiceMutationRequest,
    SuperwriterApplicationService,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected JSON object")
    return cast(dict[str, object], value)


def test_scene_to_chapter_workbench_generates_artifact_with_pinned_revision_and_visible_metadata(
    tmp_path: Path,
) -> None:
    service, project_id, novel_id, scene_id, scene_revision_id, style_rule_id, skill_id, fact_id = _seed_workbench_workspace(
        tmp_path
    )

    result = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            scene_object_id=scene_id,
            actor="author-1",
            expected_source_scene_revision_id=scene_revision_id,
        )
    )

    assert result.disposition == "generated"
    assert result.artifact_object_id is not None
    assert result.artifact_revision_id is not None
    assert result.proposal_id is None
    assert result.source_scene_revision_id == scene_revision_id
    assert result.chapter_payload["source_scene_revision_id"] == scene_revision_id
    assert result.lineage_payload == {
        "source_scene_id": scene_id,
        "source_scene_revision_id": scene_revision_id,
        "previous_artifact_revision_id": None,
    }
    delta_added = _json_object(result.delta_payload["added"])
    assert delta_added["chapter_title"] == "Glass Harbor"
    generation_context = _json_object(result.chapter_payload["generation_context"])
    assert generation_context == {
        "style_rule_ids": [style_rule_id],
        "skill_ids": [skill_id],
        "fact_ids": [fact_id],
    }
    assert "Style guidance:" in str(result.chapter_payload["body"])
    assert "Skill guidance:" in str(result.chapter_payload["body"])
    assert "Canonical facts:" in str(result.chapter_payload["body"])

    derived_rows = service.list_derived_artifacts("chapter_artifact")
    assert len(derived_rows) == 1
    assert derived_rows[0].source_scene_revision_id == scene_revision_id
    assert derived_rows[0].payload["lineage"] == result.lineage_payload

    shell = BookCommandCenter(service)
    page = shell.render_route("/workbench", project_id=project_id, novel_id=novel_id)
    assert page.status_code == 200
    assert "Scene → Chapter Workbench" in page.body
    assert scene_revision_id in page.body
    assert "lineage keys" in page.body
    assert "delta keys" in page.body


def test_scene_to_chapter_workbench_rejects_missing_or_stale_source_revision(tmp_path: Path) -> None:
    service, project_id, novel_id, scene_id, scene_revision_id, _, _, _ = _seed_workbench_workspace(tmp_path)

    with pytest.raises(KeyError):
        _ = service.generate_scene_to_chapter_workbench(
            SceneToChapterWorkbenchRequest(
                project_id=project_id,
                novel_id=novel_id,
                scene_object_id="scn_missing",
                actor="author-1",
                expected_source_scene_revision_id=scene_revision_id,
            )
        )

    update = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            target_object_id=scene_id,
            payload={
                "novel_id": novel_id,
                "event_id": "evt_harbor_001",
                "title": "Glass Harbor",
                "summary": "The courier learns the second seal is already broken.",
            },
            actor="author-1",
            source_surface="scene_editor",
            revision_reason="tighten scene summary",
        )
    )
    assert update.canonical_revision_id is not None

    with pytest.raises(ValueError, match="scene revision is stale"):
        _ = service.generate_scene_to_chapter_workbench(
            SceneToChapterWorkbenchRequest(
                project_id=project_id,
                novel_id=novel_id,
                scene_object_id=scene_id,
                actor="author-1",
                expected_source_scene_revision_id=scene_revision_id,
            )
        )


def test_scene_to_chapter_workbench_routes_unsafe_updates_into_review_desk(tmp_path: Path) -> None:
    service, project_id, novel_id, scene_id, scene_revision_id, _, _, _ = _seed_workbench_workspace(tmp_path)

    generated = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            scene_object_id=scene_id,
            actor="author-1",
            expected_source_scene_revision_id=scene_revision_id,
        )
    )
    assert generated.artifact_object_id is not None
    assert generated.artifact_revision_id is not None

    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")
    _ = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="fact_state_record",
            object_id="fsr_harbor_fact",
            payload={
                "novel_id": novel_id,
                "source_scene_id": scene_id,
                "fact": "A third witness saw the broken seal before sunrise.",
            },
            actor="author-1",
            source_surface="imported_fact",
            policy_class="import_contract:test",
            approval_state="imported",
            revision_reason="add a second canonical fact",
        )
    )

    rerun = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            scene_object_id=scene_id,
            actor="author-1",
            expected_source_scene_revision_id=scene_revision_id,
            target_artifact_object_id=generated.artifact_object_id,
            base_artifact_revision_id=generated.artifact_revision_id,
            chapter_signals=ChapterMutationSignals(
                prose_only=False,
                preserves_facts=False,
                preserves_event_order=True,
                preserves_reveal_order=True,
                preserves_character_decisions=True,
                preserves_continuity=False,
                mixed_with_structural_edit=True,
                ambiguous_intent=True,
            ),
        )
    )

    assert rerun.disposition == "review_required"
    assert rerun.proposal_id is not None
    assert rerun.artifact_revision_id is None
    assert rerun.review_route == f"/review-desk?project_id={project_id}&novel_id={novel_id}"
    delta_changed = _json_object(rerun.delta_payload["changed"])
    assert "body" in delta_changed

    derived_rows = service.list_derived_artifacts("chapter_artifact")
    assert len(derived_rows) == 1

    proposals = service.list_review_proposals(ListReviewProposalsRequest(target_object_id=generated.artifact_object_id))
    assert len(proposals.proposals) == 1
    assert proposals.proposals[0].proposal_id == rerun.proposal_id

    shell = BookCommandCenter(service)
    review_page = shell.render_route("/review-desk", project_id=project_id, novel_id=novel_id)
    assert review_page.status_code == 200
    assert rerun.proposal_id in review_page.body
    assert "Open Review Desk" in review_page.body


def _seed_workbench_workspace(
    tmp_path: Path,
) -> tuple[SuperwriterApplicationService, str, str, str, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_harbor",
            payload={"title": "Harbor Project"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed project",
        )
    )
    novel = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="novel",
            object_id="nvl_harbor",
            payload={"project_id": project.object_id, "title": "Harbor Ledger"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    scene = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="scene",
            object_id="scn_harbor",
            payload={
                "novel_id": novel.object_id,
                "event_id": "evt_harbor_001",
                "title": "Glass Harbor",
                "summary": "The courier slips into the harbor chapel with a sealed ledger.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed scene",
        )
    )
    style_rule = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="style_rule",
            object_id="sty_harbor_rule",
            payload={
                "novel_id": novel.object_id,
                "rule": "Favor quiet, observant sentences over melodrama",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed style rule",
        )
    )
    skill = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="skill",
            object_id="skl_harbor_skill",
            payload={
                "novel_id": novel.object_id,
                "skill_type": "style_rule",
                "scope": "scene_to_chapter",
                "instruction": "Keep close focal distance and keep the reveal late in the paragraph.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed scoped skill",
        )
    )
    fact = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="fact_state_record",
            object_id="fsr_harbor_seed",
            payload={
                "novel_id": novel.object_id,
                "source_scene_id": scene.object_id,
                "fact": "The seal is already cracked before the courier reaches the altar.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed canonical fact",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    return (
        service,
        project.object_id,
        novel.object_id,
        scene.object_id,
        scene.revision_id,
        style_rule.object_id,
        skill.object_id,
        fact.object_id,
    )
