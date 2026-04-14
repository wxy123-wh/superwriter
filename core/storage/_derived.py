from __future__ import annotations

from core.objects.contract import FamilyCategory
from core.storage._utils import (
    _decode_json_object,
    _encode_json,
    _fetchall,
    _fetchone,
    _generate_id,
    _normalize_payload,
    _row_int,
    _row_str,
    utc_now_iso,
)
from core.storage._types import DerivedRecordInput


class _DerivedMixin:
    def create_derived_record(self, record: DerivedRecordInput) -> str:
        contract = self._require_family_category(record.family, FamilyCategory.DERIVED)
        object_id = record.object_id or _generate_id(contract.id_contract.prefix)
        self._validate_object_id(contract, object_id)
        artifact_revision_id = _generate_id("drv")
        timestamp = utc_now_iso()
        payload = _normalize_payload(record.payload)

        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO derived_records (
                    artifact_revision_id, object_id, family, category,
                    source_scene_revision_id, payload_json, created_at, created_by,
                    source_ref, ingest_run_id
                )
                VALUES (?, ?, ?, 'derived', ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_revision_id, object_id, record.family,
                    record.source_scene_revision_id, _encode_json(payload),
                    timestamp, record.created_by, record.source_ref, record.ingest_run_id,
                ),
            )
            connection.commit()

        return artifact_revision_id

    def fetch_derived_records(self, family: str) -> list[dict[str, str | int | object]]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                """
                SELECT artifact_revision_id, object_id, source_scene_revision_id, payload_json,
                       is_authoritative, is_rebuildable
                FROM derived_records
                WHERE family = ?
                ORDER BY created_at ASC, artifact_revision_id ASC
                """,
                (family,),
            )
        return [
            {
                "artifact_revision_id": _row_str(row, "artifact_revision_id"),
                "object_id": _row_str(row, "object_id"),
                "source_scene_revision_id": _row_str(row, "source_scene_revision_id"),
                "payload": _decode_json_object(_row_str(row, "payload_json")),
                "is_authoritative": _row_int(row, "is_authoritative"),
                "is_rebuildable": _row_int(row, "is_rebuildable"),
            }
            for row in rows
        ]

    def delete_derived_object(self, family: str, object_id: str) -> bool:
        with self._connection() as connection:
            row = _fetchone(
                connection,
                "SELECT 1 FROM derived_records WHERE family = ? AND object_id = ?",
                (family, object_id),
            )
            if row is None:
                return False
            _ = connection.execute(
                "DELETE FROM derived_records WHERE family = ? AND object_id = ?",
                (family, object_id),
            )
            connection.commit()
        return True
