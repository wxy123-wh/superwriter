"""Tests for foreshadowing object contract and checker."""

from __future__ import annotations

import pytest

from core.objects.contract import (
    CANONICAL_FAMILIES,
    FAMILY_REGISTRY,
    FamilyCategory,
    RelationKind,
    get_family_contract,
    validate_registry,
)
from core.objects.foreshadowing import (
    ForeshadowingCheckResult,
    ForeshadowingChecker,
    ForeshadowingRecord,
    ForeshadowingStatus,
    ResolutionSuggestion,
)


# ── Contract tests ──────────────────────────────────────────────────────


class TestForeshadowingContract:
    """Test that foreshadowing is properly registered in FAMILY_REGISTRY."""

    def test_foreshadowing_in_registry(self):
        contract = get_family_contract("foreshadowing")
        assert contract.family == "foreshadowing"

    def test_foreshadowing_is_canonical(self):
        contract = get_family_contract("foreshadowing")
        assert contract.category is FamilyCategory.CANONICAL

    def test_foreshadowing_prefix(self):
        contract = get_family_contract("foreshadowing")
        assert contract.id_contract.prefix == "fsh"

    def test_foreshadowing_relations(self):
        contract = get_family_contract("foreshadowing")
        rel_map = {r.field_name: r for r in contract.relations}

        # Required: novel_id parent
        assert "novel_id" in rel_map
        assert rel_map["novel_id"].target_family == "novel"
        assert rel_map["novel_id"].kind is RelationKind.PARENT
        assert rel_map["novel_id"].required is True

        # Required: source_scene_id reference
        assert "source_scene_id" in rel_map
        assert rel_map["source_scene_id"].target_family == "scene"
        assert rel_map["source_scene_id"].kind is RelationKind.REFERENCE
        assert rel_map["source_scene_id"].required is True

        # Optional: target_scene_id reference
        assert "target_scene_id" in rel_map
        assert rel_map["target_scene_id"].target_family == "scene"
        assert rel_map["target_scene_id"].required is False

        # Optional: character_id reference
        assert "character_id" in rel_map
        assert rel_map["character_id"].target_family == "character"
        assert rel_map["character_id"].required is False

    def test_foreshadowing_in_canonical_families(self):
        assert "foreshadowing" in CANONICAL_FAMILIES

    def test_novel_has_foreshadowing_relation(self):
        novel = get_family_contract("novel")
        rel_names = [r.field_name for r in novel.relations]
        assert "foreshadowing_ids" in rel_names

        foreshadow_rel = [r for r in novel.relations if r.field_name == "foreshadowing_ids"][0]
        assert foreshadow_rel.target_family == "foreshadowing"
        assert foreshadow_rel.kind is RelationKind.CHILD

    def test_registry_still_validates(self):
        """Ensure the registry passes all validation with foreshadowing added."""
        validate_registry()


# ── Checker tests ───────────────────────────────────────────────────────


def _make_record(
    foreshadowing_id: str = "fsh_001",
    novel_id: str = "nvl_001",
    source_scene_id: str = "scn_001",
    target_scene_id: str | None = None,
    status: str = ForeshadowingStatus.PLANTED.value,
    importance: int = 3,
    description: str = "Mysterious key found",
    created_at: str = "2025-01-01T00:00:00Z",
) -> ForeshadowingRecord:
    return ForeshadowingRecord(
        foreshadowing_id=foreshadowing_id,
        novel_id=novel_id,
        source_scene_id=source_scene_id,
        target_scene_id=target_scene_id,
        status=status,
        importance=importance,
        description=description,
        created_at=created_at,
    )


class TestForeshadowingRecord:
    def test_is_resolved(self):
        r = _make_record(status=ForeshadowingStatus.RESOLVED.value)
        assert r.is_resolved is True

    def test_is_unresolved_planted(self):
        r = _make_record(status=ForeshadowingStatus.PLANTED.value)
        assert r.is_unresolved is True

    def test_is_unresolved_hinted(self):
        r = _make_record(status=ForeshadowingStatus.HINTED.value)
        assert r.is_unresolved is True

    def test_is_abandoned(self):
        r = _make_record(status=ForeshadowingStatus.ABANDONED.value)
        assert r.is_abandoned is True
        assert r.is_resolved is False
        assert r.is_unresolved is False


class TestForeshadowingChecker:
    def setup_method(self):
        self.checker = ForeshadowingChecker()

    def test_add_and_get_record(self):
        record = _make_record()
        self.checker.add_record(record)
        assert self.checker.get_record("fsh_001") is record

    def test_get_record_not_found(self):
        assert self.checker.get_record("nonexistent") is None

    def test_list_by_novel(self):
        self.checker.add_record(_make_record(foreshadowing_id="fsh_001", novel_id="nvl_A"))
        self.checker.add_record(_make_record(foreshadowing_id="fsh_002", novel_id="nvl_A"))
        self.checker.add_record(_make_record(foreshadowing_id="fsh_003", novel_id="nvl_B"))

        a_records = self.checker.list_by_novel("nvl_A")
        assert len(a_records) == 2
        b_records = self.checker.list_by_novel("nvl_B")
        assert len(b_records) == 1

    def test_check_unresolved_empty(self):
        result = self.checker.check_unresolved("nvl_001")
        assert result.unresolved_count == 0
        assert result.abandoned_count == 0
        assert result.well_resolved_count == 0
        assert result.issues == ()

    def test_check_unresolved_mixed(self):
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_001",
            status=ForeshadowingStatus.PLANTED.value,
            importance=4,
            description="Hidden letter",
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_002",
            status=ForeshadowingStatus.RESOLVED.value,
            target_scene_id="scn_010",
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_003",
            status=ForeshadowingStatus.ABANDONED.value,
            description="Old subplot",
        ))

        result = self.checker.check_unresolved("nvl_001")
        assert result.unresolved_count == 1
        assert result.well_resolved_count == 1
        assert result.abandoned_count == 1
        assert len(result.issues) == 2  # high-importance unresolved + abandoned
        assert "Hidden letter" in result.issues[0]
        assert "Old subplot" in result.issues[1]

    def test_update_status(self):
        self.checker.add_record(_make_record(foreshadowing_id="fsh_001"))
        updated = self.checker.update_status("fsh_001", ForeshadowingStatus.HINTED.value)
        assert updated is not None
        assert updated.status == ForeshadowingStatus.HINTED.value

    def test_update_status_not_found(self):
        assert self.checker.update_status("nonexistent", "hinted") is None

    def test_resolve(self):
        self.checker.add_record(_make_record(foreshadowing_id="fsh_001"))
        resolved = self.checker.resolve("fsh_001", "scn_050")
        assert resolved is not None
        assert resolved.target_scene_id == "scn_050"
        assert resolved.is_resolved is True

    def test_resolve_not_found(self):
        assert self.checker.resolve("nonexistent", "scn_050") is None

    def test_get_active_for_scene(self):
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_001",
            source_scene_id="scn_001",
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_002",
            source_scene_id="scn_002",
            target_scene_id="scn_010",
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_003",
            source_scene_id="scn_005",
            target_scene_id="scn_010",
        ))

        # scn_001 has one foreshadowing planted there
        active_001 = self.checker.get_active_for_scene("scn_001")
        assert len(active_001) == 1
        assert active_001[0].foreshadowing_id == "fsh_001"

        # scn_010 resolves two foreshadowing elements
        active_010 = self.checker.get_active_for_scene("scn_010")
        assert len(active_010) == 2

    def test_get_planted_for_scene(self):
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_001",
            source_scene_id="scn_001",
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_002",
            source_scene_id="scn_002",
            target_scene_id="scn_010",
        ))

        planted = self.checker.get_planted_for_scene("scn_001")
        assert len(planted) == 1
        assert planted[0].foreshadowing_id == "fsh_001"

    def test_get_resolved_by_scene(self):
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_001",
            source_scene_id="scn_001",
            target_scene_id="scn_010",
            status=ForeshadowingStatus.RESOLVED.value,
        ))

        resolved = self.checker.get_resolved_by_scene("scn_010")
        assert len(resolved) == 1
        assert resolved[0].foreshadowing_id == "fsh_001"

    def test_suggest_resolutions(self):
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_001",
            source_scene_id="scn_001",
            importance=5,
            description="The mysterious key",
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_002",
            source_scene_id="scn_002",
            target_scene_id="scn_010",
            status=ForeshadowingStatus.RESOLVED.value,
        ))

        suggestions = self.checker.suggest_resolutions(
            "nvl_001",
            available_scene_ids=("scn_005", "scn_010", "scn_020"),
        )
        # Only unresolved ones get suggestions
        assert len(suggestions) == 1
        assert suggestions[0].foreshadowing_id == "fsh_001"
        assert suggestions[0].importance == 5
        # Source scene should not be in suggestions
        assert "scn_001" not in suggestions[0].suggested_target_scenes

    def test_suggest_resolutions_sorted_by_importance(self):
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_low",
            source_scene_id="scn_001",
            importance=2,
            description="Minor detail",
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_high",
            source_scene_id="scn_002",
            importance=5,
            description="Critical plot point",
        ))

        suggestions = self.checker.suggest_resolutions("nvl_001")
        assert len(suggestions) == 2
        assert suggestions[0].importance >= suggestions[1].importance
        assert suggestions[0].foreshadowing_id == "fsh_high"

    def test_check_result_summary(self):
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_001",
            status=ForeshadowingStatus.PLANTED.value,
        ))
        self.checker.add_record(_make_record(
            foreshadowing_id="fsh_002",
            status=ForeshadowingStatus.RESOLVED.value,
            target_scene_id="scn_010",
        ))

        result = self.checker.check_unresolved("nvl_001")
        assert "2 foreshadowing elements" in result.summary
        assert "1 resolved" in result.summary
        assert "1 unresolved" in result.summary
