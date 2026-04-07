"""Tests for expanded skill type support."""

from __future__ import annotations

import pytest

from core.skills.workshop import (
    ALLOWED_FORMALITIES,
    ALLOWED_PERSPECTIVES,
    ALLOWED_STYLE_SCOPES,
    ALLOWED_TEMPOS,
    VALID_SKILL_TYPES,
    SkillType,
    validate_skill_payload,
)


def _base_payload(**overrides) -> dict:
    """Build a minimal valid skill payload."""
    payload = {
        "novel_id": "nvl_001",
        "skill_type": "style_rule",
        "name": "Test Skill",
        "instruction": "Write concisely",
        "style_scope": "scene_to_chapter",
        "is_active": True,
        "source_kind": "manual",
    }
    payload.update(overrides)
    return payload


class TestSkillTypeEnum:
    def test_all_skill_types_defined(self):
        expected = {"style_rule", "character_voice", "narrative_mode", "pacing_rule", "dialogue_style"}
        assert set(e.value for e in SkillType) == expected

    def test_valid_skill_types_matches_enum(self):
        enum_values = set(e.value for e in SkillType)
        assert enum_values == VALID_SKILL_TYPES


class TestStyleRuleValidation:
    def test_valid_style_rule(self):
        result = validate_skill_payload(_base_payload())
        assert result["skill_type"] == "style_rule"
        assert result["style_scope"] == "scene_to_chapter"

    def test_style_rule_requires_style_scope(self):
        payload = _base_payload()
        del payload["style_scope"]
        with pytest.raises(ValueError, match="style_scope is required"):
            validate_skill_payload(payload)

    def test_style_rule_rejects_invalid_scope(self):
        payload = _base_payload(style_scope="invalid_scope")
        with pytest.raises(ValueError, match="style_scope must be one of"):
            validate_skill_payload(payload)


class TestCharacterVoiceValidation:
    def test_valid_character_voice(self):
        payload = _base_payload(
            skill_type="character_voice",
            character_id="chr_001",
        )
        del payload["style_scope"]
        result = validate_skill_payload(payload)
        assert result["skill_type"] == "character_voice"
        assert result["character_id"] == "chr_001"

    def test_character_voice_without_character_id(self):
        payload = _base_payload(skill_type="character_voice")
        del payload["style_scope"]
        result = validate_skill_payload(payload)
        assert result["skill_type"] == "character_voice"
        assert "character_id" not in result


class TestNarrativeModeValidation:
    def test_valid_narrative_mode(self):
        payload = _base_payload(
            skill_type="narrative_mode",
            perspective="third_person_limited",
        )
        del payload["style_scope"]
        result = validate_skill_payload(payload)
        assert result["skill_type"] == "narrative_mode"
        assert result["perspective"] == "third_person_limited"

    def test_narrative_mode_rejects_invalid_perspective(self):
        payload = _base_payload(
            skill_type="narrative_mode",
            perspective="invalid",
        )
        del payload["style_scope"]
        with pytest.raises(ValueError, match="perspective must be one of"):
            validate_skill_payload(payload)

    def test_all_valid_perspectives(self):
        for p in ALLOWED_PERSPECTIVES:
            payload = _base_payload(skill_type="narrative_mode", perspective=p)
            del payload["style_scope"]
            result = validate_skill_payload(payload)
            assert result["perspective"] == p


class TestPacingRuleValidation:
    def test_valid_pacing_rule(self):
        payload = _base_payload(
            skill_type="pacing_rule",
            tempo="fast",
        )
        del payload["style_scope"]
        result = validate_skill_payload(payload)
        assert result["skill_type"] == "pacing_rule"
        assert result["tempo"] == "fast"

    def test_pacing_rule_rejects_invalid_tempo(self):
        payload = _base_payload(
            skill_type="pacing_rule",
            tempo="blazing",
        )
        del payload["style_scope"]
        with pytest.raises(ValueError, match="tempo must be one of"):
            validate_skill_payload(payload)

    def test_all_valid_tempos(self):
        for t in ALLOWED_TEMPOS:
            payload = _base_payload(skill_type="pacing_rule", tempo=t)
            del payload["style_scope"]
            result = validate_skill_payload(payload)
            assert result["tempo"] == t


class TestDialogueStyleValidation:
    def test_valid_dialogue_style(self):
        payload = _base_payload(
            skill_type="dialogue_style",
            formality="casual",
        )
        del payload["style_scope"]
        result = validate_skill_payload(payload)
        assert result["skill_type"] == "dialogue_style"
        assert result["formality"] == "casual"

    def test_dialogue_style_rejects_invalid_formality(self):
        payload = _base_payload(
            skill_type="dialogue_style",
            formality="ultra_formal",
        )
        del payload["style_scope"]
        with pytest.raises(ValueError, match="formality must be one of"):
            validate_skill_payload(payload)

    def test_all_valid_formalities(self):
        for f in ALLOWED_FORMALITIES:
            payload = _base_payload(skill_type="dialogue_style", formality=f)
            del payload["style_scope"]
            result = validate_skill_payload(payload)
            assert result["formality"] == f


class TestUnknownSkillType:
    def test_unknown_skill_type_raises(self):
        payload = _base_payload(skill_type="unknown_type")
        del payload["style_scope"]
        with pytest.raises(ValueError, match="skill_type must be one of"):
            validate_skill_payload(payload)


class TestBackwardCompatibility:
    def test_existing_style_rule_payload_still_works(self):
        """Existing payloads with style_rule should validate unchanged."""
        legacy_payload = {
            "novel_id": "nvl_001",
            "skill_type": "style_rule",
            "name": "Concise Style",
            "instruction": "Write concisely and clearly",
            "style_scope": "scene_to_chapter",
            "is_active": True,
            "source_kind": "manual",
        }
        result = validate_skill_payload(legacy_payload)
        assert result["skill_type"] == "style_rule"
        assert result["style_scope"] == "scene_to_chapter"
        assert result["name"] == "Concise Style"
        assert result["instruction"] == "Write concisely and clearly"
