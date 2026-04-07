from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ExportProjectionFile:
    relative_path: str
    media_type: str
    content: str


@dataclass(frozen=True, slots=True)
class FilesystemProjectionPlan:
    artifact_revision_id: str
    object_id: str
    bundle_directory: str
    files: tuple[ExportProjectionFile, ...]
    manifest: JSONObject


@dataclass(frozen=True, slots=True)
class ProjectionFailure:
    kind: str
    detail: str
    recovery_action: str


@dataclass(frozen=True, slots=True)
class ProjectionWriteResult:
    disposition: str
    bundle_path: str
    projected_files: tuple[str, ...]
    failure: ProjectionFailure | None = None


def build_filesystem_projection_plan(
    *,
    artifact_revision_id: str,
    object_id: str,
    payload: JSONObject,
) -> FilesystemProjectionPlan:
    projections_raw = payload.get("projections")
    if not isinstance(projections_raw, list) or not projections_raw:
        raise ValueError("export payload is missing explicit filesystem projections")

    files: list[ExportProjectionFile] = []
    for index, raw_projection in enumerate(projections_raw):
        if not isinstance(raw_projection, dict):
            raise ValueError(f"projection[{index}] must be an object")
        relative_path = _require_relative_path(raw_projection.get("path"), f"projection[{index}].path")
        media_type = _require_text(raw_projection.get("media_type"), f"projection[{index}].media_type")
        content = _require_text(raw_projection.get("content"), f"projection[{index}].content")
        files.append(
            ExportProjectionFile(
                relative_path=relative_path,
                media_type=media_type,
                content=content,
            )
        )

    bundle_directory = _bundle_directory(object_id=object_id, artifact_revision_id=artifact_revision_id)
    manifest: JSONObject = {
        "artifact_revision_id": artifact_revision_id,
        "object_id": object_id,
        "bundle_directory": bundle_directory,
        "novel_id": payload.get("novel_id"),
        "source_chapter_artifact_id": payload.get("source_chapter_artifact_id"),
        "source_scene_revision_id": payload.get("source_scene_revision_id"),
        "lineage": cast(JSONObject, payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}),
        "projected_files": [file.relative_path for file in files],
    }
    return FilesystemProjectionPlan(
        artifact_revision_id=artifact_revision_id,
        object_id=object_id,
        bundle_directory=bundle_directory,
        files=tuple(files),
        manifest=manifest,
    )


def write_projection_plan(
    *,
    plan: FilesystemProjectionPlan,
    output_root: Path,
    fail_after_file_count: int | None = None,
) -> ProjectionWriteResult:
    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    bundle_path = root / plan.bundle_directory
    staging_path = root / f".{plan.bundle_directory}.staging"
    if bundle_path.exists():
        return ProjectionWriteResult(
            disposition="already_published",
            bundle_path=str(bundle_path),
            projected_files=tuple(str(bundle_path / file.relative_path) for file in plan.files),
        )

    if staging_path.exists():
        _ = shutil.rmtree(staging_path)

    written_files: list[str] = []
    try:
        _ = staging_path.mkdir(parents=True, exist_ok=False)
        manifest_path = staging_path / "manifest.json"
        _ = manifest_path.write_text(
            json.dumps(plan.manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        for index, file in enumerate(plan.files, start=1):
            target = _safe_bundle_path(staging_path, file.relative_path)
            _ = target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_text(file.content, encoding="utf-8")
            written_files.append(str(bundle_path / file.relative_path))
            if fail_after_file_count is not None and index >= fail_after_file_count:
                raise RuntimeError("simulated interrupted write during staged projection publish")
        _ = staging_path.replace(bundle_path)
        return ProjectionWriteResult(
            disposition="published",
            bundle_path=str(bundle_path),
            projected_files=tuple(str(bundle_path / file.relative_path) for file in plan.files),
        )
    except Exception as error:
        if staging_path.exists():
            shutil.rmtree(staging_path, ignore_errors=True)
        return ProjectionWriteResult(
            disposition="projection_failed",
            bundle_path=str(bundle_path),
            projected_files=(),
            failure=ProjectionFailure(
                kind="interrupted_write",
                detail=str(error),
                recovery_action=(
                    "No canonical state changed and no partial bundle was left behind; re-run publish against the stored export artifact revision."
                ),
            ),
        )


def _bundle_directory(*, object_id: str, artifact_revision_id: str) -> str:
    return f"{object_id}-{artifact_revision_id}"


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected non-empty string for {label}")
    return value.strip()


def _require_relative_path(value: object, label: str) -> str:
    raw_path = _require_text(value, label)
    candidate = Path(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} must stay inside the export bundle")
    return candidate.as_posix()


def _safe_bundle_path(bundle_root: Path, relative_path: str) -> Path:
    candidate = (bundle_root / relative_path).resolve()
    bundle_root_resolved = bundle_root.resolve()
    if candidate != bundle_root_resolved and bundle_root_resolved not in candidate.parents:
        raise ValueError("projection path escapes export bundle root")
    return candidate
