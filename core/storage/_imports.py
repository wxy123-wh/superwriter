from __future__ import annotations

from core.storage._utils import (
    _decode_json_object,
    _encode_json,
    _fetchall,
    _generate_id,
    _normalize_payload,
    _row_str,
    utc_now_iso,
)
from core.storage._types import ImportRecordInput


class _ImportsMixin:
    def create_import_record(self, record: ImportRecordInput) -> str:
        record_id = _generate_id("imp")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO import_records (
                    record_id, project_id, import_source, import_payload_json,
                    created_at, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id, record.project_id, record.import_source,
                    _encode_json(_normalize_payload(record.import_payload)),
                    timestamp, record.created_by,
                ),
            )
            connection.commit()
        return record_id

    def fetch_import_records(
        self,
        *,
        project_id: str | None = None,
        import_source: str | None = None,
    ) -> list[dict[str, str | object]]:
        filters: list[str] = []
        params: list[object] = []
        if project_id is not None:
            filters.append("project_id = ?")
            params.append(project_id)
        if import_source is not None:
            filters.append("import_source = ?")
            params.append(import_source)

        query = (
            "SELECT record_id, project_id, import_source, import_payload_json, created_at, created_by "
            "FROM import_records"
        )
        if filters:
            query = f"{query} WHERE {' AND '.join(filters)}"
        query = f"{query} ORDER BY created_at ASC, record_id ASC"
        with self._connection() as connection:
            rows = _fetchall(connection, query, tuple(params))
        return [
            {
                "record_id": _row_str(row, "record_id"),
                "project_id": _row_str(row, "project_id"),
                "import_source": _row_str(row, "import_source"),
                "import_payload": _decode_json_object(_row_str(row, "import_payload_json")),
                "created_at": _row_str(row, "created_at"),
                "created_by": _row_str(row, "created_by"),
            }
            for row in rows
        ]
