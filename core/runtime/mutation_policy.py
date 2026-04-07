from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.review import ReviewLedger, ReviewProposalRequest, ReviewResolutionRequest, ReviewResolutionResult
from core.runtime.storage import CanonicalStorage, CanonicalWriteRequest, DerivedRecordInput, JSONValue

JSONObject = dict[str, JSONValue]


class MutationPolicyClass(str, Enum):
    SCENE_STRUCTURED = "scene_structured"
    CHAPTER_PROSE_STYLE = "chapter_prose_style"
    CHAPTER_STRUCTURAL = "chapter_structural"
    OUTLINE_STRUCTURED = "outline_structured"
    ENTITY_CANONICAL = "entity_canonical"
    SKILL_STYLE_RULE = "skill_style_rule"
    REVIEW_RESOLUTION = "review_resolution"
    PUBLISH_PROJECTION = "publish_projection"


class MutationDisposition(str, Enum):
    AUTO_APPLIED = "auto_applied"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class ChapterMutationSignals:
    prose_only: bool
    preserves_facts: bool
    preserves_event_order: bool
    preserves_reveal_order: bool
    preserves_character_decisions: bool
    preserves_continuity: bool
    structural_edit: bool = False
    mixed_with_structural_edit: bool = False
    changes_source_coverage: bool = False
    changes_named_entities: bool = False
    ambiguous_intent: bool = False

    def safe_for_auto_apply(self) -> bool:
        return (
            self.prose_only
            and self.preserves_facts
            and self.preserves_event_order
            and self.preserves_reveal_order
            and self.preserves_character_decisions
            and self.preserves_continuity
            and not self.structural_edit
            and not self.mixed_with_structural_edit
            and not self.changes_source_coverage
            and not self.changes_named_entities
            and not self.ambiguous_intent
        )

    def review_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.prose_only:
            reasons.append("chapter edit is not proven prose-only")
        if not self.preserves_facts:
            reasons.append("chapter edit may change facts")
        if not self.preserves_event_order:
            reasons.append("chapter edit may change event order")
        if not self.preserves_reveal_order:
            reasons.append("chapter edit may change reveal order")
        if not self.preserves_character_decisions:
            reasons.append("chapter edit may change character decisions")
        if not self.preserves_continuity:
            reasons.append("chapter edit may change continuity")
        if self.structural_edit:
            reasons.append("chapter edit includes structural change")
        if self.mixed_with_structural_edit:
            reasons.append("chapter edit mixes prose and structural changes")
        if self.changes_source_coverage:
            reasons.append("chapter edit changes source-scene coverage")
        if self.changes_named_entities:
            reasons.append("chapter edit changes named entities")
        if self.ambiguous_intent:
            reasons.append("chapter edit intent is ambiguous")
        return tuple(reasons)

    def as_payload(self) -> JSONObject:
        return {
            "prose_only": self.prose_only,
            "preserves_facts": self.preserves_facts,
            "preserves_event_order": self.preserves_event_order,
            "preserves_reveal_order": self.preserves_reveal_order,
            "preserves_character_decisions": self.preserves_character_decisions,
            "preserves_continuity": self.preserves_continuity,
            "structural_edit": self.structural_edit,
            "mixed_with_structural_edit": self.mixed_with_structural_edit,
            "changes_source_coverage": self.changes_source_coverage,
            "changes_named_entities": self.changes_named_entities,
            "ambiguous_intent": self.ambiguous_intent,
        }


@dataclass(frozen=True, slots=True)
class MutationRequest:
    target_family: str
    payload: JSONObject
    actor: str
    source_surface: str
    target_object_id: str | None = None
    base_revision_id: str | None = None
    source_scene_revision_id: str | None = None
    base_source_scene_revision_id: str | None = None
    skill: str | None = None
    source_ref: str | None = None
    ingest_run_id: str | None = None
    revision_reason: str | None = None
    revision_source_message_id: str | None = None
    chapter_signals: ChapterMutationSignals | None = None


@dataclass(frozen=True, slots=True)
class MutationEvaluation:
    policy_class: MutationPolicyClass
    disposition: MutationDisposition
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MutationExecutionResult:
    policy_class: MutationPolicyClass
    disposition: MutationDisposition
    target_family: str
    target_object_id: str
    reasons: tuple[str, ...]
    canonical_revision_id: str | None = None
    canonical_revision_number: int | None = None
    mutation_record_id: str | None = None
    artifact_revision_id: str | None = None
    proposal_id: str | None = None


class MutationPolicyEngine:
    def __init__(self, storage: CanonicalStorage):
        self._storage: CanonicalStorage = storage
        self._review: ReviewLedger = ReviewLedger(storage)

    def evaluate_mutation(self, request: MutationRequest) -> MutationEvaluation:
        policy_class = self._classify_policy_class(request)
        if policy_class is MutationPolicyClass.SCENE_STRUCTURED:
            return MutationEvaluation(
                policy_class=policy_class,
                disposition=MutationDisposition.AUTO_APPLIED,
                reasons=("scene structured edits auto-apply",),
            )
        if request.target_family == "skill":
            return MutationEvaluation(
                policy_class=policy_class,
                disposition=MutationDisposition.AUTO_APPLIED,
                reasons=("constrained skill workshop edits auto-apply through service validation",),
            )
        if request.target_family == "chapter_artifact":
            return self._evaluate_chapter_prose(request)
        return MutationEvaluation(
            policy_class=policy_class,
            disposition=MutationDisposition.REVIEW_REQUIRED,
            reasons=(f"{policy_class.value} mutations require review",),
        )

    def apply_mutation(self, request: MutationRequest) -> MutationExecutionResult:
        evaluation = self.evaluate_mutation(request)
        if evaluation.disposition is MutationDisposition.AUTO_APPLIED:
            if evaluation.policy_class in {
                MutationPolicyClass.SCENE_STRUCTURED,
                MutationPolicyClass.SKILL_STYLE_RULE,
            }:
                write_result = self._storage.write_canonical_object(
                    CanonicalWriteRequest(
                        family=request.target_family,
                        object_id=request.target_object_id,
                        payload=request.payload,
                        actor=request.actor,
                        source_surface=request.source_surface,
                        policy_class=evaluation.policy_class.value,
                        approval_state=MutationDisposition.AUTO_APPLIED.value,
                        skill=request.skill,
                        source_ref=request.source_ref,
                        ingest_run_id=request.ingest_run_id,
                        revision_reason=request.revision_reason,
                        revision_source_message_id=request.revision_source_message_id,
                    )
                )
                return MutationExecutionResult(
                    policy_class=evaluation.policy_class,
                    disposition=evaluation.disposition,
                    target_family=request.target_family,
                    target_object_id=write_result.object_id,
                    reasons=evaluation.reasons,
                    canonical_revision_id=write_result.revision_id,
                    canonical_revision_number=write_result.revision_number,
                    mutation_record_id=write_result.mutation_record_id,
                )
            artifact_revision_id = self._apply_safe_chapter_prose(request)
            if request.target_object_id is None:
                raise ValueError("chapter prose auto-apply requires an existing chapter_artifact object_id")
            return MutationExecutionResult(
                policy_class=evaluation.policy_class,
                disposition=evaluation.disposition,
                target_family=request.target_family,
                target_object_id=request.target_object_id,
                reasons=evaluation.reasons,
                artifact_revision_id=artifact_revision_id,
            )

        proposal_result = self._create_review_proposal(request, evaluation)
        return MutationExecutionResult(
            policy_class=evaluation.policy_class,
            disposition=evaluation.disposition,
            target_family=request.target_family,
            target_object_id=proposal_result.target_object_id,
            reasons=proposal_result.reasons,
            proposal_id=proposal_result.proposal_id,
        )

    def record_review_resolution(
        self, request: ReviewResolutionRequest
    ) -> ReviewResolutionResult:
        return self._review.record_resolution(request)

    def _classify_policy_class(self, request: MutationRequest) -> MutationPolicyClass:
        family = request.target_family
        if family == "scene":
            return MutationPolicyClass.SCENE_STRUCTURED
        if family == "chapter_artifact":
            signals = request.chapter_signals
            if signals is not None and signals.safe_for_auto_apply():
                return MutationPolicyClass.CHAPTER_PROSE_STYLE
            return MutationPolicyClass.CHAPTER_STRUCTURAL
        if family in {"project", "novel", "outline_node", "plot_node", "event"}:
            return MutationPolicyClass.OUTLINE_STRUCTURED
        if family in {"character", "setting", "canon_rule", "fact_state_record"}:
            return MutationPolicyClass.ENTITY_CANONICAL
        if family in {"style_rule", "skill"}:
            return MutationPolicyClass.SKILL_STYLE_RULE
        if family == "export_artifact":
            return MutationPolicyClass.PUBLISH_PROJECTION
        raise ValueError(f"Unsupported mutation target family: {family}")

    def _evaluate_chapter_prose(self, request: MutationRequest) -> MutationEvaluation:
        reasons: list[str] = []
        if request.target_object_id is None:
            reasons.append("chapter prose auto-apply requires an existing chapter_artifact object_id")
        if request.chapter_signals is None:
            reasons.append("chapter prose auto-apply requires typed chapter signals")
        if request.source_scene_revision_id is None:
            reasons.append("chapter prose auto-apply requires source_scene_revision_id")
        if request.base_source_scene_revision_id is None:
            reasons.append("chapter prose auto-apply requires base_source_scene_revision_id")
        if (
            request.source_scene_revision_id is not None
            and request.base_source_scene_revision_id is not None
            and request.source_scene_revision_id != request.base_source_scene_revision_id
        ):
            reasons.append("chapter prose edit changed pinned source scene revision")
        if request.chapter_signals is not None:
            reasons.extend(request.chapter_signals.review_reasons())

        if reasons:
            return MutationEvaluation(
                policy_class=MutationPolicyClass.CHAPTER_STRUCTURAL,
                disposition=MutationDisposition.REVIEW_REQUIRED,
                reasons=tuple(dict.fromkeys(reasons)),
            )
        return MutationEvaluation(
            policy_class=MutationPolicyClass.CHAPTER_PROSE_STYLE,
            disposition=MutationDisposition.AUTO_APPLIED,
            reasons=("chapter prose edit is rule-proven safe",),
        )

    def _apply_safe_chapter_prose(self, request: MutationRequest) -> str:
        if request.target_object_id is None:
            raise ValueError("chapter prose auto-apply requires an existing chapter_artifact object_id")
        if request.source_scene_revision_id is None:
            raise ValueError("chapter prose auto-apply requires source_scene_revision_id")
        return self._storage.create_derived_record(
            DerivedRecordInput(
                family="chapter_artifact",
                object_id=request.target_object_id,
                payload=request.payload,
                source_scene_revision_id=request.source_scene_revision_id,
                created_by=request.actor,
                source_ref=request.source_ref,
                ingest_run_id=request.ingest_run_id,
            )
        )

    def _create_review_proposal(
        self, request: MutationRequest, evaluation: MutationEvaluation
    ):
        target_object_id = request.target_object_id
        if target_object_id is None:
            raise ValueError("review-required mutations must include target_object_id")
        proposal_payload: JSONObject = {
            "requested_payload": request.payload,
            "target_family": request.target_family,
        }
        if request.chapter_signals is not None:
            proposal_payload["chapter_signals"] = request.chapter_signals.as_payload()
        proposal_result = self._review.create_mutation_proposal(
            ReviewProposalRequest(
                target_family=request.target_family,
                target_object_id=target_object_id,
                created_by=request.actor,
                policy_class=evaluation.policy_class.value,
                source_surface=request.source_surface,
                proposal_payload=proposal_payload,
                reasons=evaluation.reasons,
                base_revision_id=request.base_revision_id,
                source_scene_revision_id=request.source_scene_revision_id,
                base_source_scene_revision_id=request.base_source_scene_revision_id,
                skill=request.skill,
            )
        )
        return proposal_result


__all__ = [
    "ChapterMutationSignals",
    "MutationDisposition",
    "MutationEvaluation",
    "MutationExecutionResult",
    "MutationPolicyClass",
    "MutationPolicyEngine",
    "MutationRequest",
    "ReviewResolutionRequest",
    "ReviewResolutionResult",
]
