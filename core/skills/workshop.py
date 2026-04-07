from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias, cast

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]

DONOR_KIND_PROMPT_TEMPLATE = "prompt_template"
DONOR_KIND_CUSTOM_AGENT = "custom_agent"
DONOR_KIND_AI_ROLE = "ai_role"
SUPPORTED_DONOR_KINDS = {
    DONOR_KIND_PROMPT_TEMPLATE,
    DONOR_KIND_CUSTOM_AGENT,
    DONOR_KIND_AI_ROLE,
}
ALLOWED_STYLE_SCOPES = (
    "scene_to_chapter",
    "chapter_revision",
    "novel_voice",
)
ALLOWED_PERSPECTIVES = ("first_person", "second_person", "third_person_limited", "third_person_omniscient")
ALLOWED_TEMPOS = ("fast", "medium", "slow", "variable")
ALLOWED_FORMALITIES = ("formal", "casual", "mixed")


class SkillType(str, Enum):
    """Supported skill types for author controls."""

    STYLE_RULE = "style_rule"
    CHARACTER_VOICE = "character_voice"
    NARRATIVE_MODE = "narrative_mode"
    PACING_RULE = "pacing_rule"
    DIALOGUE_STYLE = "dialogue_style"


VALID_SKILL_TYPES = frozenset(e.value for e in SkillType)

ALLOWED_SKILL_FIELDS = {
    "novel_id",
    "skill_type",
    "name",
    "description",
    "instruction",
    "style_scope",
    "is_active",
    "source_kind",
    "import_mapping",
    # Type-specific optional fields
    "character_id",
    "perspective",
    "tempo",
    "formality",
}
FORBIDDEN_FIELD_MESSAGES = {
    "generation_params": "generation parameters are not editable in the Skill Workshop MVP",
    "model": "generation parameters are not editable in the Skill Workshop MVP",
    "temperature": "generation parameters are not editable in the Skill Workshop MVP",
    "top_p": "generation parameters are not editable in the Skill Workshop MVP",
    "max_tokens": "generation parameters are not editable in the Skill Workshop MVP",
    "retrieval_scope": "retrieval scope is not editable in the Skill Workshop MVP",
    "retrieval": "retrieval scope is not editable in the Skill Workshop MVP",
    "retrieval_k": "retrieval scope is not editable in the Skill Workshop MVP",
    "tool_permissions": "tool permissions are not editable in the Skill Workshop MVP",
    "allowed_tools": "tool permissions are not editable in the Skill Workshop MVP",
    "tools": "tool permissions are not editable in the Skill Workshop MVP",
    "tool_choice": "tool permissions are not editable in the Skill Workshop MVP",
}


def _normalize_text(value: object, field_name: str, *, required: bool = False) -> str:
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    if required and not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_bool(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "active"}:
            return True
        if normalized in {"false", "0", "no", "off", "inactive"}:
            return False
    raise ValueError(f"{field_name} must be a boolean")


def _find_forbidden_fields(value: JSONValue, *, path: str = "") -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_path = f"{path}.{key_text}" if path else key_text
            message = FORBIDDEN_FIELD_MESSAGES.get(key_text)
            if message is not None:
                matches.append((key_path, message))
            matches.extend(_find_forbidden_fields(child, path=key_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(_find_forbidden_fields(child, path=f"{path}[{index}]"))
    return matches


def validate_skill_payload(payload: dict[str, JSONValue]) -> JSONObject:
    forbidden = _find_forbidden_fields(payload)
    if forbidden:
        detail = "; ".join(f"{field}: {message}" for field, message in forbidden)
        raise ValueError(detail)

    unsupported = sorted(set(payload) - ALLOWED_SKILL_FIELDS)
    if unsupported:
        raise ValueError(
            "unsupported editable fields for constrained skill workshop: " + ", ".join(unsupported)
        )

    novel_id = _normalize_text(payload.get("novel_id"), "novel_id", required=True)
    name = _normalize_text(payload.get("name"), "name", required=True)
    instruction = _normalize_text(payload.get("instruction"), "instruction", required=True)
    description = _normalize_text(payload.get("description"), "description")
    skill_type = _normalize_text(payload.get("skill_type"), "skill_type", required=True)
    if skill_type not in VALID_SKILL_TYPES:
        raise ValueError(
            "skill_type must be one of " + ", ".join(sorted(VALID_SKILL_TYPES))
        )
    is_active = _normalize_bool(payload.get("is_active"), "is_active")
    source_kind = _normalize_text(payload.get("source_kind"), "source_kind", required=True)

    # Type-specific validation
    type_specific = _validate_type_specific_fields(skill_type, payload)

    style_scope = ""
    if skill_type == SkillType.STYLE_RULE.value:
        style_scope = _normalize_text(payload.get("style_scope"), "style_scope", required=True)
        if style_scope not in ALLOWED_STYLE_SCOPES:
            raise ValueError(
                "style_scope must be one of " + ", ".join(ALLOWED_STYLE_SCOPES)
            )

    import_mapping_raw = payload.get("import_mapping")
    import_mapping: JSONObject | None = None
    if import_mapping_raw is not None:
        if not isinstance(import_mapping_raw, dict):
            raise ValueError("import_mapping must be an object when provided")
        import_mapping = cast(JSONObject, import_mapping_raw)

    normalized: JSONObject = {
        "novel_id": novel_id,
        "skill_type": skill_type,
        "name": name,
        "description": description,
        "instruction": instruction,
        "is_active": is_active,
        "source_kind": source_kind,
    }
    if style_scope:
        normalized["style_scope"] = style_scope
    if import_mapping is not None:
        normalized["import_mapping"] = import_mapping
    # Merge type-specific fields
    normalized.update(type_specific)
    return normalized


def _validate_type_specific_fields(skill_type: str, payload: dict[str, JSONValue]) -> JSONObject:
    """Validate and extract type-specific fields for a skill.

    Returns a dict of validated type-specific fields to merge into the payload.
    """
    result: JSONObject = {}

    if skill_type == SkillType.STYLE_RULE.value:
        # style_scope is validated in the caller; nothing extra here
        pass

    elif skill_type == SkillType.CHARACTER_VOICE.value:
        character_id = _normalize_text(payload.get("character_id"), "character_id")
        if character_id:
            result["character_id"] = character_id

    elif skill_type == SkillType.NARRATIVE_MODE.value:
        perspective = _normalize_text(payload.get("perspective"), "perspective")
        if perspective:
            if perspective not in ALLOWED_PERSPECTIVES:
                raise ValueError(
                    "perspective must be one of " + ", ".join(ALLOWED_PERSPECTIVES)
                )
            result["perspective"] = perspective

    elif skill_type == SkillType.PACING_RULE.value:
        tempo = _normalize_text(payload.get("tempo"), "tempo")
        if tempo:
            if tempo not in ALLOWED_TEMPOS:
                raise ValueError(
                    "tempo must be one of " + ", ".join(ALLOWED_TEMPOS)
                )
            result["tempo"] = tempo

    elif skill_type == SkillType.DIALOGUE_STYLE.value:
        formality = _normalize_text(payload.get("formality"), "formality")
        if formality:
            if formality not in ALLOWED_FORMALITIES:
                raise ValueError(
                    "formality must be one of " + ", ".join(ALLOWED_FORMALITIES)
                )
            result["formality"] = formality

    return result


@dataclass(frozen=True, slots=True)
class SkillAdapterRequest:
    donor_kind: str
    novel_id: str
    name: str | None = None
    description: str | None = None
    instruction: str | None = None
    style_scope: str = "scene_to_chapter"
    is_active: bool = True
    source_ref: str | None = None
    donor_payload: dict[str, JSONValue] | None = None


@dataclass(frozen=True, slots=True)
class AdaptedSkillPayload:
    payload: JSONObject
    donor_kind: str
    mapping_notes: tuple[str, ...]


def adapt_donor_payload(request: SkillAdapterRequest) -> AdaptedSkillPayload:
    donor_kind = request.donor_kind.strip().lower()
    if donor_kind not in SUPPORTED_DONOR_KINDS:
        raise ValueError(
            "donor_kind must be one of " + ", ".join(sorted(SUPPORTED_DONOR_KINDS))
        )
    donor_payload = request.donor_payload or {}

    def first_text(*keys: str) -> str:
        for key in keys:
            value = donor_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    name = (request.name or "").strip() or first_text("name", "title", "role")
    if not name:
        if donor_kind == DONOR_KIND_AI_ROLE:
            name = "Imported AI Role"
        elif donor_kind == DONOR_KIND_CUSTOM_AGENT:
            name = "Imported Custom Agent"
        else:
            name = "Imported Prompt Template"

    description = (request.description or "").strip() or first_text(
        "description",
        "summary",
        "background",
        "personality",
    )
    instruction = (request.instruction or "").strip() or first_text(
        "instruction",
        "instructions",
        "prompt",
        "template",
        "system_prompt",
    )
    if not instruction:
        role_text = first_text("role")
        personality_text = first_text("personality")
        instruction = " ".join(part for part in (role_text, personality_text) if part).strip()
    if not instruction:
        raise ValueError("donor mapping must resolve an instruction for the constrained skill")

    mapping_notes = {
        DONOR_KIND_PROMPT_TEMPLATE: (
            "prompt template imported as constrained skill",
            "template text normalized into instruction",
        ),
        DONOR_KIND_CUSTOM_AGENT: (
            "custom agent imported as constrained skill",
            "agent instructions normalized into instruction",
        ),
        DONOR_KIND_AI_ROLE: (
            "AI role imported as constrained skill",
            "role/personality text normalized into instruction",
        ),
    }[donor_kind]

    skill_type = getattr(request, "skill_type", None) or "style_rule"

    payload = validate_skill_payload(
        cast(
            dict[str, JSONValue],
            {
            "novel_id": request.novel_id,
            "skill_type": skill_type,
            "name": name,
            "description": description,
            "instruction": instruction,
            "style_scope": request.style_scope,
            "is_active": request.is_active,
            "source_kind": f"import_mapping:{donor_kind}",
            "import_mapping": {
                "donor_kind": donor_kind,
                "source_ref": request.source_ref or "",
                "adapter": "skill_workshop_mvp",
                "mapped_keys": sorted(str(key) for key in donor_payload.keys()),
            },
        },
        )
    )
    return AdaptedSkillPayload(payload=payload, donor_kind=donor_kind, mapping_notes=mapping_notes)


def diff_skill_payloads(left: dict[str, JSONValue], right: dict[str, JSONValue]) -> JSONObject:
    added: JSONObject = {}
    removed: JSONObject = {}
    changed: JSONObject = {}
    for key in sorted(set(left) | set(right)):
        if key not in left:
            added[key] = right[key]
            continue
        if key not in right:
            removed[key] = left[key]
            continue
        if left[key] != right[key]:
            changed[key] = {"before": left[key], "after": right[key]}
    return {"added": added, "removed": removed, "changed": changed}


def render_skill_diff(left: dict[str, JSONValue], right: dict[str, JSONValue]) -> str:
    left_text = json.dumps(left, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    right_text = json.dumps(right, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    diff = difflib.unified_diff(left_text, right_text, fromfile="left", tofile="right", lineterm="")
    return "\n".join(diff)


__all__ = [
    "ALLOWED_FORMALITIES",
    "ALLOWED_PERSPECTIVES",
    "ALLOWED_STYLE_SCOPES",
    "ALLOWED_TEMPOS",
    "DONOR_KIND_AI_ROLE",
    "DONOR_KIND_CUSTOM_AGENT",
    "DONOR_KIND_PROMPT_TEMPLATE",
    "AdaptedSkillPayload",
    "SkillAdapterRequest",
    "SkillType",
    "VALID_SKILL_TYPES",
    "adapt_donor_payload",
    "diff_skill_payloads",
    "render_skill_diff",
    "validate_skill_payload",
]
