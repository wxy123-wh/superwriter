"""Review-related helper functions for application services."""

from __future__ import annotations

import difflib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.runtime.storage import JSONValue
    from core.runtime.types import ReviewDecisionSnapshot, ReviewProposalSnapshot

JSONObject = dict[str, "JSONValue"]


class ReviewHelpers:
    """Helper methods for review proposal processing."""

    @staticmethod
    def review_target_title(
        proposal: "ReviewProposalSnapshot",
        requested_payload: JSONObject,
        current_payload: JSONObject,
    ) -> str:
        """Extract a display title for the review target."""
        for payload in (requested_payload, current_payload):
            for key in ("chapter_title", "title", "summary"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return proposal.target_object_id

    @staticmethod
    def review_state_detail(
        approval_state: str,
        decisions: tuple["ReviewDecisionSnapshot", ...],
        drift_details: JSONObject,
    ) -> str:
        """Generate human-readable review state description."""
        if approval_state == "approved":
            return "Applied exactly once; replaying approval returns the original apply result."
        if approval_state == "rejected":
            latest_reason = ReviewHelpers.decision_reason(decisions[-1]) if decisions else None
            return latest_reason or "Rejected; canonical state is unchanged."
        if approval_state == "revision_requested":
            revise_count = sum(1 for decision in decisions if decision.approval_state == "revision_requested")
            return f"Revision requested {revise_count} time(s); the proposal remains open for another pass."
        if approval_state == "stale":
            return ReviewHelpers.drift_summary(drift_details)
        return "Pending review; no apply has been recorded yet."

    @staticmethod
    def decision_reason(decision: "ReviewDecisionSnapshot") -> str | None:
        """Extract reason from review decision."""
        for key in ("reason", "note", "summary"):
            value = decision.decision_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def drift_summary(drift_details: JSONObject) -> str:
        """Generate drift summary from drift details."""
        fragments: list[str] = []
        for key, value in drift_details.items():
            if not isinstance(value, dict):
                continue
            expected = value.get("expected_base_revision_id") or value.get("expected_revision_id")
            current = value.get("current_revision_id")
            if expected is not None or current is not None:
                fragments.append(f"{key} drifted from {expected} to {current}")
        return "; ".join(fragments) or "Revision drift detected; approval was blocked before mutating canonical state."

    @staticmethod
    def render_prose_diff(before: JSONObject, after: JSONObject) -> str:
        """Render a unified diff of prose content."""
        before_text = ReviewHelpers.prose_payload_text(before)
        after_text = ReviewHelpers.prose_payload_text(after)
        if before_text == after_text:
            return "No rendered prose delta."
        diff = list(
            difflib.unified_diff(
                before_text.splitlines(),
                after_text.splitlines(),
                fromfile="current",
                tofile="proposed",
                lineterm="",
            )
        )
        if not diff:
            return "Rendered prose changed."
        return "\n".join(diff[:24])

    @staticmethod
    def prose_payload_text(payload: JSONObject) -> str:
        """Extract prose text from payload for diff rendering."""
        parts: list[str] = []
        for key in ("title", "chapter_title", "summary", "body"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(f"{key}:\n{value.strip()}")
        if parts:
            return "\n\n".join(parts)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
