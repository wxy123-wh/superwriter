from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "ownership-map.json"


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def validate_manifest(manifest: dict[str, Any]) -> None:
    required_top_level_paths = manifest["global_policy"]["required_top_level_paths"]
    forbidden_top_level_paths = set(manifest["global_policy"]["forbidden_top_level_paths"])
    forbidden_legacy_patterns = set(manifest["global_policy"]["forbidden_legacy_patterns"])
    subsystems = manifest["subsystems"]

    assert manifest["product_shape"]["primary_shell"] == "web_command_center"
    assert (
        manifest["product_shape"]["object_truth_model"]
        == "structured_objects_over_raw_text"
    )
    assert (
        manifest["product_shape"]["migration_policy"]["implementation_base_donor"]
        == "webnovel-writer"
    )
    assert (
        manifest["product_shape"]["migration_policy"]["concept_donor_only"]
        == "restored-decompiled-artifacts"
    )

    assert set(subsystems) == set(required_top_level_paths)

    for subsystem_name in required_top_level_paths:
        entry = subsystems[subsystem_name]
        assert isinstance(entry["owner"], str) and entry["owner"].strip()
        assert len(entry["allowed_dependencies"]) == len(set(entry["allowed_dependencies"]))
        assert subsystem_name not in entry["allowed_dependencies"]

        for dependency in entry["allowed_dependencies"]:
            assert dependency in subsystems, f"Unknown dependency {dependency} in {subsystem_name}"
            assert dependency not in forbidden_top_level_paths

        donor_policy = entry["donor_reference_policy"]
        allowed_donors = donor_policy["allowed_donors"]
        assert allowed_donors, f"{subsystem_name} must declare donor policy"
        assert set(allowed_donors).issubset(
            {"webnovel-writer", "restored-decompiled-artifacts"}
        )
        if subsystem_name != "tests":
            assert allowed_donors == ["webnovel-writer"]
        else:
            assert set(allowed_donors) == {
                "webnovel-writer",
                "restored-decompiled-artifacts",
            }

        combined_forbidden = forbidden_legacy_patterns | forbidden_top_level_paths
        declared_forbidden = set(entry["forbidden_legacy_patterns"])
        assert declared_forbidden
        assert not set(entry["allowed_dependencies"]) & combined_forbidden
        assert not declared_forbidden & forbidden_top_level_paths


def test_required_directories_exist() -> None:
    manifest = load_manifest()
    validate_manifest(manifest)

    for relative_path in manifest["global_policy"]["required_top_level_paths"]:
        assert (REPO_ROOT / relative_path).is_dir(), f"Missing scaffold directory: {relative_path}"


def test_manifest_freezes_ownership_boundaries() -> None:
    manifest = load_manifest()
    validate_manifest(manifest)

    assert manifest["subsystems"]["apps/web"]["owner"] == "web-command-center"
    assert manifest["subsystems"]["core/objects"]["owner"] == "structured-object-truth"
    assert manifest["subsystems"]["core/retrieval"]["donor_reference_policy"]["reference_mode"] == (
        "implementation_base"
    )
    assert "vscode_activation" in manifest["global_policy"]["forbidden_legacy_patterns"]
    assert "src/extension.ts" in manifest["global_policy"]["forbidden_top_level_paths"]


def test_validation_rejects_forbidden_top_level_path_as_dependency() -> None:
    manifest = load_manifest()
    invalid = deepcopy(manifest)
    invalid["subsystems"]["apps/web"]["allowed_dependencies"].append("dashboard")

    try:
        validate_manifest(invalid)
    except AssertionError:
        return

    raise AssertionError("Manifest validation should reject forbidden top-level dependencies")


def test_validation_rejects_forbidden_pattern_declared_as_allowed_donor() -> None:
    manifest = load_manifest()
    invalid = deepcopy(manifest)
    invalid["subsystems"]["core/runtime"]["donor_reference_policy"]["allowed_donors"] = [
        "webnovel-writer",
        "vscode_activation",
    ]

    try:
        validate_manifest(invalid)
    except AssertionError:
        return

    raise AssertionError("Manifest validation should reject forbidden legacy patterns as allowed donors")
