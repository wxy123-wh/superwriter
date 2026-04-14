from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.runtime import (  # noqa: E402
    JSONValue,
    ReadObjectRequest,
    ServiceMutationRequest,
    SkillWorkshopCompareRequest,
    SkillWorkshopImportRequest,
    SkillWorkshopRequest,
    SkillWorkshopRollbackRequest,
    SkillWorkshopUpsertRequest,
    SuperwriterApplicationService,
)
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest  # noqa: E402


def test_skill_workshop_versions_compare_and_rollback_stay_in_one_unified_skill_model(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(tmp_path)

    created = service.upsert_skill_workshop_skill(
        SkillWorkshopUpsertRequest(
            novel_id=novel_id,
            actor="author-1",
            source_surface="skill_workshop_dialogue",
            name="Harbor hush",
            description="Quietly observant prose",
            instruction="Prefer quiet sensory detail and delayed reveals.",
            style_scope="scene_to_chapter",
            is_active=True,
        )
    )
    assert created.disposition == "auto_applied"
    assert created.policy_class == "skill_style_rule"

    updated = service.upsert_skill_workshop_skill(
        SkillWorkshopUpsertRequest(
            novel_id=novel_id,
            actor="author-1",
            source_surface="skill_workshop_form",
            skill_object_id=created.object_id,
            name="Harbor hush",
            description="Quietly observant prose",
            instruction="Prefer quiet sensory detail, delayed reveals, and sparse metaphors.",
            style_scope="chapter_revision",
            is_active=False,
        )
    )
    assert updated.revision_number == 2

    workshop = service.get_skill_workshop(
        SkillWorkshopRequest(project_id=project_id, novel_id=novel_id, selected_skill_id=created.object_id)
    )
    assert len(workshop.skills) == 1
    assert workshop.selected_skill is not None
    assert workshop.selected_skill.payload["skill_type"] == "style_rule"
    assert [version.revision_number for version in workshop.versions] == [2, 1]
    assert workshop.comparison is not None
    changed = workshop.comparison.structured_diff["changed"]
    assert isinstance(changed, dict)
    assert "instruction" in changed
    assert "style_scope" in changed

    explicit_compare = service.compare_skill_versions(
        SkillWorkshopCompareRequest(
            skill_object_id=created.object_id,
            left_revision_id=workshop.versions[1].revision_id,
            right_revision_id=workshop.versions[0].revision_id,
        )
    )
    assert "delayed reveals" in explicit_compare.rendered_diff

    rolled_back = service.rollback_skill_workshop_skill(
        SkillWorkshopRollbackRequest(
            skill_object_id=created.object_id,
            target_revision_id=workshop.versions[1].revision_id,
            actor="author-2",
            source_surface="skill_workshop_form",
        )
    )
    assert rolled_back.revision_number == 3

    final_read = service.read_object(
        ReadObjectRequest(family="skill", object_id=created.object_id, include_revisions=True, include_mutations=True)
    )
    assert final_read.head is not None
    assert final_read.head.payload["instruction"] == "Prefer quiet sensory detail and delayed reveals."
    assert final_read.head.payload["style_scope"] == "scene_to_chapter"
    assert final_read.head.payload["is_active"] is True
    assert [revision.revision_number for revision in final_read.revisions] == [1, 2, 3]
    assert [mutation.policy_class for mutation in final_read.mutations] == ["skill_style_rule", "skill_style_rule", "skill_style_rule"]


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ({"generation_params": {"temperature": 0.9}}, "generation parameters are not editable"),
        ({"retrieval_scope": "all_notes"}, "retrieval scope is not editable"),
        ({"tool_permissions": ["shell"]}, "tool permissions are not editable"),
    ],
)
def test_skill_workshop_rejects_forbidden_fields_explicitly(tmp_path: Path, payload: dict[str, object], expected_message: str) -> None:
    service, _, novel_id = _seed_workspace(tmp_path)

    with pytest.raises(ValueError, match=expected_message):
        _ = service.apply_mutation(
            ServiceMutationRequest(
                target_family="skill",
                payload=cast(
                    dict[str, JSONValue],
                    {
                        "novel_id": novel_id,
                        "skill_type": "style_rule",
                        "name": "Forbidden test",
                        "description": "",
                        "instruction": "Keep the prose clipped.",
                        "style_scope": "scene_to_chapter",
                        "is_active": True,
                        "source_kind": "skill_workshop",
                        **payload,
                    },
                ),
                actor="author-1",
                source_surface="skill_workshop_form",
            )
        )


def test_skill_workshop_imports_prompt_templates_custom_agents_and_ai_roles_through_adapters(tmp_path: Path) -> None:
    service, project_id, novel_id = _seed_workspace(tmp_path)

    prompt_template = service.import_skill_workshop_skill(
        SkillWorkshopImportRequest(
            donor_kind="prompt_template",
            novel_id=novel_id,
            actor="importer",
            source_surface="skill_workshop_form",
            donor_payload={
                "title": "Noir template",
                "template": "Use clipped noir observations and withhold the reveal until the last line.",
            },
        )
    )
    custom_agent = service.import_skill_workshop_skill(
        SkillWorkshopImportRequest(
            donor_kind="custom_agent",
            novel_id=novel_id,
            actor="importer",
            source_surface="skill_workshop_form",
            donor_payload={
                "name": "Chapel whisperer",
                "description": "A close-third stylistic helper.",
                "system_prompt": "Stay intimate, spare, and careful with reveals.",
            },
        )
    )
    ai_role = service.import_skill_workshop_skill(
        SkillWorkshopImportRequest(
            donor_kind="ai_role",
            novel_id=novel_id,
            actor="importer",
            source_surface="skill_workshop_form",
            donor_payload={
                "role": "Archivist",
                "personality": "Measured, observant, and exacting.",
                "background": "Keeps every page dusted and every omission suspicious.",
            },
        )
    )

    workshop = service.get_skill_workshop(SkillWorkshopRequest(project_id=project_id, novel_id=novel_id))
    assert [skill.payload["skill_type"] for skill in workshop.skills] == ["style_rule", "style_rule", "style_rule"]
    donor_kinds = {
        donor_kind
        for skill in workshop.skills
        for mapping in [skill.payload.get("import_mapping")]
        for donor_kind in [mapping.get("donor_kind") if isinstance(mapping, dict) else None]
        if isinstance(mapping, dict)
        if isinstance(donor_kind, str)
    }
    assert donor_kinds == {"prompt_template", "custom_agent", "ai_role"}
    assert prompt_template.object_id.startswith("skl_")
    assert custom_agent.object_id.startswith("skl_")
    assert ai_role.object_id.startswith("skl_")


def _seed_workspace(tmp_path: Path) -> tuple[SuperwriterApplicationService, str, str]:
    db_path = tmp_path / "canonical.sqlite3"
    storage = CanonicalStorage(db_path)
    project = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="project",
            object_id="prj_skill_workshop",
            payload={"title": "Skill Workshop"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed project",
        )
    )
    novel = storage.write_canonical_object(
        CanonicalWriteRequest(
            family="novel",
            object_id="nvl_skill_workshop",
            payload={"project_id": project.object_id, "title": "Harbor Ledger", "genre": "mystery"},
            actor="seed",
            source_surface="seed",
            policy_class="seed",
            approval_state="approved",
            revision_reason="seed novel",
        )
    )
    return SuperwriterApplicationService.for_sqlite(db_path), project.object_id, novel.object_id
