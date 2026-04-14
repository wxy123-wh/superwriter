"""Service for managing workbench iteration sessions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.ai.prompts import build_chapter_revision_prompt
from core.runtime.storage import CanonicalStorage, JSONObject

if TYPE_CHECKING:
    from core.runtime.services.ai_config_service import AIConfigService


class IterationService:
    """Service for managing workbench iteration sessions and candidate generation."""

    def __init__(
        self,
        storage: CanonicalStorage,
        ai_config_service: AIConfigService,
    ):
        """Initialize the iteration service.

        Args:
            storage: The canonical storage instance
            ai_config_service: The AI configuration service instance
        """
        self._storage = storage
        self._ai_config_service = ai_config_service

    def start_workbench_iteration(
        self,
        request,
        generate_candidates_callback,
    ):
        """Start a workbench iteration session.

        Creates a new session and generates initial candidates based on the
        parent object and workbench type.

        Args:
            request: The iteration request with project, novel, and parent object info
            generate_candidates_callback: Callback to generate initial candidates

        Returns:
            WorkbenchIterationResult with session ID and initial candidates
        """
        from core.runtime.application_services import WorkbenchIterationResult, CandidateDraftSnapshot

        # Create the session
        session_id = self._storage.create_workbench_session(
            project_id=request.project_id,
            novel_id=request.novel_id,
            workbench_type=request.workbench_type,
            parent_object_id=request.parent_object_id,
            actor=request.actor,
            source_surface=request.source_surface,
            source_ref=request.source_ref,
        )

        # Generate initial candidates based on workbench type
        initial_candidates = generate_candidates_callback(
            workbench_type=request.workbench_type,
            parent_object_id=request.parent_object_id,
            novel_id=request.novel_id,
            project_id=request.project_id,
            actor=request.actor,
            session_id=session_id,
            iteration_number=1,
        )

        return WorkbenchIterationResult(
            session_id=session_id,
            workbench_type=request.workbench_type,
            parent_object_id=request.parent_object_id,
            initial_candidates=tuple(
                CandidateDraftSnapshot(
                    draft_id=c["draft_id"],
                    session_id=c["session_id"],
                    iteration_number=c["iteration_number"],
                    payload=c["payload"],
                    generation_context=c["generation_context"],
                    is_selected=c["is_selected"],
                    created_at=c["created_at"],
                )
                for c in initial_candidates
            ),
            iteration_number=1,
        )

    def submit_workbench_feedback(
        self,
        request,
        generate_revision_callback,
    ):
        """Submit feedback on a candidate and generate new candidates.

        Records the feedback and generates revised candidates based on the feedback.

        Args:
            request: The feedback request with session, target draft, and feedback text
            generate_revision_callback: Callback to generate revision candidates

        Returns:
            WorkbenchFeedbackResult with new candidates and iteration info
        """
        from core.runtime.application_services import WorkbenchFeedbackResult, CandidateDraftSnapshot

        # Get the session to determine current iteration
        session = self._storage.get_workbench_session(request.session_id)
        if session is None:
            raise KeyError(f"Session not found: {request.session_id}")

        # Get the target draft to base revisions on (check before creating feedback)
        target_draft = self._storage.get_candidate_draft(request.target_draft_id)
        if target_draft is None:
            raise KeyError(f"Draft not found: {request.target_draft_id}")

        # Record the feedback
        feedback_id = self._storage.create_workbench_feedback(
            session_id=request.session_id,
            target_draft_id=request.target_draft_id,
            feedback_type=request.feedback_type,
            feedback_text=request.feedback_text,
            target_section=request.target_section,
            created_by=request.created_by,
        )

        # Increment iteration counter
        new_iteration = self._storage.increment_workbench_iteration(request.session_id)

        # Generate new candidates based on feedback
        new_candidates = generate_revision_callback(
            session=session,
            base_draft=target_draft,
            feedback=request,
            iteration_number=new_iteration,
        )

        return WorkbenchFeedbackResult(
            session_id=request.session_id,
            new_iteration_number=new_iteration,
            new_candidates=tuple(
                CandidateDraftSnapshot(
                    draft_id=c["draft_id"],
                    session_id=c["session_id"],
                    iteration_number=c["iteration_number"],
                    payload=c["payload"],
                    generation_context=c["generation_context"],
                    is_selected=c["is_selected"],
                    created_at=c["created_at"],
                )
                for c in new_candidates
            ),
            feedback_recorded_id=feedback_id,
        )

    def select_workbench_candidate(
        self,
        request,
        apply_to_canonical_callback,
    ):
        """Select a final candidate and complete the session.

        Marks the selected candidate and optionally applies it to the canonical object.

        Args:
            request: The selection request with session and selected draft ID
            apply_to_canonical_callback: Callback to apply candidate to canonical

        Returns:
            CandidateSelectionResult with selection details
        """
        from core.runtime.application_services import CandidateSelectionResult

        # Get the session
        session = self._storage.get_workbench_session(request.session_id)
        if session is None:
            raise KeyError(f"Session not found: {request.session_id}")

        # Get the selected draft
        selected_draft = self._storage.get_candidate_draft(request.selected_draft_id)
        if selected_draft is None:
            raise KeyError(f"Draft not found: {request.selected_draft_id}")

        # Mark as selected
        self._storage.select_candidate_draft(request.selected_draft_id)

        # Optionally apply to canonical
        mutation_applied = False
        mutation_record_id = None
        revision_id = None

        if request.apply_to_canonical:
            result = apply_to_canonical_callback(
                session=session,
                draft=selected_draft,
                actor=request.actor,
            )
            mutation_applied = result["applied"]
            mutation_record_id = result.get("mutation_record_id")
            revision_id = result.get("revision_id")

        # Complete the session
        self._storage.update_workbench_session_status(request.session_id, "completed")

        return CandidateSelectionResult(
            session_id=request.session_id,
            selected_draft_id=request.selected_draft_id,
            selected_payload=selected_draft["payload"],
            mutation_applied=mutation_applied,
            mutation_record_id=mutation_record_id,
            revision_id=revision_id,
            completion_status="completed",
        )

    def generate_iteration_candidates(
        self,
        workbench_type: str,
        parent_object_id: str,
        novel_id: str,
        project_id: str,
        actor: str,
        session_id: str,
        iteration_number: int,
        workbench_methods: dict,
    ) -> list[dict]:
        """Generate initial candidates for a workbench iteration session.

        Delegates to the appropriate workbench method based on type.

        Args:
            workbench_type: Type of workbench (outline_to_plot, scene_to_chapter, etc.)
            parent_object_id: ID of the parent object
            novel_id: ID of the novel
            project_id: ID of the project
            actor: Actor performing the operation
            session_id: Session ID
            iteration_number: Current iteration number
            workbench_methods: Dictionary mapping workbench types to generation methods

        Returns:
            List of candidate draft dictionaries
        """
        method = workbench_methods.get(workbench_type)
        if method is None:
            raise ValueError(f"Unknown workbench type: {workbench_type}")

        return method(
            parent_object_id=parent_object_id,
            novel_id=novel_id,
            project_id=project_id,
            actor=actor,
            session_id=session_id,
            iteration_number=iteration_number,
        )

    def generate_revision_candidates(
        self,
        session: dict,
        base_draft: dict,
        feedback,
        iteration_number: int,
        ai_client,
        gather_workspace_skills_callback,
        gather_workspace_objects_callback,
        read_object_callback,
    ) -> list[dict]:
        """Generate revised candidates based on feedback using AI when available.

        Args:
            session: The workbench session dictionary
            base_draft: The base draft to revise
            feedback: The feedback request
            iteration_number: Current iteration number
            ai_client: AI provider client (or None)
            gather_workspace_skills_callback: Callback to gather workspace skills
            gather_workspace_objects_callback: Callback to gather workspace objects
            read_object_callback: Callback to read objects

        Returns:
            List of revised candidate draft dictionaries
        """
        base_payload = dict(base_draft["payload"])

        revised_payload: JSONObject | None = None
        ai_generated = False

        if ai_client is not None and session.get("workbench_type") == "scene_to_chapter":
            try:
                novel_id = session.get("novel_id", "")
                project_id = session.get("project_id", "")
                skills = gather_workspace_skills_callback(project_id, novel_id)
                style_rules = gather_workspace_objects_callback(project_id, novel_id, "style_rule")
                facts = gather_workspace_objects_callback(project_id, novel_id, "fact_state_record")

                # Get scene context for the revision
                parent_object_id = session.get("parent_object_id", "")
                from core.runtime.application_services import ReadObjectRequest
                scene_read = read_object_callback(
                    ReadObjectRequest(family="scene", object_id=parent_object_id)
                )
                scene_context = scene_read.head.payload if scene_read.head else {}

                messages = build_chapter_revision_prompt(
                    current_chapter=base_payload,
                    revision_instructions=feedback.feedback_text,
                    scene_context=scene_context,
                    style_rules=[rule.payload for rule in style_rules],
                    skills=[skill.payload for skill in skills],
                    canonical_facts=[fact.payload for fact in facts],
                )

                output_schema = {
                    "type": "object",
                    "properties": {
                        "chapter_title": {"type": "string"},
                        "chapter_body": {"type": "string"},
                        "word_count": {"type": "integer"},
                        "changes_made": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["chapter_title", "chapter_body", "word_count"],
                }

                result = ai_client.generate_structured(
                    messages=messages, output_schema=output_schema,
                )

                revised_payload = {
                    "chapter_title": result.get("chapter_title", base_payload.get("chapter_title", "")),
                    "body": result.get("chapter_body", ""),
                    "word_count": result.get("word_count", 0),
                    "changes_made": result.get("changes_made", ""),
                    "notes": result.get("notes", ""),
                    "ai_generated": True,
                }
                ai_generated = True

            except Exception:
                revised_payload = None  # Fall through to fallback

        elif ai_client is not None:
            # Generic revision for non-chapter workbench types
            try:
                system_msg = {
                    "role": "system",
                    "content": (
                        "You are a creative writing assistant. Revise the following content "
                        "according to the user's feedback. Maintain the original structure "
                        "and style while incorporating the requested changes.\n\n"
                        "Respond with a JSON object matching the original content structure "
                        "with the revisions applied."
                    ),
                }
                user_msg = {
                    "role": "user",
                    "content": (
                        f"# Current content\n{json.dumps(base_payload, ensure_ascii=False, indent=2)}\n\n"
                        f"# Revision instructions\n{feedback.feedback_text}\n\n"
                        "Return the revised content as JSON."
                    ),
                }
                result = ai_client.generate_structured(
                    messages=[system_msg, user_msg],
                    output_schema={"type": "object"},
                )
                if isinstance(result, dict) and result:
                    revised_payload = dict(result)
                    revised_payload["ai_generated"] = True
                    ai_generated = True
            except Exception:
                revised_payload = None  # Fall through to fallback

        # Fallback: simple text append when AI unavailable or failed
        if revised_payload is None:
            revised_payload = dict(base_payload)
            notes = revised_payload.get("notes", "")
            revised_payload["notes"] = f"{notes}\n[Revision {iteration_number}: {feedback.feedback_text}]".strip()
            revised_payload["ai_generated"] = False

        # Create the revised candidate
        draft_id = self._storage.create_candidate_draft(
            session_id=session["session_id"],
            iteration_number=iteration_number,
            payload=revised_payload,
            generation_context={
                "base_draft_id": base_draft["draft_id"],
                "feedback_type": feedback.feedback_type,
                "feedback_text": feedback.feedback_text,
                "iteration_number": iteration_number,
                "ai_generated": ai_generated,
            },
        )

        draft = self._storage.get_candidate_draft(draft_id)
        if draft is None:
            raise RuntimeError("Failed to create candidate draft")

        return [draft]
