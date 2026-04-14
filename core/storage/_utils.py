from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TypeAlias, cast
import sqlite3

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


def _fetchone(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
    cursor = connection.execute(query, params)
    return cast(sqlite3.Row | None, cursor.fetchone())


def _fetchall(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    cursor = connection.execute(query, params)
    return cast(list[sqlite3.Row], cursor.fetchall())


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _encode_json(value: JSONValue) -> str:
    return json.dumps(value, ensure_ascii=False)


def _decode_json_object(data: str) -> JSONObject:
    return cast(JSONObject, json.loads(data))


def _normalize_payload(payload: JSONObject) -> JSONObject:
    """Normalize payload for storage: convert non-JSON-compatible types."""
    result: JSONObject = {}
    for k, v in payload.items():
        if isinstance(v, (dict, list, str, int, float, bool, type(None))):
            result[k] = v
        else:
            result[k] = str(v)
    return result


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Common content field keys used across modules for extracting main text content
CONTENT_KEYS: tuple[str, ...] = ("content", "body", "text", "prose", "description")
