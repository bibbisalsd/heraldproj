"""ProposalQueue and Approval Gate - Manage pending proposals."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.crsis.contracts import CRSISProposal


@dataclass(frozen=True)
class ApprovalDecision:
    """Record of an approval decision."""

    proposal_id: str
    decision: str  # "approved", "rejected"
    decided_by: str
    reason: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ProposalQueue:
    """Manage pending CRSIS proposals for human approval.

    Queue operations:
    - enqueue: Add proposal to pending queue
    - dequeue: Remove and return next pending proposal
    - peek: View next proposal without removing
    - list_pending: list all pending proposals
    """

    def __init__(self) -> None:
        self._pending: list[CRSISProposal] = []
        self._decisions: dict[str, ApprovalDecision] = {}
        self._applied: dict[str, str] = {}  # proposal_id -> applied_at

    def enqueue(self, proposal: CRSISProposal) -> str:
        """Add proposal to pending queue. Returns proposal_id."""
        self._pending.append(proposal)
        # Sort by confidence (highest first)
        self._pending.sort(
            key=lambda p: p.evidence[0].confidence if p.evidence else 0, reverse=True
        )
        return proposal.proposal_id

    def dequeue(self) -> CRSISProposal | None:
        """Remove and return next pending proposal."""
        if not self._pending:
            return None
        return self._pending.pop(0)

    def peek(self) -> CRSISProposal | None:
        """View next proposal without removing."""
        return self._pending[0] if self._pending else None

    def list_pending(self) -> list[CRSISProposal]:
        """List all pending proposals."""
        return list(self._pending)

    def get(self, proposal_id: str) -> CRSISProposal | None:
        """Get proposal by ID."""
        for p in self._pending:
            if p.proposal_id == proposal_id:
                return p
        # Check already decided
        if proposal_id in self._decisions:
            # Would need to store full proposals - for now return None
            pass
        return None

    def approve(
        self, proposal_id: str, decided_by: str = "user", reason: str | None = None
    ) -> bool:
        """Approve a proposal. Returns True if found."""
        proposal = self._find_and_remove(proposal_id)
        if not proposal:
            return False

        proposal.status = "approved"
        self._decisions[proposal_id] = ApprovalDecision(
            proposal_id=proposal_id,
            decision="approved",
            decided_by=decided_by,
            reason=reason,
        )
        return True

    def reject(
        self, proposal_id: str, decided_by: str = "user", reason: str | None = None
    ) -> bool:
        """Reject a proposal. Returns True if found."""
        proposal = self._find_and_remove(proposal_id)
        if not proposal:
            return False

        proposal.status = "rejected"
        self._decisions[proposal_id] = ApprovalDecision(
            proposal_id=proposal_id,
            decision="rejected",
            decided_by=decided_by,
            reason=reason,
        )
        return True

    def mark_applied(self, proposal_id: str) -> bool:
        """Mark proposal as applied. Returns True if found."""
        if (
            proposal_id in self._decisions
            and self._decisions[proposal_id].decision == "approved"
        ):
            self._applied[proposal_id] = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def mark_rolled_back(self, proposal_id: str) -> bool:
        """Mark proposal as rolled back."""
        if proposal_id in self._decisions:
            self._decisions[proposal_id] = ApprovalDecision(
                proposal_id=proposal_id,
                decision="rolled_back",
                decided_by="system",
                reason="Auto-rollback after failed validation",
            )
            return True
        return False

    def get_statistics(self) -> dict[str, Any]:
        """Get queue statistics."""
        return {
            "pending_count": len(self._pending),
            "approved_count": sum(
                1 for d in self._decisions.values() if d.decision == "approved"
            ),
            "rejected_count": sum(
                1 for d in self._decisions.values() if d.decision == "rejected"
            ),
            "applied_count": len(self._applied),
        }

    def _find_and_remove(self, proposal_id: str) -> CRSISProposal | None:
        """Find and remove proposal from pending queue."""
        for i, p in enumerate(self._pending):
            if p.proposal_id == proposal_id:
                return self._pending.pop(i)
        return None

    def clear(self) -> None:
        """Clear all pending proposals."""
        self._pending.clear()
