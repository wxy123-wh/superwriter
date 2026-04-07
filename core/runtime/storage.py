from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeAlias, cast

from core.objects.contract import (
    CANONICAL_FAMILIES,
    DERIVED_FAMILIES,
    FAMILY_REGISTRY,
    FamilyCategory,
    FamilyContract,
    RevisionMode,
    get_family_contract,
)

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


def _row_str(row: sqlite3.Row, key: str) -> str:
    return str(cast(object, row[key]))


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = cast(object, row[key])
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    raise TypeError(f"Row value for {key} is not int-compatible")


def _row_optional_str(row: sqlite3.Row, key: str) -> str | None:
    value = cast(object, row[key])
    return None if value is None else str(value)


def _fetchone(connection: sqlite3.Connection, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
    cursor = connection.execute(query, params)
    return cast(sqlite3.Row | None, cursor.fetchone())


def _fetchall(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    cursor = connection.execute(query, params)
    return cast(list[sqlite3.Row], cursor.fetchall())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Common content field keys used across modules for extracting main text content
CONTENT_KEYS: tuple[str, ...] = ("content", "body", "text", "prose", "description")


def extract_text_content(payload: dict) -> str:
    """Extract the main text content from a payload using common content keys."""
    for key in CONTENT_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _encode_json(payload: Mapping[str, JSONValue]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_json_object(raw: str) -> JSONObject:
    decoded = cast(object, json.loads(raw))
    if not isinstance(decoded, dict):
        raise ValueError("Expected JSON object payload")
    return cast(JSONObject, decoded)


def _normalize_json_value(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


def _normalize_payload(payload: Mapping[str, JSONValue]) -> JSONObject:
    return {str(key): _normalize_json_value(value) for key, value in payload.items()}


def _build_diff(before: Mapping[str, JSONValue], after: Mapping[str, JSONValue]) -> JSONObject:
    added: JSONObject = {}
    removed: JSONObject = {}
    changed: JSONObject = {}
    for key in sorted(set(before) | set(after)):
        if key not in before:
            added[key] = after[key]
            continue
        if key not in after:
            removed[key] = before[key]
            continue
        before_value = before[key]
        after_value = after[key]
        if before_value != after_value:
            changed[key] = {"before": before_value, "after": after_value}
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
    }


@dataclass(frozen=True, slots=True)
class CanonicalWriteRequest:
    family: str
    payload: JSONObject
    actor: str
    source_surface: str
    policy_class: str
    approval_state: str
    object_id: str | None = None
    skill: str | None = None
    created_by: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None
    revision_reason: str | None = None
    revision_source_message_id: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalWriteResult:
    object_id: str
    revision_id: str
    revision_number: int
    parent_revision_id: str | None
    mutation_record_id: str


@dataclass(frozen=True, slots=True)
class DerivedRecordInput:
    family: str
    payload: JSONObject
    source_scene_revision_id: str
    created_by: str
    object_id: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProposalRecordInput:
    target_family: str
    target_object_id: str
    created_by: str
    proposal_payload: JSONObject
    base_revision_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovalRecordInput:
    proposal_id: str
    created_by: str
    approval_state: str
    mutation_record_id: str | None = None
    decision_payload: JSONObject | None = None


@dataclass(frozen=True, slots=True)
class ImportRecordInput:
    project_id: str
    created_by: str
    import_source: str
    import_payload: JSONObject


@dataclass(frozen=True, slots=True)
class ChatSessionInput:
    project_id: str
    created_by: str
    runtime_origin: str
    novel_id: str | None = None
    title: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ChatMessageLinkInput:
    chat_session_id: str
    created_by: str
    chat_message_id: str
    chat_role: str
    payload: JSONObject
    linked_object_id: str | None = None
    linked_revision_id: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataMarkerInput:
    target_family: str
    target_object_id: str
    marker_name: str
    created_by: str
    marker_payload: JSONObject
    target_revision_id: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataMarkerSnapshot:
    marker_id: str
    target_family: str
    target_object_id: str
    target_revision_id: str | None
    marker_name: str
    payload: JSONObject
    is_authoritative: int
    is_rebuildable: int
    created_at: str
    created_by: str


@dataclass(frozen=True, slots=True)
class ChatSessionRow:
    session_id: str
    project_id: str
    novel_id: str | None
    title: str | None
    runtime_origin: str
    created_by: str


@dataclass(frozen=True, slots=True)
class ChatMessageLinkRow:
    message_state_id: str
    chat_message_id: str
    chat_role: str
    linked_object_id: str | None
    linked_revision_id: str | None
    payload: JSONObject


@dataclass(frozen=True, slots=True)
class WorkspaceCanonicalRow:
    family: str
    object_id: str
    current_revision_id: str
    current_revision_number: int
    payload: JSONObject


class CanonicalStorage:
    def __init__(self, db_path: Path):
        self.db_path: Path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connection() as connection:
            _ = connection.executescript(self._schema_sql())
            self._seed_family_catalog(connection)
            connection.commit()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        _ = connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def _schema_sql(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS family_catalog (
            family TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            revision_mode TEXT NOT NULL,
            id_prefix TEXT NOT NULL,
            is_authoritative INTEGER NOT NULL CHECK (is_authoritative IN (0, 1)),
            is_rebuildable INTEGER NOT NULL CHECK (is_rebuildable IN (0, 1)),
            is_append_only INTEGER NOT NULL CHECK (is_append_only IN (0, 1)),
            is_linkage_only INTEGER NOT NULL CHECK (is_linkage_only IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS canonical_objects (
            object_id TEXT PRIMARY KEY,
            family TEXT NOT NULL REFERENCES family_catalog(family),
            category TEXT NOT NULL CHECK (category = 'canonical'),
            current_revision_id TEXT NOT NULL,
            current_revision_number INTEGER NOT NULL,
            current_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_ref TEXT,
            ingest_run_id TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS canonical_objects_family_object_idx
            ON canonical_objects(family, object_id);

        CREATE TABLE IF NOT EXISTS canonical_revisions (
            revision_id TEXT PRIMARY KEY,
            family TEXT NOT NULL REFERENCES family_catalog(family),
            object_id TEXT NOT NULL REFERENCES canonical_objects(object_id),
            revision_number INTEGER NOT NULL,
            parent_revision_id TEXT,
            snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            revision_reason TEXT,
            revision_source_message_id TEXT,
            UNIQUE(object_id, revision_number)
        );

        CREATE TABLE IF NOT EXISTS derived_records (
            artifact_revision_id TEXT PRIMARY KEY,
            object_id TEXT NOT NULL,
            family TEXT NOT NULL REFERENCES family_catalog(family),
            category TEXT NOT NULL CHECK (category = 'derived'),
            source_scene_revision_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            is_authoritative INTEGER NOT NULL DEFAULT 0 CHECK (is_authoritative = 0),
            is_rebuildable INTEGER NOT NULL DEFAULT 1 CHECK (is_rebuildable = 1),
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            source_ref TEXT,
            ingest_run_id TEXT
        );

        CREATE TABLE IF NOT EXISTS proposals (
            record_id TEXT PRIMARY KEY,
            target_family TEXT NOT NULL REFERENCES family_catalog(family),
            target_object_id TEXT NOT NULL,
            base_revision_id TEXT,
            proposal_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approval_records (
            record_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL REFERENCES proposals(record_id),
            mutation_record_id TEXT REFERENCES mutation_records(record_id),
            approval_state TEXT NOT NULL,
            decision_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS proposal_comments (
            comment_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL REFERENCES proposals(record_id),
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            target_section TEXT,
            parent_comment_id TEXT REFERENCES proposal_comments(comment_id),
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_proposal_comments_proposal
            ON proposal_comments(proposal_id);

        CREATE TABLE IF NOT EXISTS mutation_records (
            record_id TEXT PRIMARY KEY,
            target_object_family TEXT NOT NULL REFERENCES family_catalog(family),
            target_object_id TEXT NOT NULL,
            result_revision_id TEXT NOT NULL REFERENCES canonical_revisions(revision_id),
            resulting_revision_number INTEGER NOT NULL,
            actor_id TEXT NOT NULL,
            source_surface TEXT NOT NULL,
            skill_name TEXT,
            policy_class TEXT NOT NULL,
            diff_payload_json TEXT NOT NULL,
            approval_state TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS import_records (
            record_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            import_source TEXT NOT NULL,
            import_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_state_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            novel_id TEXT,
            title TEXT,
            runtime_origin TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_ref TEXT,
            ingest_run_id TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_message_links (
            message_state_id TEXT PRIMARY KEY,
            chat_session_id TEXT NOT NULL REFERENCES chat_sessions(session_state_id),
            linked_object_id TEXT,
            linked_revision_id TEXT,
            chat_message_id TEXT NOT NULL,
            chat_role TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_ref TEXT,
            ingest_run_id TEXT
        );

        CREATE TABLE IF NOT EXISTS metadata_markers (
            marker_id TEXT PRIMARY KEY,
            target_family TEXT NOT NULL REFERENCES family_catalog(family),
            target_object_id TEXT NOT NULL,
            target_revision_id TEXT,
            marker_name TEXT NOT NULL,
            marker_payload_json TEXT NOT NULL,
            is_authoritative INTEGER NOT NULL DEFAULT 0 CHECK (is_authoritative = 0),
            is_rebuildable INTEGER NOT NULL DEFAULT 1 CHECK (is_rebuildable = 1),
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ai_provider_config (
            provider_id TEXT PRIMARY KEY,
            provider_name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            model_name TEXT NOT NULL,
            temperature REAL NOT NULL DEFAULT 0.7 CHECK (temperature >= 0 AND temperature <= 2),
            max_tokens INTEGER NOT NULL DEFAULT 4096 CHECK (max_tokens > 0),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workbench_sessions (
            session_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            novel_id TEXT NOT NULL,
            workbench_type TEXT NOT NULL,
            parent_object_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'abandoned')),
            current_iteration INTEGER NOT NULL DEFAULT 1,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            source_surface TEXT NOT NULL,
            source_ref TEXT
        );

        CREATE TABLE IF NOT EXISTS workbench_candidate_drafts (
            draft_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES workbench_sessions(session_id) ON DELETE CASCADE,
            iteration_number INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            generation_context_json TEXT NOT NULL,
            is_selected INTEGER NOT NULL DEFAULT 0 CHECK (is_selected IN (0, 1)),
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS workbench_candidate_drafts_session_idx
            ON workbench_candidate_drafts(session_id, iteration_number);

        CREATE TABLE IF NOT EXISTS workbench_feedback (
            feedback_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES workbench_sessions(session_id) ON DELETE CASCADE,
            target_draft_id TEXT NOT NULL REFERENCES workbench_candidate_drafts(draft_id) ON DELETE CASCADE,
            feedback_type TEXT NOT NULL CHECK (feedback_type IN ('accept', 'reject', 'revise', 'partial_revision')),
            feedback_text TEXT NOT NULL,
            target_section TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS workbench_feedback_session_idx
            ON workbench_feedback(session_id, created_at);
        """

    def _seed_family_catalog(self, connection: sqlite3.Connection) -> None:
        rows = [
            (
                contract.family,
                contract.category.value,
                contract.revision_policy.mode.value,
                contract.id_contract.prefix,
                1 if contract.category is FamilyCategory.CANONICAL else 0,
                1 if contract.category is FamilyCategory.DERIVED else 0,
                1 if contract.category is FamilyCategory.LEDGER else 0,
                1 if contract.revision_policy.mode is RevisionMode.RUNTIME_LINKAGE else 0,
            )
            for contract in FAMILY_REGISTRY
        ]
        _ = connection.executemany(
            """
            INSERT INTO family_catalog (
                family,
                category,
                revision_mode,
                id_prefix,
                is_authoritative,
                is_rebuildable,
                is_append_only,
                is_linkage_only
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(family) DO UPDATE SET
                category = excluded.category,
                revision_mode = excluded.revision_mode,
                id_prefix = excluded.id_prefix,
                is_authoritative = excluded.is_authoritative,
                is_rebuildable = excluded.is_rebuildable,
                is_append_only = excluded.is_append_only,
                is_linkage_only = excluded.is_linkage_only
            """,
            rows,
        )

    def _require_family_category(self, family: str, category: FamilyCategory) -> FamilyContract:
        contract = get_family_contract(family)
        if contract.category is not category:
            raise ValueError(f"{family} belongs to {contract.category.value}, not {category.value}")
        return contract

    def _validate_object_id(self, contract: FamilyContract, object_id: str) -> None:
        expected_prefix = f"{contract.id_contract.prefix}_"
        if not object_id.startswith(expected_prefix):
            raise ValueError(
                f"{contract.family} object_id must start with {expected_prefix}"
            )

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
                        object_id,
                        family,
                        category,
                        current_revision_id,
                        current_revision_number,
                        current_payload_json,
                        created_at,
                        created_by,
                        updated_at,
                        updated_by,
                        source_kind,
                        source_ref,
                        ingest_run_id
                    )
                    VALUES (?, ?, 'canonical', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        object_id,
                        request.family,
                        revision_id,
                        revision_number,
                        _encode_json(payload),
                        created_at,
                        created_by,
                        timestamp,
                        request.actor,
                        request.source_surface,
                        request.source_ref,
                        request.ingest_run_id,
                    ),
                )
            else:
                _ = connection.execute(
                    """
                    UPDATE canonical_objects
                    SET current_revision_id = ?,
                        current_revision_number = ?,
                        current_payload_json = ?,
                        updated_at = ?,
                        updated_by = ?,
                        source_kind = ?,
                        source_ref = ?,
                        ingest_run_id = ?
                    WHERE object_id = ?
                    """,
                    (
                        revision_id,
                        revision_number,
                        _encode_json(payload),
                        timestamp,
                        request.actor,
                        request.source_surface,
                        request.source_ref,
                        request.ingest_run_id,
                        object_id,
                    ),
                )

            _ = connection.execute(
                """
                INSERT INTO canonical_revisions (
                    revision_id,
                    family,
                    object_id,
                    revision_number,
                    parent_revision_id,
                    snapshot_json,
                    created_at,
                    created_by,
                    revision_reason,
                    revision_source_message_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    request.family,
                    object_id,
                    revision_number,
                    parent_revision_id,
                    _encode_json(payload),
                    timestamp,
                    request.actor,
                    request.revision_reason,
                    request.revision_source_message_id,
                ),
            )
            _ = connection.execute(
                """
                INSERT INTO mutation_records (
                    record_id,
                    target_object_family,
                    target_object_id,
                    result_revision_id,
                    resulting_revision_number,
                    actor_id,
                    source_surface,
                    skill_name,
                    policy_class,
                    diff_payload_json,
                    approval_state,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_record_id,
                    request.family,
                    object_id,
                    revision_id,
                    revision_number,
                    request.actor,
                    request.source_surface,
                    request.skill,
                    request.policy_class,
                    _encode_json(diff_payload),
                    request.approval_state,
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
                    artifact_revision_id,
                    object_id,
                    family,
                    category,
                    source_scene_revision_id,
                    payload_json,
                    created_at,
                    created_by,
                    source_ref,
                    ingest_run_id
                )
                VALUES (?, ?, ?, 'derived', ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_revision_id,
                    object_id,
                    record.family,
                    record.source_scene_revision_id,
                    _encode_json(payload),
                    timestamp,
                    record.created_by,
                    record.source_ref,
                    record.ingest_run_id,
                ),
            )
            connection.commit()

        return artifact_revision_id

    def create_proposal_record(self, record: ProposalRecordInput) -> str:
        record_id = _generate_id("prp")
        _ = self._require_known_family(record.target_family)
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO proposals (
                    record_id,
                    target_family,
                    target_object_id,
                    base_revision_id,
                    proposal_payload_json,
                    created_at,
                    created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    record.target_family,
                    record.target_object_id,
                    record.base_revision_id,
                    _encode_json(_normalize_payload(record.proposal_payload)),
                    timestamp,
                    record.created_by,
                ),
            )
            connection.commit()
        return record_id

    def create_approval_record(self, record: ApprovalRecordInput) -> str:
        record_id = _generate_id("apr")
        timestamp = utc_now_iso()
        payload = _normalize_payload(record.decision_payload or {})
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO approval_records (
                    record_id,
                    proposal_id,
                    mutation_record_id,
                    approval_state,
                    decision_payload_json,
                    created_at,
                    created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    record.proposal_id,
                    record.mutation_record_id,
                    record.approval_state,
                    _encode_json(payload),
                    timestamp,
                    record.created_by,
                ),
            )
            connection.commit()
        return record_id

    def create_import_record(self, record: ImportRecordInput) -> str:
        record_id = _generate_id("imp")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO import_records (
                    record_id,
                    project_id,
                    import_source,
                    import_payload_json,
                    created_at,
                    created_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    record.project_id,
                    record.import_source,
                    _encode_json(_normalize_payload(record.import_payload)),
                    timestamp,
                    record.created_by,
                ),
            )
            connection.commit()
        return record_id

    # ==================== Proposal Comments ====================

    def create_proposal_comment(
        self,
        proposal_id: str,
        author: str,
        content: str,
        target_section: str | None = None,
        parent_comment_id: str | None = None,
    ) -> str:
        """Create a new comment on a proposal."""
        comment_id = _generate_id("cmt")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO proposal_comments (
                    comment_id,
                    proposal_id,
                    author,
                    content,
                    target_section,
                    parent_comment_id,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comment_id,
                    proposal_id,
                    author,
                    content,
                    target_section,
                    parent_comment_id,
                    "open",
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
        return comment_id

    def get_proposal_comment(self, comment_id: str) -> dict | None:
        """Get a specific comment by ID."""
        with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT comment_id, proposal_id, author, content, target_section,
                           parent_comment_id, status, created_at, updated_at,
                           resolved_at, resolved_by
                    FROM proposal_comments
                    WHERE comment_id = ?
                    """,
                    (comment_id,),
                ).fetchone()
                if row:
                    return dict(row)
        return None

    def list_proposal_comments(self, proposal_id: str) -> list[dict]:
        """List all comments for a proposal."""
        with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT comment_id, proposal_id, author, content, target_section,
                           parent_comment_id, status, created_at, updated_at,
                           resolved_at, resolved_by
                    FROM proposal_comments
                    WHERE proposal_id = ?
                    ORDER BY created_at ASC
                    """,
                    (proposal_id,),
                )
                return [dict(row) for row in rows]
        return []

    def resolve_proposal_comment(
        self,
        comment_id: str,
        resolved_by: str,
        resolved_at: str,
    ) -> bool:
        """Mark a comment as resolved."""
        with self._connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE proposal_comments
                    SET status = ?, resolved_at = ?, resolved_by = ?, updated_at = ?
                    WHERE comment_id = ? AND status = 'open'
                    """,
                    ("resolved", resolved_at, resolved_by, resolved_at, comment_id),
                )
                connection.commit()
                return cursor.rowcount > 0
        return False

    def reopen_proposal_comment(self, comment_id: str) -> bool:
        """Reopen a resolved comment."""
        with self._connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE proposal_comments
                    SET status = ?, resolved_at = NULL, resolved_by = Null, updated_at = ?
                    WHERE comment_id = ? AND status = 'resolved'
                    """,
                    ("open", utc_now_iso(), comment_id),
                )
                connection.commit()
                return cursor.rowcount > 0
        return False

    def hide_proposal_comment(self, comment_id: str) -> bool:
        """Hide (soft delete) a comment."""
        with self._connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE proposal_comments
                    SET status = ?, updated_at = ?
                    WHERE comment_id = ?
                    """,
                    ("hidden", utc_now_iso(), comment_id),
                )
                connection.commit()
                return cursor.rowcount > 0
        return False

    def update_proposal_comment_content(
        self,
        comment_id: str,
        new_content: str,
        updated_at: str,
    ) -> bool:
        """Update the content of a comment."""
        with self._connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE proposal_comments
                    SET content = ?, updated_at = ?
                    WHERE comment_id = ?
                    """,
                    (new_content, updated_at, comment_id),
                )
                connection.commit()
                return cursor.rowcount > 0
        return False

    # ==================== End Proposal Comments ====================

    def create_chat_session(self, record: ChatSessionInput) -> str:
        session_state_id = _generate_id("chs")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO chat_sessions (
                    session_state_id,
                    project_id,
                    novel_id,
                    title,
                    runtime_origin,
                    created_at,
                    created_by,
                    updated_at,
                    updated_by,
                    source_kind,
                    source_ref,
                    ingest_run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_state_id,
                    record.project_id,
                    record.novel_id,
                    record.title,
                    record.runtime_origin,
                    timestamp,
                    record.created_by,
                    timestamp,
                    record.created_by,
                    "chat_surface",
                    record.source_ref,
                    None,
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
                    message_state_id,
                    chat_session_id,
                    linked_object_id,
                    linked_revision_id,
                    chat_message_id,
                    chat_role,
                    payload_json,
                    created_at,
                    created_by,
                    updated_at,
                    updated_by,
                    source_kind,
                    source_ref,
                    ingest_run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_state_id,
                    record.chat_session_id,
                    record.linked_object_id,
                    record.linked_revision_id,
                    record.chat_message_id,
                    record.chat_role,
                    _encode_json(_normalize_payload(record.payload)),
                    timestamp,
                    record.created_by,
                    timestamp,
                    record.created_by,
                    "chat_surface",
                    record.source_ref,
                    None,
                ),
            )
            connection.commit()
        return message_state_id

    def create_metadata_marker(self, record: MetadataMarkerInput) -> str:
        _ = self._require_known_family(record.target_family)
        marker_id = _generate_id("mdm")
        timestamp = utc_now_iso()
        with self._connection() as connection:
            _ = connection.execute(
                """
                INSERT INTO metadata_markers (
                    marker_id,
                    target_family,
                    target_object_id,
                    target_revision_id,
                    marker_name,
                    marker_payload_json,
                    created_at,
                    created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    marker_id,
                    record.target_family,
                    record.target_object_id,
                    record.target_revision_id,
                    record.marker_name,
                    _encode_json(_normalize_payload(record.marker_payload)),
                    timestamp,
                    record.created_by,
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

    def _require_known_family(self, family: str) -> FamilyContract:
        return get_family_contract(family)

    def list_tables(self) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
            )
        return tuple(_row_str(row, "name") for row in rows)

    def get_family_catalog(self) -> dict[str, dict[str, str | int]]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT family, category, revision_mode, is_authoritative, is_rebuildable, is_append_only, is_linkage_only FROM family_catalog ORDER BY family",
            )
        return {
            _row_str(row, "family"): {
                "category": _row_str(row, "category"),
                "revision_mode": _row_str(row, "revision_mode"),
                "is_authoritative": _row_int(row, "is_authoritative"),
                "is_rebuildable": _row_int(row, "is_rebuildable"),
                "is_append_only": _row_int(row, "is_append_only"),
                "is_linkage_only": _row_int(row, "is_linkage_only"),
            }
            for row in rows
        }

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
                SELECT record_id, target_object_family, target_object_id, result_revision_id, resulting_revision_number,
                       actor_id, source_surface, skill_name, policy_class, diff_payload_json, approval_state
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

    def fetch_derived_records(self, family: str) -> list[dict[str, str | int | JSONObject]]:
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

    def fetch_import_records(
        self,
        *,
        project_id: str | None = None,
        import_source: str | None = None,
    ) -> list[dict[str, str | JSONObject]]:
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

    def fetch_proposals(
        self,
        *,
        target_object_id: str | None = None,
    ) -> list[dict[str, str | JSONObject | None]]:
        query = (
            "SELECT record_id, target_family, target_object_id, base_revision_id, proposal_payload_json, "
            "created_at, created_by FROM proposals ORDER BY created_at ASC, record_id ASC"
        )
        params: tuple[object, ...] = ()
        if target_object_id is not None:
            query = (
                "SELECT record_id, target_family, target_object_id, base_revision_id, proposal_payload_json, "
                "created_at, created_by FROM proposals WHERE target_object_id = ? "
                "ORDER BY created_at ASC, record_id ASC"
            )
            params = (target_object_id,)
        with self._connection() as connection:
            rows = _fetchall(connection, query, params)
        return [
            {
                "record_id": _row_str(row, "record_id"),
                "target_family": _row_str(row, "target_family"),
                "target_object_id": _row_str(row, "target_object_id"),
                "base_revision_id": _row_optional_str(row, "base_revision_id"),
                "proposal_payload": _decode_json_object(_row_str(row, "proposal_payload_json")),
                "created_at": _row_str(row, "created_at"),
                "created_by": _row_str(row, "created_by"),
            }
            for row in rows
        ]

    def fetch_approval_records(
        self,
        *,
        proposal_id: str | None = None,
    ) -> list[dict[str, str | JSONObject | None]]:
        query = (
            "SELECT record_id, proposal_id, mutation_record_id, approval_state, decision_payload_json, "
            "created_at, created_by FROM approval_records ORDER BY created_at ASC, record_id ASC"
        )
        params: tuple[object, ...] = ()
        if proposal_id is not None:
            query = (
                "SELECT record_id, proposal_id, mutation_record_id, approval_state, decision_payload_json, "
                "created_at, created_by FROM approval_records WHERE proposal_id = ? "
                "ORDER BY created_at ASC, record_id ASC"
            )
            params = (proposal_id,)
        with self._connection() as connection:
            rows = _fetchall(connection, query, params)
        return [
            {
                "record_id": _row_str(row, "record_id"),
                "proposal_id": _row_str(row, "proposal_id"),
                "mutation_record_id": _row_optional_str(row, "mutation_record_id"),
                "approval_state": _row_str(row, "approval_state"),
                "decision_payload": _decode_json_object(_row_str(row, "decision_payload_json")),
                "created_at": _row_str(row, "created_at"),
                "created_by": _row_str(row, "created_by"),
            }
            for row in rows
        ]

    # AI Provider Configuration Methods

    def save_provider_config(
        self,
        *,
        provider_id: str | None = None,
        provider_name: str,
        base_url: str,
        api_key: str,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        is_active: bool = True,
        created_by: str = "system",
    ) -> str:
        """Save or update an AI provider configuration."""
        provider_id = provider_id or _generate_id("ai")
        timestamp = utc_now_iso()

        with self._connection() as connection:
            existing = _fetchone(
                connection,
                "SELECT provider_id FROM ai_provider_config WHERE provider_id = ?",
                (provider_id,),
            )

            if existing:
                _ = connection.execute(
                    """
                    UPDATE ai_provider_config
                    SET provider_name = ?, base_url = ?, api_key = ?, model_name = ?,
                        temperature = ?, max_tokens = ?, is_active = ?, updated_at = ?, updated_by = ?
                    WHERE provider_id = ?
                    """,
                    (provider_name, base_url, api_key, model_name, temperature,
                     max_tokens, 1 if is_active else 0, timestamp, created_by, provider_id),
                )
            else:
                _ = connection.execute(
                    """
                    INSERT INTO ai_provider_config (
                        provider_id, provider_name, base_url, api_key, model_name,
                        temperature, max_tokens, is_active, created_at, created_by, updated_at, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (provider_id, provider_name, base_url, api_key, model_name,
                     temperature, max_tokens, 1 if is_active else 0, timestamp, created_by, timestamp, created_by),
                )
            connection.commit()
        return provider_id

    def get_provider_config(self, provider_id: str) -> dict[str, object] | None:
        """Get a single AI provider configuration."""
        with self._connection() as connection:
            row = _fetchone(
                connection,
                """
                SELECT provider_id, provider_name, base_url, api_key, model_name,
                       temperature, max_tokens, is_active, created_at, created_by, updated_at, updated_by
                FROM ai_provider_config WHERE provider_id = ?
                """,
                (provider_id,),
            )
        if row is None:
            return None
        return {
            "provider_id": _row_str(row, "provider_id"),
            "provider_name": _row_str(row, "provider_name"),
            "base_url": _row_str(row, "base_url"),
            "api_key": _row_str(row, "api_key"),
            "model_name": _row_str(row, "model_name"),
            "temperature": float(row["temperature"]),
            "max_tokens": _row_int(row, "max_tokens"),
            "is_active": bool(_row_int(row, "is_active")),
            "created_at": _row_str(row, "created_at"),
            "created_by": _row_str(row, "created_by"),
            "updated_at": _row_str(row, "updated_at"),
            "updated_by": _row_str(row, "updated_by"),
        }

    def list_provider_configs(self) -> list[dict[str, object]]:
        """List all AI provider configurations."""
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                """
                SELECT provider_id, provider_name, base_url, api_key, model_name,
                       temperature, max_tokens, is_active, created_at, created_by, updated_at, updated_by
                FROM ai_provider_config ORDER BY created_at DESC
                """,
            )
        return [
            {
                "provider_id": _row_str(row, "provider_id"),
                "provider_name": _row_str(row, "provider_name"),
                "base_url": _row_str(row, "base_url"),
                "api_key": _row_str(row, "api_key"),
                "model_name": _row_str(row, "model_name"),
                "temperature": float(row["temperature"]),
                "max_tokens": _row_int(row, "max_tokens"),
                "is_active": bool(_row_int(row, "is_active")),
                "created_at": _row_str(row, "created_at"),
                "created_by": _row_str(row, "created_by"),
                "updated_at": _row_str(row, "updated_at"),
                "updated_by": _row_str(row, "updated_by"),
            }
            for row in rows
        ]

    def get_active_provider_config(self) -> dict[str, object] | None:
        """Get the currently active AI provider configuration."""
        with self._connection() as connection:
            row = _fetchone(
                connection,
                """
                SELECT provider_id, provider_name, base_url, api_key, model_name,
                       temperature, max_tokens, is_active, created_at, created_by, updated_at, updated_by
                FROM ai_provider_config WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1
                """,
                (),
            )
        if row is None:
            return None
        return {
            "provider_id": _row_str(row, "provider_id"),
            "provider_name": _row_str(row, "provider_name"),
            "base_url": _row_str(row, "base_url"),
            "api_key": _row_str(row, "api_key"),
            "model_name": _row_str(row, "model_name"),
            "temperature": float(row["temperature"]),
            "max_tokens": _row_int(row, "max_tokens"),
            "is_active": bool(_row_int(row, "is_active")),
            "created_at": _row_str(row, "created_at"),
            "created_by": _row_str(row, "created_by"),
            "updated_at": _row_str(row, "updated_at"),
            "updated_by": _row_str(row, "updated_by"),
        }

    def delete_provider_config(self, provider_id: str) -> bool:
        """Delete an AI provider configuration."""
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM ai_provider_config WHERE provider_id = ?",
                (provider_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def set_active_provider(self, provider_id: str) -> bool:
        """Set a provider as active (deactivates all others)."""
        with self._connection() as connection:
            # Deactivate all
            _ = connection.execute("UPDATE ai_provider_config SET is_active = 0")
            # Activate the target
            cursor = connection.execute(
                "UPDATE ai_provider_config SET is_active = 1, updated_at = ? WHERE provider_id = ?",
                (utc_now_iso(), provider_id),
            )
            connection.commit()
        return cursor.rowcount > 0

    # Workbench session methods

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
        from core.runtime.workbench_session import utc_now_iso

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
        from core.runtime.workbench_session import utc_now_iso

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
        from core.runtime.workbench_session import utc_now_iso

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


__all__ = [
    "CANONICAL_FAMILIES",
    "DERIVED_FAMILIES",
    "ApprovalRecordInput",
    "CanonicalStorage",
    "CanonicalWriteRequest",
    "CanonicalWriteResult",
    "ChatMessageLinkInput",
    "ChatMessageLinkRow",
    "ChatSessionRow",
    "ChatSessionInput",
    "DerivedRecordInput",
    "JSONValue",
    "ImportRecordInput",
    "MetadataMarkerSnapshot",
    "MetadataMarkerInput",
    "ProposalRecordInput",
    "WorkspaceCanonicalRow",
    # Workbench session types
    "WorkbenchSessionInput",
    "CandidateDraftInput",
    "FeedbackInput",
]
