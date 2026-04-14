from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from core.runtime.storage import JSONValue

if TYPE_CHECKING:
    from core.runtime.mutation_policy import ChapterMutationSignals
    from core.runtime.types.workspace_types import WorkspaceObjectSummary

JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class OutlineToPlotWorkbenchRequest:
    """Request to generate a canonical plot_node from an outline_node parent.

    Semantics (v1):
    - Create-only by default (target_child_object_id is None).
    - Explicit-target update when target_child_object_id is supplied;
      base_child_revision_id is then required and drift-checked.
    - expected_parent_revision_id pins the outline_node revision; stale
      parents are rejected before any generation occurs.
    - Approval replay is idempotent — no duplicate plot_node on re-approve.
    """

    project_id: str
    novel_id: str
    outline_node_object_id: str
    actor: str
    expected_parent_revision_id: str | None = None
    target_child_object_id: str | None = None
    base_child_revision_id: str | None = None
    require_ai: bool = False
    source_surface: str = "outline_to_plot_workbench"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class OutlineToPlotWorkbenchResult:
    """Result of an outline_node -> plot_node workbench generation.

    disposition values:
    - "generated"        — new plot_node created directly.
    - "review_required"  — update routed to review proposal.
    - "applied"          — update applied directly (safe mutation).
    """

    disposition: str
    outline_node_object_id: str
    source_outline_revision_id: str
    child_object_id: str | None
    child_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    plot_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    reasons: tuple[str, ...]
    additional_plot_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class PlotToEventWorkbenchRequest:
    """Request to generate a canonical event from a plot_node parent.

    Semantics (v1):
    - Create-only by default (target_child_object_id is None).
    - Explicit-target update when target_child_object_id is supplied;
      base_child_revision_id is then required and drift-checked.
    - expected_parent_revision_id pins the plot_node revision; stale
      parents are rejected before any generation occurs.
    - Approval replay is idempotent — no duplicate event on re-approve.
    """

    project_id: str
    novel_id: str
    plot_node_object_id: str
    actor: str
    expected_parent_revision_id: str | None = None
    target_child_object_id: str | None = None
    base_child_revision_id: str | None = None
    require_ai: bool = False
    source_surface: str = "plot_to_event_workbench"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class PlotToEventWorkbenchResult:
    """Result of a plot_node -> event workbench generation.

    disposition values:
    - "generated"        — new event created directly.
    - "review_required"  — update routed to review proposal.
    - "applied"          — update applied directly (safe mutation).
    """

    disposition: str
    plot_node_object_id: str
    source_plot_revision_id: str
    child_object_id: str | None
    child_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    event_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    reasons: tuple[str, ...]
    additional_event_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class EventToSceneWorkbenchRequest:
    """Request to generate a canonical scene from an event parent.

    Semantics (v1):
    - Create-only by default (target_child_object_id is None).
    - Explicit-target update when target_child_object_id is supplied;
      base_child_revision_id is then required and drift-checked.
    - expected_parent_revision_id pins the event revision; stale
      parents are rejected before any generation occurs.
    - Approval replay is idempotent — no duplicate scene on re-approve.
    """

    project_id: str
    novel_id: str
    event_object_id: str
    actor: str
    expected_parent_revision_id: str | None = None
    target_child_object_id: str | None = None
    base_child_revision_id: str | None = None
    require_ai: bool = False
    source_surface: str = "event_to_scene_workbench"
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class EventToSceneWorkbenchResult:
    """Result of an event -> scene workbench generation.

    disposition values:
    - "generated"        — new scene created directly.
    - "review_required"  — update routed to review proposal.
    - "applied"          — update applied directly (safe mutation).
    """

    disposition: str
    event_object_id: str
    source_event_revision_id: str
    child_object_id: str | None
    child_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    scene_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    reasons: tuple[str, ...]
    additional_scene_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SceneToChapterWorkbenchRequest:
    project_id: str
    novel_id: str
    scene_object_id: str
    actor: str
    expected_source_scene_revision_id: str | None = None
    target_artifact_object_id: str | None = None
    base_artifact_revision_id: str | None = None
    chapter_signals: ChapterMutationSignals | None = None
    source_surface: str = "scene_to_chapter_workbench"
    source_ref: str | None = None
    skill_name: str | None = None


@dataclass(frozen=True, slots=True)
class SceneToChapterWorkbenchResult:
    disposition: str
    scene_object_id: str
    source_scene_revision_id: str
    artifact_object_id: str | None
    artifact_revision_id: str | None
    proposal_id: str | None
    review_route: str | None
    chapter_payload: JSONObject
    delta_payload: JSONObject
    lineage_payload: JSONObject
    style_rules: tuple[WorkspaceObjectSummary, ...]
    scoped_skills: tuple[WorkspaceObjectSummary, ...]
    canonical_facts: tuple[WorkspaceObjectSummary, ...]
    reasons: tuple[str, ...]
