from __future__ import annotations

from core.objects.contract import FamilyCategory
from core.storage._utils import (
    JSONObject,
    JSONValue,
    _build_diff,
    _decode_json_object,
    _encode_json,
    _fetchall,
    _fetchone,
    _generate_id,
    _normalize_payload,
    _row_int,
    _row_optional_str,
    _row_str,
    utc_now_iso,
)
from core.storage._types import CanonicalWriteRequest, CanonicalWriteResult, WorkspaceCanonicalRow


class _CanonicalMixin:
    def write_canonical_object(self, request: CanonicalWriteRequest) -> CanonicalWriteResult:
        contract = self._require_family_category(request.family, FamilyCategory.CANONICAL)
        object_id = request.object_id or _generate_id(contract.id_contract.prefix)
        self._validate_object_id(contract, object_id)
        payload = _normalize_payload(request.payload)
        created_by = request.created_by or request.actor
        timestamp = utc_now_iso()

        with self._connection() as connection:
            existing = _fetchone(
                connection,
                """
                SELECT current_revision_id, current_revision_number, current_payload_json, created_at, created_by
                FROM canonical_objects
                WHERE object_id = ?
                """,
                (object_id,),
            )

            before_payload: JSONObject = {}
            parent_revision_id: str | None = None
            revision_number = 1
            created_at = timestamp
            if existing is not None:
                before_payload = _decode_json_object(_row_str(existing, "current_payload_json"))
                parent_revision_id = _row_str(existing, "current_revision_id")
                revision_number = _row_int(existing, "current_revision_number") + 1
                created_at = _row_str(existing, "created_at")
                created_by = _row_str(existing, "created_by")

            revision_id = _generate_id("rev")
            mutation_record_id = _generate_id("mut")
            diff_payload = _build_diff(before_payload, payload)

            if existing is None:
                _ = connection.execute(
                    """
                    INSERT INTO canonical_objects (
                        object_id, family, category, current_revision_id,
                        current_revision_number, current_payload_json,
                        created_at, created_by, updated_at, updated_by,
                        source_kind, source_ref, ingest_run_id
                    )
                    VALUES (?, ?, 'canonical', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        object_id, request.family, revision_id, revision_number,
                        _encode_json(payload), created_at, created_by, timestamp,
                        request.actor, request.source_surface, request.source_ref,
                        request.ingest_run_id,
                    ),
                )
            else:
                _ = connection.execute(
                    """
                    UPDATE canonical_objects
                    SET current_revision_id = ?, current_revision_number = ?,
                        current_payload_json = ?, updated_at = ?, updated_by = ?,
                        source_kind = ?, source_ref = ?, ingest_run_id = ?
                    WHERE object_id = ?
                    """,
                    (
                        revision_id, revision_number, _encode_json(payload), timestamp,
                        request.actor, request.source_surface, request.source_ref,
                        request.ingest_run_id, object_id,
                    ),
                )

            _ = connection.execute(
                """
                INSERT INTO canonical_revisions (
                    revision_id, family, object_id, revision_number, parent_revision_id,
                    snapshot_json, created_at, created_by, revision_reason,
                    revision_source_message_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id, request.family, object_id, revision_number,
                    parent_revision_id, _encode_json(payload), timestamp, request.actor,
                    request.revision_reason, request.revision_source_message_id,
                ),
            )
            _ = connection.execute(
                """
                INSERT INTO mutation_records (
                    record_id, target_object_family, target_object_id, result_revision_id,
                    resulting_revision_number, actor_id, source_surface, skill_name,
                    policy_class, diff_payload_json, approval_state, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_record_id, request.family, object_id, revision_id,
                    revision_number, request.actor, request.source_surface, request.skill,
                    request.policy_class, _encode_json(diff_payload), request.approval_state,
                    timestamp,
                ),
            )
            connection.commit()

        return CanonicalWriteResult(
            object_id=object_id,
            revision_id=revision_id,
            revision_number=revision_number,
            parent_revision_id=parent_revision_id,
            mutation_record_id=mutation_record_id,
        )

    def fetch_canonical_head(self, family: str, object_id: str) -> dict[str, str | int | JSONObject] | None:
        with self._connection() as connection:
            row = _fetchone(
                connection,
                """
                SELECT family, object_id, current_revision_id, current_revision_number, current_payload_json
                FROM canonical_objects
                WHERE family = ? AND object_id = ?
                """,
                (family, object_id),
            )
        if row is None:
            return None
        return {
            "family": _row_str(row, "family"),
            "object_id": _row_str(row, "object_id"),
            "current_revision_id": _row_str(row, "current_revision_id"),
            "current_revision_number": _row_int(row, "current_revision_number"),
            "payload": _decode_json_object(_row_str(row, "current_payload_json")),
        }

    def fetch_canonical_revisions(self, object_id: str) -> list[dict[str, str | int | JSONObject | None]]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                """
                SELECT revision_id, revision_number, parent_revision_id, snapshot_json
                FROM canonical_revisions
                WHERE object_id = ?
                ORDER BY revision_number ASC
                """,
                (object_id,),
            )
        return [
            {
                "revision_id": _row_str(row, "revision_id"),
                "revision_number": _row_int(row, "revision_number"),
                "parent_revision_id": _row_optional_str(row, "parent_revision_id"),
                "snapshot": _decode_json_object(_row_str(row, "snapshot_json")),
            }
            for row in rows
        ]

    def fetch_mutation_records(self, object_id: str) -> list[dict[str, str | int | JSONObject | None]]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                """
                SELECT record_id, target_object_family, target_object_id, result_revision_id,
                       resulting_revision_number, actor_id, source_surface, skill_name,
                       policy_class, diff_payload_json, approval_state
                FROM mutation_records
                WHERE target_object_id = ?
                ORDER BY resulting_revision_number ASC, record_id ASC
                """,
                (object_id,),
            )
        return [
            {
                "record_id": _row_str(row, "record_id"),
                "target_object_family": _row_str(row, "target_object_family"),
                "target_object_id": _row_str(row, "target_object_id"),
                "result_revision_id": _row_str(row, "result_revision_id"),
                "resulting_revision_number": _row_int(row, "resulting_revision_number"),
                "actor_id": _row_str(row, "actor_id"),
                "source_surface": _row_str(row, "source_surface"),
                "skill_name": _row_optional_str(row, "skill_name"),
                "policy_class": _row_str(row, "policy_class"),
                "diff_payload": _decode_json_object(_row_str(row, "diff_payload_json")),
                "approval_state": _row_str(row, "approval_state"),
            }
            for row in rows
        ]

    def delete_canonical_object(self, family: str, object_id: str) -> bool:
        with self._connection() as connection:
            row = _fetchone(
                connection,
                "SELECT 1 FROM canonical_objects WHERE family = ? AND object_id = ?",
                (family, object_id),
            )
            if row is None:
                return False
            _ = connection.execute(
                "DELETE FROM approval_records WHERE mutation_record_id IN (SELECT record_id FROM mutation_records WHERE target_object_family = ? AND target_object_id = ?)",
                (family, object_id),
            )
            _ = connection.execute(
                "DELETE FROM mutation_records WHERE target_object_family = ? AND target_object_id = ?",
                (family, object_id),
            )
            _ = connection.execute(
                "DELETE FROM canonical_revisions WHERE family = ? AND object_id = ?",
                (family, object_id),
            )
            _ = connection.execute(
                "DELETE FROM canonical_objects WHERE family = ? AND object_id = ?",
                (family, object_id),
            )
            connection.commit()
        return True

    def fetch_workspace_canonical_rows(
        self,
        *,
        project_id: str,
        novel_id: str | None = None,
    ) -> list[WorkspaceCanonicalRow]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT family, object_id, current_revision_id, current_revision_number, current_payload_json FROM canonical_objects ORDER BY family, object_id",
            )
        summaries: list[WorkspaceCanonicalRow] = []
        for row in rows:
            payload = _decode_json_object(_row_str(row, "current_payload_json"))
            payload_project_id = payload.get("project_id")
            payload_novel_id = payload.get("novel_id")
            matches_project = _row_str(row, "object_id") == project_id or payload_project_id == project_id
            matches_novel = novel_id is None or _row_str(row, "object_id") == novel_id or payload_novel_id == novel_id
            if not matches_project and not matches_novel:
                continue
            summaries.append(
                WorkspaceCanonicalRow(
                    family=_row_str(row, "family"),
                    object_id=_row_str(row, "object_id"),
                    current_revision_id=_row_str(row, "current_revision_id"),
                    current_revision_number=_row_int(row, "current_revision_number"),
                    payload=payload,
                )
            )
        return summaries

    def fetch_all_canonical_rows(self) -> list[WorkspaceCanonicalRow]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT family, object_id, current_revision_id, current_revision_number, current_payload_json FROM canonical_objects ORDER BY family, object_id",
            )
        return [
            WorkspaceCanonicalRow(
                family=_row_str(row, "family"),
                object_id=_row_str(row, "object_id"),
                current_revision_id=_row_str(row, "current_revision_id"),
                current_revision_number=_row_int(row, "current_revision_number"),
                payload=_decode_json_object(_row_str(row, "current_payload_json")),
            )
            for row in rows
        ]
