"""
Tests for Review Desk comment system.

Tests the comment functionality including:
- Creating comments
- Threaded replies
- Resolving comments
- Listing comments by proposal
"""

import tempfile
from pathlib import Path

import pytest

from core.runtime.storage import CanonicalStorage, ProposalRecordInput
from core.review.comments import (
    CommentInput,
    CommentManager,
    CommentThread,
    CommentStatus,
    ProposalComment,
)


@pytest.fixture
def temp_storage():
    """Create a temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = CanonicalStorage(db_path)
        yield storage


@pytest.fixture
def comment_manager(temp_storage: CanonicalStorage):
    """Create a CommentManager for testing."""
    return CommentManager(temp_storage)


class TestProposalComment:
    """Test ProposalComment dataclass."""

    def test_comment_creation(self):
        """Test creating a comment."""
        comment = ProposalComment(
            comment_id="cmt_001",
            proposal_id="prp_001",
            author="test_user",
            content="This is a test comment",
            target_section="paragraph_3",
            parent_comment_id=None,
            status=CommentStatus.OPEN.value,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            resolved_at=None,
            resolved_by=None,
        )
        assert comment.comment_id == "cmt_001"
        assert comment.proposal_id == "prp_001"
        assert comment.author == "test_user"
        assert comment.content == "This is a test comment"
        assert comment.target_section == "paragraph_3"
        assert comment.is_open
        assert not comment.is_resolved
        assert not comment.is_reply

    def test_comment_properties(self):
        """Test comment properties."""
        comment = ProposalComment(
            comment_id="cmt_001",
            proposal_id="prp_001",
            author="test_user",
            content="Test",
            target_section=None,
            parent_comment_id="pcmt_001",
            status=CommentStatus.OPEN.value,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            resolved_at=None,
            resolved_by=None,
        )
        assert comment.is_reply
        assert not comment.is_resolved

        # Resolved comment
        resolved = ProposalComment(
            comment_id="cmt_002",
            proposal_id="prp_001",
            author="test_user",
            content="Resolved comment",
            target_section=None,
            parent_comment_id=None,
            status=CommentStatus.RESOLVED.value,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:01:00Z",
            resolved_at="2024-01-01T00:01:00Z",
            resolved_by="admin",
        )
        assert resolved.is_resolved
        assert not resolved.is_open


class TestCommentInput:
    """Test CommentInput dataclass."""

    def test_comment_input_defaults(self):
        """Test comment input with default values."""
        input = CommentInput(
            proposal_id="prp_001",
            author="test_user",
            content="Test content",
        )
        assert input.proposal_id == "prp_001"
        assert input.author == "test_user"
        assert input.content == "Test content"
        assert input.target_section is None
        assert input.parent_comment_id is None


class TestCommentThread:
    """Test CommentThread dataclass."""

    def test_comment_thread_structure(self):
        """Test comment thread structure."""
        root = ProposalComment(
            comment_id="cmt_001",
            proposal_id="prp_001",
            author="user1",
            content="Root comment",
            target_section=None,
            parent_comment_id=None,
            status=CommentStatus.OPEN.value,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            resolved_at=None,
            resolved_by=None,
        )
        reply1 = ProposalComment(
            comment_id="cmt_002",
            proposal_id="prp_001",
            author="user2",
            content="Reply 1",
            target_section=None,
            parent_comment_id="cmt_001",
            status=CommentStatus.OPEN.value,
            created_at="2024-01-01T00:01:00Z",
            updated_at="2024-01-01T00:01:00Z",
            resolved_at=None,
            resolved_by=None,
        )
        reply2 = ProposalComment(
            comment_id="cmt_003",
            proposal_id="prp_001",
            author="user3",
            content="Reply 2",
            target_section=None,
            parent_comment_id="cmt_001",
            status=CommentStatus.RESOLVED.value,
            created_at="2024-01-01T00:02:00Z",
            updated_at="2024-01-01T00:02:00Z",
            resolved_at="2024-01-01T00:02:00Z",
            resolved_by="admin",
        )

        thread = CommentThread(root_comment=root, replies=(reply1, reply2))

        assert thread.comment_count == 3
        assert thread.has_open_comments  # root and reply1 are open

        assert thread.root_comment.comment_id == "cmt_001"


class TestCommentManager:
    """Test CommentManager class."""

    def test_add_comment(self, comment_manager: CommentManager, temp_storage: CanonicalStorage):
        """Test adding a comment via manager."""
        # First create a proposal to comment on
        proposal_id = temp_storage.create_proposal_record(
            ProposalRecordInput(
                target_family="scene",
                target_object_id="scn_001",
                created_by="test_user",
                proposal_payload={"test": "data"},
            )
        )

        # Add comment
        comment_id = comment_manager.add_comment(
            CommentInput(
                proposal_id=proposal_id,
                author="commenter",
                content="This is a test comment",
                target_section="paragraph_1",
            )
        )

        assert comment_id is not None
        assert comment_id.startswith("cmt_")

        # Retrieve comment
        comment = comment_manager.get_comment(comment_id)
        assert comment is not None
        assert comment.content == "This is a test comment"

    def test_list_proposal_comments(self, comment_manager: CommentManager, temp_storage: CanonicalStorage):
        """Test listing comments for a proposal."""
        # Create proposal
        proposal_id = temp_storage.create_proposal_record(
            ProposalRecordInput(
                target_family="scene",
                target_object_id="scn_001",
                created_by="test_user",
                proposal_payload={"test": "data"},
            )
        )

        # Add multiple comments
        comment_manager.add_comment(
            CommentInput(proposal_id=proposal_id, author="user1", content="Comment 1")
        )
        comment_manager.add_comment(
            CommentInput(proposal_id=proposal_id, author="user2", content="Comment 2"),
        )

        # List comments
        comments = comment_manager.list_proposal_comments(proposal_id)
        assert len(comments) == 2

    def test_resolve_comment(self, comment_manager: CommentManager, temp_storage: CanonicalStorage):
        """Test resolving a comment."""
        # Create proposal and comment
        proposal_id = temp_storage.create_proposal_record(
            ProposalRecordInput(
                target_family="scene",
                target_object_id="scn_001",
                created_by="test_user",
                proposal_payload={"test": "data"},
            )
        )

        comment_id = comment_manager.add_comment(
            CommentInput(proposal_id=proposal_id, author="user1", content="Open comment"),
        )

        # Resolve it
        success = comment_manager.resolve_comment(comment_id, "admin")
        assert success

        # Verify resolved
        comment = comment_manager.get_comment(comment_id)
        assert comment is not None
        assert comment.is_resolved
        assert comment.resolved_by == "admin"

    def test_comment_threads(self, comment_manager: CommentManager, temp_storage: CanonicalStorage):
        """Test getting comment threads."""
        # Create proposal
        proposal_id = temp_storage.create_proposal_record(
            ProposalRecordInput(
                target_family="scene",
                target_object_id="scn_001",
                created_by="test_user",
                proposal_payload={"test": "data"},
            )
        )

        # Add root comment
        root_id = comment_manager.add_comment(
            CommentInput(proposal_id=proposal_id, author="user1", content="Root comment"),
        )

        # Add replies
        comment_manager.add_comment(
            CommentInput(
                proposal_id=proposal_id,
                author="user2",
                content="Reply 1",
                parent_comment_id=root_id,
            ),
        )
        comment_manager.add_comment(
            CommentInput(
                proposal_id=proposal_id,
                author="user3",
                content="Reply 2",
                parent_comment_id=root_id,
            ),
        )

        # Get threads
        threads = comment_manager.get_comment_threads(proposal_id)
        assert len(threads) == 1
        assert threads[0].root_comment.comment_id == root_id
        assert len(threads[0].replies) == 2

    def test_count_open_comments(self, comment_manager: CommentManager, temp_storage: CanonicalStorage):
        """Test counting open comments."""
        # Create proposal
        proposal_id = temp_storage.create_proposal_record(
            ProposalRecordInput(
                target_family="scene",
                target_object_id="scn_001",
                created_by="test_user",
                proposal_payload={"test": "data"},
            )
        )

        # Add comments
        c1 = comment_manager.add_comment(
            CommentInput(proposal_id=proposal_id, author="user1", content="Open 1"),
        )
        c2 = comment_manager.add_comment(
            CommentInput(proposal_id=proposal_id, author="user2", content="Open 2"),
        )

        # Resolve one
        comment_manager.resolve_comment(c1, "admin")

        # Count open
        count = comment_manager.count_open_comments(proposal_id)
        assert count == 1
