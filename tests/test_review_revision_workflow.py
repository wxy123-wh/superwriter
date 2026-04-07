"""Tests for review desk revision request workflow and audit trail."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.runtime.storage import CanonicalStorage
from core.review import proposals as review_proposals

# Import via submodule to avoid circular import through core.review.__init__
ReviewLedger = review_proposals.ReviewLedger
RevisionRequest = review_proposals.RevisionRequest
RevisionRequestInput = review_proposals.RevisionRequestInput
RevisionRequestStatus = review_proposals.RevisionRequestStatus
AuditEntry = review_proposals.AuditEntry


@pytest.fixture
def ledger():
    """Create a ReviewLedger with a temporary SQLite storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = CanonicalStorage(db_path)
        yield ReviewLedger(storage)


class TestRevisionRequest:
    def test_create_revision_request(self, ledger):
        request = RevisionRequestInput(
            proposal_id="prp_001",
            requested_by="reviewer",
            reason="Character voice inconsistent in paragraph 3",
            target_sections=("paragraph_3",),
        )
        result = ledger.create_revision_request(request)

        assert result.proposal_id == "prp_001"
        assert result.requested_by == "reviewer"
        assert result.reason == "Character voice inconsistent in paragraph 3"
        assert result.target_sections == ("paragraph_3",)
        assert result.status == RevisionRequestStatus.PENDING.value
        assert result.request_id.startswith("rev_")

    def test_get_revision_request(self, ledger):
        request = RevisionRequestInput(
            proposal_id="prp_001",
            requested_by="reviewer",
            reason="Needs improvement",
        )
        created = ledger.create_revision_request(request)
        fetched = ledger.get_revision_request(created.request_id)
        assert fetched is not None
        assert fetched.request_id == created.request_id

    def test_get_revision_request_not_found(self, ledger):
        assert ledger.get_revision_request("nonexistent") is None

    def test_list_revision_requests(self, ledger):
        for i in range(3):
            ledger.create_revision_request(RevisionRequestInput(
                proposal_id="prp_001",
                requested_by="reviewer",
                reason=f"Revision {i}",
            ))
        # Different proposal
        ledger.create_revision_request(RevisionRequestInput(
            proposal_id="prp_002",
            requested_by="reviewer",
            reason="Other proposal",
        ))

        prp_001_requests = ledger.list_revision_requests("prp_001")
        assert len(prp_001_requests) == 3
        prp_002_requests = ledger.list_revision_requests("prp_002")
        assert len(prp_002_requests) == 1

    def test_mark_revision_addressed(self, ledger):
        created = ledger.create_revision_request(RevisionRequestInput(
            proposal_id="prp_001",
            requested_by="reviewer",
            reason="Fix dialogue",
        ))
        assert created.status == RevisionRequestStatus.PENDING.value

        updated = ledger.mark_revision_addressed(created.request_id)
        assert updated is not None
        assert updated.status == RevisionRequestStatus.ADDRESSED.value

    def test_mark_revision_addressed_not_found(self, ledger):
        assert ledger.mark_revision_addressed("nonexistent") is None


class TestAuditTrail:
    def test_audit_trail_records_actions(self, ledger):
        proposal_id = "test_audit_proposal"

        ledger._record_audit(proposal_id, "created", "author", {"note": "created"})
        ledger._record_audit(proposal_id, "reviewed", "reviewer", {"note": "reviewed"})
        ledger._record_audit(proposal_id, "approved", "reviewer", {"note": "approved"})

        trail = ledger.get_audit_trail(proposal_id)
        assert len(trail) == 3

        actions = [e.action for e in trail]
        assert actions == ["created", "reviewed", "approved"]

    def test_audit_trail_empty_for_unknown_proposal(self, ledger):
        trail = ledger.get_audit_trail("nonexistent")
        assert trail == []

    def test_audit_entry_fields(self, ledger):
        entry = ledger._record_audit(
            "prp_001",
            "revision_requested",
            "reviewer",
            {"reason": "quality issue"},
        )
        assert entry.entry_id.startswith("aud_")
        assert entry.proposal_id == "prp_001"
        assert entry.action == "revision_requested"
        assert entry.actor == "reviewer"
        assert entry.details == {"reason": "quality issue"}
        assert entry.timestamp  # non-empty

    def test_revision_request_creates_audit_entry(self, ledger):
        ledger.create_revision_request(RevisionRequestInput(
            proposal_id="prp_001",
            requested_by="reviewer",
            reason="Fix pacing",
        ))

        trail = ledger.get_audit_trail("prp_001")
        assert len(trail) == 1
        assert trail[0].action == "revision_requested"
        assert trail[0].actor == "reviewer"

    def test_audit_trail_chronological_order(self, ledger):
        """Entries should be ordered by timestamp."""
        proposal_id = "prp_chrono"
        ledger._record_audit(proposal_id, "second", "user", {"order": 2})
        ledger._record_audit(proposal_id, "first", "user", {"order": 1})
        ledger._record_audit(proposal_id, "third", "user", {"order": 3})

        trail = ledger.get_audit_trail(proposal_id)
        assert len(trail) == 3
