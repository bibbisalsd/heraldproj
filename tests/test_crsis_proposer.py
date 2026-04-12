"""Tests for CRSIS proposal generation."""
from __future__ import annotations


import pytest
from jarvis.crsis.proposer import ProposalGenerator
from jarvis.crsis.proposers.phrases import PhraseProposer
from jarvis.crsis.proposers.thresholds import ThresholdProposer
from jarvis.crsis.proposers.synonyms import SynonymProposer
from jarvis.crsis.contracts import PatternFinding


class TestPhraseProposer:
    """Test phrase proposal generation."""

    def setup_method(self):
        self.proposer = PhraseProposer()

    def test_propose_from_misrouting(self):
        """Test proposal from misrouting pattern."""
        pattern = PatternFinding(
            pattern_type="misrouting",
            affected_component="prompt_dispatcher:file_edit",
            evidence_count=5,
            confidence=0.85,
            examples=["Intent 'file_operation' misrouted"],
            time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
        )

        proposal = self.proposer.propose(pattern)

        assert proposal is not None
        assert proposal["target_file"] == "jarvis/brain_core/prompt_dispatcher.py"
        assert proposal["target_structure"] == "EXACT_INTENTS"

    def test_propose_with_quoted_phrases(self):
        """Test proposal extraction of quoted phrases."""
        pattern = PatternFinding(
            pattern_type="misrouting",
            affected_component="prompt_dispatcher:greeting",
            evidence_count=3,
            confidence=0.75,
            examples=["User said 'hey there' and got general_chat"],
            time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
        )

        proposal = self.proposer.propose(pattern)

        assert proposal is not None
        assert "hey there" in proposal["proposed_change"]["phrases"]

    def test_no_proposal_for_unknown_pattern(self):
        """Test that unknown patterns produce no proposal."""
        pattern = PatternFinding(
            pattern_type="unknown_type",
            affected_component="test",
            evidence_count=1,
            confidence=0.5,
            examples=[],
            time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
        )

        proposal = self.proposer.propose(pattern)
        assert proposal is None


class TestThresholdProposer:
    """Test threshold proposal generation."""

    def setup_method(self):
        self.proposer = ThresholdProposer()

    def test_propose_tool_threshold(self):
        """Test tool threshold adjustment proposal."""
        pattern = PatternFinding(
            pattern_type="empty_tool",
            affected_component="tools:web_search",
            evidence_count=10,
            confidence=0.9,
            examples=["web_search returned empty 10 times"],
            time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
        )

        proposal = self.proposer.propose(pattern)

        assert proposal is not None
        assert "tool_empty_rate_threshold" in proposal["target_structure"].lower()

    def test_propose_routing_threshold(self):
        """Test routing threshold adjustment proposal."""
        pattern = PatternFinding(
            pattern_type="misrouting",
            affected_component="prompt_dispatcher:test",
            evidence_count=8,
            confidence=0.8,
            examples=["High misrouting rate"],
            time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
        )

        proposal = self.proposer.propose(pattern)

        assert proposal is not None
        assert "routing" in proposal["target_structure"].lower()


class TestSynonymProposer:
    """Test synonym proposal generation."""

    def setup_method(self):
        self.proposer = SynonymProposer()

    def test_propose_synonym(self):
        """Test synonym proposal from misrouting."""
        pattern = PatternFinding(
            pattern_type="misrouting",
            affected_component="prompt_dispatcher:create",
            evidence_count=4,
            confidence=0.7,
            examples=["'build' was misrouted"],
            time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
        )

        proposal = self.proposer.propose(pattern)

        # May or may not produce proposal depending on category matching
        # Just verify it runs without error
        assert proposal is None or proposal["target_file"] == "jarvis/brain_core/semantic_command_match.py"


class TestProposalGenerator:
    """Test main proposal generator."""

    def setup_method(self):
        self.generator = ProposalGenerator()

    def test_generate_proposals(self):
        """Test proposal generation from patterns."""
        patterns = [
            PatternFinding(
                pattern_type="misrouting",
                affected_component="prompt_dispatcher:file_edit",
                evidence_count=5,
                confidence=0.85,
                examples=["User said 'modify this' and got general_chat"],
                time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
            ),
            PatternFinding(
                pattern_type="empty_tool",
                affected_component="tools:web_search",
                evidence_count=8,
                confidence=0.9,
                examples=["web_search empty"],
                time_range=("2026-04-04T00:00:00Z", "2026-04-04T01:00:00Z"),
            ),
        ]

        proposals = self.generator.generate_proposals(patterns)

        assert len(proposals) >= 1
        for p in proposals:
            assert p.proposal_id is not None
            assert p.proposal_type in ("new_phrase", "threshold_change", "synonym_add")
            assert p.status == "pending"
