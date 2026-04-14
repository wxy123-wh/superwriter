from __future__ import annotations

from core.storage._utils import (
    _fetchall,
    _fetchone,
    _generate_id,
    _row_int,
    _row_str,
    utc_now_iso,
)


class _ProvidersMixin:
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
