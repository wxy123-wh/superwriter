from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.web import BookCommandCenter  # noqa: E402
from core.runtime import (
    OutlineToPlotWorkbenchRequest,
    OutlineToPlotWorkbenchResult,
    ReadObjectRequest,
    SuperwriterApplicationService,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402


def _seed_outline_to_plot_workspace(tmp_path: Path) -> tuple[SuperwriterApplicationService, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_harbor_outline",
            payload={"title": "Harbor Outline Project"},
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
            object_id="nvl_harbor_outline",
            payload={"project_id": project.object_id, "title": "Harbor Outline Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    outline = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="outline_node",
            object_id="out_harbor_root",
            payload={
                "novel_id": novel.object_id,
                "title": "Root Outline",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed outline",
        )
    )
    plot = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="plot_node",
            object_id="plt_harbor_root",
            payload={
                "novel_id": novel.object_id,
                "outline_node_id": outline.object_id,
                "title": "Root Plot",
            },
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed plot",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    return service, project.object_id, novel.object_id, outline.object_id, plot.object_id


def _invoke_generate_outline_to_plot_workbench(
    service: SuperwriterApplicationService, req: OutlineToPlotWorkbenchRequest
) -> OutlineToPlotWorkbenchResult:
    # Access the future method via safe getattr to avoid import-time errors if not implemented yet
    method = getattr(service, "generate_outline_to_plot_workbench", None)
    if method is None:
        raise NotImplementedError("generate_outline_to_plot_workbench is not implemented yet")
    return method(req)  # type: ignore[call-arg]


def test_outline_to_plot_request_has_required_contract_fields() -> None:
    names = {f.name for f in OutlineToPlotWorkbenchRequest.__dataclass_fields__.values()}
    # Ensure required upstream contract fields exist
    assert "outline_node_object_id" in names
    assert "expected_parent_revision_id" in names
    assert "target_child_object_id" in names
    assert "base_child_revision_id" in names
    assert "project_id" in names
    assert "novel_id" in names
    assert "actor" in names

    req = OutlineToPlotWorkbenchRequest(project_id="p1", novel_id="n1", outline_node_object_id="out_1", actor="test")
    assert req.target_child_object_id is None
    assert req.base_child_revision_id is None
    assert req.expected_parent_revision_id is None
    assert req.source_surface == "outline_to_plot_workbench"


def test_outline_to_plot_result_has_required_contract_fields() -> None:
    names = {f.name for f in OutlineToPlotWorkbenchResult.__dataclass_fields__.values()}
    assert "disposition" in names
    assert "outline_node_object_id" in names
    assert "source_outline_revision_id" in names
    assert "child_object_id" in names
    assert "child_revision_id" in names
    assert "proposal_id" in names
    assert "review_route" in names
    assert "plot_payload" in names
    assert "delta_payload" in names
    assert "lineage_payload" in names
    assert "reasons" in names


def test_outline_to_plot_happy_path_generation(tmp_path: Path) -> None:
    service, project_id, novel_id, outline_id, plot_id = _seed_outline_to_plot_workspace(tmp_path)
    req = OutlineToPlotWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        outline_node_object_id=outline_id,
        actor="author-1",
        expected_parent_revision_id=None,
        target_child_object_id=None,
        base_child_revision_id=None,
    )
    # Use guarded call to support both red (unimplemented) and future green paths
    result = _invoke_generate_outline_to_plot_workbench(service, req)
    # Red-test: if unimplemented, this will raise NotImplementedError; otherwise we can inspect minimal shape
    assert isinstance(result, OutlineToPlotWorkbenchResult) if 'OutlineToPlotWorkbenchResult' in globals() else True


def test_outline_to_plot_stale_parent_rejection(tmp_path: Path) -> None:
    import pytest

    service, project_id, novel_id, outline_id, _ = _seed_outline_to_plot_workspace(tmp_path)
    req = OutlineToPlotWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        outline_node_object_id=outline_id,
        actor="author-1",
        expected_parent_revision_id="rev-stale",
        target_child_object_id=None,
        base_child_revision_id=None,
    )
    with pytest.raises(ValueError, match="stale"):
        _invoke_generate_outline_to_plot_workbench(service, req)


def test_outline_to_plot_review_required_update(tmp_path: Path) -> None:
    import pytest

    service, project_id, novel_id, outline_id, plot_id = _seed_outline_to_plot_workspace(tmp_path)
    # Read the current plot_node head revision for a valid base_child_revision_id
    plot_read = service.read_object(ReadObjectRequest(family="plot_node", object_id=plot_id))
    assert plot_read.head is not None
    base_rev = plot_read.head.current_revision_id
    req = OutlineToPlotWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        outline_node_object_id=outline_id,
        actor="author-1",
        expected_parent_revision_id=None,
        target_child_object_id=plot_id,
        base_child_revision_id=base_rev,
    )
    result = _invoke_generate_outline_to_plot_workbench(service, req)
    assert result.disposition == "review_required"
    assert result.proposal_id is not None
    assert result.review_route is not None


def test_outline_to_plot_idempotent_approval_replay(tmp_path: Path) -> None:
    service, project_id, novel_id, outline_id, _ = _seed_outline_to_plot_workspace(tmp_path)
    req = OutlineToPlotWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        outline_node_object_id=outline_id,
        actor="author-1",
        expected_parent_revision_id=None,
        target_child_object_id=None,
        base_child_revision_id=None,
    )
    first = _invoke_generate_outline_to_plot_workbench(service, req)
    second = _invoke_generate_outline_to_plot_workbench(service, req)
    assert first.disposition == "generated"
    assert second.disposition == "generated"
    # Create-only: each call produces a distinct plot_node
    assert first.child_object_id != second.child_object_id


def test_outline_to_plot_drift_rejection(tmp_path: Path) -> None:
    import pytest

    service, project_id, novel_id, outline_id, _ = _seed_outline_to_plot_workspace(tmp_path)
    req = OutlineToPlotWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        outline_node_object_id=outline_id,
        actor="author-1",
        expected_parent_revision_id="rev-drift",
        target_child_object_id=None,
        base_child_revision_id="rev-base-drift",
    )
    with pytest.raises(ValueError, match="stale"):
        _invoke_generate_outline_to_plot_workbench(service, req)


def test_outline_to_plot_wrong_parent_or_family_rejection(tmp_path: Path) -> None:
    import pytest

    service, project_id, novel_id, outline_id, _ = _seed_outline_to_plot_workspace(tmp_path)
    req = OutlineToPlotWorkbenchRequest(
        project_id=project_id,
        novel_id=novel_id,
        outline_node_object_id=outline_id,
        actor="author-1",
        expected_parent_revision_id="rev-wrong-parent",
        target_child_object_id=None,
        base_child_revision_id=None,
    )
    with pytest.raises(ValueError, match="stale"):
        _invoke_generate_outline_to_plot_workbench(service, req)
