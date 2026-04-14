from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from core.runtime.storage import JSONValue

JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class WorkbenchIterationRequest:
    """Request to start a workbench iteration session."""
    project_id: str
    novel_id: str
    workbench_type: str
    parent_object_id: str
    actor: str
    source_surface: str = "workbench_iteration"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateDraftSnapshot:
    """Snapshot of a candidate draft in a workbench session."""
    draft_id: str
    session_id: str
    iteration_number: int
    payload: JSONObject
    generation_context: JSONObject
    is_selected: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class WorkbenchIterationResult:
    """Result of starting a workbench iteration session."""
    session_id: str
    workbench_type: str
    parent_object_id: str
    initial_candidates: tuple[CandidateDraftSnapshot, ...]
    iteration_number: int


@dataclass(frozen=True, slots=True)
class WorkbenchFeedbackRequest:
    """Request to submit feedback on a candidate draft."""
    session_id: str
    target_draft_id: str
    feedback_type: str
    feedback_text: str
    target_section: str | None = None
    created_by: str = ""


@dataclass(frozen=True, slots=True)
class WorkbenchFeedbackResult:
    """Result of submitting feedback and generating new candidates."""
    session_id: str
    new_iteration_number: int
    new_candidates: tuple[CandidateDraftSnapshot, ...]
    feedback_recorded_id: str


@dataclass(frozen=True, slots=True)
class CandidateSelectionRequest:
    """Request to select a final candidate and complete the session."""
    session_id: str
    selected_draft_id: str
    actor: str
    apply_to_canonical: bool = True


@dataclass(frozen=True, slots=True)
class CandidateSelectionResult:
    """Result of selecting a candidate and completing the session."""
    session_id: str
    selected_draft_id: str
    selected_payload: JSONObject
    mutation_applied: bool
    mutation_record_id: str | None
    revision_id: str | None
    completion_status: str
