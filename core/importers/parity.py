from __future__ import annotations

import json
from pathlib import Path
from typing import cast

REQUIRED_ENTRY_KEYS: tuple[str, ...] = (
    "feature_key",
    "donor_source",
    "donor_owner",
    "target_owner",
    "touched_families",
    "must_match_behavior",
    "acceptable_delta",
    "provenance_requirements",
    "verification_check",
    "sunset_criteria",
)


def semantic_parity_matrix_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "semantic_parity_matrix.json"


def load_semantic_parity_matrix() -> dict[str, object]:
    matrix = cast(object, json.loads(semantic_parity_matrix_path().read_text(encoding="utf-8")))
    if not isinstance(matrix, dict):
        raise ValueError("Semantic parity matrix must be a JSON object")
    typed_matrix = cast(dict[str, object], matrix)
    validate_semantic_parity_matrix(typed_matrix)
    return typed_matrix


def validate_semantic_parity_matrix(matrix: dict[str, object]) -> None:
    entries = matrix.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Semantic parity matrix must contain a non-empty entries list")
    typed_entries = cast(list[object], entries)

    seen_feature_keys: set[str] = set()
    for index, entry in enumerate(typed_entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Matrix entry {index} must be an object")
        typed_entry = cast(dict[str, object], entry)
        missing = [key for key in REQUIRED_ENTRY_KEYS if key not in typed_entry]
        if missing:
            raise ValueError(f"Matrix entry {index} is missing keys: {', '.join(missing)}")
        feature_key = typed_entry["feature_key"]
        if not isinstance(feature_key, str) or not feature_key:
            raise ValueError(f"Matrix entry {index} has invalid feature_key")
        if feature_key in seen_feature_keys:
            raise ValueError(f"Duplicate feature_key in semantic parity matrix: {feature_key}")
        seen_feature_keys.add(feature_key)
        for list_key in ("touched_families", "provenance_requirements"):
            value = typed_entry[list_key]
            if not isinstance(value, list) or not value:
                raise ValueError(f"Matrix entry {feature_key} must define non-empty {list_key}")
            typed_values = cast(list[object], value)
            if not all(isinstance(item, str) and item for item in typed_values):
                raise ValueError(f"Matrix entry {feature_key} must define non-empty {list_key}")


__all__ = [
    "REQUIRED_ENTRY_KEYS",
    "load_semantic_parity_matrix",
    "semantic_parity_matrix_path",
    "validate_semantic_parity_matrix",
]
