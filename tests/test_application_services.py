from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.runtime import (  # noqa: E402
    ChatMessageRequest,
    ChatTurnRequest,
    ExportArtifactRequest,
    GetChatSessionRequest,
    ImportRequest,
    ListReviewProposalsRequest,
    OpenChatSessionRequest,
    PublishExportRequest,
    ReadObjectRequest,
    ReviewTransitionRequest,
    ServiceMutationRequest,
    SkillExecutionRequest,
    SuperwriterApplicationService,
    SupportedDonor,
)


def test_application_service_routes_scene_mutations_through_canonical_api(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")

    mutation = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            payload={
                "novel_id": "nvl_demo",
                "event_id": "evt_demo",
                "title": "Clocktower meeting",
                "summary": "The courier reveals the forged seal before dawn.",
            },
            actor="author-1",
            source_surface="workbench",
            revision_reason="create structured scene",
        )
    )

    assert mutation.disposition == "auto_applied"
    assert mutation.policy_class == "scene_structured"
    assert mutation.target_object_id.startswith("scn_")
    assert mutation.canonical_revision_id is not None

    read_result = service.read_object(
        ReadObjectRequest(
            family="scene",
            object_id=mutation.target_object_id,
            include_revisions=True,
            include_mutations=True,
        )
    )

    assert read_result.head is not None
    assert read_result.head.payload == {
        "novel_id": "nvl_demo",
        "event_id": "evt_demo",
        "title": "Clocktower meeting",
        "summary": "The courier reveals the forged seal before dawn.",
    }
    assert [revision.revision_number for revision in read_result.revisions] == [1]
    assert len(read_result.mutations) == 1
    assert read_result.mutations[0].source_surface == "workbench"
    assert read_result.mutations[0].policy_class == "scene_structured"


def test_chat_turn_creates_typed_runtime_links_and_durable_mutation_records(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    session = service.open_chat_session(
        OpenChatSessionRequest(
            project_id="prj_demo",
            novel_id="nvl_demo",
            title="Draft assistant",
            runtime_origin="web",
            created_by="author-1",
        )
    )

    turn = service.process_chat_turn(
        ChatTurnRequest(
            session_id=session.session_id,
            project_id="prj_demo",
            novel_id="nvl_demo",
            title="Draft assistant",
            runtime_origin="web",
            created_by="author-1",
            user_message=ChatMessageRequest(
                chat_message_id="msg_user_1",
                chat_role="user",
                payload={"text": "Create the next scene."},
            ),
            assistant_message=ChatMessageRequest(
                chat_message_id="msg_assistant_1",
                chat_role="assistant",
                payload={"text": "Created a new scene through the service layer."},
            ),
            mutation_requests=(
                ServiceMutationRequest(
                    target_family="scene",
                    payload={
                        "novel_id": "nvl_demo",
                        "event_id": "evt_demo_2",
                        "title": "Harbor escape",
                        "summary": "They swap ledgers on the foggy pier.",
                    },
                    actor="author-1",
                    source_surface="chat_surface",
                    revision_reason="chat-requested scene create",
                ),
            ),
        )
    )

    assert len(turn.mutation_results) == 1
    mutation = turn.mutation_results[0]
    assert mutation.canonical_revision_id is not None

    chat_session = service.get_chat_session(GetChatSessionRequest(session_id=session.session_id))
    assert [message.chat_role for message in chat_session.messages] == ["user", "assistant"]
    assert chat_session.messages[1].linked_object_id == mutation.target_object_id
    assert chat_session.messages[1].linked_revision_id == mutation.canonical_revision_id

    read_result = service.read_object(
        ReadObjectRequest(
            family="scene",
            object_id=mutation.target_object_id,
            include_mutations=True,
        )
    )
    assert read_result.mutations[0].source_surface == "chat_surface"


def test_public_application_api_rejects_lower_level_write_bypass_surface(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")

    unsupported_bypass_names = (
        "write_canonical_object",
        "create_derived_record",
        "create_proposal_record",
        "create_approval_record",
        "create_chat_session",
        "create_chat_message_link",
        "storage",
        "policy_engine",
    )
    for attribute_name in unsupported_bypass_names:
        assert not hasattr(service, attribute_name)
        with pytest.raises(AttributeError):
            getattr(service, attribute_name)

    assert callable(service.apply_mutation)
    assert callable(service.process_chat_turn)
    assert callable(service.open_chat_session)


def test_import_review_export_and_skill_flows_share_one_canonical_service_surface(tmp_path: Path) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    donor_root = tmp_path / "donor-project"
    donor_state_dir = donor_root / ".webnovel"
    donor_state_dir.mkdir(parents=True)
    state_path = donor_state_dir / "state.json"
    _ = state_path.write_text(
        json.dumps(
            {
                "project": {"id": "legacy-project", "title": "Legacy Project"},
                "novel": {"id": "legacy-novel", "title": "Legacy Novel", "genre": "mystery"},
                "scenes": [
                    {
                        "id": "legacy-scene-1",
                        "event_id": "evt_legacy_1",
                        "title": "Warehouse discovery",
                        "summary": "The smuggler leaves the lock half-open.",
                    }
                ],
                "chapters": [
                    {
                        "source_scene_id": "legacy-scene-1",
                        "title": "Chapter 1",
                        "body": "The warehouse smelled of rain and iron.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    imported = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=donor_root,
            actor="importer-1",
        )
    )

    imported_novel = next(item for item in imported.imported_objects if item.family == "novel")
    imported_scene = next(item for item in imported.imported_objects if item.family == "scene")
    assert imported.project_id.startswith("prj_")
    assert imported_novel.object_id.startswith("nvl_")
    assert imported_scene.object_id.startswith("scn_")

    review_required = service.apply_mutation(
        ServiceMutationRequest(
            target_family="novel",
            target_object_id=imported_novel.object_id,
            payload={
                "project_id": imported.project_id,
                "title": "Legacy Novel Revised",
                "genre": "mystery",
            },
            actor="editor-1",
            source_surface="review_desk",
            revision_reason="rename imported novel",
        )
    )
    assert review_required.disposition == "review_required"
    assert review_required.proposal_id is not None

    proposals = service.list_review_proposals(
        ListReviewProposalsRequest(target_object_id=imported_novel.object_id)
    )
    assert len(proposals.proposals) == 1
    assert proposals.proposals[0].proposal_id == review_required.proposal_id

    review_transition = service.transition_review(
        ReviewTransitionRequest(
            proposal_id=review_required.proposal_id,
            created_by="reviewer-1",
            approval_state="approved",
            decision_payload={"note": "approved from review desk"},
        )
    )
    assert review_transition.proposal_id == review_required.proposal_id
    assert review_transition.approval_state == "approved"
    assert review_transition.resolution == "applied"

    updated_novel = service.read_object(
        ReadObjectRequest(family="novel", object_id=imported_novel.object_id)
    )
    assert updated_novel.head is not None
    assert updated_novel.head.payload["title"] == "Legacy Novel Revised"

    remaining_proposals = service.list_review_proposals(
        ListReviewProposalsRequest(target_object_id=imported_novel.object_id)
    )
    assert remaining_proposals.proposals == ()

    export_result = service.create_export_artifact(
        ExportArtifactRequest(
            actor="exporter-1",
            source_surface="publish_surface",
            source_scene_revision_id=imported_scene.revision_id,
            payload={
                "novel_id": imported_novel.object_id,
                "format": "markdown",
                "body": "# Legacy Novel Revised\n\nCompiled export.",
            },
        )
    )
    assert export_result.family == "export_artifact"
    assert export_result.object_id.startswith("exp_")

    published = service.publish_export(
        PublishExportRequest(
            project_id=imported.project_id,
            novel_id=imported_novel.object_id,
            actor="publisher-1",
            output_root=tmp_path / "publish-output",
            chapter_artifact_object_id=next(
                item.object_id for item in imported.imported_objects if item.family == "chapter_artifact"
            ),
            base_chapter_artifact_revision_id=next(
                item.revision_id for item in imported.imported_objects if item.family == "chapter_artifact"
            ),
            expected_source_scene_revision_id=imported_scene.revision_id,
        )
    )
    assert published.disposition == "published"
    assert published.export_result is not None
    assert published.publish_result is not None
    assert (Path(published.publish_result.bundle_path) / "manifest.json").exists()

    skill_result = service.execute_skill(
        SkillExecutionRequest(
            skill_name="scene-polish",
            actor="author-1",
            source_surface="skill_studio",
            mutation_request=ServiceMutationRequest(
                target_family="scene",
                payload={
                    "novel_id": imported_novel.object_id,
                    "event_id": "evt_skill_1",
                    "title": "Rooftop confession",
                    "summary": "The courier admits the ledger was copied, not stolen.",
                },
                actor="author-1",
                source_surface="ignored-by-skill-wrapper",
                revision_reason="skill-generated scene",
            ),
        )
    )

    assert skill_result.mutation_result is not None
    assert skill_result.mutation_result.disposition == "auto_applied"
    skill_read = service.read_object(
        ReadObjectRequest(
            family="scene",
            object_id=skill_result.mutation_result.target_object_id,
            include_mutations=True,
        )
    )
    assert skill_read.mutations[0].source_surface == "skill_studio"
    assert skill_read.mutations[0].skill_name == "scene-polish"
