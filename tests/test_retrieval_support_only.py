from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.runtime import (  # noqa: E402
    CanonicalWriteRequest,
    CanonicalStorage,
    MetadataMarkerSnapshot,
    RetrievalRebuildRequest,
    RetrievalSearchRequest,
    ServiceMutationRequest,
    SuperwriterApplicationService,
)


def test_retrieval_rebuild_stays_support_only_and_replaces_current_scope_markers(tmp_path: Path) -> None:
    db_path = tmp_path / "canonical.sqlite3"
    service = SuperwriterApplicationService.for_sqlite(db_path)
    project_id, novel_id, scene_id, _ = _seed_retrieval_workspace(service, db_path)
    storage = CanonicalStorage(db_path)

    revisions_before = _count_rows(storage, "canonical_revisions")
    markers_before = len(storage.fetch_metadata_markers(marker_name="retrieval_document"))

    first = service.rebuild_retrieval_support(
        RetrievalRebuildRequest(project_id=project_id, novel_id=novel_id, actor="indexer-1")
    )

    document_markers = _scope_document_markers(storage, novel_id)
    status_markers = storage.fetch_metadata_markers(
        marker_name="retrieval_status",
        target_family="novel",
        target_object_id=novel_id,
    )

    assert first.status.support_only is True
    assert first.status.rebuildable is True
    assert first.status.degraded is False
    assert first.status.indexed_object_count == len(document_markers)
    assert first.document_count == len(document_markers)
    assert first.replaced_marker_count == 0
    assert markers_before == 0
    assert len(status_markers) == 1
    assert all(marker.is_authoritative == 0 for marker in document_markers)
    assert all(marker.is_rebuildable == 1 for marker in document_markers)
    assert all(marker.payload.get("support_only") is True for marker in document_markers)
    assert all(marker.payload.get("source_kind") == "canonical_objects_and_revisions" for marker in document_markers)
    assert _count_rows(storage, "canonical_revisions") == revisions_before

    second = service.rebuild_retrieval_support(
        RetrievalRebuildRequest(project_id=project_id, novel_id=novel_id, actor="indexer-2")
    )

    assert second.replaced_marker_count == first.document_count + 1
    assert len(_scope_document_markers(storage, novel_id)) == first.document_count
    assert len(
        storage.fetch_metadata_markers(
            marker_name="retrieval_status",
            target_family="novel",
            target_object_id=novel_id,
        )
    ) == 1
    assert _count_rows(storage, "canonical_revisions") == revisions_before

    search = service.search_retrieval_support(
        RetrievalSearchRequest(project_id=project_id, novel_id=novel_id, query="broken seal", limit=3)
    )
    assert search.matches
    assert search.matches[0].target_object_id == scene_id
    assert _count_rows(storage, "canonical_revisions") == revisions_before


def test_retrieval_conflicts_become_warnings_and_review_hints_not_canonical_writes(tmp_path: Path) -> None:
    db_path = tmp_path / "canonical.sqlite3"
    service = SuperwriterApplicationService.for_sqlite(db_path)
    project_id, novel_id, _, second_scene_id = _seed_retrieval_workspace(service, db_path)
    storage = CanonicalStorage(db_path)
    revisions_before = _count_rows(storage, "canonical_revisions")

    _ = service.rebuild_retrieval_support(
        RetrievalRebuildRequest(project_id=project_id, novel_id=novel_id, actor="indexer-1")
    )

    result = service.search_retrieval_support(
        RetrievalSearchRequest(project_id=project_id, novel_id=novel_id, query="midnight seal witness", limit=5)
    )

    assert len(result.matches) >= 2
    assert any("conflict" in warning.lower() for warning in result.warnings)
    assert any("verify" in hint.lower() for hint in result.review_hints)
    assert any(match.target_object_id == second_scene_id for match in result.matches[:2])
    assert result.matches[0].ranking_metadata["support_only"] is True
    assert _count_rows(storage, "canonical_revisions") == revisions_before


def test_retrieval_degradation_warns_but_does_not_block_authoring_flows(tmp_path: Path) -> None:
    db_path = tmp_path / "canonical.sqlite3"
    service = SuperwriterApplicationService.for_sqlite(db_path)
    project_id, novel_id, scene_id, _ = _seed_retrieval_workspace(service, db_path)
    storage = CanonicalStorage(db_path)

    _ = service.rebuild_retrieval_support(
        RetrievalRebuildRequest(project_id=project_id, novel_id=novel_id, actor="indexer-1")
    )

    updated_scene = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            target_object_id=scene_id,
            payload={
                "novel_id": novel_id,
                "event_id": "evt_retrieval_001",
                "title": "Broken seal at the quay",
                "summary": "A new witness confirms the seal broke before sunrise.",
            },
            actor="author-1",
            source_surface="scene_editor",
            revision_reason="tighten retrieval source summary",
        )
    )
    assert updated_scene.canonical_revision_id is not None

    degraded = service.search_retrieval_support(
        RetrievalSearchRequest(project_id=project_id, novel_id=novel_id, query="before sunrise", limit=3)
    )

    assert degraded.status.degraded is True
    assert any("stale" in warning.lower() or "rebuild" in warning.lower() for warning in degraded.warnings)

    next_mutation = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            payload={
                "novel_id": novel_id,
                "event_id": "evt_retrieval_003",
                "title": "Harbor ledger handoff",
                "summary": "The courier trades the marked ledger without waiting for retrieval rebuilds.",
            },
            actor="author-1",
            source_surface="scene_editor",
            revision_reason="continue authoring while retrieval is degraded",
        )
    )
    assert next_mutation.disposition == "auto_applied"
    assert next_mutation.canonical_revision_id is not None
    assert storage.fetch_canonical_head("scene", next_mutation.target_object_id) is not None


def _seed_retrieval_workspace(
    service: SuperwriterApplicationService,
    db_path: Path,
) -> tuple[str, str, str, str]:
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            payload={"title": "Retrieval Demo Project"},
            actor="author-1",
            source_surface="setup",
            policy_class="test_seed",
            approval_state="approved",
            revision_reason="seed project",
        )
    )
    novel = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="novel",
            payload={
                "project_id": project.object_id,
                "title": "Harbor of Echoes",
                "genre": "mystery",
            },
            actor="author-1",
            source_surface="setup",
            policy_class="test_seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    scene_one = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            payload={
                "novel_id": novel.object_id,
                "event_id": "evt_retrieval_001",
                "title": "Broken seal at the quay",
                "summary": "The courier learns the first witness saw the broken seal at midnight.",
            },
            actor="author-1",
            source_surface="setup",
            revision_reason="seed first scene",
        )
    )
    _ = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            target_object_id=scene_one.target_object_id,
            payload={
                "novel_id": novel.object_id,
                "event_id": "evt_retrieval_001",
                "title": "Broken seal at the quay",
                "summary": "The courier learns the first witness saw the broken seal at midnight near the harbor chains.",
            },
            actor="author-1",
            source_surface="setup",
            revision_reason="create a second scene revision for retrieval lineage",
        )
    )
    scene_two = service.apply_mutation(
        ServiceMutationRequest(
            target_family="scene",
            payload={
                "novel_id": novel.object_id,
                "event_id": "evt_retrieval_002",
                "title": "Midnight witness on the pier",
                "summary": "Another witness swears the midnight seal changed hands before the bells finished.",
            },
            actor="author-1",
            source_surface="setup",
            revision_reason="seed second scene",
        )
    )
    _ = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="fact_state_record",
            payload={
                "novel_id": novel.object_id,
                "source_scene_id": scene_one.target_object_id,
                "fact": "A dockworker reported the seal was already cracked.",
            },
            actor="author-1",
            source_surface="setup",
            policy_class="test_seed",
            approval_state="approved",
            revision_reason="seed supporting fact",
        )
    )
    _ = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="character",
            payload={
                "novel_id": novel.object_id,
                "name": "Courier Vale",
                "summary": "Keeps a ledger of every broken promise and missing seal.",
            },
            actor="author-1",
            source_surface="setup",
            policy_class="test_seed",
            approval_state="approved",
            revision_reason="seed retrieval character",
        )
    )
    return project.object_id, novel.object_id, scene_one.target_object_id, scene_two.target_object_id


def _count_rows(storage: CanonicalStorage, table_name: str) -> int:
    with storage.connect() as connection:
        row = cast(sqlite3.Row | None, connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone())
    if row is None:
        raise RuntimeError(f"Missing row count for {table_name}")
    count = cast(object, row["count"])
    if isinstance(count, bool):
        return int(count)
    if isinstance(count, int | float | str):
        return int(count)
    raise TypeError(f"Unexpected row count type for {table_name}")


def _scope_document_markers(storage: CanonicalStorage, novel_id: str) -> list[MetadataMarkerSnapshot]:
    return [
        marker
        for marker in storage.fetch_metadata_markers(marker_name="retrieval_document")
        if marker.payload.get("novel_id") == novel_id
    ]
