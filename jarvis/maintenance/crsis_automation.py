"""CRSISAutomation - CRSIS loop orchestration."""

from __future__ import annotations


from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis.crsis.analyzer import DecisionLogAnalyzer
from jarvis.crsis.proposer import ProposalGenerator
from jarvis.crsis.api import ProposalAPI
from jarvis.crsis.applier import ChangeApplier
from jarvis.crsis.contracts import CRSISLoopResult, PatternFinding


@dataclass(frozen=True)
class CRSISLoopConfig:
    """Configuration for CRSIS loop execution."""

    analysis_window_hours: int = 24
    auto_apply_threshold: float = 0.95
    dry_run: bool = False
    require_approval: bool = True


class CRSISAutomation:
    """Orchestrate the CRSIS self-improvement loop.

    Loop steps:
    1. Analyze: DecisionLogAnalyzer analyzes event logs
    2. Generate: ProposalGenerator creates proposals from patterns
    3. Queue: Proposals queued for approval
    4. Apply: High-confidence proposals auto-applied (optional)

    Manual CLI trigger - not automated scheduling.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        event_log: Any | None = None,
    ) -> None:
        self._project_root = project_root or Path.cwd()
        self._event_log = event_log

        self._analyzer = DecisionLogAnalyzer(event_log)
        self._proposer = ProposalGenerator()
        self._api = ProposalAPI(project_root)
        self._applier = ChangeApplier(project_root)

    def run_loop(self, config: CRSISLoopConfig | None = None) -> CRSISLoopResult:
        """Run the CRSIS improvement loop.

        Args:
            config: Loop configuration (optional)

        Returns:
            CRSISLoopResult with execution statistics
        """
        cfg = config or CRSISLoopConfig()

        # Step 1: Analyze
        patterns = self._analyzer.analyze_last_n_hours(cfg.analysis_window_hours)

        # Step 2: Generate proposals
        proposals = self._proposer.generate_proposals(patterns)

        # Step 3: Queue for approval
        for proposal in proposals:
            self._api.submit(proposal)

        # Step 4: Auto-apply high-confidence proposals (optional)
        auto_applied = 0
        applied_successfully = 0
        rolled_back = 0

        if not cfg.require_approval and not cfg.dry_run:
            for proposal in proposals:
                # Check confidence from evidence
                confidence = (
                    proposal.evidence[0].confidence if proposal.evidence else 0.0
                )
                if confidence >= cfg.auto_apply_threshold:
                    auto_applied += 1

                    # Approve and apply
                    proposal.status = "approved"
                    result = self._applier.apply(proposal)

                    if result.success:
                        self._api.mark_applied(proposal.proposal_id)
                        applied_successfully += 1
                    else:
                        self._api.mark_rolled_back(proposal.proposal_id, result.error)
                        rolled_back += 1

        return CRSISLoopResult(
            patterns_detected=len(patterns),
            proposals_generated=len(proposals),
            auto_applied=auto_applied,
            applied_successfully=applied_successfully,
            rolled_back=rolled_back,
        )

    def analyze_only(self, hours: int = 24) -> list[PatternFinding]:
        """Run analysis only, without generating proposals."""
        return self._analyzer.analyze_last_n_hours(hours)

    def generate_proposals_only(
        self, patterns: list[PatternFinding], dry_run: bool = True
    ) -> list:
        """Generate proposals from patterns without queuing."""
        proposals = self._proposer.generate_proposals(patterns)
        if dry_run:
            # Don't persist, just return
            return proposals
        for p in proposals:
            self._api.submit(p)
        return proposals

    def get_proposal_status(self, proposal_id: str) -> dict[str, Any] | None:
        """Get status of a proposal."""
        return self._api.get(proposal_id)

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        """List all pending proposals."""
        return self._api.list_pending()

    def approve_proposal(self, proposal_id: str, decided_by: str = "user") -> bool:
        """Approve a proposal."""
        return self._api.approve(proposal_id, decided_by)

    def reject_proposal(
        self, proposal_id: str, decided_by: str = "user", reason: str = ""
    ) -> bool:
        """Reject a proposal."""
        return self._api.reject(proposal_id, decided_by, reason)

    def apply_pending(self, proposal_id: str) -> dict[str, Any]:
        """Apply an approved proposal."""
        proposal_data = self._api.get(proposal_id)
        if not proposal_data:
            return {"success": False, "error": "Proposal not found"}

        if proposal_data.get("status") != "approved":
            return {"success": False, "error": "Proposal not approved"}

        # Convert to CRSISProposal
        from jarvis.crsis.contracts import CRSISProposal

        proposal = CRSISProposal(
            **{
                k: v
                for k, v in proposal_data.items()
                if k in CRSISProposal.__dataclass_fields__
            }
        )

        result = self._applier.apply(proposal)

        if result.success:
            self._api.mark_applied(proposal_id)
            return {"success": True, "backup_path": result.backup_path}
        else:
            self._api.mark_rolled_back(proposal_id, result.error)
            return {
                "success": False,
                "error": result.error,
                "rolled_back": result.rolled_back,
            }

    def get_statistics(self) -> dict[str, Any]:
        """Get CRSIS automation statistics."""
        proposal_stats = self._api.get_statistics()
        return {
            "proposal_stats": proposal_stats,
            "last_run": None,  # Would track in persistence
        }
