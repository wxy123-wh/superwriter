from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from core.storage._chat import _ChatMixin
from core.storage._providers import _ProvidersMixin
from core.storage._metadata import _MetadataMixin
from core.storage._schema import SCHEMA_SQL
from core.storage._utils import _fetchall, _row_str


class CanonicalStorage(_ChatMixin, _ProvidersMixin, _MetadataMixin):
    """Simplified storage engine retaining only chat, provider, and metadata tables."""

    def __init__(self, db_path: Path):
        self.db_path: Path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connection() as connection:
            _ = connection.executescript(self._schema_sql())
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
        return SCHEMA_SQL

    def list_tables(self) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = _fetchall(
                connection,
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
            )
        return tuple(_row_str(row, "name") for row in rows)
