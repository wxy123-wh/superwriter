"""
MetadataStore - SQLite storage for configuration data only
Stores: novel, project, ai_provider_config, skill
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

JSONValue = str | int | float | bool | None | dict[str, Any] | list[Any]
JSONObject = dict[str, JSONValue]


class MetadataStore:
    """SQLite store for metadata (novel, project, ai_provider_config, skill)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize metadata tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    family TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (family, object_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metadata_family
                ON metadata(family)
            """)

    def write(self, family: str, object_id: str, payload: JSONObject) -> None:
        """Write or update metadata object."""
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO metadata (family, object_id, payload, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(family, object_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
            """, (family, object_id, json.dumps(payload)))

    def read(self, family: str, object_id: str) -> JSONObject | None:
        """Read metadata object."""
        import json
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT payload FROM metadata
                WHERE family = ? AND object_id = ?
            """, (family, object_id))
            row = cursor.fetchone()
            if row is None:
                return None
            return json.loads(row[0])

    def list_family(self, family: str) -> list[tuple[str, JSONObject]]:
        """List all objects in a family."""
        import json
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT object_id, payload FROM metadata
                WHERE family = ?
                ORDER BY object_id
            """, (family,))
            return [(row[0], json.loads(row[1])) for row in cursor.fetchall()]

    def delete(self, family: str, object_id: str) -> bool:
        """Delete metadata object. Returns True if deleted, False if not found."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM metadata
                WHERE family = ? AND object_id = ?
            """, (family, object_id))
            return cursor.rowcount > 0

    def exists(self, family: str, object_id: str) -> bool:
        """Check if metadata object exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 1 FROM metadata
                WHERE family = ? AND object_id = ?
            """, (family, object_id))
            return cursor.fetchone() is not None
