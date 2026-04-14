from __future__ import annotations

from core.storage._utils import (
    _decode_json_object,
    _encode_json,
    _fetchall,
    _generate_id,
    _normalize_payload,
    _row_int,
    _row_optional_str,
    _row_str,
    utc_now_iso,
)
from core.storage._types import MetadataMarkerInput, MetadataMarkerSnapshot


class _MetadataMixin:
    def create_metadata_marker(self, record: MetadataMarkerInput) -> str:
        marker_id = _generate_id("mdm")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO metadata_markers (
                    marker_id, target_family, target_object_id, target_revision_id,
                    marker_name, marker_payload_json, created_at, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    marker_id, record.target_family, record.target_object_id,
                    record.target_revision_id, record.marker_name,
                    _encode_json(_normalize_payload(record.marker_payload)),
                    timestamp, record.created_by,
                ),
            )
            connection.commit()
        return marker_id

    def fetch_metadata_markers(
        self,
        *,
        marker_name: str | None = None,
        target_family: str | None = None,
        target_object_id: str | None = None,
        target_revision_id: str | None = None,
    ) -> list[MetadataMarkerSnapshot]:
        filters: list[str] = []
        params: list[object] = []
        if marker_name is not None:
            filters.append("marker_name = ?")
            params.append(marker_name)
        if target_family is not None:
            filters.append("target_family = ?")
            params.append(target_family)
        if target_object_id is not None:
            filters.append("target_object_id = ?")
            params.append(target_object_id)
        if target_revision_id is not None:
            filters.append("target_revision_id = ?")
            params.append(target_revision_id)

        query = (
            "SELECT marker_id, target_family, target_object_id, target_revision_id, marker_name, "
            "marker_payload_json, is_authoritative, is_rebuildable, created_at, created_by "
            "FROM metadata_markers"
        )
        if filters:
            query = f"{query} WHERE {' AND '.join(filters)}"
        query = f"{query} ORDER BY created_at ASC, marker_id ASC"

        with self._connection() as connection:
            rows = _fetchall(connection, query, tuple(params))
        return [
            MetadataMarkerSnapshot(
                marker_id=_row_str(row, "marker_id"),
                target_family=_row_str(row, "target_family"),
                target_object_id=_row_str(row, "target_object_id"),
                target_revision_id=_row_optional_str(row, "target_revision_id"),
                marker_name=_row_str(row, "marker_name"),
                payload=_decode_json_object(_row_str(row, "marker_payload_json")),
                is_authoritative=_row_int(row, "is_authoritative"),
                is_rebuildable=_row_int(row, "is_rebuildable"),
                created_at=_row_str(row, "created_at"),
                created_by=_row_str(row, "created_by"),
            )
            for row in rows
        ]

    def delete_metadata_markers(
        self,
        *,
        marker_name: str | None = None,
        target_family: str | None = None,
        target_object_id: str | None = None,
        target_revision_id: str | None = None,
    ) -> int:
        filters: list[str] = []
        params: list[object] = []
        if marker_name is not None:
            filters.append("marker_name = ?")
            params.append(marker_name)
        if target_family is not None:
            filters.append("target_family = ?")
            params.append(target_family)
        if target_object_id is not None:
            filters.append("target_object_id = ?")
            params.append(target_object_id)
        if target_revision_id is not None:
            filters.append("target_revision_id = ?")
            params.append(target_revision_id)
        if not filters:
            raise ValueError("delete_metadata_markers requires at least one filter")

        query = f"DELETE FROM metadata_markers WHERE {' AND '.join(filters)}"
        with self._connection() as connection:
            cursor = connection.execute(query, tuple(params))
            connection.commit()
        return int(cursor.rowcount)
