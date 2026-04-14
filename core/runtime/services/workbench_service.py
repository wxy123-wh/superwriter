"""Workbench service for content generation pipelines."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from core.ai.provider import AIProviderError
from core.ai.prompts import (
    build_outline_to_plot_prompt,
    build_plot_to_event_prompt,
    build_event_to_scene_prompt,
    build_scene_to_chapter_prompt,
)
from core.runtime.mutation_policy import MutationDisposition, MutationPolicyClass
from core.runtime.storage import CanonicalWriteRequest, DerivedRecordInput
from core.runtime.utils import (
    _build_object_diff,
    _candidate_string_list,
    _non_empty_candidate_text,
    _payload_text,
)
from core.runtime.types import (
    CanonicalObjectSnapshot,
    DerivedArtifactSnapshot,
    JSONValue,
    OutlineToPlotWorkbenchRequest,
    OutlineToPlotWorkbenchResult,
    PlotToEventWorkbenchRequest,
    PlotToEventWorkbenchResult,
    EventToSceneWorkbenchRequest,
    EventToSceneWorkbenchResult,
    SceneToChapterWorkbenchRequest,
    SceneToChapterWorkbenchResult,
    ReadObjectRequest,
    ServiceMutationRequest,
    WorkspaceSnapshotRequest,
    WorkspaceObjectSummary,
)

if TYPE_CHECKING:
    from core.runtime.storage import CanonicalStorage
    from core.runtime.services.ai_config_service import AIConfigService
    from features.pipeline.service import PipelineGenerationService

JSONObject = dict[str, JSONValue]


class WorkbenchService:
    """Service for content generation workbench operations."""

    def __init__(
        self,
        storage: CanonicalStorage,
        ai_config_service: AIConfigService,
        pipeline_service: PipelineGenerationService,
    ):
        self._storage = storage
        self._ai_config_service = ai_config_service
        self._pipeline_service = pipeline_service

    def generate_outline_to_plot_workbench(
        self,
        request: OutlineToPlotWorkbenchRequest,
    ) -> OutlineToPlotWorkbenchResult:
        """Generate plot nodes from outline node."""
        self._pipeline_service.ai_provider = self._ai_config_service.get_active_ai_provider()
        return self._pipeline_service.generate_outline_to_plot_workbench(
            request, generate_plot_nodes_func=self._generate_plot_nodes_with_ai
        )

    def generate_plot_to_event_workbench(
        self,
        request: PlotToEventWorkbenchRequest,
    ) -> PlotToEventWorkbenchResult:
        """Generate events from plot node."""
        self._pipeline_service.ai_provider = self._ai_config_service.get_active_ai_provider()
        return self._pipeline_service.generate_plot_to_event_workbench(request)

    def generate_event_to_scene_workbench(
        self,
        request: EventToSceneWorkbenchRequest,
    ) -> EventToSceneWorkbenchResult:
        """Generate scenes from event."""
        self._pipeline_service.ai_provider = self._ai_config_service.get_active_ai_provider()
        return self._pipeline_service.generate_event_to_scene_workbench(request)

    def generate_scene_to_chapter_workbench(
        self,
        request: SceneToChapterWorkbenchRequest,
    ) -> SceneToChapterWorkbenchResult:
        """Generate chapter from scene."""
        self._pipeline_service.ai_provider = self._ai_config_service.get_active_ai_provider()
        return self._pipeline_service.generate_scene_to_chapter_workbench(request)

    # Helper methods for AI generation

    def _generate_plot_nodes_with_ai(
        self,
        outline_node: CanonicalObjectSnapshot,
        novel_context: JSONObject,
        skills: tuple[WorkspaceObjectSummary, ...],
        parent_outline: CanonicalObjectSnapshot | None,
    ) -> list[JSONObject]:
        """Generate plot nodes from outline using AI."""
        ai_client = self._ai_config_service.get_active_ai_provider()
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
        ai_client = self._ai_config_service.get_active_ai_provider()
        if ai_client is None:
            raise AIProviderError("未配置可用的 AI 提供商。请先在设置页保存并激活模型。")

        try:
            skill_payloads = [skill.payload for skill in skills]
            messages = build_plot_to_event_prompt(
                plot_node=plot_node.payload,
                novel_context=novel_context,
                outline_context=outline_context.payload if outline_context else None,
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
                                "characters_involved": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
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
    ) -> list[JSONObject]:
        """Generate scenes from event using AI."""
        ai_client = self._ai_config_service.get_active_ai_provider()
        if ai_client is None:
            raise AIProviderError("未配置可用的 AI 提供商。请先在设置页保存并激活模型。")

        try:
            skill_payloads = [skill.payload for skill in skills]
            messages = build_event_to_scene_prompt(
                event=event.payload,
                novel_context=novel_context,
                plot_context=plot_context.payload if plot_context else None,
                skills=skill_payloads,
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
                                "summary": {"type": "string"},
                                "sequence_order": {"type": "integer"},
                                "location": {"type": "string"},
                                "characters": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["title", "summary", "sequence_order"],
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
