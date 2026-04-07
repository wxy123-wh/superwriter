from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "core" / "objects" / "contract.py"
SPEC = importlib.util.spec_from_file_location("superwriter_object_contract", CONTRACT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load object contract module from {CONTRACT_PATH}")

CONTRACT_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CONTRACT_MODULE
SPEC.loader.exec_module(CONTRACT_MODULE)

CANONICAL_FAMILIES = CONTRACT_MODULE.CANONICAL_FAMILIES
DERIVED_FAMILIES = CONTRACT_MODULE.DERIVED_FAMILIES
FAMILY_REGISTRY = CONTRACT_MODULE.FAMILY_REGISTRY
LEDGER_FAMILIES = CONTRACT_MODULE.LEDGER_FAMILIES
SUPPORT_FAMILIES = CONTRACT_MODULE.SUPPORT_FAMILIES
FamilyCategory = CONTRACT_MODULE.FamilyCategory
FamilyContract = CONTRACT_MODULE.FamilyContract
RevisionMode = CONTRACT_MODULE.RevisionMode
get_family_contract = CONTRACT_MODULE.get_family_contract
get_family_contract_from_registry = CONTRACT_MODULE.get_family_contract_from_registry
validate_registry = CONTRACT_MODULE.validate_registry


def _replace_contract(
    family: str, **changes: object
) -> tuple[FamilyContract, ...]:
    updated: list[FamilyContract] = []
    for contract in FAMILY_REGISTRY:
        if contract.family == family:
            updated_contract = replace(contract, **changes)
            updated.append(updated_contract)
        else:
            updated.append(contract)
    return tuple(updated)


def test_registry_declares_all_required_object_families() -> None:
    expected_families = {
        "project",
        "novel",
        "outline_node",
        "plot_node",
        "event",
        "scene",
        "chapter_artifact",
        "character",
        "setting",
        "canon_rule",
        "fact_state_record",
        "style_rule",
        "skill",
        "foreshadowing",
        "proposal",
        "approval_record",
        "mutation_record",
        "import_record",
        "export_artifact",
        "chat_session",
        "chat_message_link",
    }

    observed_families = {contract.family for contract in FAMILY_REGISTRY}

    assert observed_families == expected_families
    assert CANONICAL_FAMILIES == (
        "project",
        "novel",
        "outline_node",
        "plot_node",
        "event",
        "scene",
        "character",
        "setting",
        "canon_rule",
        "fact_state_record",
        "style_rule",
        "skill",
        "foreshadowing",
    )
    assert DERIVED_FAMILIES == ("chapter_artifact", "export_artifact")
    assert LEDGER_FAMILIES == ("proposal", "approval_record", "mutation_record")
    assert SUPPORT_FAMILIES == ("import_record", "chat_session", "chat_message_link")


def test_canonical_families_use_stable_ids_and_revision_chains() -> None:
    for family_name in CANONICAL_FAMILIES:
        contract = get_family_contract(family_name)

        assert contract.owner == "structured-object-truth"
        assert contract.category is FamilyCategory.CANONICAL
        assert contract.id_contract.field_name == "object_id"
        assert contract.id_contract.opaque is True
        assert contract.id_contract.assigned_by == "superwriter"
        assert contract.id_contract.scope == f"family:{family_name}"
        assert contract.revision_policy.mode is RevisionMode.CANONICAL_CHAIN
        assert contract.revision_policy.revision_id_field == "revision_id"
        assert contract.revision_policy.revision_number_field == "revision_number"
        assert contract.revision_policy.parent_revision_id_field == "parent_revision_id"
        assert contract.revision_policy.derived_from_revision_field is None


def test_narrative_and_world_state_relations_are_explicit() -> None:
    scene = get_family_contract("scene")
    fact_state_record = get_family_contract("fact_state_record")
    chapter_artifact = get_family_contract("chapter_artifact")

    assert any(
        relation.field_name == "event_id" and relation.target_family == "event"
        for relation in scene.relations
    )
    assert {
        relation.target_family for relation in fact_state_record.relations
    } >= {"character", "setting", "canon_rule", "scene"}
    assert any(
        relation.field_name == "source_scene_revision_id"
        and relation.target_family == "scene"
        for relation in chapter_artifact.relations
    )


def test_derived_and_runtime_families_do_not_share_canonical_mutation_semantics() -> None:
    chapter_artifact = get_family_contract("chapter_artifact")
    export_artifact = get_family_contract("export_artifact")
    chat_session = get_family_contract("chat_session")
    chat_message_link = get_family_contract("chat_message_link")

    assert chapter_artifact.category is FamilyCategory.DERIVED
    assert export_artifact.category is FamilyCategory.DERIVED
    assert chapter_artifact.revision_policy.mode is RevisionMode.SNAPSHOT_DERIVED
    assert export_artifact.revision_policy.mode is RevisionMode.SNAPSHOT_DERIVED
    assert chapter_artifact.revision_policy.derived_from_revision_field == "source_scene_revision_id"
    assert export_artifact.revision_policy.derived_from_revision_field == "source_scene_revision_id"

    assert chat_session.category is FamilyCategory.SUPPORT
    assert chat_message_link.category is FamilyCategory.SUPPORT
    assert chat_session.revision_policy.mode is RevisionMode.RUNTIME_LINKAGE
    assert chat_message_link.revision_policy.mode is RevisionMode.RUNTIME_LINKAGE
    assert chat_session.revision_policy.revision_number_field is None
    assert chat_message_link.revision_policy.parent_revision_id_field is None


def test_validation_rejects_promoting_chapter_artifact_to_canonical_revision_chain() -> None:
    chapter_artifact = get_family_contract("chapter_artifact")
    invalid_policy = replace(
        chapter_artifact.revision_policy,
        mode=RevisionMode.CANONICAL_CHAIN,
        revision_id_field="revision_id",
        revision_number_field="revision_number",
        parent_revision_id_field="parent_revision_id",
        derived_from_revision_field=None,
    )
    invalid_registry = _replace_contract(
        "chapter_artifact",
        category=FamilyCategory.CANONICAL,
        revision_policy=invalid_policy,
    )

    try:
        validate_registry(invalid_registry)
    except ValueError as error:
        assert "chapter_artifact" in str(error)
        return

    raise AssertionError("Derived chapter artifacts must not validate as canonical narrative objects")


def test_validation_rejects_chat_linkage_using_narrative_revision_mode() -> None:
    chat_session = get_family_contract_from_registry(FAMILY_REGISTRY, "chat_session")
    invalid_policy = replace(chat_session.revision_policy, mode=RevisionMode.SNAPSHOT_DERIVED)
    invalid_registry = _replace_contract("chat_session", revision_policy=invalid_policy)

    try:
        validate_registry(invalid_registry)
    except ValueError as error:
        assert "chat_session" in str(error)
        return

    raise AssertionError("Chat sessions must remain runtime linkage objects")


# ---------------------------------------------------------------------------
# Upstream canonical-link workbench request/result contract tests
# ---------------------------------------------------------------------------
# These tests verify that the v1 request/result dataclasses for the three
# upstream links (outline->plot, plot->event, event->scene) exist with the
# correct fields and follow the locked semantics:
#   - parent_id + expected_parent_revision_id for stale-parent rejection
#   - target_child_object_id + base_child_revision_id for explicit updates
#   - create-only default when target_child_object_id is None
#   - idempotent approval (documented, enforced downstream)
# ---------------------------------------------------------------------------

from core.runtime import (
    OutlineToPlotWorkbenchRequest,
    OutlineToPlotWorkbenchResult,
    PlotToEventWorkbenchRequest,
    PlotToEventWorkbenchResult,
    EventToSceneWorkbenchRequest,
    EventToSceneWorkbenchResult,
)
from dataclasses import fields as dataclass_fields


def _field_names(cls: type) -> set[str]:
    return {f.name for f in dataclass_fields(cls)}


def test_outline_to_plot_request_has_required_contract_fields() -> None:
    names = _field_names(OutlineToPlotWorkbenchRequest)
    # Parent pinning
    assert "outline_node_object_id" in names
    assert "expected_parent_revision_id" in names
    # Explicit-target update identifiers
    assert "target_child_object_id" in names
    assert "base_child_revision_id" in names
    # Standard context
    assert "project_id" in names
    assert "novel_id" in names
    assert "actor" in names
    assert "source_surface" in names

    # Create-only default: target fields default to None
    req = OutlineToPlotWorkbenchRequest(
        project_id="p1", novel_id="n1", outline_node_object_id="out_1", actor="test"
    )
    assert req.target_child_object_id is None
    assert req.base_child_revision_id is None
    assert req.expected_parent_revision_id is None
    assert req.source_surface == "outline_to_plot_workbench"


def test_outline_to_plot_result_has_required_contract_fields() -> None:
    names = _field_names(OutlineToPlotWorkbenchResult)
    assert "disposition" in names
    assert "outline_node_object_id" in names
    assert "source_outline_revision_id" in names
    assert "child_object_id" in names
    assert "child_revision_id" in names
    assert "proposal_id" in names
    assert "review_route" in names
    assert "plot_payload" in names
    assert "delta_payload" in names
    assert "lineage_payload" in names
    assert "reasons" in names


def test_plot_to_event_request_has_required_contract_fields() -> None:
    names = _field_names(PlotToEventWorkbenchRequest)
    assert "plot_node_object_id" in names
    assert "expected_parent_revision_id" in names
    assert "target_child_object_id" in names
    assert "base_child_revision_id" in names
    assert "project_id" in names
    assert "novel_id" in names
    assert "actor" in names

    req = PlotToEventWorkbenchRequest(
        project_id="p1", novel_id="n1", plot_node_object_id="plt_1", actor="test"
    )
    assert req.target_child_object_id is None
    assert req.base_child_revision_id is None
    assert req.expected_parent_revision_id is None
    assert req.source_surface == "plot_to_event_workbench"


def test_plot_to_event_result_has_required_contract_fields() -> None:
    names = _field_names(PlotToEventWorkbenchResult)
    assert "disposition" in names
    assert "plot_node_object_id" in names
    assert "source_plot_revision_id" in names
    assert "child_object_id" in names
    assert "child_revision_id" in names
    assert "proposal_id" in names
    assert "review_route" in names
    assert "event_payload" in names
    assert "delta_payload" in names
    assert "lineage_payload" in names
    assert "reasons" in names


def test_event_to_scene_request_has_required_contract_fields() -> None:
    names = _field_names(EventToSceneWorkbenchRequest)
    assert "event_object_id" in names
    assert "expected_parent_revision_id" in names
    assert "target_child_object_id" in names
    assert "base_child_revision_id" in names
    assert "project_id" in names
    assert "novel_id" in names
    assert "actor" in names

    req = EventToSceneWorkbenchRequest(
        project_id="p1", novel_id="n1", event_object_id="evt_1", actor="test"
    )
    assert req.target_child_object_id is None
    assert req.base_child_revision_id is None
    assert req.expected_parent_revision_id is None
    assert req.source_surface == "event_to_scene_workbench"


def test_event_to_scene_result_has_required_contract_fields() -> None:
    names = _field_names(EventToSceneWorkbenchResult)
    assert "disposition" in names
    assert "event_object_id" in names
    assert "source_event_revision_id" in names
    assert "child_object_id" in names
    assert "child_revision_id" in names
    assert "proposal_id" in names
    assert "review_route" in names
    assert "scene_payload" in names
    assert "delta_payload" in names
    assert "lineage_payload" in names
    assert "reasons" in names


def test_upstream_workbench_requests_share_consistent_update_contract() -> None:
    """All three upstream request types follow the same create-vs-update contract:
    target_child_object_id=None means create-only; supplying it means update
    with mandatory base_child_revision_id for drift checking."""
    for cls in (
        OutlineToPlotWorkbenchRequest,
        PlotToEventWorkbenchRequest,
        EventToSceneWorkbenchRequest,
    ):
        names = _field_names(cls)
        assert "target_child_object_id" in names, f"{cls.__name__} missing target_child_object_id"
        assert "base_child_revision_id" in names, f"{cls.__name__} missing base_child_revision_id"
        assert "expected_parent_revision_id" in names, f"{cls.__name__} missing expected_parent_revision_id"


def test_upstream_workbench_results_share_consistent_disposition_contract() -> None:
    """All three upstream result types carry disposition, child IDs, proposal_id,
    and review_route — matching the review-aware pattern from scene->chapter."""
    for cls in (
        OutlineToPlotWorkbenchResult,
        PlotToEventWorkbenchResult,
        EventToSceneWorkbenchResult,
    ):
        names = _field_names(cls)
        assert "disposition" in names, f"{cls.__name__} missing disposition"
        assert "child_object_id" in names, f"{cls.__name__} missing child_object_id"
        assert "child_revision_id" in names, f"{cls.__name__} missing child_revision_id"
        assert "proposal_id" in names, f"{cls.__name__} missing proposal_id"
        assert "review_route" in names, f"{cls.__name__} missing review_route"
