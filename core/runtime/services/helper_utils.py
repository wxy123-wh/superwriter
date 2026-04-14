"""Helper utility functions for application services."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from core.runtime.mutation_policy import MutationExecutionResult
    from core.runtime.storage import CanonicalStorage, JSONValue
    from core.runtime.types import (
        DerivedArtifactSnapshot,
        ServiceMutationResult,
        WorkspaceObjectSummary,
    )

JSONObject = dict[str, "JSONValue"]


class HelperUtils:
    """Utility helper methods for payload and data extraction."""

    def __init__(self, storage: "CanonicalStorage"):
        self.__storage = storage

    def payload_text_value(self, payload: JSONObject, key: str) -> str | None:
        """Extract text value from payload, returning None if empty."""
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def payload_int_value(self, payload: JSONObject, key: str, default: int) -> int:
        """Extract integer value from payload with default fallback."""
        value = payload.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float | str):
            return int(value)
        return default

    def prose_payload_text(self, payload: JSONObject) -> str:
        """Extract prose text from payload for display."""
        for key in ("body", "summary", "title", "instruction", "rule"):
            value = self.payload_text_value(payload, key)
            if value:
                return value[:200] + ("..." if len(value) > 200 else "")
        return "(empty payload)"

    def workspace_summary_text(self, summary: "WorkspaceObjectSummary") -> str:
        """Extract display text from workspace object summary."""
        for key in ("title", "rule", "instruction", "summary", "fact", "state", "name"):
            value = summary.payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return summary.object_id

    def latest_artifact_for_object_id(
        self,
        object_id: str,
        *,
        family: str = "chapter_artifact",
        list_derived_artifacts_func,
    ) -> "DerivedArtifactSnapshot | None":
        """Get the latest artifact for a given object ID."""
        candidates = [
            artifact
            for artifact in list_derived_artifacts_func(family)
            if artifact.object_id == object_id
        ]
        return candidates[-1] if candidates else None

    def latest_scene_chapter_artifact(
        self,
        scene_object_id: str,
        *,
        novel_id: str,
        list_derived_artifacts_func,
    ) -> "DerivedArtifactSnapshot | None":
        """Get the latest chapter artifact for a scene."""
        matching = [
            artifact
            for artifact in list_derived_artifacts_func("chapter_artifact")
            if artifact.payload.get("source_scene_id") == scene_object_id
            and artifact.payload.get("novel_id") == novel_id
        ]
        return matching[-1] if matching else None

    def derived_artifact_by_revision(
        self,
        artifact_revision_id: str,
        *,
        family: str = "chapter_artifact",
        list_derived_artifacts_func,
    ) -> "DerivedArtifactSnapshot | None":
        """Find artifact by revision ID."""
        for artifact in list_derived_artifacts_func(family):
            if artifact.artifact_revision_id == artifact_revision_id:
                return artifact
        return None

    def latest_import_source(self, project_id: str) -> str | None:
        """Get the latest import source for a project."""
        import_rows = self.__storage.fetch_import_records(project_id=project_id)
        if not import_rows:
            return None
        return str(import_rows[-1]["import_source"])

    def service_mutation_result(self, result: "MutationExecutionResult") -> "ServiceMutationResult":
        """Convert mutation execution result to service result."""
        from core.runtime.types import ServiceMutationResult

        return ServiceMutationResult(
            policy_class=result.policy_class.value,
            disposition=result.disposition.value,
            target_family=result.target_family,
            target_object_id=result.target_object_id,
            reasons=result.reasons,
            canonical_revision_id=result.canonical_revision_id,
            canonical_revision_number=result.canonical_revision_number,
            mutation_record_id=result.mutation_record_id,
            artifact_revision_id=result.artifact_revision_id,
            proposal_id=result.proposal_id,
        )
