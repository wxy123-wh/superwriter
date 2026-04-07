"""
Tests for Review Desk candidate comparison.

Tests the comparison functionality including:
- Building comparisons from workbench sessions
- Calculating diffs between candidates
- Determining recommendations
"""

import tempfile
from pathlib import Path

import pytest

# Import storage first to avoid circular import
from core.runtime.storage import CanonicalStorage

from core.review.comparison import (
    CandidateComparison,
    CandidateVersion,
    ComparisonBuilder,
    DiffSegment,
    SideBySideDiff,
)


@pytest.fixture
def temp_storage():
    """Create a temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = CanonicalStorage(db_path)
        yield storage


@pytest.fixture
def comparison_builder(temp_storage: CanonicalStorage):
    """Create a ComparisonBuilder for testing."""
    return ComparisonBuilder(temp_storage)


@pytest.fixture
def session_with_candidates(temp_storage: CanonicalStorage):
    """Create a session with multiple candidates for testing."""
    # Create session
    session_id = temp_storage.create_workbench_session(
        project_id="prj_test",
        novel_id="nvl_test",
        workbench_type="scene_to_chapter",
        parent_object_id="scn_001",
        actor="test_user",
    )

    # Create first candidate
    draft1_id = temp_storage.create_candidate_draft(
        session_id=session_id,
        iteration_number=1,
        payload={"content": "This is the first version of the chapter content."},
        generation_context={"model": "test"},
    )

    # Create second candidate
    draft2_id = temp_storage.create_candidate_draft(
        session_id=session_id,
        iteration_number=1,
        payload={"content": "This is the second version with some changes."},
        generation_context={"model": "test"},
    )

    # Create third candidate (later iteration)
    draft3_id = temp_storage.create_candidate_draft(
        session_id=session_id,
        iteration_number=2,
        payload={"content": "This is the refined version from iteration two."},
        generation_context={"model": "test"},
    )

    return {
        "session_id": session_id,
        "draft_ids": [draft1_id, draft2_id, draft3_id],
    }


class TestCandidateVersion:
    """Test CandidateVersion dataclass."""

    def test_candidate_version_creation(self):
        """Test creating a candidate version."""
        version = CandidateVersion(
            draft_id="draft_001",
            iteration_number=1,
            payload={"content": "Test content"},
            created_at="2024-01-01T00:00:00Z",
            is_selected=False,
        )
        assert version.draft_id == "draft_001"
        assert version.iteration_number == 1
        assert version.content == "Test content"

    def test_content_extraction_various_keys(self):
        """Test content extraction from different payload keys."""
        # Standard content key
        v1 = CandidateVersion(
            draft_id="d1", iteration_number=1,
            payload={"content": "main content"}, created_at="", is_selected=False
        )
        assert v1.content == "main content"

        # Body key
        v2 = CandidateVersion(
            draft_id="d2", iteration_number=1,
            payload={"body": "body content"}, created_at="", is_selected=False
        )
        assert v2.content == "body content"

        # Text key
        v3 = CandidateVersion(
            draft_id="d3", iteration_number=1,
            payload={"text": "text content"}, created_at="", is_selected=False
        )
        assert v3.content == "text content"

    def test_content_extraction_empty_payload(self):
        """Test content extraction from empty payload."""
        version = CandidateVersion(
            draft_id="d1", iteration_number=1,
            payload={}, created_at="", is_selected=False
        )
        assert version.content == ""


class TestDiffSegment:
    """Test DiffSegment dataclass."""

    def test_diff_segment_creation(self):
        """Test creating a diff segment."""
        segment = DiffSegment(
            type="equal",
            text="same text",
            source_start=0,
            source_end=9,
            target_start=0,
            target_end=9,
        )
        assert segment.type == "equal"
        assert segment.text == "same text"


class TestSideBySideDiff:
    """Test SideBySideDiff dataclass."""

    def test_diff_creation(self):
        """Test creating a side-by-side diff."""
        diff = SideBySideDiff(
            source_id="d1",
            target_id="d2",
            segments=(),
            similarity_ratio=0.85,
            added_lines=2,
            removed_lines=1,
            changed_lines=3,
        )
        assert diff.source_id == "d1"
        assert diff.similarity_ratio == 0.85


class TestComparisonBuilder:
    """Test ComparisonBuilder class."""

    def test_build_comparison_nonexistent_session(
        self, comparison_builder: ComparisonBuilder
    ):
        """Test building comparison for nonexistent session."""
        result = comparison_builder.build_comparison("nonexistent_session")
        assert result is None

    def test_build_comparison_single_candidate(
        self,
        comparison_builder: ComparisonBuilder,
        temp_storage: CanonicalStorage,
    ):
        """Test building comparison with only one candidate."""
        # Create session with single candidate
        session_id = temp_storage.create_workbench_session(
            project_id="prj_test",
            novel_id="nvl_test",
            workbench_type="scene_to_chapter",
            parent_object_id="scn_001",
            actor="test_user",
        )

        temp_storage.create_candidate_draft(
            session_id=session_id,
            iteration_number=1,
            payload={"content": "Single candidate"},
            generation_context={},
        )

        result = comparison_builder.build_comparison(session_id)

        assert result is not None
        assert len(result.candidates) == 1
        assert result.candidates[0].content == "Single candidate"
        assert len(result.pairwise_diffs) == 0

    def test_build_comparison_multiple_candidates(
        self,
        comparison_builder: ComparisonBuilder,
        session_with_candidates: dict,
    ):
        """Test building comparison with multiple candidates."""
        result = comparison_builder.build_comparison(
            session_with_candidates["session_id"]
        )

        assert result is not None
        assert len(result.candidates) == 3
        assert len(result.pairwise_diffs) == 3  # C(3,2) = 3 pairs

    def test_comparison_recommends_latest_iteration(
        self,
        comparison_builder: ComparisonBuilder,
        session_with_candidates: dict,
    ):
        """Test that comparison recommends candidate from latest iteration."""
        result = comparison_builder.build_comparison(
            session_with_candidates["session_id"]
        )

        assert result is not None
        assert result.recommended_selection is not None
        # Should recommend draft3 (iteration 2)
        recommended = next(
            c for c in result.candidates if c.draft_id == result.recommended_selection
        )
        assert recommended.iteration_number == 2

    def test_comparison_with_specific_candidates(
        self,
        comparison_builder: ComparisonBuilder,
        session_with_candidates: dict,
    ):
        """Test building comparison with specific candidate subset."""
        draft_ids = session_with_candidates["draft_ids"]

        # Compare only first two candidates
        result = comparison_builder.build_comparison(
            session_with_candidates["session_id"],
            candidate_ids=[draft_ids[0], draft_ids[1]],
        )

        assert result is not None
        assert len(result.candidates) == 2
        assert len(result.pairwise_diffs) == 1  # Only 1 pair

    def test_comparison_includes_similarity_ratio(
        self,
        comparison_builder: ComparisonBuilder,
        session_with_candidates: dict,
    ):
        """Test that comparison includes similarity ratio."""
        result = comparison_builder.build_comparison(
            session_with_candidates["session_id"]
        )

        assert result is not None
        for diff in result.pairwise_diffs:
            assert 0.0 <= diff.similarity_ratio <= 1.0


class TestCandidateComparison:
    """Test CandidateComparison dataclass."""

    def test_comparison_structure(self):
        """Test comparison data structure."""
        candidates = (
            CandidateVersion(
                draft_id="d1",
                iteration_number=1,
                payload={"content": "v1"},
                created_at="2024-01-01T00:00:00Z",
                is_selected=False,
            ),
            CandidateVersion(
                draft_id="d2",
                iteration_number=1,
                payload={"content": "v2"},
                created_at="2024-01-01T00:01:00Z",
                is_selected=True,
            ),
        )

        comparison = CandidateComparison(
            proposal_id="prop_001",
            target_object_id="obj_001",
            candidates=candidates,
            pairwise_diffs=(),
            recommended_selection="d2",
            recommendation_reason="User selected",
        )

        assert comparison.proposal_id == "prop_001"
        assert len(comparison.candidates) == 2
        assert comparison.recommended_selection == "d2"


class TestDiffCalculation:
    """Test diff calculation between candidates."""

    def test_identical_content_high_similarity(
        self, comparison_builder: ComparisonBuilder, temp_storage: CanonicalStorage
    ):
        """Test that identical content produces high similarity."""
        session_id = temp_storage.create_workbench_session(
            project_id="prj_test",
            novel_id="nvl_test",
            workbench_type="test",
            parent_object_id="obj_001",
            actor="test_user",
        )

        same_content = "This is the same content for both candidates."

        temp_storage.create_candidate_draft(
            session_id=session_id,
            iteration_number=1,
            payload={"content": same_content},
            generation_context={},
        )

        temp_storage.create_candidate_draft(
            session_id=session_id,
            iteration_number=1,
            payload={"content": same_content},
            generation_context={},
        )

        result = comparison_builder.build_comparison(session_id)

        assert result is not None
        assert len(result.pairwise_diffs) == 1
        assert result.pairwise_diffs[0].similarity_ratio == 1.0

    def test_different_content_low_similarity(
        self, comparison_builder: ComparisonBuilder, temp_storage: CanonicalStorage
    ):
        """Test that different content produces lower similarity."""
        session_id = temp_storage.create_workbench_session(
            project_id="prj_test",
            novel_id="nvl_test",
            workbench_type="test",
            parent_object_id="obj_001",
            actor="test_user",
        )

        temp_storage.create_candidate_draft(
            session_id=session_id,
            iteration_number=1,
            payload={"content": "Completely different content here."},
            generation_context={},
        )

        temp_storage.create_candidate_draft(
            session_id=session_id,
            iteration_number=1,
            payload={"content": "Something else entirely unrelated."},
            generation_context={},
        )

        result = comparison_builder.build_comparison(session_id)

        assert result is not None
        assert len(result.pairwise_diffs) == 1
        # Similarity should be relatively low
        assert result.pairwise_diffs[0].similarity_ratio < 0.5
