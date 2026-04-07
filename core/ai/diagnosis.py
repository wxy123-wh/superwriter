from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

JSONObject = dict[str, Any]

_ACTION_TITLES = {
    "outline_to_plot": "扩展大纲为剧情",
    "plot_to_event": "分解剧情为事件",
    "event_to_scene": "展开事件为场景",
    "scene_to_chapter": "写作章节正文",
    "review_desk": "处理审核提议",
    "create_character": "创建人物对象",
    "create_setting": "创建场景设定",
}

_ACTION_ROUTES = {
    "outline_to_plot": "/workbench",
    "plot_to_event": "/workbench",
    "event_to_scene": "/workbench",
    "scene_to_chapter": "/workbench",
    "review_desk": "/review-desk",
    "create_character": "/command-center",
    "create_setting": "/command-center",
}


@dataclass(frozen=True, slots=True)
class DiagnosisRequest:
    """Request for intelligent project diagnosis."""

    project_id: str
    novel_id: str | None
    workspace_snapshot: Any  # WorkspaceSnapshotResult


@dataclass(frozen=True, slots=True)
class DiagnosisIssue:
    """A specific issue identified in the project."""

    severity: str  # "error", "warning", "info"
    category: str  # "structure", "consistency", "completeness", "quality"
    title: str
    description: str
    affected_objects: list[str]
    suggested_action: str | None


@dataclass(frozen=True, slots=True)
class DiagnosisReport:
    """Report from intelligent project analysis."""

    issues_found: list[DiagnosisIssue]
    suggested_actions: list[JSONObject]
    quality_assessment: JSONObject
    consistency_warnings: list[JSONObject]
    overall_health_score: float  # 0-100
    next_priority: str | None


class IntelligentDiagnoser:
    """
    AI-powered project analysis and diagnosis.

    Analyzes the project state and provides intelligent suggestions
    for next steps, quality improvements, and consistency checks.
    """

    def __init__(self, ai_client: Any):  # AIProviderClient
        """Initialize with an AI client for intelligent analysis."""
        self._ai_client = ai_client

    def diagnose(self, request: DiagnosisRequest) -> DiagnosisReport:
        """
        Perform a comprehensive diagnosis of the project.

        Uses rule-based analysis first, then supplements with AI analysis
        when an AI provider is configured.

        Args:
            request: The diagnosis request with workspace snapshot

        Returns:
            A comprehensive diagnosis report
        """
        # Rule-based analysis (always runs)
        structural_issues = self._analyze_structure(request)
        consistency_issues = self._check_consistency(request)
        completeness_issues = self._check_completeness(request)

        all_issues = structural_issues + consistency_issues + completeness_issues

        # AI-powered analysis (when provider is available)
        if self._ai_client is not None:
            ai_issues = self._ai_analyze_structure(request)
            if ai_issues:
                all_issues = self._merge_issues(all_issues, ai_issues)

            ai_consistency = self._ai_check_consistency(request)
            if ai_consistency:
                consistency_issues = consistency_issues + ai_consistency

        # Generate quality assessment
        quality_assessment = self._assess_quality(request, all_issues)

        # Suggest next actions
        suggested_actions = self._suggest_actions(request, all_issues)

        # Calculate overall health score
        health_score = self._calculate_health_score(request, all_issues)

        return DiagnosisReport(
            issues_found=all_issues,
            suggested_actions=suggested_actions,
            quality_assessment=quality_assessment,
            consistency_warnings=consistency_issues,
            overall_health_score=health_score,
            next_priority=suggested_actions[0].get("title") if suggested_actions else None,
        )

    # --- AI-powered analysis methods ---

    def _build_workspace_summary(self, request: DiagnosisRequest) -> dict:
        """Build a serializable workspace summary for AI analysis."""
        workspace = request.workspace_snapshot
        canonical_objects = list(workspace.canonical_objects) if hasattr(workspace, "canonical_objects") else []

        counts: dict[str, int] = {}
        objects_by_family: dict[str, list[dict]] = {}
        for obj in canonical_objects:
            family = obj.family if hasattr(obj, "family") else "unknown"
            counts[family] = counts.get(family, 0) + 1
            if family not in objects_by_family:
                objects_by_family[family] = []
            payload = obj.payload if hasattr(obj, "payload") else {}
            title = payload.get("title", payload.get("name", obj.object_id if hasattr(obj, "object_id") else ""))
            objects_by_family[family].append({"id": getattr(obj, "object_id", ""), "title": str(title)})

        return {
            "project_id": request.project_id,
            "novel_id": request.novel_id,
            "object_counts": counts,
            "objects_by_family": objects_by_family,
            "total_objects": len(canonical_objects),
        }

    def _ai_analyze_structure(self, request: DiagnosisRequest) -> list[DiagnosisIssue]:
        """Use AI to analyze narrative structure, pacing, and gaps."""
        try:
            from core.ai.prompts import build_diagnosis_prompt

            summary = self._build_workspace_summary(request)
            focus_areas = ["叙事链条完整性", "节奏与平衡", "内容深度", "推进优先级"]
            messages = build_diagnosis_prompt(summary, focus_areas)

            result = self._ai_client.generate_structured(
                messages=messages,
                output_schema={"type": "object"},
            )

            if not isinstance(result, dict):
                return []

            issues: list[DiagnosisIssue] = []
            raw_issues = result.get("structural_issues", [])
            for item in raw_issues:
                if not isinstance(item, dict):
                    continue
                severity = item.get("severity", "info")
                if severity not in ("error", "warning", "info"):
                    severity = "info"
                issues.append(DiagnosisIssue(
                    severity=severity,
                    category=item.get("category", "structure"),
                    title=str(item.get("title", "AI identified issue")),
                    description=str(item.get("description", "")),
                    affected_objects=item.get("affected_objects", []),
                    suggested_action=item.get("suggested_action"),
                ))

            return issues

        except Exception:
            return []

    def _ai_check_consistency(self, request: DiagnosisRequest) -> list[DiagnosisIssue]:
        """Use AI to cross-validate characters, settings, and established facts."""
        try:
            from core.ai.prompts import build_consistency_check_prompt

            workspace = request.workspace_snapshot
            canonical_objects = list(workspace.canonical_objects) if hasattr(workspace, "canonical_objects") else []

            # Extract characters, settings, and fact records for AI analysis
            characters = [
                obj.payload for obj in canonical_objects
                if hasattr(obj, "family") and obj.family == "character" and hasattr(obj, "payload")
            ]
            settings = [
                obj.payload for obj in canonical_objects
                if hasattr(obj, "family") and obj.family == "setting" and hasattr(obj, "payload")
            ]
            facts = [
                obj.payload for obj in canonical_objects
                if hasattr(obj, "family") and obj.family == "fact_state_record" and hasattr(obj, "payload")
            ]

            if not characters and not settings and not facts:
                return []

            messages = build_consistency_check_prompt(characters[:10], facts[:20])

            result = self._ai_client.generate_structured(
                messages=messages,
                output_schema={"type": "object"},
            )

            if not isinstance(result, dict):
                return []

            issues: list[DiagnosisIssue] = []
            raw_issues = result.get("consistency_issues", [])
            for item in raw_issues:
                if not isinstance(item, dict):
                    continue
                severity = item.get("severity", "info")
                if severity not in ("error", "warning", "info"):
                    severity = "info"
                issues.append(DiagnosisIssue(
                    severity=severity,
                    category=item.get("category", "consistency"),
                    title=str(item.get("title", "AI identified inconsistency")),
                    description=str(item.get("description", "")),
                    affected_objects=item.get("affected_objects", []),
                    suggested_action=None,
                ))

            return issues

        except Exception:
            return []

    @staticmethod
    def _merge_issues(
        existing: list[DiagnosisIssue],
        new_issues: list[DiagnosisIssue],
    ) -> list[DiagnosisIssue]:
        """Merge AI-identified issues with rule-based issues, deduplicating by title."""
        existing_titles = {issue.title for issue in existing}
        merged = list(existing)
        for issue in new_issues:
            if issue.title not in existing_titles:
                merged.append(issue)
                existing_titles.add(issue.title)
        return merged

    def _analyze_structure(self, request: DiagnosisRequest) -> list[DiagnosisIssue]:
        """Analyze the structural integrity of the project."""
        issues: list[DiagnosisIssue] = []

        workspace = request.workspace_snapshot
        canonical_objects = list(workspace.canonical_objects) if hasattr(workspace, "canonical_objects") else []

        # Count objects by family
        counts: dict[str, int] = {}
        for obj in canonical_objects:
            family = obj.family if hasattr(obj, "family") else "unknown"
            counts[family] = counts.get(family, 0) + 1

        # Check for orphaned objects (no parent references)
        # This is a simplified check; a full implementation would trace relationships

        # Check for broken narrative chain
        if counts.get("outline_node", 0) > 0 and counts.get("plot_node", 0) == 0:
            issues.append(DiagnosisIssue(
                severity="warning",
                category="structure",
                title="大纲节点没有对应的剧情节点",
                description="项目中存在大纲节点，但尚未创建剧情节点。考虑使用大纲→剧情工作台进行扩展。",
                affected_objects=[f"{counts['outline_node']} outline_nodes"],
                suggested_action="outline_to_plot",
            ))

        if counts.get("plot_node", 0) > 0 and counts.get("event", 0) == 0:
            issues.append(DiagnosisIssue(
                severity="warning",
                category="structure",
                title="剧情节点没有对应的事件",
                description="项目中存在剧情节点，但尚未创建事件。考虑使用剧情→事件工作台进行分解。",
                affected_objects=[f"{counts['plot_node']} plot_nodes"],
                suggested_action="plot_to_event",
            ))

        if counts.get("event", 0) > 0 and counts.get("scene", 0) == 0:
            issues.append(DiagnosisIssue(
                severity="warning",
                category="structure",
                title="事件没有对应的场景",
                description="项目中存在事件，但尚未创建场景。考虑使用事件→场景工作台进行展开。",
                affected_objects=[f"{counts['event']} events"],
                suggested_action="event_to_scene",
            ))

        if counts.get("scene", 0) > 0:
            chapter_count = counts.get("chapter_artifact", 0)
            if chapter_count == 0:
                issues.append(DiagnosisIssue(
                    severity="info",
                    category="completeness",
                    title="场景尚未写成章节",
                    description=f"项目中有 {counts['scene']} 个场景，但尚未生成章节正文。",
                    affected_objects=[f"{counts['scene']} scenes"],
                    suggested_action="scene_to_chapter",
                ))

        return issues

    def _check_consistency(self, request: DiagnosisRequest) -> list[DiagnosisIssue]:
        """Check for consistency issues in the project."""
        issues: list[DiagnosisIssue] = []

        # Check for pending proposals that might indicate conflicts
        workspace = request.workspace_snapshot
        proposals = list(workspace.review_proposals) if hasattr(workspace, "review_proposals") else []

        if len(proposals) > 5:
            issues.append(DiagnosisIssue(
                severity="warning",
                category="consistency",
                title=f"有 {len(proposals)} 个待审核提议",
                description="大量待审核提议可能表明需要处理的结构性变更。请访问审核台进行审查。",
                affected_objects=[],
                suggested_action="review_desk",
            ))

        return issues

    def _check_completeness(self, request: DiagnosisRequest) -> list[DiagnosisIssue]:
        """Check for completeness gaps in the project."""
        issues: list[DiagnosisIssue] = []

        workspace = request.workspace_snapshot
        canonical_objects = list(workspace.canonical_objects) if hasattr(workspace, "canonical_objects") else []

        counts: dict[str, int] = {}
        for obj in canonical_objects:
            family = obj.family if hasattr(obj, "family") else "unknown"
            counts[family] = counts.get(family, 0) + 1

        # Check for missing novel-level configuration
        if counts.get("character", 0) == 0:
            issues.append(DiagnosisIssue(
                severity="info",
                category="completeness",
                title="尚未创建人物对象",
                description="人物对象可以帮助追踪角色发展。考虑添加主要人物。",
                affected_objects=[],
                suggested_action="create_character",
            ))

        if counts.get("setting", 0) == 0:
            issues.append(DiagnosisIssue(
                severity="info",
                category="completeness",
                title="尚未创建场景设定对象",
                description="场景设定对象可以帮助保持世界一致性。考虑添加主要地点。",
                affected_objects=[],
                suggested_action="create_setting",
            ))

        return issues

    def _assess_quality(self, request: DiagnosisRequest, issues: list[DiagnosisIssue]) -> JSONObject:
        """Assess the overall quality of the project."""
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        info_count = sum(1 for i in issues if i.severity == "info")

        # Determine quality level
        if error_count > 0:
            quality_level = "需要修复"
            quality_color = "danger"
        elif warning_count > 3:
            quality_level = "需要注意"
            quality_color = "warning"
        elif warning_count > 0 or info_count > 2:
            quality_level = "良好"
            quality_color = "info"
        else:
            quality_level = "优秀"
            quality_color = "success"

        return {
            "level": quality_level,
            "color": quality_color,
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "total_issues": len(issues),
        }

    def _suggest_actions(self, request: DiagnosisRequest, issues: list[DiagnosisIssue]) -> list[JSONObject]:
        """Suggest prioritized actions based on diagnosis."""
        actions: list[JSONObject] = []

        # Prioritize by severity
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        for issue in errors + warnings[:3]:
            if issue.suggested_action:
                actions.append({
                    "title": _ACTION_TITLES.get(issue.suggested_action, issue.title),
                    "description": issue.description,
                    "route": _ACTION_ROUTES.get(issue.suggested_action, "/command-center"),
                    "priority": issue.severity,
                })

        # Always add provider configuration if no AI is set
        if self._ai_client is None:
            actions.append({
                "title": "配置 AI 提供者",
                "description": "配置 AI 提供者以启用智能内容生成",
                "route": "/settings",
                "priority": "info",
            })

        return actions

    def _calculate_health_score(self, request: DiagnosisRequest, issues: list[DiagnosisIssue]) -> float:
        """Calculate an overall health score (0-100)."""
        base_score = 100.0

        # Deduct points for issues
        for issue in issues:
            if issue.severity == "error":
                base_score -= 20
            elif issue.severity == "warning":
                base_score -= 10
            elif issue.severity == "info":
                base_score -= 5

        return max(0.0, min(100.0, base_score))


__all__ = [
    "DiagnosisRequest",
    "DiagnosisIssue",
    "DiagnosisReport",
    "IntelligentDiagnoser",
]
