from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from core.runtime.storage import JSONValue
from core.runtime.types.common_types import SupportedDonor

JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ExportArtifactRequest:
    actor: str
    source_surface: str
    source_scene_revision_id: str
    payload: JSONObject
    object_id: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExportArtifactResult:
    artifact_revision_id: str
    object_id: str
    family: str
    source_scene_revision_id: str


@dataclass(frozen=True, slots=True)
class PublishExportRequest:
    project_id: str
    novel_id: str
    actor: str
    output_root: Path
    chapter_artifact_object_id: str | None = None
    base_chapter_artifact_revision_id: str | None = None
    expected_source_scene_revision_id: str | None = None
    export_object_id: str | None = None
    expected_import_source: str | None = "webnovel-writer"
    export_format: str = "markdown"
    source_surface: str = "publish_surface"
    source_ref: str | None = None
    ingest_run_id: str | None = None
    fail_after_file_count: int | None = None


@dataclass(frozen=True, slots=True)
class PublishExportArtifactRequest:
    artifact_revision_id: str
    actor: str
    output_root: Path
    source_surface: str = "publish_surface"
    fail_after_file_count: int | None = None


@dataclass(frozen=True, slots=True)
class PublishExportArtifactResult:
    disposition: str
    artifact_revision_id: str
    object_id: str
    bundle_path: str
    projected_files: tuple[str, ...]
    failure_kind: str | None = None
    failure_detail: str | None = None
    recovery_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PublishExportResult:
    disposition: str
    export_result: ExportArtifactResult | None
    publish_result: PublishExportArtifactResult | None
    stale_details: JSONObject | None = None
    recovery_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportRequest:
    donor_key: SupportedDonor
    source_path: Path
    actor: str
    project_id: str | None = None
    novel_id: str | None = None


@dataclass(frozen=True, slots=True)
class ImportObjectResult:
    family: str
    object_id: str
    revision_id: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class ImportResult:
    donor_key: str
    ingest_run_id: str
    import_record_id: str
    project_id: str
    imported_objects: tuple[ImportObjectResult, ...]
