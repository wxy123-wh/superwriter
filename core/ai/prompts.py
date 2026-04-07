from __future__ import annotations

import json
from typing import Any


JSONObject = dict[str, Any]
MessageList = list[dict[str, str]]


def _build_system_message(content: str) -> dict[str, str]:
    return {"role": "system", "content": content}


def _build_user_message(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def _format_skills(skills: list[JSONObject]) -> str:
    if not skills:
        return "No specific skills defined."
    return "\n".join(
        f"- {skill.get('name', 'Unnamed')}: {skill.get('instruction', '')[:200]}"
        for skill in skills
    )


def _format_style_rules(style_rules: list[JSONObject]) -> str:
    if not style_rules:
        return "No specific style rules defined."
    return "\n".join(
        f"- {rule.get('rule', '')[:200]}"
        for rule in style_rules
    )


def _format_canonical_facts(facts: list[JSONObject]) -> str:
    if not facts:
        return "No canonical facts established."
    return "\n".join(
        f"- {fact.get('subject', 'Unknown')}: {fact.get('statement', '')[:200]}"
        for fact in facts
    )


def build_outline_to_plot_prompt(
    outline_node: JSONObject,
    novel_context: JSONObject,
    skills: list[JSONObject],
    parent_outline: JSONObject | None = None,
) -> MessageList:
    """
    Build a prompt for expanding an outline node into plot nodes.

    Args:
        outline_node: The outline node to expand
        novel_context: Novel-level context (title, premise, etc.)
        skills: Active skills for this operation
        parent_outline: Optional parent outline node for context

    Returns:
        List of messages for the AI API
    """
    system_content = """You are a story structure expert. Your task is to expand a high-level outline into detailed plot nodes.

Each plot node should:
- Represent a discrete narrative unit that advances the story
- Have a clear beginning, middle, and end
- Maintain continuity with parent and sibling nodes
- Support the overall story arc

Respond with a JSON object containing a "plot_nodes" array, where each node has:
- title: Short descriptive title
- summary: 2-3 sentence summary of what happens
- sequence_order: Integer position in sequence
- notes: Any additional context or concerns"""

    user_content = f"""# Novel Context
Title: {novel_context.get('title', 'Untitled')}
Premise: {novel_context.get('premise', 'Not specified')}
Genre: {novel_context.get('genre', 'Not specified')}

# Skills to Apply
{_format_skills(skills)}

# Parent Outline (if applicable)
{parent_outline.get('title', 'None') if parent_outline else 'None'}
{parent_outline.get('summary', '') if parent_outline else ''}

# Outline Node to Expand
Title: {outline_node.get('title', 'Untitled')}
Summary: {outline_node.get('summary', '')}
Notes: {outline_node.get('notes', '')}

# Task
Expand this outline node into 3-7 plot nodes. Each plot node should represent a meaningful step in the narrative progression."""

    return [
        _build_system_message(system_content),
        _build_user_message(user_content),
    ]


def build_plot_to_event_prompt(
    plot_node: JSONObject,
    novel_context: JSONObject,
    outline_context: JSONObject,
    skills: list[JSONObject],
) -> MessageList:
    """
    Build a prompt for breaking down a plot node into events.

    Args:
        plot_node: The plot node to break down
        novel_context: Novel-level context
        outline_context: The parent outline node
        skills: Active skills for this operation

    Returns:
        List of messages for the AI API
    """
    system_content = """You are a narrative analyst. Your task is to break down a plot node into specific events.

Each event should:
- Be a discrete, observable occurrence
- Have a clear impact on character or plot
- Be ordered chronologically or logically
- Support the plot node's purpose

Respond with a JSON object containing an "events" array, where each event has:
- title: Short descriptive title
- description: What happens in this event
- sequence_order: Integer position
- location: Where it takes place (if known)
- characters_involved: List of character names (if applicable)"""

    user_content = f"""# Novel Context
Title: {novel_context.get('title', 'Untitled')}

# Parent Outline
{outline_context.get('title', 'Untitled')}: {outline_context.get('summary', '')}

# Skills to Apply
{_format_skills(skills)}

# Plot Node to Break Down
Title: {plot_node.get('title', 'Untitled')}
Summary: {plot_node.get('summary', '')}
Notes: {plot_node.get('notes', '')}

# Task
Break this plot node into 3-10 specific events. Each event should be something that actually happens in the story world."""

    return [
        _build_system_message(system_content),
        _build_user_message(user_content),
    ]


def build_event_to_scene_prompt(
    event: JSONObject,
    novel_context: JSONObject,
    plot_context: JSONObject,
    skills: list[JSONObject],
    characters: list[JSONObject],
    settings: list[JSONObject],
) -> MessageList:
    """
    Build a prompt for expanding an event into one or more scenes.

    Args:
        event: The event to expand
        novel_context: Novel-level context
        plot_context: The parent plot node
        skills: Active skills for this operation
        characters: Available characters
        settings: Available settings

    Returns:
        List of messages for the AI API
    """
    system_content = """You are a scene architect. Your task is to expand an event into one or more fully-realized scenes.

Each scene should:
- Have a clear setting and time
- Include specific character actions and dialogue
- Build tension or advance character arcs
- Have a purpose within the event

Respond with a JSON object containing a "scenes" array, where each scene has:
- title: Scene title
- setting: Where and when the scene takes place
- pov_character: Main point-of-view character (if applicable)
- characters_present: List of characters in the scene
- scene_summary: What happens in the scene
- beat_breakdown: Key narrative beats (3-5 items)"""

    user_content = f"""# Novel Context
Title: {novel_context.get('title', 'Untitled')}

# Parent Plot
{plot_context.get('title', 'Untitled')}: {plot_context.get('summary', '')}

# Skills to Apply
{_format_skills(skills)}

# Available Characters
{chr(10).join(f"- {c.get('name', 'Unknown')}: {c.get('role', '')[:100]}" for c in characters[:10]) if characters else 'No characters defined yet.'}

# Available Settings
{chr(10).join(f"- {s.get('name', 'Unknown')}: {s.get('description', '')[:100]}" for s in settings[:5]) if settings else 'No settings defined yet.'}

# Event to Expand
Title: {event.get('title', 'Untitled')}
Description: {event.get('description', '')}
Notes: {event.get('notes', '')}

# Task
Expand this event into 1-3 scenes. Each scene should be a distinct time/place combination where meaningful action occurs."""

    return [
        _build_system_message(system_content),
        _build_user_message(user_content),
    ]


def build_scene_to_chapter_prompt(
    scene: JSONObject,
    novel_context: JSONObject,
    style_rules: list[JSONObject],
    skills: list[JSONObject],
    canonical_facts: list[JSONObject],
    previous_chapter: JSONObject | None = None,
) -> MessageList:
    """
    Build a prompt for converting a scene into prose chapter.

    Args:
        scene: The scene to convert to prose
        novel_context: Novel-level context
        style_rules: Active style rules
        skills: Active skills (especially scene_to_chapter scoped)
        canonical_facts: Established facts to maintain consistency
        previous_chapter: Optional previous chapter for continuity

    Returns:
        List of messages for the AI API
    """
    system_content = """You are a prose writer specializing in novel fiction. Your task is to write a chapter based on a scene outline.

Your chapter should:
- Use vivid, sensory prose appropriate to the genre
- Maintain consistent POV and voice
- Include meaningful dialogue that advances plot or character
- Balance showing vs. telling
- Honor all style rules and skill instructions
- Maintain consistency with established facts

Write approximately 1500-2500 words unless otherwise specified.

Respond with a JSON object containing:
- chapter_title: Title for the chapter
- chapter_body: The full prose content of the chapter
- word_count: Approximate word count
- notes: Any concerns or suggestions for revision"""

    # Build style guidance
    style_guidance = []
    if style_rules:
        style_guidance.append("# Style Rules")
        style_guidance.append(_format_style_rules(style_rules))

    if skills:
        style_guidance.append("# Skills")
        style_guidance.append(_format_skills(skills))

    # Build fact guidance
    fact_guidance = ""
    if canonical_facts:
        fact_guidance = f"""# Established Facts to Maintain
{_format_canonical_facts(canonical_facts)}"""

    # Build previous chapter context
    previous_context = ""
    if previous_chapter:
        previous_context = f"""
# Previous Chapter Context
Title: {previous_chapter.get('chapter_title', 'Untitled')}
Last line: {previous_chapter.get('ending_note', 'Not available')}"""

    user_content = f"""# Novel Context
Title: {novel_context.get('title', 'Untitled')}
Genre: {novel_context.get('genre', 'Not specified')}
Voice: {novel_context.get('voice', 'Third person limited')}

{chr(10).join(style_guidance)}

{fact_guidance}

{previous_context}

# Scene to Write
Title: {scene.get('title', 'Untitled')}
Summary: {scene.get('summary', '')}

Setting: {scene.get('setting', 'Not specified')}
Time: {scene.get('time', 'Not specified')}

POV Character: {scene.get('pov_character', 'Not specified')}
Characters Present: {', '.join(scene.get('characters_present', []))}

Scene Beats:
{chr(10).join(f"- {beat}" for beat in scene.get('beat_breakdown', []))}

Notes: {scene.get('notes', '')}

# Task
Write this scene as a complete chapter of prose. Focus on bringing the scene beats to life through action, dialogue, and sensory detail."""

    return [
        _build_system_message(system_content),
        _build_user_message(user_content),
    ]


def build_chapter_revision_prompt(
    current_chapter: JSONObject,
    revision_instructions: str,
    scene_context: JSONObject,
    style_rules: list[JSONObject],
    skills: list[JSONObject],
    canonical_facts: list[JSONObject],
) -> MessageList:
    """
    Build a prompt for revising an existing chapter.

    Args:
        current_chapter: The chapter content to revise
        revision_instructions: Specific revision instructions
        scene_context: The source scene for reference
        style_rules: Active style rules
        skills: Active skills
        canonical_facts: Established facts

    Returns:
        List of messages for the AI API
    """
    system_content = """You are a revision specialist. Your task is to revise a chapter based on specific instructions while maintaining quality and consistency.

When revising:
- Address all specific revision instructions
- Maintain the chapter's core purpose and emotional beats
- Improve prose quality where possible
- Ensure consistency with style rules and canonical facts
- Preserve word count approximately unless instructed otherwise

Respond with a JSON object containing:
- chapter_title: (possibly updated) title
- chapter_body: The revised prose
- word_count: Approximate word count
- changes_made: Summary of key changes made
- notes: Any concerns or suggestions"""

    user_content = f"""# Revision Instructions
{revision_instructions}

# Current Chapter
Title: {current_chapter.get('chapter_title', 'Untitled')}
Word Count: {current_chapter.get('word_count', 'Unknown')}

Content:
{current_chapter.get('chapter_body', '')[:5000]}...

# Source Scene Reference
{scene_context.get('title', 'Untitled')}: {scene_context.get('summary', '')}

# Style Rules
{_format_style_rules(style_rules)}

# Skills
{_format_skills(skills)}

# Canonical Facts
{_format_canonical_facts(canonical_facts)}

# Task
Revise this chapter according to the instructions provided."""

    return [
        _build_system_message(system_content),
        _build_user_message(user_content),
    ]


def build_partial_revision_prompt(
    section_content: str,
    section_type: str,
    revision_instruction: str,
    context: JSONObject,
) -> str:
    """Build a prompt for partial revision of a specific section.

    Args:
        section_content: The content of the section to revise
        section_type: The type of section (paragraph, scene, chapter, etc.)
        revision_instruction: The user's revision instruction
        context: Additional context for the revision

    Returns:
        Prompt string for AI generation
    """
    context_parts = []

    # Add context information
    if context.get("scene_title"):
        context_parts.append(f"Scene: {context['scene_title']}")
    if context.get("characters"):
        chars = ", ".join(context.get("characters", []))
        context_parts.append(f"Characters: {chars}")
    if context.get("setting"):
        context_parts.append(f"Setting: {context['setting']}")

    context_str = "\n".join(context_parts) if context_parts else "No additional context"

    prompt = f"""# Partial Revision Request

You are revising a specific {section_type} of a novel. Rewrite the section according to the user's instruction while maintaining consistency with the surrounding content.

## Section to Revise
{section_content}

## Revision Instruction
{revision_instruction}

## Context
{context_str}

## Guidelines
- Maintain the tone and style of the original
- Keep approximately the same length unless instructed otherwise
- Ensure continuity with adjacent content
- Preserve any character voice or dialogue patterns

## Task
Rewrite the {section_type} above according to the revision instruction. Respond only with the revised content, no explanations or commentary."""

    return prompt


def build_diagnosis_prompt(
    workspace_summary: dict,
    focus_areas: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build a prompt for AI-powered structural diagnosis of a novel project.

    Args:
        workspace_summary: Summary of workspace state (object counts, chain gaps, etc.)
        focus_areas: Optional specific areas to focus analysis on

    Returns:
        List of messages for the AI API
    """
    focus_text = ""
    if focus_areas:
        focus_text = "请特别关注以下方面：\n" + "\n".join(f"- {area}" for area in focus_areas)

    system_content = f"""你是一位专业的小说结构分析师。你的任务是分析小说项目的整体结构，
识别叙事链条中的缺口、节奏问题和结构性弱点。

你需要从以下维度进行分析：
1. 叙事链条完整性：大纲→剧情→事件→场景→章节 是否有断裂
2. 节奏与平衡：各层级的数量分布是否合理，是否有过度密集或稀疏的区域
3. 内容深度：是否有大纲过于笼统、剧情缺少转折、事件缺乏细节等问题
4. 推进优先级：作者应该优先处理什么

请用中文回答。以 JSON 格式返回分析结果。"""

    workspace_text = json.dumps(workspace_summary, ensure_ascii=False, indent=2) if isinstance(workspace_summary, dict) else str(workspace_summary)

    user_content = f"""# 项目工作区概览

{workspace_text}

{focus_text}

请分析这个小说项目的结构状况，返回 JSON 格式的结果：
{{
    "structural_issues": [
        {{
            "severity": "error/warning/info",
            "category": "structure/rhythm/depth",
            "title": "问题标题",
            "description": "问题描述",
            "suggested_action": "建议的操作"
        }}
    ],
    "quality_assessment": {{
        "narrative_chain_completeness": 0-100,
        "content_depth_score": 0-100,
        "overall_assessment": "一句话总结"
    }},
    "next_priority": "最优先应该做的事情"
}}"""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def build_consistency_check_prompt(
    canonical_objects: list[dict],
    fact_records: list[dict],
) -> list[dict[str, str]]:
    """Build a prompt for AI-powered consistency checking.

    Args:
        canonical_objects: Key canonical objects (characters, settings, etc.)
        fact_records: Established facts and state records

    Returns:
        List of messages for the AI API
    """
    system_content = """你是一位小说连续性审核专家。你的任务是检查小说项目中的人物设定、世界规则和已建立事实之间是否存在矛盾或不一致。

你需要关注：
1. 人物属性是否前后矛盾
2. 设定/地点描述是否一致
3. 已建立的事实是否与后续内容冲突
4. 时间线是否合理

请用中文回答。以 JSON 格式返回检查结果。"""

    objects_text = json.dumps(canonical_objects, ensure_ascii=False, indent=2)
    facts_text = json.dumps(fact_records, ensure_ascii=False, indent=2)

    user_content = f"""# 项目核心对象

{objects_text}

# 已建立的事实记录

{facts_text}

请检查上述内容的一致性，返回 JSON 格式的结果：
{{
    "consistency_issues": [
        {{
            "severity": "error/warning/info",
            "category": "character/setting/timeline/fact",
            "title": "问题标题",
            "description": "矛盾的详细描述",
            "affected_objects": ["相关对象ID"]
        }}
    ],
    "overall_consistency": "一致/基本一致/存在问题/严重矛盾"
}}"""

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


__all__ = [
    "build_outline_to_plot_prompt",
    "build_plot_to_event_prompt",
    "build_event_to_scene_prompt",
    "build_scene_to_chapter_prompt",
    "build_chapter_revision_prompt",
    "build_partial_revision_prompt",
    "build_diagnosis_prompt",
    "build_consistency_check_prompt",
]
