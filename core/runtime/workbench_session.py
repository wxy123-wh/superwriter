"""
Workbench session model for multi-turn iteration support.

This module provides the data structures and logic for managing iterative
workbench sessions where users can:
1. Generate initial content
2. Provide feedback (accept/reject/revise/partial_revision)
3. Generate new candidates based on feedback
4. Select the final candidate

The session tracks all candidates, feedback, and the iteration state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias, cast

from core.runtime.storage import JSONValue, utc_now_iso

JSONObject: TypeAlias = dict[str, JSONValue]


class WorkbenchType(str, Enum):
    """Types of workbenches that support iteration."""

    OUTLINE_TO_PLOT = "outline_to_plot"
    PLOT_TO_EVENT = "plot_to_event"
    EVENT_TO_SCENE = "event_to_scene"
    SCENE_TO_CHAPTER = "scene_to_chapter"


class SessionStatus(str, Enum):
    """Status of a workbench session."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class FeedbackType(str, Enum):
    """Types of feedback that can be given on a candidate."""

    ACCEPT = "accept"
    REJECT = "reject"
    REVISE = "revise"
    PARTIAL_REVISION = "partial_revision"


@dataclass(frozen=True, slots=True)
class WorkbenchSession:
    """A workbench iteration session.

    Tracks the state of an iterative workbench operation, including
    the parent object being worked on, the current iteration number,
    and the session status.
    """

    session_id: str
    workbench_type: str
    project_id: str
    novel_id: str
    parent_object_id: str
    actor: str
    started_at: str
    current_iteration: int
    status: str
    completed_at: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE.value

    @property
    def is_completed(self) -> bool:
        return self.status == SessionStatus.COMPLETED.value


@dataclass(frozen=True, slots=True)
class CandidateDraft:
    """A candidate draft generated during a workbench session.

    Each iteration can produce one or more candidates. Candidates
    are stored with their generation context for reference.
    """

    draft_id: str
    session_id: str
    iteration_number: int
    payload: JSONObject
    generation_context: JSONObject
    is_selected: bool
    created_at: str

    @property
    def title(self) -> str:
        """Get a title for the candidate from its payload."""
        title = self.payload.get("title")
        if isinstance(title, str):
            return title
        # Fallback to other common title fields
        for key in ("name", "summary", "content"):
            value = self.payload.get(key)
            if isinstance(value, str) and value:
                return value[:50] + "..." if len(value) > 50 else value
        return f"Candidate {self.draft_id}"


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    """Feedback given on a candidate draft.

    Feedback can be of various types (accept, reject, revise, partial_revision)
    and may target a specific section of the candidate for partial revisions.
    """

    feedback_id: str
    session_id: str
    target_draft_id: str
    feedback_type: str
    feedback_text: str
    target_section: str | None
    created_at: str
    created_by: str

    @property
    def is_revision_request(self) -> bool:
        """Check if this feedback requests a revision."""
        return self.feedback_type in (
            FeedbackType.REVISE.value,
            FeedbackType.PARTIAL_REVISION.value,
        )

    @property
    def is_partial_revision(self) -> bool:
        """Check if this is a partial revision request."""
        return self.feedback_type == FeedbackType.PARTIAL_REVISION.value


@dataclass(frozen=True, slots=True)
class WorkbenchSessionInput:
    """Input for creating a new workbench session."""

    project_id: str
    novel_id: str
    workbench_type: str
    parent_object_id: str
    actor: str
    source_surface: str = "workbench_iteration"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateDraftInput:
    """Input for creating a new candidate draft."""

    session_id: str
    iteration_number: int
    payload: JSONObject
    generation_context: JSONObject
    created_by: str


@dataclass(frozen=True, slots=True)
class FeedbackInput:
    """Input for submitting feedback on a candidate."""

    session_id: str
    target_draft_id: str
    feedback_type: str
    feedback_text: str
    target_section: str | None = None
    created_by: str = ""


@dataclass(frozen=True, slots=True)
class SessionSelectionInput:
    """Input for selecting a final candidate and completing the session."""

    session_id: str
    selected_draft_id: str
    actor: str


__all__ = [
    "WorkbenchType",
    "SessionStatus",
    "FeedbackType",
    "WorkbenchSession",
    "CandidateDraft",
    "FeedbackRecord",
    "WorkbenchSessionInput",
    "CandidateDraftInput",
    "FeedbackInput",
    "SessionSelectionInput",
]
