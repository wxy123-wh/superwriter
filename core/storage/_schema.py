from __future__ import annotations

SCHEMA_SQL = """
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

        CREATE TABLE IF NOT EXISTS metadata_markers (
            marker_id TEXT PRIMARY KEY,
            target_family TEXT NOT NULL,
            target_object_id TEXT NOT NULL,
            target_revision_id TEXT,
            marker_name TEXT NOT NULL,
            marker_payload_json TEXT NOT NULL,
            is_authoritative INTEGER NOT NULL DEFAULT 0 CHECK (is_authoritative = 0),
            is_rebuildable INTEGER NOT NULL DEFAULT 1 CHECK (is_rebuildable = 1),
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_metadata_markers_name
            ON metadata_markers(marker_name);
        CREATE INDEX IF NOT EXISTS idx_metadata_markers_target
            ON metadata_markers(target_family, target_object_id);
        """
