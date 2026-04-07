from __future__ import annotations

import json
from sqlite3 import Row
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.importers import (
    FANBIANYI_CONTRACT,
    IMPORTER_CONTRACTS,
    WEBNOVEL_WRITER_CONTRACT,
    load_semantic_parity_matrix,
)
from core.runtime import CanonicalStorage, ImportRequest, SuperwriterApplicationService, SupportedDonor


def _fetch_import_records(storage: CanonicalStorage) -> list[dict[str, object]]:
    with storage.connect() as connection:
        rows = cast(
            list[Row],
            connection.execute(
                "SELECT project_id, import_source, import_payload_json FROM import_records ORDER BY record_id ASC"
            ).fetchall(),
        )
    records: list[dict[str, object]] = []
    for row in rows:
        payload = cast(object, json.loads(str(cast(object, row["import_payload_json"]))))
        records.append(
            {
                "project_id": str(cast(object, row["project_id"])),
                "import_source": str(cast(object, row["import_source"])),
                "payload": cast(dict[str, object], payload),
            }
        )
    return records


def _fetch_canonical_provenance(storage: CanonicalStorage, family: str) -> list[dict[str, str | None]]:
    with storage.connect() as connection:
        rows = cast(
            list[Row],
            connection.execute(
                "SELECT source_kind, source_ref, ingest_run_id FROM canonical_objects WHERE family = ? ORDER BY object_id ASC",
                (family,),
            ).fetchall(),
        )
    return [
        {
            "source_kind": str(cast(object, row["source_kind"])),
            "source_ref": None if row["source_ref"] is None else str(cast(object, row["source_ref"])),
            "ingest_run_id": None if row["ingest_run_id"] is None else str(cast(object, row["ingest_run_id"])),
        }
        for row in rows
    ]


def test_webnovel_writer_import_contract_imports_canonical_and_derived_objects(tmp_path: Path) -> None:
    source_root = tmp_path / "webnovel-project"
    state_dir = source_root / ".webnovel"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    _ = state_path.write_text(
        json.dumps(
            {
                "project": {"id": "wv-project-1", "title": "Lantern Archive"},
                "novel": {"id": "wv-novel-1", "title": "Lantern Archive", "genre": "mystery"},
                "scenes": [
                    {
                        "id": "scene-001",
                        "event_id": "evt-001",
                        "title": "Bridge oath",
                        "summary": "The couriers swear to hide the ledger before dawn."
                    }
                ],
                "chapters": [
                    {
                        "source_scene_id": "scene-001",
                        "title": "Chapter 1",
                        "body": "Mist rolled under the bridge as the oath was spoken."
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")
    result = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=source_root,
            actor="importer.webnovel_writer",
        )
    )

    assert WEBNOVEL_WRITER_CONTRACT.input_only is True
    assert WEBNOVEL_WRITER_CONTRACT.supported_artifacts[0].path_hint == ".webnovel/state.json"
    assert {record.family for record in result.imported_objects} == {"project", "novel", "scene", "chapter_artifact"}

    project_records = _fetch_canonical_provenance(storage, "project")
    novel_records = _fetch_canonical_provenance(storage, "novel")
    scene_records = _fetch_canonical_provenance(storage, "scene")
    assert project_records == [
        {
            "source_kind": "import:webnovel-writer",
            "source_ref": str(state_path.resolve()),
            "ingest_run_id": result.ingest_run_id,
        }
    ]
    assert novel_records == [
        {
            "source_kind": "import:webnovel-writer",
            "source_ref": str(state_path.resolve()),
            "ingest_run_id": result.ingest_run_id,
        }
    ]
    assert scene_records == [
        {
            "source_kind": "import:webnovel-writer",
            "source_ref": f"{state_path.resolve()}#scenes[0]",
            "ingest_run_id": result.ingest_run_id,
        }
    ]

    derived_rows = storage.fetch_derived_records("chapter_artifact")
    assert len(derived_rows) == 1
    assert derived_rows[0]["source_scene_revision_id"] == next(
        record.revision_id for record in result.imported_objects if record.family == "scene"
    )
    derived_payload = cast(dict[str, object], derived_rows[0]["payload"])
    assert derived_payload["source_kind"] == "import:webnovel-writer"
    assert derived_payload["source_ref"] == f"{state_path.resolve()}#chapters[0]"
    assert derived_payload["ingest_run_id"] == result.ingest_run_id

    import_records = _fetch_import_records(storage)
    assert len(import_records) == 1
    assert import_records[0]["project_id"] == result.project_id
    assert import_records[0]["import_source"] == "webnovel-writer"
    import_payload = cast(dict[str, object], import_records[0]["payload"])
    assert import_payload["input_only"] is True
    assert import_payload["ingest_run_id"] == result.ingest_run_id
    imported = cast(list[dict[str, object]], import_payload["imported"])
    assert {row["family"] for row in imported} == {"project", "novel", "scene", "chapter_artifact"}


def test_fanbianyi_import_contract_revalidates_character_exports_without_runtime_dependency(
    tmp_path: Path,
) -> None:
    service = SuperwriterApplicationService.for_sqlite(tmp_path / "canonical.sqlite3")
    storage = CanonicalStorage(tmp_path / "canonical.sqlite3")
    source_root = tmp_path / "webnovel-project"
    state_dir = source_root / ".webnovel"
    state_dir.mkdir(parents=True)
    _ = (state_dir / "state.json").write_text(
        json.dumps(
            {
                "project": {"id": "wv-project-2", "title": "Stone Records"},
                "novel": {"id": "wv-novel-2", "title": "Stone Records", "genre": "xianxia"},
            }
        ),
        encoding="utf-8",
    )
    seed_result = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.WEBNOVEL_WRITER,
            source_path=source_root,
            actor="importer.webnovel_writer",
        )
    )
    imported_novel_id = next(record.object_id for record in seed_result.imported_objects if record.family == "novel")
    novel_head = storage.fetch_canonical_head("novel", imported_novel_id)
    if novel_head is None:
        raise AssertionError("Expected seeded novel head")

    export_path = tmp_path / "characters.json"
    _ = export_path.write_text(
        json.dumps(
            [
                {
                    "id": "legacy-char-1",
                    "name": "Shen Ye",
                    "role": "protagonist",
                    "description": "A courier who remembers every lie told in the market.",
                    "personality": "careful",
                    "background": "Raised by bridge keepers."
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = service.import_from_donor(
        ImportRequest(
            donor_key=SupportedDonor.RESTORED_DECOMPILED_ARTIFACTS,
            source_path=export_path,
            actor="importer.fanbianyi",
            project_id=seed_result.project_id,
            novel_id=imported_novel_id,
        )
    )

    assert FANBIANYI_CONTRACT.input_only is True
    assert FANBIANYI_CONTRACT.trust_level.value == "low"
    assert "vectorService side effects" in FANBIANYI_CONTRACT.forbidden_runtime_dependencies

    provenance_rows = _fetch_canonical_provenance(storage, "character")
    assert provenance_rows == [
        {
            "source_kind": "import:restored-decompiled-artifacts",
            "source_ref": f"{export_path.resolve()}#characters[0]",
            "ingest_run_id": result.ingest_run_id,
        }
    ]
    character_head = storage.fetch_canonical_head(
        "character",
        result.imported_objects[0].object_id,
    )
    if character_head is None:
        raise AssertionError("Expected imported character head")
    payload = cast(dict[str, object], character_head["payload"])
    assert payload["name"] == "Shen Ye"
    assert payload["donor_character_id"] == "legacy-char-1"
    assert payload["revalidated_from_decompiled_export"] is True

    import_records = _fetch_import_records(storage)
    low_trust_record = next(
        record for record in import_records if record["import_source"] == "restored-decompiled-artifacts"
    )
    assert low_trust_record["import_source"] == "restored-decompiled-artifacts"
    import_payload = cast(dict[str, object], low_trust_record["payload"])
    assert import_payload["trust_level"] == "low"
    assert "panelRefreshService callbacks" in cast(list[str], import_payload["forbidden_runtime_dependencies"])


def test_semantic_parity_matrix_covers_importers_and_declares_accepted_deltas() -> None:
    matrix = load_semantic_parity_matrix()
    entries = cast(list[dict[str, object]], matrix["entries"])

    assert matrix["version"] == 1
    assert {entry["feature_key"] for entry in entries} == {
        "webnovel_project_state_import",
        "fanbianyi_character_export_import",
        "fanbianyi_runtime_side_effects_are_not_parity_targets",
    }
    assert {contract.donor_key for contract in IMPORTER_CONTRACTS} == {
        "webnovel-writer",
        "restored-decompiled-artifacts",
    }

    by_feature = {str(entry["feature_key"]): entry for entry in entries}
    assert by_feature["webnovel_project_state_import"]["target_owner"] == "structured-object-truth"
    assert "chapter_artifact" in cast(list[str], by_feature["webnovel_project_state_import"]["touched_families"])
    assert "source_kind" in cast(list[str], by_feature["webnovel_project_state_import"]["provenance_requirements"])
    assert "fresh canonical object IDs" in str(
        by_feature["fanbianyi_character_export_import"]["acceptable_delta"]
    )
    assert "not depend on embeddings" in str(
        by_feature["fanbianyi_runtime_side_effects_are_not_parity_targets"]["must_match_behavior"]
    )
