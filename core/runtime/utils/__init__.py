from __future__ import annotations

from typing import TypeAlias

JSONValue: TypeAlias = str | int | float | bool | None | dict[str, "JSONValue"] | list["JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


def _payload_text(payload: JSONObject, key: str) -> str | None:
    """Extract a text string from a payload dict, or None."""
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
