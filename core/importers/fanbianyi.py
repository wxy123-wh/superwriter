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

DONOR_KEY = "restored-decompiled-artifacts"
SOURCE_SURFACE = "import:restored-decompiled-artifacts"
ACTOR = "importer.fanbianyi"


@dataclass(frozen=True, slots=True)
class CharacterExportImportRow:
    name: str
    role: str
    description: str
    personality: str
    background: str
    donor_character_id: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class CharacterExportImportData:
    source_path: Path
    ingest_run_id: str
    rows: tuple[CharacterExportImportRow, ...]

CONTRACT = DonorImporterContract(
    donor_key=DONOR_KEY,
    donor_owner="concept-donor:restored-decompiled-artifacts",
    target_owner="structured-object-truth",
    trust_level=DonorTrust.LOW,
    input_only=True,
    supported_artifacts=(
        SupportedArtifactContract(
            artifact_key="character_export",
            path_hint="characters.json",
            format="json-array",
            required_fields=("name",),
            optional_fields=("id", "role", "description", "personality", "background", "updatedAt"),
            target_families=("character", "import_record"),
            write_paths=("canonical", "support/import_record"),
            notes="Only accepts offline character export payloads. Decompiled services remain forbidden runtime dependencies.",
        ),
    ),
    forbidden_runtime_dependencies=(
        "characterRepository runtime",
        "aiService embeddings",
        "vectorService side effects",
        "panelRefreshService callbacks",
        ".novel-assistant workspace storage as live truth",
    ),
    notes="Lower-trust donor. Accept imported character rows only after explicit field mapping into canonical character objects.",
)


def _read_rows(path: Path) -> list[dict[str, object]]:
    raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array in {path}")
    raw_items = cast(list[object], raw)
    rows: list[dict[str, object]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError(f"Expected characters[{index}] to be an object")
        rows.append(cast(dict[str, object], item))
    return rows


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected non-empty string for {label}")
    return value.strip()


def load_character_export_import_data(source_path: Path) -> CharacterExportImportData:
    rows = _read_rows(source_path.resolve())
    ingest_run_id = new_ingest_run_id(DONOR_KEY)
    return CharacterExportImportData(
        source_path=source_path.resolve(),
        ingest_run_id=ingest_run_id,
        rows=tuple(
            CharacterExportImportRow(
                name=_text(row.get("name"), f"characters[{index}].name"),
                role=str(row.get("role", "")),
                description=str(row.get("description", "")),
                personality=str(row.get("personality", "")),
                background=str(row.get("background", "")),
                donor_character_id=str(row.get("id", "")),
                source_ref=f"{source_path.resolve()}#characters[{index}]",
            )
            for index, row in enumerate(rows)
        ),
    )


__all__ = [
    "ACTOR",
    "CONTRACT",
    "CharacterExportImportData",
    "CharacterExportImportRow",
    "DONOR_KEY",
    "SOURCE_SURFACE",
    "load_character_export_import_data",
]
