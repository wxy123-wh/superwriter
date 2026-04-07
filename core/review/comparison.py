"""
Candidate comparison for Review Desk.

This module provides the ability to compare multiple candidate versions
side-by-side, highlighting differences and recommending selections.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from core.runtime.storage import CanonicalStorage

JSONObject: TypeAlias = dict[str, Any]


@dataclass(frozen=True, slots=True)
class CandidateVersion:
    """A single candidate version for comparison."""

    draft_id: str
    iteration_number: int
    payload: JSONObject
    created_at: str
    is_selected: bool

    @property
    def content(self) -> str:
        """Extract the main content from the payload."""
        for key in ("content", "body", "text", "prose", "description"):
            value = self.payload.get(key)
            if isinstance(value, str):
                return value
        return ""


@dataclass(frozen=True, slots=True)
class DiffSegment:
    """A segment of text difference."""

    type: str  # "equal", "insert", "delete", "replace"
    text: str
    source_start: int
    source_end: int
    target_start: int
    target_end: int


@dataclass(frozen=True, slots=True)
class SideBySideDiff:
    """Side-by-side diff between two candidates."""

    source_id: str
    target_id: str
    segments: tuple[DiffSegment, ...]
    similarity_ratio: float
    added_lines: int
    removed_lines: int
    changed_lines: int


@dataclass(frozen=True, slots=True)
class CandidateComparison:
    """Complete comparison between multiple candidates."""

    proposal_id: str
    target_object_id: str
    candidates: tuple[CandidateVersion, ...]
    pairwise_diffs: tuple[SideBySideDiff, ...]
    recommended_selection: str | None
    recommendation_reason: str | None


class ComparisonBuilder:
    """Builds candidate comparisons for Review Desk."""

    def __init__(self, storage: CanonicalStorage):
        """Initialize with storage reference."""
        self._storage = storage

    def build_comparison(
        self,
        session_id: str,
        candidate_ids: list[str] | None = None,
    ) -> CandidateComparison | None:
        """
        Build a comparison of candidates from a workbench session.

        Args:
            session_id: The workbench session ID
            candidate_ids: Optional list of specific candidate IDs to compare.
                          If None, compares all candidates from the session.

        Returns:
            CandidateComparison if candidates found, None otherwise
        """
        # Load session
        session = self._storage.get_workbench_session(session_id)
        if session is None:
            return None

        # Load candidates
        all_drafts = self._storage.list_candidate_drafts(session_id)

        if candidate_ids:
            drafts = [d for d in all_drafts if d["draft_id"] in candidate_ids]
        else:
            drafts = all_drafts

        if len(drafts) < 2:
            # Need at least 2 candidates for comparison
            if len(drafts) == 1:
                # Return single candidate comparison
                candidate = self._draft_to_version(drafts[0])
                return CandidateComparison(
                    proposal_id=session_id,  # Use session_id as proposal_id
                    target_object_id=session.get("parent_object_id", ""),
                    candidates=(candidate,),
                    pairwise_diffs=(),
                    recommended_selection=drafts[0]["draft_id"] if drafts[0].get("is_selected") else None,
                    recommendation_reason="Single candidate available",
                )
            return None

        # Convert to CandidateVersion objects
        candidates = tuple(self._draft_to_version(d) for d in drafts)

        # Build pairwise diffs
        pairwise_diffs = []
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                diff = self._build_diff(candidates[i], candidates[j])
                pairwise_diffs.append(diff)

        # Determine recommendation
        recommended_id, reason = self._determine_recommendation(candidates, pairwise_diffs)

        return CandidateComparison(
            proposal_id=session_id,
            target_object_id=session.get("parent_object_id", ""),
            candidates=candidates,
            pairwise_diffs=tuple(pairwise_diffs),
            recommended_selection=recommended_id,
            recommendation_reason=reason,
        )

    def _draft_to_version(self, draft: dict) -> CandidateVersion:
        """Convert a draft dict to CandidateVersion."""
        return CandidateVersion(
            draft_id=draft["draft_id"],
            iteration_number=draft.get("iteration_number", 1),
            payload=draft.get("payload", {}),
            created_at=draft.get("created_at", ""),
            is_selected=draft.get("is_selected", False),
        )

    def _build_diff(self, source: CandidateVersion, target: CandidateVersion) -> SideBySideDiff:
        """Build a diff between two candidate versions."""
        source_content = source.content
        target_content = target.content

        # Use SequenceMatcher for diff
        matcher = SequenceMatcher(None, source_content, target_content)

        segments = []
        added = 0
        removed = 0
        changed = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            segment = DiffSegment(
                type=tag,
                text=source_content[i1:i2] if tag in ("equal", "delete", "replace") else target_content[j1:j2],
                source_start=i1,
                source_end=i2,
                target_start=j1,
                target_end=j2,
            )
            segments.append(segment)

            if tag == "insert":
                added += 1
            elif tag == "delete":
                removed += 1
            elif tag == "replace":
                changed += 1

        return SideBySideDiff(
            source_id=source.draft_id,
            target_id=target.draft_id,
            segments=tuple(segments),
            similarity_ratio=matcher.ratio(),
            added_lines=added,
            removed_lines=removed,
            changed_lines=changed,
        )

    def _determine_recommendation(
        self,
        candidates: tuple[CandidateVersion, ...],
        diffs: tuple[SideBySideDiff, ...],
    ) -> tuple[str | None, str | None]:
        """
        Determine which candidate to recommend.

        Strategy:
        1. If any candidate is already selected, recommend that
        2. Prefer candidates from later iterations (more refined)
        3. If tied, prefer candidate with highest similarity to others (most consensus)
        """
        for c in candidates:
            if c.is_selected:
                return c.draft_id, "Previously selected by user"

        max_iteration = max(c.iteration_number for c in candidates)
        later_candidates = [c for c in candidates if c.iteration_number == max_iteration]

        if len(later_candidates) == 1:
            return later_candidates[0].draft_id, f"Latest iteration (#{max_iteration})"

        # Among tied candidates, find one with highest average similarity to others
        if diffs:
            sim_by_candidate: dict[str, list[float]] = {}
            for d in diffs:
                sim_by_candidate.setdefault(d.source_id, []).append(d.similarity_ratio)
                sim_by_candidate.setdefault(d.target_id, []).append(d.similarity_ratio)

            similarity_scores: dict[str, float] = {}
            for c in later_candidates:
                scores = sim_by_candidate.get(c.draft_id, [])
                if scores:
                    similarity_scores[c.draft_id] = sum(scores) / len(scores)

            if similarity_scores:
                best_id = max(similarity_scores.keys(), key=lambda k: similarity_scores[k])
                return best_id, f"Highest similarity score ({similarity_scores[best_id]:.1%})"

        # Default: return first candidate
        return candidates[0].draft_id, "Default selection"


__all__ = [
    "CandidateVersion",
    "DiffSegment",
    "SideBySideDiff",
    "CandidateComparison",
    "ComparisonBuilder",
]
