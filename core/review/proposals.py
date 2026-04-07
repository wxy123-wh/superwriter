from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.runtime.storage import ApprovalRecordInput, CanonicalStorage, JSONValue, ProposalRecordInput

JSONObject = dict[str, JSONValue]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RevisionRequestStatus(str, Enum):
    """Status of a revision request."""

    PENDING = "pending"
    ADDRESSED = "addressed"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class RevisionRequest:
    """A request for revision created when a proposal is rejected."""

    request_id: str
    proposal_id: str
    requested_by: str
    reason: str
    target_sections: tuple[str, ...]
    created_at: str
    status: str = RevisionRequestStatus.PENDING.value


@dataclass(frozen=True, slots=True)
class RevisionRequestInput:
    """Input for creating a revision request."""

    proposal_id: str
    requested_by: str
    reason: str
    target_sections: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """A single entry in the review audit trail."""

    entry_id: str
    proposal_id: str
    action: str  # created, approved, rejected, revision_requested, comment_added
    actor: str
    timestamp: str
    details: JSONObject


@dataclass(frozen=True, slots=True)
class ReviewProposalRequest:
    target_family: str
    target_object_id: str
    created_by: str
    policy_class: str
    source_surface: str
    proposal_payload: JSONObject
    reasons: tuple[str, ...]
    base_revision_id: str | None = None
    source_scene_revision_id: str | None = None
    base_source_scene_revision_id: str | None = None
    skill: str | None = None

    def as_payload(self) -> JSONObject:
        payload: JSONObject = {
            "policy_class": self.policy_class,
            "source_surface": self.source_surface,
            "payload": self.proposal_payload,
            "reasons": list(self.reasons),
        }
        if self.skill is not None:
            payload["skill"] = self.skill
        if self.source_scene_revision_id is not None:
            payload["source_scene_revision_id"] = self.source_scene_revision_id
        if self.base_source_scene_revision_id is not None:
            payload["base_source_scene_revision_id"] = self.base_source_scene_revision_id
        return payload


@dataclass(frozen=True, slots=True)
class ReviewProposalResult:
    proposal_id: str
    target_family: str
    target_object_id: str
    policy_class: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewResolutionRequest:
    proposal_id: str
    created_by: str
    approval_state: str
    mutation_record_id: str | None = None
    decision_payload: JSONObject | None = None


@dataclass(frozen=True, slots=True)
class ReviewResolutionResult:
    approval_record_id: str
    proposal_id: str
    approval_state: str
    mutation_record_id: str | None


class ReviewLedger:
    def __init__(self, storage: CanonicalStorage):
        self._storage: CanonicalStorage = storage
        self._revision_requests: dict[str, RevisionRequest] = {}
        self._audit_entries: dict[str, list[AuditEntry]] = {}

    def create_mutation_proposal(self, request: ReviewProposalRequest) -> ReviewProposalResult:
        proposal_id = self._storage.create_proposal_record(
            ProposalRecordInput(
                target_family=request.target_family,
                target_object_id=request.target_object_id,
                created_by=request.created_by,
                proposal_payload=request.as_payload(),
                base_revision_id=request.base_revision_id,
            )
        )
        self._record_audit(
            proposal_id=proposal_id,
            action="created",
            actor=request.created_by,
            details={"policy_class": request.policy_class, "reasons": list(request.reasons)},
        )
        return ReviewProposalResult(
            proposal_id=proposal_id,
            target_family=request.target_family,
            target_object_id=request.target_object_id,
            policy_class=request.policy_class,
            reasons=request.reasons,
        )

    def record_resolution(self, request: ReviewResolutionRequest) -> ReviewResolutionResult:
        approval_record_id = self._storage.create_approval_record(
            ApprovalRecordInput(
                proposal_id=request.proposal_id,
                created_by=request.created_by,
                approval_state=request.approval_state,
                mutation_record_id=request.mutation_record_id,
                decision_payload=request.decision_payload,
            )
        )
        action = "approved" if request.approval_state == "approved" else "rejected"
        self._record_audit(
            proposal_id=request.proposal_id,
            action=action,
            actor=request.created_by,
            details={"approval_state": request.approval_state},
        )
        return ReviewResolutionResult(
            approval_record_id=approval_record_id,
            proposal_id=request.proposal_id,
            approval_state=request.approval_state,
            mutation_record_id=request.mutation_record_id,
        )

    # ── Revision requests ──────────────────────────────────────────

    def create_revision_request(self, request: RevisionRequestInput) -> RevisionRequest:
        """Create a revision request, typically when a proposal is rejected."""
        request_id = f"rev_{_utc_now_iso()}_{len(self._revision_requests)}"
        record = RevisionRequest(
            request_id=request_id,
            proposal_id=request.proposal_id,
            requested_by=request.requested_by,
            reason=request.reason,
            target_sections=request.target_sections,
            created_at=_utc_now_iso(),
            status=RevisionRequestStatus.PENDING.value,
        )
        self._revision_requests[request_id] = record
        self._record_audit(
            proposal_id=request.proposal_id,
            action="revision_requested",
            actor=request.requested_by,
            details={"request_id": request_id, "reason": request.reason},
        )
        return record

    def get_revision_request(self, request_id: str) -> RevisionRequest | None:
        """Get a revision request by ID."""
        return self._revision_requests.get(request_id)

    def list_revision_requests(self, proposal_id: str) -> list[RevisionRequest]:
        """List all revision requests for a proposal."""
        return [
            r for r in self._revision_requests.values()
            if r.proposal_id == proposal_id
        ]

    def mark_revision_addressed(self, request_id: str) -> RevisionRequest | None:
        """Mark a revision request as addressed."""
        record = self._revision_requests.get(request_id)
        if record is None:
            return None
        updated = RevisionRequest(
            request_id=record.request_id,
            proposal_id=record.proposal_id,
            requested_by=record.requested_by,
            reason=record.reason,
            target_sections=record.target_sections,
            created_at=record.created_at,
            status=RevisionRequestStatus.ADDRESSED.value,
        )
        self._revision_requests[request_id] = updated
        return updated

    # ── Audit trail ─────────────────────────────────────────────────

    def _record_audit(
        self,
        proposal_id: str,
        action: str,
        actor: str,
        details: JSONObject,
    ) -> AuditEntry:
        """Record an audit entry for a proposal."""
        entry_id = f"aud_{_utc_now_iso()}_{len(self._audit_entries)}"
        entry = AuditEntry(
            entry_id=entry_id,
            proposal_id=proposal_id,
            action=action,
            actor=actor,
            timestamp=_utc_now_iso(),
            details=details,
        )
        self._audit_entries.setdefault(proposal_id, []).append(entry)
        return entry

    def get_audit_trail(self, proposal_id: str) -> list[AuditEntry]:
        """Get the full audit trail for a proposal, ordered chronologically."""
        entries = self._audit_entries.get(proposal_id, [])
        return sorted(entries, key=lambda e: e.timestamp)


__all__ = [
    "AuditEntry",
    "RevisionRequest",
    "RevisionRequestInput",
    "RevisionRequestStatus",
    "ReviewLedger",
    "ReviewProposalRequest",
    "ReviewProposalResult",
    "ReviewResolutionRequest",
    "ReviewResolutionResult",
]
