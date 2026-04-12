"""Judge - Cross-reference claims against evidence, tag claims with provenance."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.world_model.evidence_store import EvidenceStore


@dataclass(frozen=True)
class Claim:
    """A claim with provenance tagging."""

    claim_id: str
    content: str
    tag: str  # "observed", "recalled", "inferred", "guessed"
    evidence_ids: list[str]
    confidence: float
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def with_updated_confidence(self, confidence: float) -> "Claim":
        """Create a new Claim with updated confidence."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {confidence}"
            )
        return Claim(
            claim_id=self.claim_id,
            content=self.content,
            tag=self.tag,
            evidence_ids=list(self.evidence_ids),
            confidence=confidence,
            created_at=self.created_at,
        )


@dataclass(frozen=True)
class ClaimContext:
    """Context for claim tagging."""

    source: str | None = None
    has_evidence: bool = False
    evidence_ids: list[str] = field(default_factory=list)
    reasoning_chain: list[str] = field(default_factory=list)
    from_memory: bool = False
    memory_provenance: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    """Result of claim verification."""

    claim_id: str
    verified: bool
    tag: str
    confidence: float
    contradictions: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    notes: str = ""


class Judge:
    """Cross-reference claims against evidence, tag claims with provenance.

    Supports tiered verification:
    - Shallow (runtime): Tag based on evidence ID presence - fast, deterministic
    - Deep (async bg1): Cross-reference content, check contradictions, validate reasoning
    """

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}

    def tag_claim(self, claim_content: str, context: ClaimContext) -> Claim:
        """Tag a claim based on its context.

        Tag logic:
        - observed: Has direct tool output / file read / OCR evidence
        - recalled: Retrieved from PocketMemory with provenance
        - inferred: Derived from reasoning chain with explicit basis
        - guessed: No supporting evidence, low confidence
        """
        claim_id = f"claim_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

        # Determine tag based on context
        if context.has_evidence and context.evidence_ids:
            tag = "observed"
            base_confidence = 0.9
        elif context.from_memory and context.memory_provenance:
            tag = "recalled"
            base_confidence = 0.7
        elif context.reasoning_chain:
            tag = "inferred"
            base_confidence = 0.6
        else:
            tag = "guessed"
            base_confidence = 0.3

        claim = Claim(
            claim_id=claim_id,
            content=claim_content,
            tag=tag,
            evidence_ids=list(context.evidence_ids),
            confidence=base_confidence,
        )

        self._claims[claim_id] = claim
        return claim

    def verify(self, claim: Claim, evidence_store: EvidenceStore) -> VerificationResult:
        """Verify a claim against evidence store.

        Shallow verification - checks evidence ID presence.
        For deep verification, use verify_deep().
        """
        if not claim.evidence_ids:
            return VerificationResult(
                claim_id=claim.claim_id,
                verified=False,
                tag=claim.tag,
                confidence=0.3,
                notes="No supporting evidence IDs",
            )

        # Check that all evidence exists
        missing_evidence = []
        for eid in claim.evidence_ids:
            if evidence_store.get(eid) is None:
                missing_evidence.append(eid)

        if missing_evidence:
            return VerificationResult(
                claim_id=claim.claim_id,
                verified=False,
                tag=claim.tag,
                confidence=0.4,
                notes=f"Missing evidence: {missing_evidence}",
            )

        # Check for contradictions
        contradictions = []
        for eid in claim.evidence_ids:
            if evidence_store.has_contradictions(eid):
                contradictions.extend(evidence_store.get_contradictions(eid))

        # Calculate confidence based on evidence quality
        confidences = []
        for eid in claim.evidence_ids:
            confidences.append(evidence_store.get_effective_confidence(eid))

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Penalty for contradictions
        if contradictions:
            avg_confidence *= 0.7

        verified = avg_confidence >= 0.5 and not contradictions

        return VerificationResult(
            claim_id=claim.claim_id,
            verified=verified,
            tag=claim.tag,
            confidence=avg_confidence,
            contradictions=contradictions,
            supporting_evidence=list(claim.evidence_ids),
        )

    def verify_deep(
        self,
        claim: Claim,
        evidence_store: EvidenceStore,
        reasoning_validator: Any | None = None,
    ) -> VerificationResult:
        """Deep verification - cross-reference content, check contradictions, validate reasoning.

        Runs async in bg1 lane for thorough verification.
        """
        # Start with shallow verification
        shallow_result = self.verify(claim, evidence_store)

        if not shallow_result.verified:
            return shallow_result

        # Additional deep checks
        notes = []

        # Check evidence content actually supports claim
        claim_content_lower = claim.content.lower()
        for eid in claim.evidence_ids:
            evidence = evidence_store.get(eid)
            if evidence:
                evidence_content = str(evidence.content).lower()
                # Simple overlap check
                claim_words = set(claim_content_lower.split())
                evidence_words = set(evidence_content.split())
                overlap = claim_words & evidence_words
                if len(overlap) < 3:
                    notes.append(f"Weak content overlap with evidence {eid}")

        # Validate reasoning chain if provided
        if reasoning_validator and hasattr(reasoning_validator, "validate"):
            reasoning_valid = reasoning_validator.validate(claim)
            if not reasoning_valid:
                shallow_result = VerificationResult(
                    claim_id=claim.claim_id,
                    verified=False,
                    tag=claim.tag,
                    confidence=shallow_result.confidence * 0.5,
                    contradictions=shallow_result.contradictions,
                    supporting_evidence=shallow_result.supporting_evidence,
                    notes="Reasoning chain validation failed",
                )

        if notes:
            shallow_result = VerificationResult(
                claim_id=claim.claim_id,
                verified=shallow_result.verified,
                tag=shallow_result.tag,
                confidence=shallow_result.confidence,
                contradictions=shallow_result.contradictions,
                supporting_evidence=shallow_result.supporting_evidence,
                notes="; ".join(notes),
            )

        return shallow_result

    def get_claim(self, claim_id: str) -> Claim | None:
        """Get a claim by ID."""
        return self._claims.get(claim_id)

    def get_all_claims(self) -> list[Claim]:
        """Get all claims."""
        return list(self._claims.values())

    def get_claims_by_tag(self, tag: str) -> list[Claim]:
        """Get claims by tag."""
        return [c for c in self._claims.values() if c.tag == tag]

    def get_unverified_claims(self) -> list[Claim]:
        """Get claims with low confidence (< 0.5)."""
        return [c for c in self._claims.values() if c.confidence < 0.5]
