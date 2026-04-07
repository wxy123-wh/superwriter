"""
Foreshadowing checker for tracking narrative setup and payoff.

This module provides tools to:
1. Track foreshadowing objects across scenes (planted → hinted → resolved/abandoned)
2. Detect unresolved foreshadowing that needs payoff
3. Suggest scenes that could resolve open foreshadowing
4. Surface active foreshadowing during scene generation
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ForeshadowingStatus(str, Enum):
    """Lifecycle status of a foreshadowing element."""

    PLANTED = "planted"
    HINTED = "hinted"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True)
class ForeshadowingRecord:
    """A single foreshadowing object."""

    foreshadowing_id: str
    novel_id: str
    source_scene_id: str
    target_scene_id: str | None
    status: str
    importance: int  # 1-5
    description: str
    created_at: str

    @property
    def is_resolved(self) -> bool:
        return self.status == ForeshadowingStatus.RESOLVED.value

    @property
    def is_unresolved(self) -> bool:
        return self.status in (
            ForeshadowingStatus.PLANTED.value,
            ForeshadowingStatus.HINTED.value,
        )

    @property
    def is_abandoned(self) -> bool:
        return self.status == ForeshadowingStatus.ABANDONED.value


@dataclass(frozen=True, slots=True)
class ForeshadowingCheckResult:
    """Result of checking foreshadowing status for a novel."""

    unresolved_count: int
    abandoned_count: int
    well_resolved_count: int
    issues: tuple[str, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class ResolutionSuggestion:
    """A suggestion for resolving an unresolved foreshadowing."""

    foreshadowing_id: str
    description: str
    source_scene_id: str
    importance: int
    suggested_target_scenes: tuple[str, ...]
    reason: str


class ForeshadowingChecker:
    """
    Checks and manages foreshadowing objects across a novel.

    Uses in-memory storage for MVP. Can be backed by CanonicalStorage
    in a production integration.
    """

    def __init__(self) -> None:
        self._records: dict[str, ForeshadowingRecord] = {}

    def add_record(self, record: ForeshadowingRecord) -> None:
        """Register a foreshadowing record."""
        self._records[record.foreshadowing_id] = record

    def get_record(self, foreshadowing_id: str) -> ForeshadowingRecord | None:
        """Get a single foreshadowing record by ID."""
        return self._records.get(foreshadowing_id)

    def update_status(self, foreshadowing_id: str, new_status: str) -> ForeshadowingRecord | None:
        """Update the status of a foreshadowing record.

        Returns the updated record, or None if not found.
        """
        record = self._records.get(foreshadowing_id)
        if record is None:
            return None
        updated = ForeshadowingRecord(
            foreshadowing_id=record.foreshadowing_id,
            novel_id=record.novel_id,
            source_scene_id=record.source_scene_id,
            target_scene_id=record.target_scene_id,
            status=new_status,
            importance=record.importance,
            description=record.description,
            created_at=record.created_at,
        )
        self._records[foreshadowing_id] = updated
        return updated

    def resolve(self, foreshadowing_id: str, target_scene_id: str) -> ForeshadowingRecord | None:
        """Mark a foreshadowing as resolved with the target scene.

        Returns the updated record, or None if not found.
        """
        record = self._records.get(foreshadowing_id)
        if record is None:
            return None
        updated = ForeshadowingRecord(
            foreshadowing_id=record.foreshadowing_id,
            novel_id=record.novel_id,
            source_scene_id=record.source_scene_id,
            target_scene_id=target_scene_id,
            status=ForeshadowingStatus.RESOLVED.value,
            importance=record.importance,
            description=record.description,
            created_at=record.created_at,
        )
        self._records[foreshadowing_id] = updated
        return updated

    def list_by_novel(self, novel_id: str) -> list[ForeshadowingRecord]:
        """List all foreshadowing records for a novel."""
        return [r for r in self._records.values() if r.novel_id == novel_id]

    def check_unresolved(self, novel_id: str) -> ForeshadowingCheckResult:
        """Check for unresolved foreshadowing in a novel.

        Scans all foreshadowing objects for the novel, identifying:
        - Unresolved (planted or hinted, no target scene)
        - Abandoned
        - Well-resolved (has target scene and resolved status)
        """
        records = self.list_by_novel(novel_id)
        issues: list[str] = []

        unresolved = [r for r in records if r.is_unresolved]
        abandoned = [r for r in records if r.is_abandoned]
        resolved = [r for r in records if r.is_resolved]

        # High-importance unresolved items are issues
        for r in unresolved:
            if r.importance >= 4:
                issues.append(
                    f"High-importance foreshadowing '{r.description}' "
                    f"(fsh: {r.foreshadowing_id}) remains unresolved"
                )

        # Abandoned items might need attention
        for r in abandoned:
            issues.append(
                f"Abandoned foreshadowing '{r.description}' "
                f"(fsh: {r.foreshadowing_id}) may need resolution or removal"
            )

        summary = (
            f"{len(records)} foreshadowing elements: "
            f"{len(resolved)} resolved, {len(unresolved)} unresolved, "
            f"{len(abandoned)} abandoned"
        )

        return ForeshadowingCheckResult(
            unresolved_count=len(unresolved),
            abandoned_count=len(abandoned),
            well_resolved_count=len(resolved),
            issues=tuple(issues),
            summary=summary,
        )

    def get_active_for_scene(self, scene_id: str) -> list[ForeshadowingRecord]:
        """Get foreshadowing elements planted in or resolved by a scene.

        Returns foreshadowing where:
        - source_scene_id matches (planted here), or
        - target_scene_id matches (resolved here)
        """
        results = []
        for r in self._records.values():
            if r.source_scene_id == scene_id or r.target_scene_id == scene_id:
                results.append(r)
        return results

    def get_planted_for_scene(self, scene_id: str) -> list[ForeshadowingRecord]:
        """Get foreshadowing elements planted in a specific scene."""
        return [
            r for r in self._records.values()
            if r.source_scene_id == scene_id
        ]

    def get_resolved_by_scene(self, scene_id: str) -> list[ForeshadowingRecord]:
        """Get foreshadowing elements resolved by a specific scene."""
        return [
            r for r in self._records.values()
            if r.target_scene_id == scene_id
        ]

    def suggest_resolutions(
        self,
        novel_id: str,
        available_scene_ids: tuple[str, ...] | None = None,
    ) -> list[ResolutionSuggestion]:
        """Suggest scenes that could resolve unresolved foreshadowing.

        Args:
            novel_id: The novel to check
            available_scene_ids: Optional pool of scene IDs to suggest from.
                                 If None, suggestions include all scenes in the novel.

        Returns:
            List of ResolutionSuggestion for each unresolved foreshadowing.
        """
        records = self.list_by_novel(novel_id)
        unresolved = [r for r in records if r.is_unresolved]

        # Build scene pool for suggestions
        all_scene_ids: set[str] = set()
        for r in records:
            all_scene_ids.add(r.source_scene_id)
            if r.target_scene_id:
                all_scene_ids.add(r.target_scene_id)

        if available_scene_ids:
            suggestion_pool = [s for s in available_scene_ids if s in all_scene_ids]
            # Also include scenes not yet referenced
            for s in available_scene_ids:
                if s not in all_scene_ids:
                    suggestion_pool.append(s)
        else:
            suggestion_pool = list(all_scene_ids)

        suggestions = []
        for r in unresolved:
            # Suggest scenes that come after the source scene
            # For MVP, just suggest all scenes except the source
            candidate_scenes = [
                s for s in suggestion_pool
                if s != r.source_scene_id
            ]

            reason = (
                f"Unresolved {r.status} foreshadowing (importance {r.importance}): "
                f"{r.description}"
            )

            suggestions.append(ResolutionSuggestion(
                foreshadowing_id=r.foreshadowing_id,
                description=r.description,
                source_scene_id=r.source_scene_id,
                importance=r.importance,
                suggested_target_scenes=tuple(candidate_scenes),
                reason=reason,
            ))

        # Sort by importance (highest first)
        suggestions.sort(key=lambda s: s.importance, reverse=True)
        return suggestions


__all__ = [
    "ForeshadowingStatus",
    "ForeshadowingRecord",
    "ForeshadowingCheckResult",
    "ResolutionSuggestion",
    "ForeshadowingChecker",
]
