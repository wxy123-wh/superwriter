"""Payload builder service for constructing artifact payloads."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from core.runtime.storage import JSONValue
    from core.runtime.types import (
        CanonicalObjectSnapshot,
        DerivedArtifactSnapshot,
        ReadObjectRequest,
        WorkspaceObjectSummary,
        WorkspaceSnapshotRequest,
    )

JSONObject = dict[str, "JSONValue"]


class PayloadBuilderService:
    """Service for building payloads for various artifacts."""

    def __init__(
        self,
        get_active_ai_provider_func,
        read_object_func,
        get_workspace_snapshot_func,
        payload_text_value_func,
        workspace_summary_text_func,
    ):
        self._get_active_ai_provider = get_active_ai_provider_func
        self._read_object = read_object_func
        self._get_workspace_snapshot = get_workspace_snapshot_func
        self._payload_text_value = payload_text_value_func
        self._workspace_summary_text = workspace_summary_text_func

    def build_scene_to_chapter_payload(
        self,
        *,
        scene: "CanonicalObjectSnapshot",
        style_rules: tuple["WorkspaceObjectSummary", ...],
        scoped_skills: tuple["WorkspaceObjectSummary", ...],
        canonical_facts: tuple["WorkspaceObjectSummary", ...],
        previous_payload: JSONObject,
        previous_artifact_revision_id: str | None,
    ) -> JSONObject:
        """Build payload for scene-to-chapter artifact."""
        from core.ai.prompts import build_scene_to_chapter_prompt
        from core.runtime.utils import _build_object_diff
        from core.runtime.types import ReadObjectRequest

        chapter_title = self.scene_chapter_title(scene.payload, scene.object_id)

        # Try AI generation first
        ai_client = self._get_active_ai_provider()
        body: str
        generation_notes: str

        if ai_client is not None:
            try:
                # Get novel context for the prompt
                novel_id = cast(str, scene.payload.get("novel_id"))
                novel_read = self._read_object(ReadObjectRequest(family="novel", object_id=novel_id))
                novel_context: JSONObject = {}
                if novel_read.head is not None:
                    novel_context = {
                        "title": novel_read.head.payload.get("title", "Untitled"),
                        "premise": novel_read.head.payload.get("premise", ""),
                        "genre": novel_read.head.payload.get("genre", ""),
                        "voice": novel_read.head.payload.get("voice", "Third person limited"),
                    }

                # Prepare context objects
                style_rule_payloads = [rule.payload for rule in style_rules]
                skill_payloads = [skill.payload for skill in scoped_skills]
                fact_payloads = [fact.payload for fact in canonical_facts]

                # Get previous chapter if available for continuity
                previous_chapter: JSONObject | None = None
                if previous_artifact_revision_id and previous_payload.get("chapter_title"):
                    previous_chapter = {
                        "chapter_title": str(previous_payload.get("chapter_title", "")),
                        "ending_note": str(previous_payload.get("body", ""))[-500:]
                        if previous_payload.get("body")
                        else "",
                    }

                # Build prompt and generate
                messages = build_scene_to_chapter_prompt(
                    scene=scene.payload,
                    novel_context=novel_context,
                    style_rules=style_rule_payloads,
                    skills=skill_payloads,
                    canonical_facts=fact_payloads,
                    previous_chapter=previous_chapter,
                )

                # Use structured generation for consistent output
                output_schema = {
                    "type": "object",
                    "properties": {
                        "chapter_title": {"type": "string"},
                        "chapter_body": {"type": "string"},
                        "word_count": {"type": "integer"},
                        "notes": {"type": "string"},
                    },
                    "required": ["chapter_title", "chapter_body", "word_count"],
                }

                result = ai_client.generate_structured(
                    messages=messages,
                    output_schema=output_schema,
                )

                # Extract generated content
                generated_title = str(result.get("chapter_title", chapter_title))
                body = str(result.get("chapter_body", ""))
                word_count = int(result.get("word_count", 0))
                notes = str(result.get("notes", ""))

                # Use AI-generated title if provided
                if generated_title and generated_title != "Untitled":
                    chapter_title = generated_title

                # Add metadata about AI generation
                generation_notes = f"AI-generated chapter (~{word_count} words)."
                if notes:
                    generation_notes += f" {notes}"

            except Exception as e:
                # Fall back to mock generation on error
                body_sections = [self.scene_body_seed(scene.payload)]
                body_sections.append(f"[AI generation unavailable: {e}])")
                if style_rules:
                    style_notes = "; ".join(self._workspace_summary_text(item) for item in style_rules)
                    body_sections.append(f"Style guidance: {style_notes}.")
                if scoped_skills:
                    skill_notes = "; ".join(self._workspace_summary_text(item) for item in scoped_skills)
                    body_sections.append(f"Skill guidance: {skill_notes}.")
                if canonical_facts:
                    fact_notes = "; ".join(self._workspace_summary_text(item) for item in canonical_facts)
                    body_sections.append(f"Canonical facts: {fact_notes}.")
                body = "\n\n".join(section for section in body_sections if section)
                generation_notes = "Mock content (AI provider not configured or generation failed)."
        else:
            # No AI provider configured - use mock generation
            body_sections = [self.scene_body_seed(scene.payload)]
            if style_rules:
                style_notes = "; ".join(self._workspace_summary_text(item) for item in style_rules)
                body_sections.append(f"Style guidance: {style_notes}.")
            if scoped_skills:
                skill_notes = "; ".join(self._workspace_summary_text(item) for item in scoped_skills)
                body_sections.append(f"Skill guidance: {skill_notes}.")
            if canonical_facts:
                fact_notes = "; ".join(self._workspace_summary_text(item) for item in canonical_facts)
                body_sections.append(f"Canonical facts: {fact_notes}.")
            body = "\n\n".join(section for section in body_sections if section)
            generation_notes = "Mock content (no AI provider configured)."

        lineage_payload: JSONObject = {
            "source_scene_id": scene.object_id,
            "source_scene_revision_id": scene.current_revision_id,
            "previous_artifact_revision_id": previous_artifact_revision_id,
        }
        payload: JSONObject = {
            "novel_id": cast(str, scene.payload["novel_id"]),
            "source_scene_id": scene.object_id,
            "source_scene_revision_id": scene.current_revision_id,
            "chapter_title": chapter_title,
            "body": body,
            "lineage": lineage_payload,
            "generation_notes": generation_notes,
            "delta_from_previous": _build_object_diff(
                previous_payload,
                {
                    "novel_id": cast(str, scene.payload["novel_id"]),
                    "source_scene_id": scene.object_id,
                    "source_scene_revision_id": scene.current_revision_id,
                    "chapter_title": chapter_title,
                    "body": body,
                },
            ),
            "generation_context": {
                "style_rule_ids": [item.object_id for item in style_rules],
                "skill_ids": [item.object_id for item in scoped_skills],
                "fact_ids": [item.object_id for item in canonical_facts],
            },
        }
        return payload

    def build_publish_export_payload(
        self,
        *,
        project_id: str,
        novel: "CanonicalObjectSnapshot",
        chapter_artifact: "DerivedArtifactSnapshot | None",
        export_format: str,
    ) -> JSONObject:
        """Build payload for publish export."""
        from core.runtime.types import WorkspaceSnapshotRequest

        if chapter_artifact is None:
            raise ValueError("publish export requires a chapter_artifact source in the current MVP")
        chapter_title = self._payload_text_value(chapter_artifact.payload, "chapter_title") or chapter_artifact.object_id
        chapter_body = self._payload_text_value(chapter_artifact.payload, "body") or ""
        source_scene_id = self._payload_text_value(chapter_artifact.payload, "source_scene_id")
        active_skills = tuple(
            summary.object_id
            for summary in self._get_workspace_snapshot(
                WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel.object_id)
            ).canonical_objects
            if summary.family == "skill"
            and summary.payload.get("novel_id") == novel.object_id
            and bool(summary.payload.get("is_active", False))
        )
        markdown_body = (
            f"# {self._payload_text_value(novel.payload, 'title') or novel.object_id}\n\n"
            f"## {chapter_title}\n\n"
            f"{chapter_body.strip()}\n"
        )
        lineage: JSONObject = {
            "project_id": project_id,
            "novel_id": novel.object_id,
            "novel_revision_id": novel.current_revision_id,
            "source_chapter_artifact_id": chapter_artifact.object_id,
            "source_chapter_artifact_revision_id": chapter_artifact.artifact_revision_id,
            "source_scene_id": source_scene_id,
            "source_scene_revision_id": chapter_artifact.source_scene_revision_id,
            "active_skill_ids": list(active_skills),
        }
        projections: list[JSONValue] = [
            {
                "path": "manuscript.md",
                "media_type": "text/markdown",
                "content": markdown_body,
            },
            {
                "path": "lineage.json",
                "media_type": "application/json",
                "content": json.dumps(lineage, ensure_ascii=False, indent=2, sort_keys=True),
            },
        ]
        return cast(
            JSONObject,
            {
                "project_id": project_id,
                "novel_id": novel.object_id,
                "source_chapter_artifact_id": chapter_artifact.object_id,
                "source_scene_id": source_scene_id,
                "source_scene_revision_id": chapter_artifact.source_scene_revision_id,
                "export_format": export_format,
                "chapter_title": chapter_title,
                "body": markdown_body,
                "lineage": lineage,
                "projections": projections,
            },
        )

    @staticmethod
    def scene_chapter_title(payload: JSONObject, scene_object_id: str) -> str:
        """Extract chapter title from scene payload."""
        title = payload.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        return f"Chapter from {scene_object_id}"

    @staticmethod
    def scene_body_seed(payload: JSONObject) -> str:
        """Generate body seed from scene payload."""
        title = payload.get("title")
        summary = payload.get("summary")
        event_id = payload.get("event_id")
        parts: list[str] = []
        if isinstance(title, str) and title.strip():
            parts.append(title.strip())
        if isinstance(summary, str) and summary.strip():
            parts.append(summary.strip())
        if isinstance(event_id, str) and event_id.strip():
            parts.append(f"Event anchor: {event_id.strip()}.")
        return " ".join(parts) if parts else "Scene seed imported without prose summary."

    @staticmethod
    def skill_matches_scene_to_chapter_scope(payload: JSONObject) -> bool:
        """Check if skill matches scene-to-chapter scope."""
        scope_candidates = (
            payload.get("scope"),
            payload.get("pipeline_scope"),
            payload.get("target_pair"),
            payload.get("target_family"),
        )
        normalized = {
            candidate.strip().lower()
            for candidate in scope_candidates
            if isinstance(candidate, str) and candidate.strip()
        }
        if {"scene_to_chapter", "scene->chapter", "chapter_artifact"} & normalized:
            return True
        skill_type = payload.get("skill_type")
        return isinstance(skill_type, str) and skill_type.strip().lower() == "style_rule"
