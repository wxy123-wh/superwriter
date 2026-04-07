"""
Tests for workbench iteration flow.

Tests the multi-turn iteration support for workbenches, including:
- Starting iteration sessions
- Submitting feedback and getting new candidates
- Selecting final candidates
"""

import tempfile
from pathlib import Path

import pytest

from core.runtime.application_services import (
    CandidateSelectionRequest,
    CandidateSelectionResult,
    ServiceMutationRequest,
    SuperwriterApplicationService,
    WorkbenchFeedbackRequest,
    WorkbenchFeedbackResult,
    WorkbenchIterationRequest,
    WorkbenchIterationResult,
)
from core.runtime.storage import CanonicalStorage
from core.runtime.workbench_session import SessionStatus, WorkbenchType


@pytest.fixture
def temp_storage():
    """Create a temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = CanonicalStorage(db_path)
        yield storage


@pytest.fixture
def service(temp_storage: CanonicalStorage):
    """Create an application service for testing."""
    return SuperwriterApplicationService(temp_storage)


@pytest.fixture
def sample_project(service: SuperwriterApplicationService):
    """Create a sample project and novel for testing."""
    # For workbench iteration tests, we only need the IDs
    # The actual objects don't need to exist for basic iteration testing
    return {
        "project_id": "prj_test",
        "novel_id": "nvl_test",
        "scene_id": "scn_test",
        "event_id": "evt_test",
    }


class TestWorkbenchIterationFlow:
    """Test the workbench iteration flow."""

    def test_start_workbench_iteration(
        self,
        service: SuperwriterApplicationService,
        sample_project: dict,
    ):
        """Test starting a workbench iteration session."""
        request = WorkbenchIterationRequest(
            project_id=sample_project["project_id"],
            novel_id=sample_project["novel_id"],
            workbench_type=WorkbenchType.SCENE_TO_CHAPTER.value,
            parent_object_id=sample_project["scene_id"],
            actor="test_user",
        )

        result = service.start_workbench_iteration(request)

        assert result.session_id.startswith("wbs_")
        assert result.workbench_type == WorkbenchType.SCENE_TO_CHAPTER.value
        assert result.parent_object_id == sample_project["scene_id"]
        assert result.iteration_number == 1
        assert len(result.initial_candidates) > 0

    def test_submit_workbench_feedback(
        self,
        service: SuperwriterApplicationService,
        sample_project: dict,
    ):
        """Test submitting feedback on a candidate."""
        # Start a session first
        iteration_request = WorkbenchIterationRequest(
            project_id=sample_project["project_id"],
            novel_id=sample_project["novel_id"],
            workbench_type=WorkbenchType.SCENE_TO_CHAPTER.value,
            parent_object_id=sample_project["scene_id"],
            actor="test_user",
        )
        iteration_result = service.start_workbench_iteration(iteration_request)

        # Get the first candidate
        first_candidate = iteration_result.initial_candidates[0]

        # Submit feedback
        feedback_request = WorkbenchFeedbackRequest(
            session_id=iteration_result.session_id,
            target_draft_id=first_candidate.draft_id,
            feedback_type="revise",
            feedback_text="Make it more dramatic",
            created_by="test_user",
        )

        feedback_result = service.submit_workbench_feedback(feedback_request)

        assert feedback_result.session_id == iteration_result.session_id
        assert feedback_result.new_iteration_number == 2
        assert len(feedback_result.new_candidates) > 0
        assert feedback_result.feedback_recorded_id.startswith("wbf_")

    def test_select_workbench_candidate(
        self,
        service: SuperwriterApplicationService,
        sample_project: dict,
    ):
        """Test selecting a final candidate."""
        # Start a session
        iteration_request = WorkbenchIterationRequest(
            project_id=sample_project["project_id"],
            novel_id=sample_project["novel_id"],
            workbench_type=WorkbenchType.SCENE_TO_CHAPTER.value,
            parent_object_id=sample_project["scene_id"],
            actor="test_user",
        )
        iteration_result = service.start_workbench_iteration(iteration_request)

        # Select the first candidate
        first_candidate = iteration_result.initial_candidates[0]
        selection_request = CandidateSelectionRequest(
            session_id=iteration_result.session_id,
            selected_draft_id=first_candidate.draft_id,
            actor="test_user",
            apply_to_canonical=False,  # Don't actually apply in tests
        )

        selection_result = service.select_workbench_candidate(selection_request)

        assert selection_result.session_id == iteration_result.session_id
        assert selection_result.selected_draft_id == first_candidate.draft_id
        assert selection_result.completion_status == "completed"

    def test_full_iteration_flow(
        self,
        service: SuperwriterApplicationService,
        sample_project: dict,
    ):
        """Test the complete iteration flow: start → feedback → select."""
        # 1. Start session
        iteration_request = WorkbenchIterationRequest(
            project_id=sample_project["project_id"],
            novel_id=sample_project["novel_id"],
            workbench_type=WorkbenchType.EVENT_TO_SCENE.value,
            parent_object_id="evt_test",  # Using a non-existent object for simplicity
            actor="test_user",
        )
        iteration_result = service.start_workbench_iteration(iteration_request)

        # 2. Submit feedback
        first_candidate = iteration_result.initial_candidates[0]
        feedback_request = WorkbenchFeedbackRequest(
            session_id=iteration_result.session_id,
            target_draft_id=first_candidate.draft_id,
            feedback_type="revise",
            feedback_text="Add more detail",
            created_by="test_user",
        )
        feedback_result = service.submit_workbench_feedback(feedback_request)

        assert feedback_result.new_iteration_number == 2

        # 3. Select final candidate
        revised_candidate = feedback_result.new_candidates[0]
        selection_request = CandidateSelectionRequest(
            session_id=iteration_result.session_id,
            selected_draft_id=revised_candidate.draft_id,
            actor="test_user",
            apply_to_canonical=False,
        )
        selection_result = service.select_workbench_candidate(selection_request)

        assert selection_result.completion_status == "completed"

        # Verify session is completed
        session = service._SuperwriterApplicationService__storage.get_workbench_session(
            iteration_result.session_id
        )
        assert session["status"] == "completed"

    def test_session_not_found_error(
        self,
        service: SuperwriterApplicationService,
    ):
        """Test error handling for non-existent session."""
        feedback_request = WorkbenchFeedbackRequest(
            session_id="wbs_nonexistent",
            target_draft_id="cbd_fake",
            feedback_type="revise",
            feedback_text="Test",
        )

        with pytest.raises(KeyError, match="Session not found"):
            service.submit_workbench_feedback(feedback_request)

    def test_draft_not_found_error(
        self,
        service: SuperwriterApplicationService,
        sample_project: dict,
    ):
        """Test error handling for non-existent draft."""
        # Start a session
        iteration_request = WorkbenchIterationRequest(
            project_id=sample_project["project_id"],
            novel_id=sample_project["novel_id"],
            workbench_type=WorkbenchType.PLOT_TO_EVENT.value,
            parent_object_id="plt_test",
            actor="test_user",
        )
        iteration_result = service.start_workbench_iteration(iteration_request)

        # Try to submit feedback on non-existent draft
        feedback_request = WorkbenchFeedbackRequest(
            session_id=iteration_result.session_id,
            target_draft_id="cbd_nonexistent",
            feedback_type="revise",
            feedback_text="Test",
        )

        with pytest.raises(KeyError, match="Draft not found"):
            service.submit_workbench_feedback(feedback_request)


class TestWorkbenchIterationDataStructures:
    """Test the data structures for workbench iteration."""

    def test_iteration_request_defaults(self):
        """Test WorkbenchIterationRequest default values."""
        request = WorkbenchIterationRequest(
            project_id="prj",
            novel_id="nvl",
            workbench_type="scene_to_chapter",
            parent_object_id="scn",
            actor="user",
        )
        assert request.source_surface == "workbench_iteration"
        assert request.source_ref is None

    def test_feedback_request_defaults(self):
        """Test WorkbenchFeedbackRequest default values."""
        request = WorkbenchFeedbackRequest(
            session_id="wbs",
            target_draft_id="cbd",
            feedback_type="revise",
            feedback_text="Fix it",
        )
        assert request.target_section is None
        assert request.created_by == ""

    def test_selection_request_defaults(self):
        """Test CandidateSelectionRequest default values."""
        request = CandidateSelectionRequest(
            session_id="wbs",
            selected_draft_id="cbd",
            actor="user",
        )
        assert request.apply_to_canonical is True
