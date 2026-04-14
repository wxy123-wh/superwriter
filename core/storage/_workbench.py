from __future__ import annotations

from core.storage._utils import (
    JSONObject,
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


class _WorkbenchMixin:
    def create_workbench_session(
        self,
        project_id: str,
        novel_id: str,
        workbench_type: str,
        parent_object_id: str,
        actor: str,
        source_surface: str = "workbench_iteration",
        source_ref: str | None = None,
    ) -> str:
        """Create a new workbench iteration session."""
        session_id = _generate_id("wbs")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO workbench_sessions (
                    session_id, project_id, novel_id, workbench_type,
                    parent_object_id, actor, status, current_iteration,
                    started_at, source_surface, source_ref
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (session_id, project_id, novel_id, workbench_type,
                 parent_object_id, actor, "active", timestamp, source_surface, source_ref),
            )
            connection.commit()
        return session_id

    def get_workbench_session(self, session_id: str) -> dict[str, object] | None:
        """Get a workbench session by ID."""
        with self._connection() as connection:
            row = _fetchone(
                connection,
                """
                SELECT session_id, project_id, novel_id, workbench_type,
                       parent_object_id, actor, status, current_iteration,
                       started_at, completed_at, source_surface, source_ref
                FROM workbench_sessions WHERE session_id = ?
                """,
                (session_id,),
            )
        if row is None:
            return None
        return {
            "session_id": _row_str(row, "session_id"),
            "project_id": _row_str(row, "project_id"),
            "novel_id": _row_str(row, "novel_id"),
            "workbench_type": _row_str(row, "workbench_type"),
            "parent_object_id": _row_str(row, "parent_object_id"),
            "actor": _row_str(row, "actor"),
            "status": _row_str(row, "status"),
            "current_iteration": _row_int(row, "current_iteration"),
            "started_at": _row_str(row, "started_at"),
            "completed_at": _row_optional_str(row, "completed_at"),
            "source_surface": _row_str(row, "source_surface"),
            "source_ref": _row_optional_str(row, "source_ref"),
        }

    def list_workbench_sessions(
        self,
        project_id: str | None = None,
        novel_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        """List workbench sessions with optional filters."""
        conditions = []
        params = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if novel_id:
            conditions.append("novel_id = ?")
            params.append(novel_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                f"""
                SELECT session_id, project_id, novel_id, workbench_type,
                       parent_object_id, actor, status, current_iteration,
                       started_at, completed_at
                FROM workbench_sessions
                {where_clause}
                ORDER BY started_at DESC
                """,
                tuple(params),
            )
        return [
            {
                "session_id": _row_str(row, "session_id"),
                "project_id": _row_str(row, "project_id"),
                "novel_id": _row_str(row, "novel_id"),
                "workbench_type": _row_str(row, "workbench_type"),
                "parent_object_id": _row_str(row, "parent_object_id"),
                "actor": _row_str(row, "actor"),
                "status": _row_str(row, "status"),
                "current_iteration": _row_int(row, "current_iteration"),
                "started_at": _row_str(row, "started_at"),
                "completed_at": _row_optional_str(row, "completed_at"),
            }
            for row in rows
        ]

    def update_workbench_session_status(
        self,
        session_id: str,
        status: str,
    ) -> bool:
        """Update the status of a workbench session."""
        updates = ["status = ?"]
        params = [status]
        if status == "completed":
            updates.append("completed_at = ?")
            params.append(utc_now_iso())

        params.append(session_id)
        with self._connection() as connection:
            cursor = connection.execute(
                f"UPDATE workbench_sessions SET {', '.join(updates)} WHERE session_id = ?",
                tuple(params),
            )
            connection.commit()
        return cursor.rowcount > 0

    def increment_workbench_iteration(self, session_id: str) -> int:
        """Increment the iteration counter for a session and return the new value."""
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE workbench_sessions SET current_iteration = current_iteration + 1 WHERE session_id = ?",
                (session_id,),
            )
            connection.commit()
            if cursor.rowcount == 0:
                return 0
            # Fetch the new value
            row = _fetchone(
                connection,
                "SELECT current_iteration FROM workbench_sessions WHERE session_id = ?",
                (session_id,),
            )
            return _row_int(row, "current_iteration") if row else 0

    def create_candidate_draft(
        self,
        session_id: str,
        iteration_number: int,
        payload: JSONObject,
        generation_context: JSONObject,
    ) -> str:
        """Create a new candidate draft for a workbench session."""
        draft_id = _generate_id("cbd")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO workbench_candidate_drafts (
                    draft_id, session_id, iteration_number,
                    payload_json, generation_context_json, is_selected, created_at
                )
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (draft_id, session_id, iteration_number,
                 _encode_json(_normalize_payload(payload)),
                 _encode_json(_normalize_payload(generation_context)), timestamp),
            )
            connection.commit()
        return draft_id

    def get_candidate_draft(self, draft_id: str) -> dict[str, object] | None:
        """Get a candidate draft by ID."""
        with self._connection() as connection:
            row = _fetchone(
                connection,
                """
                SELECT draft_id, session_id, iteration_number,
                       payload_json, generation_context_json, is_selected, created_at
                FROM workbench_candidate_drafts WHERE draft_id = ?
                """,
                (draft_id,),
            )
        if row is None:
            return None
        return {
            "draft_id": _row_str(row, "draft_id"),
            "session_id": _row_str(row, "session_id"),
            "iteration_number": _row_int(row, "iteration_number"),
            "payload": _decode_json_object(_row_str(row, "payload_json")),
            "generation_context": _decode_json_object(_row_str(row, "generation_context_json")),
            "is_selected": bool(_row_int(row, "is_selected")),
            "created_at": _row_str(row, "created_at"),
        }

    def list_candidate_drafts(
        self,
        session_id: str,
        iteration_number: int | None = None,
    ) -> list[dict[str, object]]:
        """List candidate drafts for a session."""
        conditions = ["session_id = ?"]
        params = [session_id]
        if iteration_number is not None:
            conditions.append("iteration_number = ?")
            params.append(iteration_number)

        with self._connection() as connection:
            rows = _fetchall(
                connection,
                f"""
                SELECT draft_id, session_id, iteration_number,
                       payload_json, generation_context_json, is_selected, created_at
                FROM workbench_candidate_drafts
                WHERE {' AND '.join(conditions)}
                ORDER BY iteration_number, created_at
                """,
                tuple(params),
            )
        return [
            {
                "draft_id": _row_str(row, "draft_id"),
                "session_id": _row_str(row, "session_id"),
                "iteration_number": _row_int(row, "iteration_number"),
                "payload": _decode_json_object(_row_str(row, "payload_json")),
                "generation_context": _decode_json_object(_row_str(row, "generation_context_json")),
                "is_selected": bool(_row_int(row, "is_selected")),
                "created_at": _row_str(row, "created_at"),
            }
            for row in rows
        ]

    def select_candidate_draft(self, draft_id: str) -> bool:
        """Mark a candidate draft as selected (deselects others in the same session)."""
        with self._connection() as connection:
            # First get the session_id
            row = _fetchone(
                connection,
                "SELECT session_id FROM workbench_candidate_drafts WHERE draft_id = ?",
                (draft_id,),
            )
            if row is None:
                return False
            session_id = _row_str(row, "session_id")

            # Deselect all in session
            _ = connection.execute(
                "UPDATE workbench_candidate_drafts SET is_selected = 0 WHERE session_id = ?",
                (session_id,),
            )
            # Select the target
            cursor = connection.execute(
                "UPDATE workbench_candidate_drafts SET is_selected = 1 WHERE draft_id = ?",
                (draft_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def create_workbench_feedback(
        self,
        session_id: str,
        target_draft_id: str,
        feedback_type: str,
        feedback_text: str,
        target_section: str | None = None,
        created_by: str = "",
    ) -> str:
        """Create a feedback record for a candidate draft."""
        feedback_id = _generate_id("wbf")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO workbench_feedback (
                    feedback_id, session_id, target_draft_id,
                    feedback_type, feedback_text, target_section, created_at, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, session_id, target_draft_id,
                 feedback_type, feedback_text, target_section, timestamp, created_by),
            )
            connection.commit()
        return feedback_id

    def list_workbench_feedback(
        self,
        session_id: str,
        target_draft_id: str | None = None,
    ) -> list[dict[str, object]]:
        """List feedback records for a session."""
        conditions = ["session_id = ?"]
        params = [session_id]
        if target_draft_id:
            conditions.append("target_draft_id = ?")
            params.append(target_draft_id)

        with self._connection() as connection:
            rows = _fetchall(
                connection,
                f"""
                SELECT feedback_id, session_id, target_draft_id,
                       feedback_type, feedback_text, target_section, created_at, created_by
                FROM workbench_feedback
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at
                """,
                tuple(params),
            )
        return [
            {
                "feedback_id": _row_str(row, "feedback_id"),
                "session_id": _row_str(row, "session_id"),
                "target_draft_id": _row_str(row, "target_draft_id"),
                "feedback_type": _row_str(row, "feedback_type"),
                "feedback_text": _row_str(row, "feedback_text"),
                "target_section": _row_optional_str(row, "target_section"),
                "created_at": _row_str(row, "created_at"),
                "created_by": _row_str(row, "created_by"),
            }
            for row in rows
        ]
