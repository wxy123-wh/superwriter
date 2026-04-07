from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from core.importers.contracts import (
    DonorImporterContract,
    DonorTrust,
    SupportedArtifactContract,
    new_ingest_run_id,
)

DONOR_KEY = "webnovel-writer"
SOURCE_SURFACE = "import:webnovel-writer"
ACTOR = "importer.webnovel_writer"


@dataclass(frozen=True, slots=True)
class WebnovelSceneImportRow:
    donor_scene_id: str
    event_id: str
    title: str
    summary: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class WebnovelChapterImportRow:
    donor_scene_id: str
    chapter_title: str
    body: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class WebnovelProjectImportData:
    source_root: Path
    state_path: Path
    ingest_run_id: str
    project_title: str
    donor_project_id: str
    novel_title: str
    donor_novel_id: str
    genre: str
    scenes: tuple[WebnovelSceneImportRow, ...]
    chapters: tuple[WebnovelChapterImportRow, ...]

CONTRACT = DonorImporterContract(
    donor_key=DONOR_KEY,
    donor_owner="implementation-donor:webnovel-writer",
    target_owner="structured-object-truth",
    trust_level=DonorTrust.HIGH,
    input_only=True,
    supported_artifacts=(
        SupportedArtifactContract(
            artifact_key="project_state",
            path_hint=".webnovel/state.json",
            format="json",
            required_fields=("project", "novel"),
            optional_fields=("scenes", "chapters"),
            target_families=("project", "novel", "scene", "chapter_artifact", "import_record"),
            write_paths=("canonical", "derived", "support/import_record"),
            notes="Accepts a validated donor project root and only reads state.json as an import boundary.",
        ),
    ),
    forbidden_runtime_dependencies=(
        ".webnovel/chat.db as live dependency",
        "dashboard runtime services",
        "project-root discovery after import completion",
    ),
    notes="Higher-trust donor. Imports normalized project data into canonical and derived superwriter seams only.",
)


def _read_json(path: Path) -> dict[str, object]:
    raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return cast(dict[str, object], raw)


def _require_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected {label} to be an object")
    return cast(dict[str, object], value)


def _require_list(value: object, label: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Expected {label} to be a list")
    raw_items = cast(list[object], value)
    rows: list[dict[str, object]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError(f"Expected {label}[{index}] to be an object")
        rows.append(cast(dict[str, object], item))
    return rows


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected non-empty string for {label}")
    return value.strip()


def load_project_root_import_data(source_root: Path) -> WebnovelProjectImportData:
    state_path = source_root.resolve() / ".webnovel" / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Missing donor artifact: {state_path}")

    state = _read_json(state_path)
    project = _require_mapping(state.get("project"), "project")
    novel = _require_mapping(state.get("novel"), "novel")
    scenes = _require_list(state.get("scenes"), "scenes")
    chapters = _require_list(state.get("chapters"), "chapters")
    ingest_run_id = new_ingest_run_id(DONOR_KEY)
    return WebnovelProjectImportData(
        source_root=source_root.resolve(),
        state_path=state_path,
        ingest_run_id=ingest_run_id,
        project_title=_text(project.get("title"), "project.title"),
        donor_project_id=str(project.get("id", "")),
        novel_title=_text(novel.get("title"), "novel.title"),
        donor_novel_id=str(novel.get("id", "")),
        genre=str(novel.get("genre", "")),
        scenes=tuple(
            WebnovelSceneImportRow(
                donor_scene_id=_text(scene.get("id"), f"scenes[{index}].id"),
                event_id=str(scene.get("event_id", f"evt_donor_{index + 1}")),
                title=_text(scene.get("title"), f"scenes[{index}].title"),
                summary=str(scene.get("summary", "")),
                source_ref=f"{state_path}#scenes[{index}]",
            )
            for index, scene in enumerate(scenes)
        ),
        chapters=tuple(
            WebnovelChapterImportRow(
                donor_scene_id=_text(chapter.get("source_scene_id"), f"chapters[{index}].source_scene_id"),
                chapter_title=_text(chapter.get("title"), f"chapters[{index}].title"),
                body=_text(chapter.get("body"), f"chapters[{index}].body"),
                source_ref=f"{state_path}#chapters[{index}]",
            )
            for index, chapter in enumerate(chapters)
        ),
    )


__all__ = [
    "ACTOR",
    "CONTRACT",
    "DONOR_KEY",
    "SOURCE_SURFACE",
    "WebnovelChapterImportRow",
    "WebnovelProjectImportData",
    "WebnovelSceneImportRow",
    "load_project_root_import_data",
]
