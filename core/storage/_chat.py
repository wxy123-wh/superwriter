from __future__ import annotations

from core.storage._utils import (
    _decode_json_object,
    _encode_json,
    _fetchall,
    _fetchone,
    _generate_id,
    _normalize_payload,
    _row_optional_str,
    _row_str,
    utc_now_iso,
)
from core.storage._types import ChatMessageLinkInput, ChatMessageLinkRow, ChatSessionInput, ChatSessionRow


class _ChatMixin:
    def create_chat_session(self, record: ChatSessionInput) -> str:
        session_state_id = _generate_id("chs")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO chat_sessions (
                    session_state_id, project_id, novel_id, title, runtime_origin,
                    created_at, created_by, updated_at, updated_by, source_kind,
                    source_ref, ingest_run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_state_id, record.project_id, record.novel_id, record.title,
                    record.runtime_origin, timestamp, record.created_by, timestamp,
                    record.created_by, "chat_surface", record.source_ref, None,
                ),
            )
            connection.commit()
        return session_state_id

    def create_chat_message_link(self, record: ChatMessageLinkInput) -> str:
        message_state_id = _generate_id("cml")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO chat_message_links (
                    message_state_id, chat_session_id, linked_object_id, linked_revision_id,
                    chat_message_id, chat_role, payload_json, created_at, created_by,
                    updated_at, updated_by, source_kind, source_ref, ingest_run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_state_id, record.chat_session_id, record.linked_object_id,
                    record.linked_revision_id, record.chat_message_id, record.chat_role,
                    _encode_json(_normalize_payload(record.payload)), timestamp,
                    record.created_by, timestamp, record.created_by, "chat_surface",
                    record.source_ref, None,
                ),
            )
            connection.commit()
        return message_state_id

    def fetch_chat_session_row(self, session_id: str) -> ChatSessionRow | None:
        with self._connection() as connection:
            row = _fetchone(
                connection,
                "SELECT session_state_id, project_id, novel_id, title, runtime_origin, created_by FROM chat_sessions WHERE session_state_id = ?",
                (session_id,),
            )
        if row is None:
            return None
        return ChatSessionRow(
            session_id=_row_str(row, "session_state_id"),
            project_id=_row_str(row, "project_id"),
            novel_id=_row_optional_str(row, "novel_id"),
            title=_row_optional_str(row, "title"),
            runtime_origin=_row_str(row, "runtime_origin"),
            created_by=_row_str(row, "created_by"),
        )

    def fetch_chat_message_link_rows(self, session_id: str) -> list[ChatMessageLinkRow]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT message_state_id, chat_message_id, chat_role, linked_object_id, linked_revision_id, payload_json FROM chat_message_links WHERE chat_session_id = ? ORDER BY created_at ASC, message_state_id ASC",
                (session_id,),
            )
        return [
            ChatMessageLinkRow(
                message_state_id=_row_str(row, "message_state_id"),
                chat_message_id=_row_str(row, "chat_message_id"),
                chat_role=_row_str(row, "chat_role"),
                linked_object_id=_row_optional_str(row, "linked_object_id"),
                linked_revision_id=_row_optional_str(row, "linked_revision_id"),
                payload=_decode_json_object(_row_str(row, "payload_json")),
            )
            for row in rows
        ]
