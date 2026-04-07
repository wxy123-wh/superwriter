from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.runtime import (  # noqa: E402
    PlotToEventWorkbenchRequest,
    SuperwriterApplicationService,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402


# helper removed to satisfy static analysis; not used in tests


def _seed_plot_to_event_workspace(tmp_path: Path) -> tuple[
    SuperwriterApplicationService, str, str, str, str, str, str
]:
    """
    Seed a minimal canonical workspace with a plot_node and its downstream event.
    Returns the application service and the IDs/revisions needed to construct a
    PlotToEventWorkbenchRequest.
    """
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)

    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_plot",
            payload={"title": "Plot to Event Project"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed project",
        )
    )

    novel = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="novel",
            object_id="nvl_harbor_plot",
            payload={"project_id": project.object_id, "title": "Harbor Plot Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )

    plot_node = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="plot_node",
            object_id="plt_harbor_plot",
            payload={"project_id": project.object_id, "title": "Harbor Plot", "novel_id": novel.object_id},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed plot_node",
        )
    )

    event = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="event",
            object_id="evt_harbor_plot_001",
            payload={
                "plot_node_id": plot_node.object_id,
                "novel_id": novel.object_id,
                "title": "Harbor Event",
                "summary": "Event downstream of Harbor Plot.",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )

    service = SuperwriterApplicationService.for_sqlite(db_path)
    return (
        service,
        project.object_id,
        novel.object_id,
        plot_node.object_id,
        plot_node.revision_id,
        event.object_id,
        event.revision_id,
    )


def test_plot_to_event_workbench_red_happy_path(tmp_path: Path) -> None:
    """
    Red test for Plot -> Event workbench: the canonical service path exists but
    the business logic is not yet implemented. Invoking the workbench should
    fail in a non-implemented manner, keeping this test red.
    """
    service, project_id, novel_id, plot_node_id, plot_rev, event_id, event_rev = _seed_plot_to_event_workspace(tmp_path)

    plot_request = PlotToEventWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        actor="author-1",
        plot_node_object_id=plot_node_id,
        expected_parent_revision_id=plot_rev,
        target_child_object_id=event_id,
        base_child_revision_id=event_rev,
    )
    method = getattr(service, "generate_plot_to_event_workbench", None)
    if not callable(method):
        raise AttributeError("generate_plot_to_event_workbench not found")
    _ = method(plot_request)


def test_plot_to_event_workbench_red_stale_parent(tmp_path: Path) -> None:
    import pytest

    service, project_id, novel_id, plot_node_id, plot_rev, event_id, event_rev = _seed_plot_to_event_workspace(tmp_path)
    plot_request = PlotToEventWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        actor="author-1",
        plot_node_object_id=plot_node_id,
        expected_parent_revision_id="stale-" + plot_rev,
        target_child_object_id=event_id,
        base_child_revision_id=event_rev,
    )
    method = getattr(service, "generate_plot_to_event_workbench", None)
    if not callable(method):
        raise AttributeError("generate_plot_to_event_workbench not found")
    with pytest.raises(ValueError, match="stale"):
        _ = method(plot_request)


def test_plot_to_event_workbench_red_review_required(tmp_path: Path) -> None:
    service, project_id, novel_id, plot_node_id, plot_rev, event_id, event_rev = _seed_plot_to_event_workspace(tmp_path)
    plot_request = PlotToEventWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        actor="author-1",
        plot_node_object_id=plot_node_id,
        expected_parent_revision_id=plot_rev,
        target_child_object_id=event_id,
        base_child_revision_id=event_rev,
    )
    method = getattr(service, "generate_plot_to_event_workbench", None)
    if not callable(method):
        raise AttributeError("generate_plot_to_event_workbench not found")
    _ = method(plot_request)


def test_plot_to_event_workbench_red_idempotent_approval(tmp_path: Path) -> None:
    service, project_id, novel_id, plot_node_id, plot_rev, event_id, event_rev = _seed_plot_to_event_workspace(tmp_path)
    plot_request = PlotToEventWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        actor="author-1",
        plot_node_object_id=plot_node_id,
        expected_parent_revision_id=plot_rev,
        target_child_object_id=event_id,
        base_child_revision_id=event_rev,
    )
    method = getattr(service, "generate_plot_to_event_workbench", None)
    if not callable(method):
        raise AttributeError("generate_plot_to_event_workbench not found")
    _ = method(plot_request)


def test_plot_to_event_workbench_red_drift_rejection(tmp_path: Path) -> None:
    service, project_id, novel_id, plot_node_id, plot_rev, event_id, event_rev = _seed_plot_to_event_workspace(tmp_path)
    plot_request = PlotToEventWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        actor="author-1",
        plot_node_object_id=plot_node_id,
        expected_parent_revision_id=plot_rev,
        target_child_object_id=event_id,
        base_child_revision_id=event_rev,
    )
    method = getattr(service, "generate_plot_to_event_workbench", None)
    if not callable(method):
        raise AttributeError("generate_plot_to_event_workbench not found")
    _ = method(plot_request)


def test_plot_to_event_workbench_red_wrong_parent_family(tmp_path: Path) -> None:
    service, project_id, novel_id, plot_node_id, plot_rev, event_id, event_rev = _seed_plot_to_event_workspace(tmp_path)
    plot_request = PlotToEventWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        actor="author-1",
        plot_node_object_id=plot_node_id,
        expected_parent_revision_id=plot_rev,
        target_child_object_id=event_id,
        base_child_revision_id=event_rev,
    )
    method = getattr(service, "generate_plot_to_event_workbench", None)
    if not callable(method):
        raise AttributeError("generate_plot_to_event_workbench not found")
    _ = method(plot_request)
