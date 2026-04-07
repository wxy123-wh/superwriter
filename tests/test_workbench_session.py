"""
Tests for workbench session functionality.

Tests the multi-turn iteration support for workbenches, including:
- Session creation and management
- Candidate draft creation and selection
- Feedback submission and retrieval
"""

import tempfile
from pathlib import Path

import pytest

from core.runtime.storage import CanonicalStorage
from core.runtime.workbench_session import (
    CandidateDraft,
    FeedbackRecord,
    FeedbackType,
    SessionStatus,
    WorkbenchSession,
    WorkbenchType,
)
from core.ai.partial_modifier import SectionTarget


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = CanonicalStorage(db_path)
        yield storage


@pytest.fixture
def sample_session_id(temp_db: CanonicalStorage) -> str:
    """Create a sample workbench session for testing."""
    session_id = temp_db.create_workbench_session(
        project_id="prj_test",
        novel_id="nvl_test",
        workbench_type=WorkbenchType.SCENE_TO_CHAPTER.value,
        parent_object_id="scn_001",
        actor="test_user",
        source_surface="test_workbench",
    )
    return session_id


class TestWorkbenchSessionModel:
    """Test the WorkbenchSession data model."""

    def test_session_creation(self):
        """Test creating a WorkbenchSession instance."""
        session = WorkbenchSession(
            session_id="wbs_001",
            workbench_type=WorkbenchType.SCENE_TO_CHAPTER.value,
            project_id="prj_test",
            novel_id="nvl_test",
            parent_object_id="scn_001",
            actor="test_user",
            started_at="2024-01-01T00:00:00Z",
            current_iteration=1,
            status=SessionStatus.ACTIVE.value,
        )
        assert session.session_id == "wbs_001"
        assert session.is_active
        assert not session.is_completed

    def test_session_status_properties(self):
        """Test session status properties."""
        active_session = WorkbenchSession(
            session_id="wbs_001",
            workbench_type="test",
            project_id="prj",
            novel_id="nvl",
            parent_object_id="obj",
            actor="user",
            started_at="2024-01-01T00:00:00Z",
            current_iteration=1,
            status=SessionStatus.ACTIVE.value,
        )
        assert active_session.is_active
        assert not active_session.is_completed

        completed_session = WorkbenchSession(
            session_id="wbs_002",
            workbench_type="test",
            project_id="prj",
            novel_id="nvl",
            parent_object_id="obj",
            actor="user",
            started_at="2024-01-01T00:00:00Z",
            current_iteration=3,
            status=SessionStatus.COMPLETED.value,
            completed_at="2024-01-01T01:00:00Z",
        )
        assert not completed_session.is_active
        assert completed_session.is_completed


class TestCandidateDraftModel:
    """Test the CandidateDraft data model."""

    def test_candidate_creation(self):
        """Test creating a CandidateDraft instance."""
        candidate = CandidateDraft(
            draft_id="cbd_001",
            session_id="wbs_001",
            iteration_number=1,
            payload={"title": "Test Chapter", "content": "Test content"},
            generation_context={"model": "gpt-4", "temperature": 0.7},
            is_selected=False,
            created_at="2024-01-01T00:00:00Z",
        )
        assert candidate.draft_id == "cbd_001"
        assert candidate.iteration_number == 1
        assert not candidate.is_selected

    def test_candidate_title_extraction(self):
        """Test title extraction from candidate payload."""
        candidate_with_title = CandidateDraft(
            draft_id="cbd_001",
            session_id="wbs_001",
            iteration_number=1,
            payload={"title": "My Chapter", "content": "..."},
            generation_context={},
            is_selected=False,
            created_at="2024-01-01T00:00:00Z",
        )
        assert candidate_with_title.title == "My Chapter"

        candidate_with_name = CandidateDraft(
            draft_id="cbd_002",
            session_id="wbs_001",
            iteration_number=1,
            payload={"name": "Scene Name", "description": "..."},
            generation_context={},
            is_selected=False,
            created_at="2024-01-01T00:00:00Z",
        )
        assert candidate_with_name.title == "Scene Name"

        candidate_with_content = CandidateDraft(
            draft_id="cbd_003",
            session_id="wbs_001",
            iteration_number=1,
            payload={"content": "This is a long content that needs truncation"},
            generation_context={},
            is_selected=False,
            created_at="2024-01-01T00:00:00Z",
        )
        assert candidate_with_content.title.startswith("This is a long content")


class TestFeedbackRecordModel:
    """Test the FeedbackRecord data model."""

    def test_feedback_creation(self):
        """Test creating a FeedbackRecord instance."""
        feedback = FeedbackRecord(
            feedback_id="wbf_001",
            session_id="wbs_001",
            target_draft_id="cbd_001",
            feedback_type=FeedbackType.REVISE.value,
            feedback_text="Make it more dramatic",
            target_section=None,
            created_at="2024-01-01T00:00:00Z",
            created_by="test_user",
        )
        assert feedback.feedback_id == "wbf_001"
        assert feedback.is_revision_request
        assert not feedback.is_partial_revision

    def test_partial_revision_feedback(self):
        """Test partial revision feedback."""
        partial_feedback = FeedbackRecord(
            feedback_id="wbf_002",
            session_id="wbs_001",
            target_draft_id="cbd_001",
            feedback_type=FeedbackType.PARTIAL_REVISION.value,
            feedback_text="Fix the dialogue",
            target_section="paragraph 3",
            created_at="2024-01-01T00:00:00Z",
            created_by="test_user",
        )
        assert partial_feedback.is_partial_revision
        assert partial_feedback.target_section == "paragraph 3"


class TestSectionTarget:
    """Test the SectionTarget model."""

    def test_section_target_with_index(self):
        """Test section target with index."""
        target = SectionTarget(section_type="paragraph", index=3, identifier=None, raw_match="paragraph 3")
        assert str(target) == "paragraph 3"

    def test_section_target_with_identifier(self):
        """Test section target with identifier."""
        target = SectionTarget(section_type="scene", index=None, identifier="intro", raw_match="intro scene")
        assert str(target) == "scene 'intro'"

    def test_section_target_without_index_or_identifier(self):
        """Test section target without index or identifier."""
        target = SectionTarget(section_type="chapter", index=None, identifier=None, raw_match="chapter")
        assert str(target) == "chapter"


class TestStorageWorkbenchMethods:
    """Test workbench session storage methods."""

    def test_create_workbench_session(self, temp_db: CanonicalStorage):
        """Test creating a workbench session."""
        session_id = temp_db.create_workbench_session(
            project_id="prj_test",
            novel_id="nvl_test",
            workbench_type=WorkbenchType.EVENT_TO_SCENE.value,
            parent_object_id="evt_001",
            actor="test_user",
        )
        assert session_id.startswith("wbs_")

        session = temp_db.get_workbench_session(session_id)
        assert session is not None
        assert session["project_id"] == "prj_test"
        assert session["novel_id"] == "nvl_test"
        assert session["workbench_type"] == WorkbenchType.EVENT_TO_SCENE.value
        assert session["parent_object_id"] == "evt_001"
        assert session["status"] == "active"
        assert session["current_iteration"] == 1

    def test_get_nonexistent_session(self, temp_db: CanonicalStorage):
        """Test getting a session that doesn't exist."""
        session = temp_db.get_workbench_session("wbs_nonexistent")
        assert session is None

    def test_list_workbench_sessions(self, temp_db: CanonicalStorage):
        """Test listing workbench sessions."""
        temp_db.create_workbench_session(
            project_id="prj_test",
            novel_id="nvl_test",
            workbench_type=WorkbenchType.OUTLINE_TO_PLOT.value,
            parent_object_id="out_001",
            actor="user1",
        )
        temp_db.create_workbench_session(
            project_id="prj_test",
            novel_id="nvl_test",
            workbench_type=WorkbenchType.PLOT_TO_EVENT.value,
            parent_object_id="plt_001",
            actor="user1",
        )

        sessions = temp_db.list_workbench_sessions(project_id="prj_test")
        assert len(sessions) == 2
        assert all(s["project_id"] == "prj_test" for s in sessions)

    def test_update_session_status(self, temp_db: CanonicalStorage, sample_session_id: str):
        """Test updating session status."""
        result = temp_db.update_workbench_session_status(sample_session_id, "completed")
        assert result is True

        session = temp_db.get_workbench_session(sample_session_id)
        assert session["status"] == "completed"
        assert session["completed_at"] is not None

    def test_increment_iteration(self, temp_db: CanonicalStorage, sample_session_id: str):
        """Test incrementing the iteration counter."""
        new_iteration = temp_db.increment_workbench_iteration(sample_session_id)
        assert new_iteration == 2

        session = temp_db.get_workbench_session(sample_session_id)
        assert session["current_iteration"] == 2

    def test_create_candidate_draft(self, temp_db: CanonicalStorage, sample_session_id: str):
        """Test creating a candidate draft."""
        draft_id = temp_db.create_candidate_draft(
            session_id=sample_session_id,
            iteration_number=1,
            payload={"title": "Test", "content": "Content"},
            generation_context={"model": "gpt-4"},
        )
        assert draft_id.startswith("cbd_")

        draft = temp_db.get_candidate_draft(draft_id)
        assert draft is not None
        assert draft["session_id"] == sample_session_id
        assert draft["iteration_number"] == 1
        assert draft["payload"]["title"] == "Test"
        assert not draft["is_selected"]

    def test_list_candidate_drafts(self, temp_db: CanonicalStorage, sample_session_id: str):
        """Test listing candidate drafts."""
        temp_db.create_candidate_draft(
            session_id=sample_session_id,
            iteration_number=1,
            payload={"title": "Draft 1"},
            generation_context={},
        )
        temp_db.create_candidate_draft(
            session_id=sample_session_id,
            iteration_number=1,
            payload={"title": "Draft 2"},
            generation_context={},
        )

        drafts = temp_db.list_candidate_drafts(sample_session_id)
        assert len(drafts) == 2

    def test_select_candidate_draft(self, temp_db: CanonicalStorage, sample_session_id: str):
        """Test selecting a candidate draft."""
        draft_id_1 = temp_db.create_candidate_draft(
            session_id=sample_session_id,
            iteration_number=1,
            payload={"title": "Draft 1"},
            generation_context={},
        )
        draft_id_2 = temp_db.create_candidate_draft(
            session_id=sample_session_id,
            iteration_number=1,
            payload={"title": "Draft 2"},
            generation_context={},
        )

        # Select first draft
        result = temp_db.select_candidate_draft(draft_id_1)
        assert result is True

        # Verify selection
        draft_1 = temp_db.get_candidate_draft(draft_id_1)
        draft_2 = temp_db.get_candidate_draft(draft_id_2)
        assert draft_1["is_selected"]
        assert not draft_2["is_selected"]

        # Select second draft (should deselect first)
        result = temp_db.select_candidate_draft(draft_id_2)
        assert result is True

        draft_1 = temp_db.get_candidate_draft(draft_id_1)
        draft_2 = temp_db.get_candidate_draft(draft_id_2)
        assert not draft_1["is_selected"]
        assert draft_2["is_selected"]

    def test_create_workbench_feedback(self, temp_db: CanonicalStorage, sample_session_id: str):
        """Test creating workbench feedback."""
        draft_id = temp_db.create_candidate_draft(
            session_id=sample_session_id,
            iteration_number=1,
            payload={"title": "Test"},
            generation_context={},
        )

        feedback_id = temp_db.create_workbench_feedback(
            session_id=sample_session_id,
            target_draft_id=draft_id,
            feedback_type=FeedbackType.REVISE.value,
            feedback_text="Make it better",
            created_by="test_user",
        )
        assert feedback_id.startswith("wbf_")

    def test_list_workbench_feedback(self, temp_db: CanonicalStorage, sample_session_id: str):
        """Test listing workbench feedback."""
        draft_id = temp_db.create_candidate_draft(
            session_id=sample_session_id,
            iteration_number=1,
            payload={"title": "Test"},
            generation_context={},
        )

        temp_db.create_workbench_feedback(
            session_id=sample_session_id,
            target_draft_id=draft_id,
            feedback_type=FeedbackType.REVISE.value,
            feedback_text="Fix it",
            created_by="user1",
        )
        temp_db.create_workbench_feedback(
            session_id=sample_session_id,
            target_draft_id=draft_id,
            feedback_type=FeedbackType.ACCEPT.value,
            feedback_text="Good",
            created_by="user2",
        )

        feedback_list = temp_db.list_workbench_feedback(sample_session_id)
        assert len(feedback_list) == 2
        assert feedback_list[0]["feedback_text"] == "Fix it"
        assert feedback_list[1]["feedback_text"] == "Good"
