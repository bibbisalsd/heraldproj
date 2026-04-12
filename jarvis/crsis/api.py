"""ProposalAPI - API for proposal operations."""

from __future__ import annotations


import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.crsis.contracts import CRSISProposal
from jarvis.crsis.approval import ProposalQueue


class ProposalAPI:
    """API for CRSIS proposal operations.

    Persists proposals to disk for CLI review.
    File format: JSON files in .crsis/proposals/ directory
    """

    def __init__(self, base_dir: str | None = None) -> None:
        """Initialize API.

        Args:
            base_dir: Base directory for proposal storage (default: project root)
        """
        self._queue = ProposalQueue()
        self._base_dir = Path(base_dir) if base_dir else Path.cwd()
        self._proposals_dir = self._base_dir / ".crsis" / "proposals"
        self._proposals_dir.mkdir(parents=True, exist_ok=True)

    def submit(self, proposal: CRSISProposal) -> str:
        """Submit a proposal to the queue and persist to disk."""
        # Add to queue
        self._queue.enqueue(proposal)

        # Persist to disk
        self._save_proposal(proposal)

        return proposal.proposal_id

    def list_pending(self) -> list[dict[str, Any]]:
        """List pending proposals from disk."""
        proposals = []
        for filepath in self._proposals_dir.glob("*.json"):
            data = self._load_proposal_file(filepath)
            if data and data.get("status") == "pending":
                proposals.append(data)
        return sorted(proposals, key=lambda p: p.get("created_at", ""), reverse=True)

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        """Get proposal by ID."""
        filepath = self._proposals_dir / f"{proposal_id}.json"
        if not filepath.exists():
            return None
        return self._load_proposal_file(filepath)

    def approve(
        self, proposal_id: str, decided_by: str = "user", reason: str | None = None
    ) -> bool:
        """Approve a proposal."""
        proposal_data = self.get(proposal_id)
        if not proposal_data:
            return False

        proposal_data["status"] = "approved"
        proposal_data["approved_by"] = decided_by
        proposal_data["approved_reason"] = reason
        proposal_data["approved_at"] = datetime.now(timezone.utc).isoformat()

        self._save_proposal_data(proposal_id, proposal_data)
        self._queue.approve(proposal_id, decided_by, reason)
        return True

    def reject(
        self, proposal_id: str, decided_by: str = "user", reason: str | None = None
    ) -> bool:
        """Reject a proposal."""
        proposal_data = self.get(proposal_id)
        if not proposal_data:
            return False

        proposal_data["status"] = "rejected"
        proposal_data["rejected_by"] = decided_by
        proposal_data["rejected_reason"] = reason
        proposal_data["rejected_at"] = datetime.now(timezone.utc).isoformat()

        self._save_proposal_data(proposal_id, proposal_data)
        self._queue.reject(proposal_id, decided_by, reason)
        return True

    def mark_applied(self, proposal_id: str) -> bool:
        """Mark proposal as applied."""
        proposal_data = self.get(proposal_id)
        if not proposal_data or proposal_data.get("status") != "approved":
            return False

        proposal_data["status"] = "applied"
        proposal_data["applied_at"] = datetime.now(timezone.utc).isoformat()

        self._save_proposal_data(proposal_id, proposal_data)
        self._queue.mark_applied(proposal_id)
        return True

    def mark_rolled_back(self, proposal_id: str, reason: str = "") -> bool:
        """Mark proposal as rolled back."""
        proposal_data = self.get(proposal_id)
        if not proposal_data:
            return False

        proposal_data["status"] = "rolled_back"
        proposal_data["rollback_reason"] = reason
        proposal_data["rolled_back_at"] = datetime.now(timezone.utc).isoformat()

        self._save_proposal_data(proposal_id, proposal_data)
        self._queue.mark_rolled_back(proposal_id)
        return True

    def get_statistics(self) -> dict[str, Any]:
        """Get proposal statistics."""
        stats = {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "applied": 0,
            "rolled_back": 0,
        }

        for filepath in self._proposals_dir.glob("*.json"):
            data = self._load_proposal_file(filepath)
            if data:
                status = data.get("status", "pending")
                if status in stats:
                    stats[status] += 1

        return stats

    def _save_proposal(self, proposal: CRSISProposal) -> None:
        """Save proposal to disk."""
        data = asdict(proposal)
        # Convert evidence to serializable format
        data["evidence"] = [
            asdict(e) if hasattr(e, "__dataclass_fields__") else e
            for e in proposal.evidence
        ]
        self._save_proposal_data(proposal.proposal_id, data)

    def _save_proposal_data(self, proposal_id: str, data: dict[str, Any]) -> None:
        """Save proposal data to disk."""
        filepath = self._proposals_dir / f"{proposal_id}.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def _load_proposal_file(self, filepath: Path) -> dict[str, Any] | None:
        """Load proposal from disk."""
        try:
            with open(filepath) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def clear_old_proposals(self, days_old: int = 30) -> int:
        """Clear proposals older than specified days. Returns count removed."""
        now = datetime.now(timezone.utc)
        removed = 0

        for filepath in self._proposals_dir.glob("*.json"):
            data = self._load_proposal_file(filepath)
            if not data:
                continue

            created_at = data.get("created_at", "")
            try:
                created = datetime.fromisoformat(created_at)
                age = (now - created).days
                if age > days_old and data.get("status") in (
                    "applied",
                    "rejected",
                    "rolled_back",
                ):
                    filepath.unlink()
                    removed += 1
            except (ValueError, TypeError):
                continue

        return removed
