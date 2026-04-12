"""Tests for Judge claim tagging and verification."""
from __future__ import annotations


import pytest
from datetime import datetime, timezone

from jarvis.world_model.judge import Judge, Claim, ClaimContext, VerificationResult
from jarvis.world_model.evidence_store import Evidence, EvidenceStore, Provenance


class TestClaim:
    """Test Claim dataclass."""

    def test_create_claim(self):
        """Test creating Claim."""
        claim = Claim(
            claim_id="claim_001",
            content="The calculator returned 42",
            tag="observed",
            evidence_ids=["evidence_001"],
            confidence=0.9,
        )
        assert claim.claim_id == "claim_001"
        assert claim.content == "The calculator returned 42"
        assert claim.tag == "observed"
        assert "evidence_001" in claim.evidence_ids
        assert claim.confidence == 0.9

    def test_with_updated_confidence(self):
        """Test with_updated_confidence returns new claim."""
        original = Claim(
            claim_id="claim_001",
            content="Test claim",
            tag="observed",
            evidence_ids=["evidence_001"],
            confidence=0.5,
        )
        updated = original.with_updated_confidence(0.9)
        assert original.confidence == 0.5
        assert updated.confidence == 0.9

    def test_with_updated_confidence_validation(self):
        """Test confidence validation."""
        claim = Claim(
            claim_id="claim_001",
            content="Test",
            tag="observed",
            evidence_ids=[],
            confidence=0.5,
        )
        with pytest.raises(ValueError):
            claim.with_updated_confidence(1.5)


class TestClaimContext:
    """Test ClaimContext dataclass."""

    def test_create_context_minimal(self):
        """Test creating ClaimContext with defaults."""
        context = ClaimContext()
        assert context.source is None
        assert context.has_evidence is False
        assert context.evidence_ids == []
        assert context.reasoning_chain == []
        assert context.from_memory is False

    def test_create_context_observed(self):
        """Test creating context for observed claim."""
        context = ClaimContext(
            source="tool",
            has_evidence=True,
            evidence_ids=["evidence_001", "evidence_002"],
        )
        assert context.source == "tool"
        assert context.has_evidence is True


class TestVerificationResult:
    """Test VerificationResult dataclass."""

    def test_create_result(self):
        """Test creating VerificationResult."""
        result = VerificationResult(
            claim_id="claim_001",
            verified=True,
            tag="observed",
            confidence=0.9,
        )
        assert result.claim_id == "claim_001"
        assert result.verified is True
        assert result.tag == "observed"
        assert result.confidence == 0.9


class TestJudge:
    """Test Judge claim tagging and verification."""

    def test_tag_claim_with_evidence(self):
        """Test tagging claim with evidence as 'observed'."""
        judge = Judge()
        context = ClaimContext(
            source="tool",
            has_evidence=True,
            evidence_ids=["evidence_001"],
        )
        claim = judge.tag_claim("Calculator returned 42", context)
        assert claim.tag == "observed"
        assert claim.confidence == 0.9
        assert "evidence_001" in claim.evidence_ids

    def test_tag_claim_from_memory(self):
        """Test tagging claim from memory as 'recalled'."""
        judge = Judge()
        context = ClaimContext(
            source="memory",
            from_memory=True,
            memory_provenance="persistent",
        )
        claim = judge.tag_claim("User prefers dark mode", context)
        assert claim.tag == "recalled"
        assert claim.confidence == 0.7

    def test_tag_claim_with_reasoning(self):
        """Test tagging claim with reasoning chain as 'inferred'."""
        judge = Judge()
        context = ClaimContext(
            source="brain",
            reasoning_chain=["step1", "step2", "step3"],
        )
        claim = judge.tag_claim("User likely wants to edit the file", context)
        assert claim.tag == "inferred"
        assert claim.confidence == 0.6

    def test_tag_claim_no_evidence(self):
        """Test tagging claim without evidence as 'guessed'."""
        judge = Judge()
        context = ClaimContext()
        claim = judge.tag_claim("Maybe the user wants help", context)
        assert claim.tag == "guessed"
        assert claim.confidence == 0.3

    def test_tag_priority_evidence_over_memory(self):
        """Test evidence takes priority over memory."""
        judge = Judge()
        context = ClaimContext(
            source="tool",
            has_evidence=True,
            evidence_ids=["evidence_001"],
            from_memory=True,
            memory_provenance="persistent",
        )
        claim = judge.tag_claim("Result is 42", context)
        assert claim.tag == "observed"  # Evidence wins

    def test_verify_claim_no_evidence_ids(self):
        """Test verification fails without evidence IDs."""
        judge = Judge()
        evidence_store = EvidenceStore()
        claim = Claim(
            claim_id="claim_001",
            content="Unsubstantiated claim",
            tag="guessed",
            evidence_ids=[],
            confidence=0.3,
        )
        result = judge.verify(claim, evidence_store)
        assert result.verified is False
        assert "No supporting evidence" in result.notes

    def test_verify_claim_missing_evidence(self):
        """Test verification fails when evidence is missing."""
        judge = Judge()
        evidence_store = EvidenceStore()
        claim = Claim(
            claim_id="claim_001",
            content="Claim with missing evidence",
            tag="observed",
            evidence_ids=["nonexistent"],
            confidence=0.9,
        )
        result = judge.verify(claim, evidence_store)
        assert result.verified is False
        assert "Missing evidence" in result.notes

    def test_verify_claim_success(self):
        """Test verification succeeds with valid evidence."""
        judge = Judge()
        evidence_store = EvidenceStore()
        evidence_store.update_source_reliability("calculator", 1.0)
        evidence_store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        claim = Claim(
            claim_id="claim_001",
            content="Calculator returned 42",
            tag="observed",
            evidence_ids=["evidence_001"],
            confidence=0.9,
        )
        result = judge.verify(claim, evidence_store)
        assert result.verified is True
        assert result.confidence >= 0.5

    def test_verify_claim_with_contradictions(self):
        """Test verification detects contradictions."""
        judge = Judge()
        evidence_store = EvidenceStore()
        # Add evidence that contradicts
        evidence_store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content="true",
            source="source1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.9,
            provenance=Provenance(source="source1"),
        ))
        evidence_store.add(Evidence(
            evidence_id="evidence_002",
            evidence_type="tool_result",
            content="false",
            source="source2",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.9,
            provenance=Provenance(source="source2"),
        ))
        claim = Claim(
            claim_id="claim_001",
            content="Claim based on contradictory evidence",
            tag="observed",
            evidence_ids=["evidence_001"],
            confidence=0.9,
        )
        result = judge.verify(claim, evidence_store)
        # Contradictions reduce confidence
        assert result.contradictions  # Should have contradictions

    def test_verify_deep_weak_content_overlap(self):
        """Test deep verification detects weak content overlap."""
        judge = Judge()
        evidence_store = EvidenceStore()
        evidence_store.update_source_reliability("source1", 1.0)
        evidence_store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content="completely different content here",
            source="source1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.9,
            provenance=Provenance(source="source1"),
        ))
        claim = Claim(
            claim_id="claim_001",
            content="no shared words at all",
            tag="observed",
            evidence_ids=["evidence_001"],
            confidence=0.9,
        )
        result = judge.verify_deep(claim, evidence_store)
        assert "Weak content overlap" in result.notes

    def test_get_claim(self):
        """Test retrieving claim by ID."""
        judge = Judge()
        context = ClaimContext(has_evidence=True, evidence_ids=["evidence_001"])
        claim = judge.tag_claim("Test claim", context)
        retrieved = judge.get_claim(claim.claim_id)
        assert retrieved is not None
        assert retrieved.claim_id == claim.claim_id

    def test_get_missing_claim(self):
        """Test retrieving non-existent claim."""
        judge = Judge()
        result = judge.get_claim("nonexistent")
        assert result is None

    def test_get_all_claims(self):
        """Test getting all claims."""
        judge = Judge()
        judge.tag_claim("Claim 1", ClaimContext(has_evidence=True))
        judge.tag_claim("Claim 2", ClaimContext(has_evidence=True))
        claims = judge.get_all_claims()
        assert len(claims) == 2

    def test_get_claims_by_tag(self):
        """Test getting claims by tag."""
        judge = Judge()
        # Need both has_evidence=True AND evidence_ids for "observed" tag
        judge.tag_claim("Observed", ClaimContext(has_evidence=True, evidence_ids=["evidence_001"]))
        judge.tag_claim("Guessed", ClaimContext())
        observed = judge.get_claims_by_tag("observed")
        guessed = judge.get_claims_by_tag("guessed")
        assert len(observed) == 1
        assert len(guessed) == 1

    def test_get_unverified_claims(self):
        """Test getting low confidence claims."""
        judge = Judge()
        judge.tag_claim("High confidence", ClaimContext(has_evidence=True, evidence_ids=["e1"]))
        judge.tag_claim("Low confidence", ClaimContext())
        unverified = judge.get_unverified_claims()
        # Guessed claims have 0.3 confidence (< 0.5)
        assert len(unverified) == 1
        assert unverified[0].tag == "guessed"


class TestJudgeTaggingHierarchy:
    """Test Judge tagging hierarchy logic."""

    def test_observed_tag_highest_confidence(self):
        """Test observed claims get highest confidence."""
        judge = Judge()
        observed = judge.tag_claim("Test", ClaimContext(has_evidence=True, evidence_ids=["e1"]))
        recalled = judge.tag_claim("Test", ClaimContext(from_memory=True, memory_provenance="x"))
        inferred = judge.tag_claim("Test", ClaimContext(reasoning_chain=["x"]))
        guessed = judge.tag_claim("Test", ClaimContext())

        assert observed.confidence == 0.9
        assert recalled.confidence == 0.7
        assert inferred.confidence == 0.6
        assert guessed.confidence == 0.3

    def test_tag_hierarchy_order(self):
        """Test tag hierarchy: observed > recalled > inferred > guessed."""
        judge = Judge()
        # Evidence + memory = observed wins
        claim = judge.tag_claim("Test", ClaimContext(
            has_evidence=True,
            evidence_ids=["e1"],
            from_memory=True,
            memory_provenance="persistent",
        ))
        assert claim.tag == "observed"

        # Memory + reasoning = recalled wins
        claim = judge.tag_claim("Test", ClaimContext(
            from_memory=True,
            memory_provenance="persistent",
            reasoning_chain=["x"],
        ))
        assert claim.tag == "recalled"
