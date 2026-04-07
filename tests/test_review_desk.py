from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import BookCommandCenter  # noqa: E402
from core.runtime import (  # noqa: E402
    ChapterMutationSignals,
    ListReviewProposalsRequest,
    OutlineToPlotWorkbenchRequest,
    ReadObjectRequest,
    ReviewDeskRequest,
    ReviewTransitionRequest,
    SceneToChapterWorkbenchRequest,
    ServiceMutationRequest,
    SuperwriterApplicationService,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402


def test_review_desk_approve_applies_chapter_proposal_exactly_once(tmp_path: Path) -> None:
    service, project_id, novel_id, _, _, artifact_object_id, proposal_id = _seed_chapter_review_proposal(tmp_path)

    first = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-1",
            approval_state="approved",
            decision_payload={"note": "Ship this revision."},
        )
    )
    assert first.resolution == "applied"
    assert first.artifact_revision_id is not None

    artifacts_after_first = [
        artifact
        for artifact in service.list_derived_artifacts("chapter_artifact")
        if artifact.object_id == artifact_object_id
    ]
    assert len(artifacts_after_first) == 2

    replay = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-2",
            approval_state="approved",
        )
    )
    assert replay.resolution == "already_applied"
    assert replay.artifact_revision_id == first.artifact_revision_id

    artifacts_after_replay = [
        artifact
        for artifact in service.list_derived_artifacts("chapter_artifact")
        if artifact.object_id == artifact_object_id
    ]
    assert len(artifacts_after_replay) == 2

    desk = service.get_review_desk(ReviewDeskRequest(project_id=project_id, novel_id=novel_id))
    proposal = next(item for item in desk.proposals if item.proposal_id == proposal_id)
    assert proposal.approval_state == "approved"
    assert proposal.approval_state_detail == "Applied exactly once; replaying approval returns the original apply result."

    shell = BookCommandCenter(service)
    page = shell.render_route("/review-desk", project_id=project_id, novel_id=novel_id)
    assert page.status_code == 200
    assert "Applied exactly once" in page.body
    assert "渲染的散文差异" in page.body
    assert proposal_id in page.body


def test_review_desk_reject_and_revise_preserve_state_and_keep_revise_loops_visible(tmp_path: Path) -> None:
    service, project_id, novel_id, _, _, artifact_object_id, proposal_id = _seed_chapter_review_proposal(tmp_path)

    revise = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-1",
            approval_state="revise",
            decision_payload={"reason": "Tighten continuity before applying."},
        )
    )
    assert revise.approval_state == "revision_requested"
    assert revise.resolution == "recorded"

    unresolved = service.list_review_proposals(ListReviewProposalsRequest(target_object_id=artifact_object_id))
    assert [proposal.proposal_id for proposal in unresolved.proposals] == [proposal_id]

    reject = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-2",
            approval_state="rejected",
            decision_payload={"reason": "Continuity still breaks the scene timeline."},
        )
    )
    assert reject.approval_state == "rejected"
    assert reject.resolution == "recorded"

    artifacts = [
        artifact
        for artifact in service.list_derived_artifacts("chapter_artifact")
        if artifact.object_id == artifact_object_id
    ]
    assert len(artifacts) == 1

    desk = service.get_review_desk(ReviewDeskRequest(project_id=project_id, novel_id=novel_id))
    proposal = next(item for item in desk.proposals if item.proposal_id == proposal_id)
    assert proposal.approval_state == "rejected"
    assert [decision.approval_state for decision in proposal.decisions] == ["revision_requested", "rejected"]

    shell = BookCommandCenter(service)
    page = shell.render_route("/review-desk", project_id=project_id, novel_id=novel_id)
    assert "已请求修订 1 次" in page.body
    assert "Continuity still breaks the scene timeline." in page.body


def test_review_desk_blocks_stale_proposals_with_explicit_revision_drift(tmp_path: Path) -> None:
    service, project_id, novel_id, scene_id, _, artifact_object_id, proposal_id = _seed_chapter_review_proposal(tmp_path)

    scene_update = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            target_object_id=scene_id,
            payload={
                "novel_id": novel_id,
                "event_id": "evt_harbor_001",
                "title": "Glass Harbor",
                "summary": "The courier learns a witness saw the cracked seal before dawn.",
            },
            actor="author-1",
            source_surface="scene_editor",
            revision_reason="advance the source scene after proposal creation",
        )
    )
    assert scene_update.canonical_revision_id is not None

    stale = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-1",
            approval_state="approved",
            decision_payload={"note": "Try applying after drift."},
        )
    )
    assert stale.approval_state == "stale"
    assert stale.resolution == "stale"
    assert stale.drift_details is not None
    assert "source_scene" in stale.drift_details

    artifacts = [
        artifact
        for artifact in service.list_derived_artifacts("chapter_artifact")
        if artifact.object_id == artifact_object_id
    ]
    assert len(artifacts) == 1

    desk = service.get_review_desk(ReviewDeskRequest(project_id=project_id, novel_id=novel_id))
    proposal = next(item for item in desk.proposals if item.proposal_id == proposal_id)
    assert proposal.approval_state == "stale"
    assert proposal.is_stale is True
    assert "source_scene" in proposal.drift_details

    shell = BookCommandCenter(service)
    page = shell.render_route("/review-desk", project_id=project_id, novel_id=novel_id)
    assert "source_scene drifted" in page.body
    assert proposal_id in page.body


def test_review_desk_approve_replay_is_idempotent_for_upstream_scene_proposals(tmp_path: Path) -> None:
    service, project_id, novel_id, plot_id, plot_revision_id, proposal_id = _seed_plot_review_proposal(tmp_path)

    first = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-1",
            approval_state="approved",
            decision_payload={"note": "Apply the upstream rewrite."},
        )
    )
    assert first.resolution == "applied"
    assert first.canonical_revision_id is not None

    applied_plot = service.read_object(ReadObjectRequest(family="plot_node", object_id=plot_id))
    assert applied_plot.head is not None
    assert applied_plot.head.current_revision_id == first.canonical_revision_id
    assert applied_plot.head.payload["title"] == "Harbor Revelation"

    replay = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-2",
            approval_state="approved",
        )
    )
    assert replay.resolution == "already_applied"
    assert replay.canonical_revision_id == first.canonical_revision_id

    replayed_plot = service.read_object(ReadObjectRequest(family="plot_node", object_id=plot_id))
    assert replayed_plot.head is not None
    assert replayed_plot.head.current_revision_id == first.canonical_revision_id

    desk = service.get_review_desk(ReviewDeskRequest(project_id=project_id, novel_id=novel_id))
    proposal = next(item for item in desk.proposals if item.proposal_id == proposal_id)
    assert proposal.target_family == "plot_node"
    assert proposal.approval_state == "approved"
    assert proposal.approval_state_detail == "Applied exactly once; replaying approval returns the original apply result."
    assert proposal.revision_lineage["base_revision_id"] == plot_revision_id
    assert proposal.revision_lineage["current_revision_id"] == first.canonical_revision_id

    shell = BookCommandCenter(service)
    page = shell.render_route("/review-desk", project_id=project_id, novel_id=novel_id)
    assert page.status_code == 200
    assert "Applied exactly once" in page.body
    assert proposal_id in page.body


def test_review_desk_upstream_revise_then_reject_keeps_plot_proposal_visible_until_rejected(tmp_path: Path) -> None:
    service, project_id, novel_id, plot_id, plot_revision_id, proposal_id = _seed_plot_review_proposal(tmp_path)

    revise = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-1",
            approval_state="revise",
            decision_payload={"reason": "Clarify the harbor turning point before applying."},
        )
    )
    assert revise.approval_state == "revision_requested"
    assert revise.resolution == "recorded"

    unresolved = service.list_review_proposals(ListReviewProposalsRequest(target_object_id=plot_id))
    assert [proposal.proposal_id for proposal in unresolved.proposals] == [proposal_id]

    reject = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-2",
            approval_state="rejected",
            decision_payload={"reason": "The upstream plot rewrite still jumps past the clue setup."},
        )
    )
    assert reject.approval_state == "rejected"
    assert reject.resolution == "recorded"

    rejected_plot = service.read_object(ReadObjectRequest(family="plot_node", object_id=plot_id))
    assert rejected_plot.head is not None
    assert rejected_plot.head.current_revision_id == plot_revision_id
    assert rejected_plot.head.payload["title"] == "Old Harbor Draft"

    desk = service.get_review_desk(ReviewDeskRequest(project_id=project_id, novel_id=novel_id))
    proposal = next(item for item in desk.proposals if item.proposal_id == proposal_id)
    assert proposal.target_family == "plot_node"
    assert proposal.approval_state == "rejected"
    assert [decision.approval_state for decision in proposal.decisions] == ["revision_requested", "rejected"]
    assert proposal.approval_state_detail == "The upstream plot rewrite still jumps past the clue setup."

    shell = BookCommandCenter(service)
    page = shell.render_route("/review-desk", project_id=project_id, novel_id=novel_id)
    assert "已请求修订 1 次" in page.body
    assert "The upstream plot rewrite still jumps past the clue setup." in page.body
    assert proposal_id in page.body


def test_review_desk_upstream_proposal_blocks_stale_plot_drift_before_apply(tmp_path: Path) -> None:
    service, project_id, novel_id, plot_id, _, proposal_id = _seed_plot_review_proposal(tmp_path)

    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")
    drifted_plot = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="plot_node",
            object_id=plot_id,
            payload={
                "novel_id": novel_id,
                "outline_node_id": "out_harbor_plot_review",
                "title": "Harbor Revelation Revised Elsewhere",
            },
            actor="author-2",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="advance plot after proposal creation",
        )
    )

    stale = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=proposal_id,
            created_by="reviewer-1",
            approval_state="approved",
            decision_payload={"note": "Try applying after plot drift."},
        )
    )
    assert stale.approval_state == "stale"
    assert stale.resolution == "stale"
    assert stale.canonical_revision_id is None
    assert stale.drift_details is not None
    assert stale.drift_details["kind"] == "canonical_revision_drift"
    assert stale.drift_details["current_revision_id"] == drifted_plot.revision_id

    desk = service.get_review_desk(ReviewDeskRequest(project_id=project_id, novel_id=novel_id))
    proposal = next(item for item in desk.proposals if item.proposal_id == proposal_id)
    assert proposal.target_family == "plot_node"
    assert proposal.approval_state == "stale"
    assert proposal.is_stale is True
    assert proposal.drift_details["kind"] == "canonical_revision_drift"
    assert proposal.drift_details["current_revision_id"] == drifted_plot.revision_id
    assert proposal.approval_state_detail == "Revision drift detected; approval was blocked before mutating canonical state."

    shell = BookCommandCenter(service)
    page = shell.render_route("/review-desk", project_id=project_id, novel_id=novel_id)
    assert "current_revision_id" in page.body
    assert drifted_plot.revision_id in page.body
    assert proposal_id in page.body


def _seed_chapter_review_proposal(
    tmp_path: Path,
) -> tuple[SuperwriterApplicationService, str, str, str, str, str, str]:
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
    _ = storage.write_canonical_object(
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

    initial = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project.object_id,
            novel_id=novel.object_id,
            scene_object_id=scene.object_id,
            actor="author-1",
            expected_source_scene_revision_id=scene.revision_id,
        )
    )
    assert initial.artifact_object_id is not None
    assert initial.artifact_revision_id is not None

    _ = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="fact_state_record",
            object_id="fsr_harbor_new",
            payload={
                "novel_id": novel.object_id,
                "source_scene_id": scene.object_id,
                "fact": "A second witness saw the broken seal before sunrise.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed second canonical fact",
        )
    )

    rerun = service.generate_scene_to_chapter_workbench(
        SceneToChapterWorkbenchRequest(
            project_id=project.object_id,
            novel_id=novel.object_id,
            scene_object_id=scene.object_id,
            actor="author-1",
            expected_source_scene_revision_id=scene.revision_id,
            target_artifact_object_id=initial.artifact_object_id,
            base_artifact_revision_id=initial.artifact_revision_id,
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
    assert rerun.proposal_id is not None
    return (
        service,
        project.object_id,
        novel.object_id,
        scene.object_id,
        scene.revision_id,
        initial.artifact_object_id,
        rerun.proposal_id,
    )


def _seed_plot_review_proposal(
    tmp_path: Path,
) -> tuple[SuperwriterApplicationService, str, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_harbor_plot_review",
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
            object_id="nvl_harbor_plot_review",
            payload={"project_id": project.object_id, "title": "Harbor Ledger"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    outline = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="outline_node",
            object_id="out_harbor_plot_review",
            payload={
                "novel_id": novel.object_id,
                "title": "Harbor Revelation",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed outline",
        )
    )
    plot = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="plot_node",
            object_id="plt_harbor_plot_review",
            payload={
                "novel_id": novel.object_id,
                "outline_node_id": outline.object_id,
                "title": "Old Harbor Draft",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed plot",
        )
    )

    service = SuperwriterApplicationService.for_sqlite(db_path)
    rerun = service.generate_outline_to_plot_workbench(
        OutlineToPlotWorkbenchRequest(
            project_id=project.object_id,
            novel_id=novel.object_id,
            outline_node_object_id=outline.object_id,
            actor="author-1",
            expected_parent_revision_id=outline.revision_id,
            target_child_object_id=plot.object_id,
            base_child_revision_id=plot.revision_id,
        )
    )
    assert rerun.disposition == "review_required"
    assert rerun.proposal_id is not None
    return (
        service,
        project.object_id,
        novel.object_id,
        plot.object_id,
        plot.revision_id,
        rerun.proposal_id,
    )
