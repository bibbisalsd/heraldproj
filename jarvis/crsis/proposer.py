"""ProposalGenerator - Generate improvement proposals from patterns."""

from __future__ import annotations


import uuid
from datetime import datetime, timezone

from jarvis.crsis.contracts import CRSISProposal, PatternFinding
from jarvis.crsis.proposers.phrases import PhraseProposer
from jarvis.crsis.proposers.thresholds import ThresholdProposer
from jarvis.crsis.proposers.synonyms import SynonymProposer


class ProposalGenerator:
    """Generate CRSIS proposals from detected patterns.

    Routes patterns to specialized proposers:
    - PhraseProposer: New exact-match phrases
    - ThresholdProposer: Threshold adjustments
    - SynonymProposer: New synonym mappings
    """

    def __init__(self) -> None:
        self._phrase_proposer = PhraseProposer()
        self._threshold_proposer = ThresholdProposer()
        self._synonym_proposer = SynonymProposer()

    def generate_proposals(self, patterns: list[PatternFinding]) -> list[CRSISProposal]:
        """Generate proposals from pattern findings.

        Args:
            patterns: list of PatternFinding from analyzer

        Returns: list of CRSISProposal ready for approval queue
        """
        proposals: list[CRSISProposal] = []
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        for pattern in patterns:
            sub_proposals = self._generate_for_pattern(pattern, timestamp)
            proposals.extend(sub_proposals)

        return proposals

    def _generate_for_pattern(
        self, pattern: PatternFinding, timestamp: str
    ) -> list[CRSISProposal]:
        """Generate proposals for a single pattern."""
        proposals = []

        if pattern.pattern_type == "misrouting":
            # Route to phrase or synonym proposer based on affected component
            if "EXACT_INTENTS" in pattern.affected_component:
                prop = self._phrase_proposer.propose(pattern)
                if prop:
                    proposals.append(
                        self._to_crsis_proposal(prop, pattern, timestamp, "new_phrase")
                    )
            elif "semantic" in pattern.affected_component.lower():
                prop = self._synonym_proposer.propose(pattern)
                if prop:
                    proposals.append(
                        self._to_crsis_proposal(prop, pattern, timestamp, "synonym_add")
                    )

        elif pattern.pattern_type == "empty_tool":
            # Tools may need threshold adjustments
            prop = self._threshold_proposer.propose(pattern)
            if prop:
                proposals.append(
                    self._to_crsis_proposal(
                        prop, pattern, timestamp, "threshold_change"
                    )
                )

        elif pattern.pattern_type == "correction_cluster":
            # May indicate need for new phrases or threshold changes
            prop = self._phrase_proposer.propose(pattern)
            if prop:
                proposals.append(
                    self._to_crsis_proposal(prop, pattern, timestamp, "new_phrase")
                )

        elif pattern.pattern_type == "latency_bottleneck":
            # Propose moving tool to BG1 if it is too slow for realtime
            tool_name = pattern.affected_component.split(":")[-1]
            proposals.append(
                CRSISProposal(
                    proposal_id=f"prop_{timestamp}_{uuid.uuid4().hex[:8]}",
                    proposal_type="tool_policy_change",
                    target_file="jarvis/brain_core/tool_manifest.py",
                    target_structure=f"TOOL_MANIFEST['{tool_name}'].safe_in_realtime",
                    proposed_change="False",
                    evidence=[pattern],
                    expected_impact=f"Reduce realtime latency by moving slow tool '{tool_name}' to background lane.",
                    rollback_path=f"TOOL_MANIFEST['{tool_name}'].safe_in_realtime = True",
                )
            )

        return proposals

    def _to_crsis_proposal(
        self,
        sub_proposal: dict,
        pattern: PatternFinding,
        timestamp: str,
        proposal_type: str,
    ) -> CRSISProposal:
        """Convert sub-proposal to CRSISProposal."""
        proposal_id = f"prop_{timestamp}_{uuid.uuid4().hex[:8]}"

        return CRSISProposal(
            proposal_id=proposal_id,
            proposal_type=proposal_type,
            target_file=sub_proposal["target_file"],
            target_structure=sub_proposal["target_structure"],
            proposed_change=sub_proposal["proposed_change"],
            evidence=[pattern],
            expected_impact=sub_proposal.get(
                "expected_impact", "Improve routing accuracy"
            ),
            rollback_path=sub_proposal["rollback_path"],
        )
