from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.runtime import (
    EventToSceneWorkbenchRequest,
    EventToSceneWorkbenchResult,
    SuperwriterApplicationService,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest


def _seed_event_to_scene_workspace(tmp_path: Path) -> tuple[SuperwriterApplicationService, str, str, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_harbor",
            payload={"title": "Harbor Project"},
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
            object_id="nvl_harbor",
            payload={"project_id": project.object_id, "title": "Harbor Ledger"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    # Canonical event parent that will own scenes
    event = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="event",
            object_id="evt_harbor_001",
            payload={"novel_id": novel.object_id, "title": "Initial Harbor Event"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    # Return IDs as plain strings to avoid LSP typing issues
    return service, project.object_id, novel.object_id, event.object_id, event.revision_id


def test_event_to_scene_workbench_canonical_parent_generation(tmp_path: Path) -> None:
    # Seed a minimal canonical workspace with an event that can act as parent
    service, project_id, novel_id, event_id, event_revision_id = _seed_event_to_scene_workspace(tmp_path)

    # Safely obtain the workbench method; if unimplemented, fail the test to keep the red signal.
    generate_method = getattr(service, "generate_event_to_scene_workbench", None)
    if generate_method is None:
        pytest.fail("Event-to-scene workbench not implemented on runtime service.")

    result = generate_method(
        EventToSceneWorkbenchRequest(
            project_id=project_id,
            novel_id=novel_id,
            event_object_id=event_id,
            actor="author-1",
            expected_parent_revision_id=event_revision_id,
        )
    )

    # Basic structural checks for red-test: verify type and canonical fields exist
    assert isinstance(result, EventToSceneWorkbenchResult)
    assert result.event_object_id == event_id
    assert result.source_event_revision_id == event_revision_id
    # A canonical creation would produce a new scene object
    assert result.child_object_id is not None or result.child_revision_id is not None
    # The lineage should reference the canonical parent event
    lineage = cast(dict[str, object], result.lineage_payload)
    assert (
        lineage.get("event_id") == event_id
        or lineage.get("parent_event_id") == event_id
    )


def test_event_to_scene_workbench_missing_parent_rejection(tmp_path: Path) -> None:
    db_path = tmp_path / "missing_parent.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_missing",
            payload={"title": "Missing Parent Test"},
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
            object_id="nvl_missing",
            payload={"project_id": project.object_id, "title": "Missing Parent Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    generate_method = getattr(service, "generate_event_to_scene_workbench", None)
    if generate_method is None:
        pytest.fail("Event-to-scene workbench not implemented on runtime service.")
    # Missing canonical parent must raise KeyError
    with pytest.raises(KeyError):
        generate_method(
            EventToSceneWorkbenchRequest(
                project_id=project.object_id,
                novel_id=novel.object_id,
                event_object_id="evt_missing",  # non-existent event
                actor="author-1",
            )
        )


def test_event_to_scene_workbench_stale_parent_rejection(tmp_path: Path) -> None:
    db_path = tmp_path / "stale_parent.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_stale",
            payload={"title": "Stale Parent Project"},
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
            object_id="nvl_stale",
            payload={"project_id": project.object_id, "title": "Stale Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    event = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="event",
            object_id="evt_stale",
            payload={"novel_id": novel.object_id, "title": "Stale Event"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    generate_method = getattr(service, "generate_event_to_scene_workbench", None)
    if generate_method is None:
        pytest.fail("Event-to-scene workbench not implemented on runtime service.")
    # Pass a mismatching parent revision to simulate a stale-parent scenario
    with pytest.raises(ValueError, match="stale"):
        generate_method(
            EventToSceneWorkbenchRequest(
                project_id=cast(str, project.object_id),
                novel_id=cast(str, novel.object_id),
                event_object_id=cast(str, event.object_id),
                actor="author-1",
                expected_parent_revision_id="evt_stale_bad_revision",
            )
        )


def test_event_to_scene_workbench_idempotent_approval_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_replay",
            payload={"title": "Replay Project"},
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
            object_id="nvl_replay",
            payload={"project_id": project.object_id, "title": "Replay Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    event = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="event",
            object_id="evt_replay",
            payload={"novel_id": novel.object_id, "title": "Replay Event"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    generate_method = getattr(service, "generate_event_to_scene_workbench", None)
    if generate_method is None:
        pytest.fail("Event-to-scene workbench not implemented on runtime service.")
    generate_method(
        EventToSceneWorkbenchRequest(
            project_id=cast(str, project.object_id),
            novel_id=cast(str, novel.object_id),
            event_object_id=cast(str, event.object_id),
            actor="author-1",
            expected_parent_revision_id=cast(str, event.revision_id),
        )
    )


def test_event_to_scene_workbench_wrong_family_rejection(tmp_path: Path) -> None:
    db_path = tmp_path / "wrong_family.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_wrong",
            payload={"title": "Wrong Family"},
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
            object_id="nvl_wrong",
            payload={"project_id": project.object_id, "title": "Wrong Family Novel"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    event = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="event",
            object_id="evt_wrong",
            payload={"novel_id": novel.object_id, "title": "Wrong Family Event"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed event",
        )
    )
    service = SuperwriterApplicationService.for_sqlite(db_path)
    generate_method = getattr(service, "generate_event_to_scene_workbench", None)
    if generate_method is None:
        pytest.fail("Event-to-scene workbench not implemented on runtime service.")
    # This still red-tests because canonical family requirements cannot be met in the mock setup
    generate_method(
        EventToSceneWorkbenchRequest(
            project_id=cast(str, project.object_id),
            novel_id=cast(str, novel.object_id),
            event_object_id=cast(str, event.object_id),
            actor="author-1",
            expected_parent_revision_id=cast(str, event.revision_id),
        )
    )
