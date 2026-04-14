from __future__ import annotations

from typing import Callable, cast

from core.ai import AIProviderClient
from core.ai.provider import AIProviderError
from core.ai.prompts import (
    build_outline_to_plot_prompt,
    build_plot_to_event_prompt,
    build_event_to_scene_prompt,
)
from core.runtime.storage import CanonicalStorage, JSONValue
from core.runtime.types import (
    CanonicalObjectSnapshot,
    ReadObjectRequest,
    WorkspaceObjectSummary,
    WorkspaceSnapshotRequest,
    WorkspaceSnapshotResult,
)

JSONObject = dict[str, JSONValue]


class LegacyWorkbenchService:
    """Service for legacy AI-powered workbench generation methods.

    This service contains the original workbench generation logic that will be
    replaced by the new pipeline-based approach. It's extracted here to keep
    the main application service clean during the transition.
    """

    def __init__(
        self,
        storage: CanonicalStorage,
        get_active_ai_provider_func: Callable[[], AIProviderClient | None],
        read_object_func: Callable[[ReadObjectRequest], object],
        get_workspace_snapshot_func: Callable[[WorkspaceSnapshotRequest], WorkspaceSnapshotResult],
        build_scene_to_chapter_payload_func: Callable[..., JSONObject],
    ):
        """Initialize the legacy workbench service.

        Args:
            storage: The canonical storage instance
            get_active_ai_provider_func: Function to get the active AI provider
            read_object_func: Function to read canonical objects
            get_workspace_snapshot_func: Function to get workspace snapshots
            build_scene_to_chapter_payload_func: Function to build scene-to-chapter payloads
        """
        self._storage = storage
        self._get_active_ai_provider = get_active_ai_provider_func
        self._read_object = read_object_func
        self._get_workspace_snapshot = get_workspace_snapshot_func
        self._build_scene_to_chapter_payload = build_scene_to_chapter_payload_func

    def _generate_plot_nodes_with_ai(
        self,
        outline_node: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        skills: tuple[WorkspaceObjectSummary, ...],
        parent_outline: CanonicalObjectSnapshot | None,
    ) -> list[JSONObject]:
        """Generate plot nodes from outline using AI."""
        ai_client = self._get_active_ai_provider()
        if ai_client is None:
            raise AIProviderError("未配置可用的 AI 提供商。请先在设置页保存并激活模型。")

        try:
            skill_payloads = [skill.payload for skill in skills]
            messages = build_outline_to_plot_prompt(
                outline_node=outline_node.payload,
                novel_context=novel_context,
                skills=skill_payloads,
                parent_outline=parent_outline.payload if parent_outline else None,
            )

            output_schema = {
                "type": "object",
                "properties": {
                    "plot_nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "summary": {"type": "string"},
                                "sequence_order": {"type": "integer"},
                                "notes": {"type": "string"},
                            },
                            "required": ["title", "summary", "sequence_order"],
                        },
                    },
                },
                "required": ["plot_nodes"],
            }

            result = ai_client.generate_structured(messages=messages, output_schema=output_schema)
            return cast(list[JSONObject], result.get("plot_nodes", []))
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(f"剧情节点生成失败：{exc}") from exc

    def _generate_events_with_ai(
        self,
        plot_node: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        outline_context: CanonicalObjectSnapshot | None,
        skills: tuple[WorkspaceObjectSummary, ...],
    ) -> list[JSONObject]:
        """Generate events from plot node using AI."""
        ai_client = self._get_active_ai_provider()
        if ai_client is None:
            raise AIProviderError("未配置可用的 AI 提供商。请先在设置页保存并激活模型。")

        try:
            skill_payloads = [skill.payload for skill in skills]
            messages = build_plot_to_event_prompt(
                plot_node=plot_node.payload,
                novel_context=novel_context,
                outline_context=outline_context.payload if outline_context else {},
                skills=skill_payloads,
            )

            output_schema = {
                "type": "object",
                "properties": {
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "sequence_order": {"type": "integer"},
                                "location": {"type": "string"},
                                "characters_involved": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["title", "description", "sequence_order"],
                        },
                    },
                },
                "required": ["events"],
            }

            result = ai_client.generate_structured(messages=messages, output_schema=output_schema)
            return cast(list[JSONObject], result.get("events", []))
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(f"事件节点生成失败：{exc}") from exc

    def _generate_scenes_with_ai(
        self,
        event: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        plot_context: CanonicalObjectSnapshot | None,
        skills: tuple[WorkspaceObjectSummary, ...],
        characters: tuple[WorkspaceObjectSummary, ...],
        settings: tuple[WorkspaceObjectSummary, ...],
    ) -> list[JSONObject]:
        """Generate scenes from event using AI."""
        ai_client = self._get_active_ai_provider()
        if ai_client is None:
            raise AIProviderError("未配置可用的 AI 提供商。请先在设置页保存并激活模型。")

        try:
            skill_payloads = [skill.payload for skill in skills]
            character_payloads = [c.payload for c in characters]
            setting_payloads = [s.payload for s in settings]
            messages = build_event_to_scene_prompt(
                event=event.payload,
                novel_context=novel_context,
                plot_context=plot_context.payload if plot_context else {},
                skills=skill_payloads,
                characters=character_payloads,
                settings=setting_payloads,
            )

            output_schema = {
                "type": "object",
                "properties": {
                    "scenes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "setting": {"type": "string"},
                                "pov_character": {"type": "string"},
                                "characters_present": {"type": "array", "items": {"type": "string"}},
                                "scene_summary": {"type": "string"},
                                "beat_breakdown": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["title", "setting", "scene_summary", "beat_breakdown"],
                        },
                    },
                },
                "required": ["scenes"],
            }

            result = ai_client.generate_structured(messages=messages, output_schema=output_schema)
            return cast(list[JSONObject], result.get("scenes", []))
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(f"场景节点生成失败：{exc}") from exc

    def _gather_novel_context(self, novel_id: str) -> JSONObject:
        """Read novel-level context for AI prompt construction."""
        novel_read = self._read_object(ReadObjectRequest(family="novel", object_id=novel_id))
        if novel_read.head is None:
            return {}
        return {
            "title": novel_read.head.payload.get("title", "Untitled"),
            "premise": novel_read.head.payload.get("premise", ""),
            "genre": novel_read.head.payload.get("genre", ""),
            "voice": novel_read.head.payload.get("voice", "Third person limited"),
        }

    def _gather_workspace_skills(
        self, project_id: str, novel_id: str,
    ) -> tuple[WorkspaceObjectSummary, ...]:
        """Get active skills scoped to a novel."""
        workspace = self._get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        return tuple(
            s for s in workspace.canonical_objects
            if s.family == "skill" and s.payload.get("novel_id") == novel_id
        )

    def _gather_workspace_objects(
        self, project_id: str, novel_id: str, *families: str,
    ) -> tuple[WorkspaceObjectSummary, ...]:
        """Get workspace objects of specified families scoped to a novel."""
        workspace = self._get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )
        return tuple(
            s for s in workspace.canonical_objects
            if s.family in families and s.payload.get("novel_id") == novel_id
        )

    def _create_candidates_from_items(
        self,
        items: list[JSONObject],
        session_id: str,
        iteration_number: int,
        method: str,
        ai_generated: bool,
    ) -> list[dict]:
        """Create candidate drafts from a list of AI-generated items."""
        if not items:
            return []
        results: list[dict] = []
        for item in items:
            draft_id = self._storage.create_candidate_draft(
                session_id=session_id,
                iteration_number=iteration_number,
                payload=item,
                generation_context={"method": method, "ai_generated": ai_generated},
            )
            draft = self._storage.get_candidate_draft(draft_id)
            if draft:
                results.append(draft)
        return results

    def _outline_to_plot_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate plot candidates from an outline node using AI."""
        outline_read = self._read_object(
            ReadObjectRequest(family="outline_node", object_id=parent_object_id)
        )

        if outline_read.head is not None:
            outline = outline_read.head
            novel_context = self._gather_novel_context(novel_id)
            skills = self._gather_workspace_skills(project_id, novel_id)

            parent_outline_id = outline.payload.get("parent_outline_node_id")
            parent_outline: CanonicalObjectSnapshot | None = None
            if parent_outline_id:
                parent_read = self._read_object(
                    ReadObjectRequest(family="outline_node", object_id=str(parent_outline_id))
                )
                parent_outline = parent_read.head

            generated = self._generate_plot_nodes_with_ai(
                outline_node=outline,
                novel_context=novel_context,
                skills=skills,
                parent_outline=parent_outline,
            )

            if generated:
                items = [
                    {
                        "novel_id": novel_id,
                        "outline_node_id": parent_object_id,
                        "title": node.get("title", ""),
                        "summary": node.get("summary", ""),
                        "sequence_order": node.get("sequence_order", i + 1),
                        "notes": node.get("notes", ""),
                        "ai_generated": True,
                    }
                    for i, node in enumerate(generated)
                ]
                return self._create_candidates_from_items(
                    items, session_id, iteration_number, "outline_to_plot", ai_generated=True,
                )

            # AI returned nothing — use outline title for fallback
            fallback_payload: JSONObject = {
                "novel_id": novel_id,
                "outline_node_id": parent_object_id,
                "title": outline.payload.get("title", "Untitled Plot"),
                "summary": "Plot from outline (AI not available)",
                "ai_generated": False,
            }
            return self._create_candidates_from_items(
                [fallback_payload], session_id, iteration_number, "outline_to_plot", ai_generated=False,
            )

        # Fallback when parent not found
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "outline_node_id": parent_object_id,
            "title": "Generated Plot",
            "summary": "Plot candidate (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "outline_to_plot", ai_generated=False,
        )

    def _plot_to_event_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate event candidates from a plot node using AI."""
        plot_read = self._read_object(
            ReadObjectRequest(family="plot_node", object_id=parent_object_id)
        )
        if plot_read.head is not None:
            plot_node = plot_read.head
            novel_context = self._gather_novel_context(novel_id)
            skills = self._gather_workspace_skills(project_id, novel_id)

            outline_node_id = plot_node.payload.get("outline_node_id")
            outline_context: CanonicalObjectSnapshot | None = None
            if outline_node_id:
                outline_read = self._read_object(
                    ReadObjectRequest(family="outline_node", object_id=str(outline_node_id))
                )
                outline_context = outline_read.head

            generated = self._generate_events_with_ai(
                plot_node=plot_node,
                novel_context=novel_context,
                outline_context=outline_context,  # type: ignore
                skills=skills,
            )

            if generated:
                items = [
                    {
                        "novel_id": novel_id,
                        "plot_node_id": parent_object_id,
                        "title": node.get("title", ""),
                        "description": node.get("description", ""),
                        "sequence_order": node.get("sequence_order", i + 1),
                        "location": node.get("location", ""),
                        "characters_involved": node.get("characters_involved", []),
                        "ai_generated": True,
                    }
                    for i, node in enumerate(generated)
                ]
                return self._create_candidates_from_items(
                    items, session_id, iteration_number, "plot_to_event", ai_generated=True,
                )

            # AI returned nothing — use plot node title for fallback
            fallback_payload: JSONObject = {
                "novel_id": novel_id,
                "plot_node_id": parent_object_id,
                "title": plot_node.payload.get("title", "Untitled Event"),
                "description": "Event from plot node (AI not available)",
                "ai_generated": False,
            }
            return self._create_candidates_from_items(
                [fallback_payload], session_id, iteration_number, "plot_to_event", ai_generated=False,
            )

        # Fallback when parent not found
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "plot_node_id": parent_object_id,
            "title": "Generated Event",
            "description": "Event candidate (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "plot_to_event", ai_generated=False,
        )

    def _event_to_scene_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate scene candidates from an event using AI."""
        event_read = self._read_object(
            ReadObjectRequest(family="event", object_id=parent_object_id)
        )

        if event_read.head is not None:
            event = event_read.head
            novel_context = self._gather_novel_context(novel_id)
            skills = self._gather_workspace_skills(project_id, novel_id)
            characters = self._gather_workspace_objects(project_id, novel_id, "character")
            settings = self._gather_workspace_objects(project_id, novel_id, "setting")

            plot_node_id = event.payload.get("plot_node_id")
            plot_context: CanonicalObjectSnapshot | None = None
            if plot_node_id:
                plot_read = self._read_object(
                    ReadObjectRequest(family="plot_node", object_id=str(plot_node_id))
                )
                plot_context = plot_read.head

            generated = self._generate_scenes_with_ai(
                event=event,
                novel_context=novel_context,
                plot_context=plot_context,  # type: ignore
                skills=skills,
                characters=characters,
                settings=settings,
            )

            if generated:
                items = [
                    {
                        "novel_id": novel_id,
                        "event_id": parent_object_id,
                        "title": node.get("title", ""),
                        "setting": node.get("setting", ""),
                        "pov_character": node.get("pov_character", ""),
                        "characters_present": node.get("characters_present", []),
                        "summary": node.get("scene_summary", ""),
                        "beat_breakdown": node.get("beat_breakdown", []),
                        "ai_generated": True,
                    }
                    for node in generated
                ]
                return self._create_candidates_from_items(
                    items, session_id, iteration_number, "event_to_scene", ai_generated=True,
                )

            # AI returned nothing — use event title for fallback
            fallback_payload: JSONObject = {
                "novel_id": novel_id,
                "event_id": parent_object_id,
                "title": event.payload.get("title", "Untitled Scene"),
                "summary": "Scene from event (AI not available)",
                "ai_generated": False,
            }
            return self._create_candidates_from_items(
                [fallback_payload], session_id, iteration_number, "event_to_scene", ai_generated=False,
            )

        # Fallback when parent not found
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "event_id": parent_object_id,
            "title": "Generated Scene",
            "summary": "Scene candidate (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "event_to_scene", ai_generated=False,
        )

    def _scene_to_chapter_candidates(
        self, parent_object_id: str, novel_id: str, project_id: str,
        actor: str, session_id: str, iteration_number: int,
    ) -> list[dict]:
        """Generate chapter candidates from a scene using AI."""
        scene_read = self._read_object(
            ReadObjectRequest(family="scene", object_id=parent_object_id)
        )
        if scene_read.head is not None:
            scene = scene_read.head

            # Gather context for chapter generation
            style_rules = self._gather_workspace_objects(project_id, novel_id, "style_rule")
            skills = self._gather_workspace_skills(project_id, novel_id)
            facts = self._gather_workspace_objects(project_id, novel_id, "fact_state_record")

            chapter_payload = self._build_scene_to_chapter_payload(
                scene=scene,
                style_rules=style_rules,
                scoped_skills=skills,
                canonical_facts=facts,
                previous_payload={},
                previous_artifact_revision_id=None,
            )

            if chapter_payload.get("generation_notes", "").startswith("AI"):
                chapter_payload["ai_generated"] = True
                return self._create_candidates_from_items(
                    [chapter_payload], session_id, iteration_number, "scene_to_chapter", ai_generated=True,
                )

            # Fallback from _build_scene_to_chapter_payload (mock or no AI)
            chapter_payload["ai_generated"] = False
            return self._create_candidates_from_items(
                [chapter_payload], session_id, iteration_number, "scene_to_chapter", ai_generated=False,
            )

        # Fallback when scene has no head revision
        fallback_payload: JSONObject = {
            "novel_id": novel_id,
            "scene_id": parent_object_id,
            "chapter_title": "Generated Chapter",
            "body": "Chapter content (awaiting enrichment)",
            "ai_generated": False,
        }
        return self._create_candidates_from_items(
            [fallback_payload], session_id, iteration_number, "scene_to_chapter", ai_generated=False,
        )


__all__ = ["LegacyWorkbenchService"]
