"""Diagnosis service for project health analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ai import AIProviderClient
    from core.runtime.storage import JSONValue
    from core.runtime.types import WorkspaceSnapshotRequest, WorkspaceSnapshotResult

JSONObject = dict[str, "JSONValue"]


class DiagnosisService:
    """Service for diagnosing project health and suggesting improvements."""

    def __init__(self, get_active_ai_provider_func, get_workspace_snapshot_func):
        self._get_active_ai_provider = get_active_ai_provider_func
        self._get_workspace_snapshot = get_workspace_snapshot_func

    def diagnose_project(self, project_id: str, novel_id: str | None) -> JSONObject:
        """
        Run intelligent diagnosis on the project.

        Returns a diagnosis report with issues, suggested actions, and health score.
        """
        from core.ai.diagnosis import IntelligentDiagnoser, DiagnosisRequest

        # Get workspace snapshot
        workspace = self._get_workspace_snapshot(
            WorkspaceSnapshotRequest(project_id=project_id, novel_id=novel_id)
        )

        # Check if AI is available for intelligent diagnosis
        ai_client = self._get_active_ai_provider()

        if ai_client is not None:
            diagnoser = IntelligentDiagnoser(ai_client)
            request = DiagnosisRequest(
                project_id=project_id,
                novel_id=novel_id,
                workspace_snapshot=workspace,
            )
            report = diagnoser.diagnose(request)

            return {
                "health_score": report.overall_health_score,
                "quality_level": report.quality_assessment.get("level", "unknown"),
                "issues": [
                    {
                        "severity": issue.severity,
                        "category": issue.category,
                        "title": issue.title,
                        "description": issue.description,
                        "suggested_action": issue.suggested_action,
                    }
                    for issue in report.issues_found
                ],
                "suggested_actions": report.suggested_actions,
                "next_priority": report.next_priority,
                "ai_powered": True,
            }
        else:
            # Fallback to basic analysis without AI
            return self._basic_diagnosis(project_id, novel_id, workspace)

    def _basic_diagnosis(
        self, project_id: str, novel_id: str | None, workspace: "WorkspaceSnapshotResult"
    ) -> JSONObject:
        """Basic diagnosis without AI - simple rule-based analysis."""
        issues: list[JSONObject] = []
        suggested_actions: list[JSONObject] = []

        # Count objects by family
        counts: dict[str, int] = {}
        for obj in workspace.canonical_objects:
            counts[obj.family] = counts.get(obj.family, 0) + 1

        # Check for structural gaps
        if counts.get("outline_node", 0) > 0 and counts.get("plot_node", 0) == 0:
            issues.append(
                {
                    "severity": "warning",
                    "category": "structure",
                    "title": "大纲节点没有对应的剧情节点",
                    "description": "项目中存在大纲节点，但尚未创建剧情节点。",
                    "suggested_action": "outline_to_plot",
                }
            )
            suggested_actions.append(
                {
                    "title": "扩展大纲为剧情",
                    "description": "使用大纲→剧情工作台进行扩展",
                    "route": "/workbench",
                    "priority": "warning",
                }
            )

        if counts.get("scene", 0) > 0 and counts.get("chapter_artifact", 0) == 0:
            issues.append(
                {
                    "severity": "info",
                    "category": "completeness",
                    "title": "场景尚未写成章节",
                    "description": f"项目中有 {counts['scene']} 个场景，但尚未生成章节正文。",
                    "suggested_action": "scene_to_chapter",
                }
            )
            suggested_actions.append(
                {
                    "title": "写作章节正文",
                    "description": "使用场景→章节工作台进行写作",
                    "route": "/workbench",
                    "priority": "info",
                }
            )

        # Add provider configuration action if no AI
        if self._get_active_ai_provider() is None:
            suggested_actions.append(
                {
                    "title": "配置 AI 提供者",
                    "description": "配置 AI 提供者以启用智能内容生成",
                    "route": "/settings",
                    "priority": "info",
                }
            )

        # Calculate basic health score
        health_score = 100.0
        health_score -= len([i for i in issues if i["severity"] == "error"]) * 20
        health_score -= len([i for i in issues if i["severity"] == "warning"]) * 10
        health_score -= len([i for i in issues if i["severity"] == "info"]) * 5
        health_score = max(0.0, min(100.0, health_score))

        return {
            "health_score": health_score,
            "quality_level": "basic",
            "issues": issues,
            "suggested_actions": suggested_actions,
            "next_priority": suggested_actions[0]["title"] if suggested_actions else None,
            "ai_powered": False,
        }
