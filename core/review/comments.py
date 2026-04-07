"""
Comment system for Review Desk.

This module provides the ability to add comments to proposals,
track comment threads, and resolve discussions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from core.runtime.storage import CanonicalStorage

from core.runtime.storage import utc_now_iso

JSONObject: TypeAlias = dict[str, Any]


class CommentStatus(str, Enum):
    """Status of a comment."""

    OPEN = "open"
    RESOLVED = "resolved"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class ProposalComment:
    """A comment on a review proposal."""

    comment_id: str
    proposal_id: str
    author: str
    content: str
    target_section: str | None  # Comment on specific section (e.g., "paragraph_3")
    parent_comment_id: str | None  # For threaded replies
    status: str
    created_at: str
    updated_at: str
    resolved_at: str | None
    resolved_by: str | None

    @property
    def is_open(self) -> bool:
        return self.status == CommentStatus.OPEN.value

    @property
    def is_resolved(self) -> bool:
        return self.status == CommentStatus.RESOLVED.value

    @property
    def is_reply(self) -> bool:
        return self.parent_comment_id is not None


@dataclass(frozen=True, slots=True)
class CommentInput:
    """Input for creating a new comment."""

    proposal_id: str
    author: str
    content: str
    target_section: str | None = None
    parent_comment_id: str | None = None


@dataclass(frozen=True, slots=True)
class CommentThread:
    """A thread of comments with replies."""

    root_comment: ProposalComment
    replies: tuple[ProposalComment, ...]

    @property
    def comment_count(self) -> int:
        return 1 + len(self.replies)

    @property
    def has_open_comments(self) -> bool:
        if self.root_comment.is_open:
            return True
        return any(r.is_open for r in self.replies)


class CommentManager:
    """Manages comments on review proposals."""

    def __init__(self, storage: CanonicalStorage):
        """Initialize with storage reference."""
        self._storage = storage

    def add_comment(self, input: CommentInput) -> str:
        """
        Add a comment to a proposal.

        Args:
            input: Comment input data

        Returns:
            The new comment ID
        """
        comment_id = self._storage.create_proposal_comment(
            proposal_id=input.proposal_id,
            author=input.author,
            content=input.content,
            target_section=input.target_section,
            parent_comment_id=input.parent_comment_id,
        )

        return comment_id

    def get_comment(self, comment_id: str) -> ProposalComment | None:
        """
        Get a specific comment.

        Args:
            comment_id: The comment ID

        Returns:
            ProposalComment if found, None otherwise
        """
        row = self._storage.get_proposal_comment(comment_id)
        if row is None:
            return None
        return self._row_to_comment(row)

    def list_proposal_comments(self, proposal_id: str) -> list[ProposalComment]:
        """
        List all comments for a proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            List of ProposalComment objects
        """
        rows = self._storage.list_proposal_comments(proposal_id)
        return [self._row_to_comment(row) for row in rows]

    def get_comment_threads(self, proposal_id: str) -> list[CommentThread]:
        """
        Get comments organized into threads.

        Args:
            proposal_id: The proposal ID

        Returns:
            List of CommentThread objects
        """
        comments = self.list_proposal_comments(proposal_id)

        roots = [c for c in comments if c.parent_comment_id is None]
        replies = [c for c in comments if c.parent_comment_id is not None]

        # Group replies by parent for O(1) lookup
        reply_map: dict[str, list[ProposalComment]] = {}
        for r in replies:
            reply_map.setdefault(r.parent_comment_id, []).append(r)

        threads = []
        for root in roots:
            root_replies = tuple(
                sorted(
                    reply_map.get(root.comment_id, []),
                    key=lambda x: x.created_at,
                )
            )
            threads.append(CommentThread(root_comment=root, replies=root_replies))

        return threads

    def resolve_comment(self, comment_id: str, resolved_by: str) -> bool:
        """
        Mark a comment as resolved.

        Args:
            comment_id: The comment ID
            resolved_by: User who resolved the comment

        Returns:
            True if resolved, False if not found
        """
        return self._storage.resolve_proposal_comment(
            comment_id=comment_id,
            resolved_by=resolved_by,
            resolved_at=utc_now_iso(),
        )

    def reopen_comment(self, comment_id: str) -> bool:
        """
        Reopen a resolved comment.

        Args:
            comment_id: The comment ID

        Returns:
            True if reopened, False if not found
        """
        return self._storage.reopen_proposal_comment(comment_id)

    def delete_comment(self, comment_id: str) -> bool:
        """
        Delete (hide) a comment.

        Args:
            comment_id: The comment ID

        Returns:
            True if deleted, False if not found
        """
        return self._storage.hide_proposal_comment(comment_id)

    def update_comment_content(self, comment_id: str, new_content: str) -> bool:
        """
        Update the content of a comment.

        Args:
            comment_id: The comment ID
            new_content: New comment content

        Returns:
            True if updated, False if not found
        """
        return self._storage.update_proposal_comment_content(
            comment_id=comment_id,
            new_content=new_content,
            updated_at=utc_now_iso(),
        )

    def count_open_comments(self, proposal_id: str) -> int:
        """
        Count open (unresolved) comments for a proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            Number of open comments
        """
        comments = self.list_proposal_comments(proposal_id)
        return sum(1 for c in comments if c.is_open)

    def _row_to_comment(self, row: dict) -> ProposalComment:
        """Convert a database row to ProposalComment."""
        return ProposalComment(
            comment_id=row["comment_id"],
            proposal_id=row["proposal_id"],
            author=row.get("author", ""),
            content=row.get("content", ""),
            target_section=row.get("target_section"),
            parent_comment_id=row.get("parent_comment_id"),
            status=row.get("status", CommentStatus.OPEN.value),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
            resolved_at=row.get("resolved_at"),
            resolved_by=row.get("resolved_by"),
        )


__all__ = [
    "CommentStatus",
    "ProposalComment",
    "CommentInput",
    "CommentThread",
    "CommentManager",
]
