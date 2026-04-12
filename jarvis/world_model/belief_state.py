"""BeliefState - Track inferences, hunches, defaults with uncertainty."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Belief:
    """A belief with explicit uncertainty and conflict detection."""

    belief_id: str
    content: str
    belief_type: str  # "inference", "hunch", "default", "prediction"
    confidence: float  # 0.0 to 1.0 - explicit uncertainty
    basis: list[str]  # Evidence IDs that support this belief
    contradicts: list[str]  # Evidence IDs that contradict
    expires_at: str | None = None  # Time-bound beliefs
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def is_expired(self) -> bool:
        """Check if belief has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc).isoformat() > self.expires_at

    def with_confidence(self, confidence: float) -> "Belief":
        """Create a new Belief with updated confidence."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {confidence}"
            )
        return Belief(
            belief_id=self.belief_id,
            content=self.content,
            belief_type=self.belief_type,
            confidence=confidence,
            basis=self.basis,
            contradicts=self.contradicts,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )

    def add_basis(self, evidence_id: str) -> "Belief":
        """Create a new Belief with added supporting evidence."""
        new_basis = list(self.basis)
        if evidence_id not in new_basis:
            new_basis.append(evidence_id)
        return Belief(
            belief_id=self.belief_id,
            content=self.content,
            belief_type=self.belief_type,
            confidence=self.confidence,
            basis=new_basis,
            contradicts=self.contradicts,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )

    def add_contradiction(self, evidence_id: str) -> "Belief":
        """Create a new Belief with added contradicting evidence."""
        new_contradicts = list(self.contradicts)
        if evidence_id not in new_contradicts:
            new_contradicts.append(evidence_id)
        return Belief(
            belief_id=self.belief_id,
            content=self.content,
            belief_type=self.belief_type,
            confidence=self.confidence,
            basis=self.basis,
            contradicts=new_contradicts,
            expires_at=self.expires_at,
            created_at=self.created_at,
        )


@dataclass(frozen=True)
class BeliefConflict:
    """A conflict between two beliefs."""

    belief1_id: str
    belief2_id: str
    conflict_type: str  # "content_conflict", "evidence_conflict"
    severity: str  # "low", "medium", "high"


class BeliefState:
    """Track beliefs with explicit uncertainty and conflict detection.

    Separate from Evidence Store - beliefs are inferences, not observations.
    """

    def __init__(self) -> None:
        self._beliefs: dict[str, Belief] = {}
        self._conflicts: list[BeliefConflict] = []

    def add(self, belief: Belief) -> str:
        """Add a belief and return belief_id."""
        self._beliefs[belief.belief_id] = belief

        # Check for conflicts with existing beliefs
        self._detect_conflicts(belief)

        return belief.belief_id

    def get(self, belief_id: str) -> Belief | None:
        """Get a belief by ID."""
        return self._beliefs.get(belief_id)

    def query(
        self,
        belief_type: str | None = None,
        min_confidence: float = 0.0,
        exclude_expired: bool = True,
    ) -> list[Belief]:
        """Query beliefs with filters."""
        results = []
        for belief in self._beliefs.values():
            if belief_type and belief.belief_type != belief_type:
                continue
            if belief.confidence < min_confidence:
                continue
            if exclude_expired and belief.is_expired():
                continue
            results.append(belief)
        return results

    def get_conflicts(self) -> list[BeliefConflict]:
        """Get all detected conflicts."""
        # Return active conflicts only (both beliefs still exist and not expired)
        active_conflicts = []
        for conflict in self._conflicts:
            belief1 = self._beliefs.get(conflict.belief1_id)
            belief2 = self._beliefs.get(conflict.belief2_id)
            if (
                belief1
                and belief2
                and not belief1.is_expired()
                and not belief2.is_expired()
            ):
                active_conflicts.append(conflict)
        return active_conflicts

    def update(self, belief_id: str, **updates: Any) -> bool:
        """Update a belief. Returns True if successful."""
        belief = self._beliefs.get(belief_id)
        if not belief:
            return False

        new_belief = Belief(
            belief_id=belief.belief_id,
            content=updates.get("content", belief.content),
            belief_type=updates.get("belief_type", belief.belief_type),
            confidence=updates.get("confidence", belief.confidence),
            basis=updates.get("basis", list(belief.basis)),
            contradicts=updates.get("contradicts", list(belief.contradicts)),
            expires_at=updates.get("expires_at", belief.expires_at),
            created_at=belief.created_at,
        )

        self._beliefs[belief_id] = new_belief
        self._detect_conflicts(new_belief)
        return True

    def remove(self, belief_id: str) -> bool:
        """Remove a belief. Returns True if existed."""
        if belief_id in self._beliefs:
            del self._beliefs[belief_id]
            # Clean up conflicts involving this belief
            self._conflicts = [
                c
                for c in self._conflicts
                if c.belief1_id != belief_id and c.belief2_id != belief_id
            ]
            return True
        return False

    def get_by_basis(self, evidence_id: str) -> list[Belief]:
        """Get all beliefs that have this evidence in their basis."""
        return [b for b in self._beliefs.values() if evidence_id in b.basis]

    def get_conflicting_beliefs(self, evidence_id: str) -> list[Belief]:
        """Get all beliefs that have this evidence as a contradiction."""
        return [b for b in self._beliefs.values() if evidence_id in b.contradicts]

    def _detect_conflicts(self, new_belief: Belief) -> None:
        """Detect conflicts between new belief and existing beliefs."""
        for existing_id, existing in self._beliefs.items():
            if existing_id == new_belief.belief_id:
                continue

            # Check for content conflict (same content, different confidence levels suggesting conflict)
            if (
                existing.content == new_belief.content
                and abs(existing.confidence - new_belief.confidence) > 0.3
            ):
                self._conflicts.append(
                    BeliefConflict(
                        belief1_id=existing_id,
                        belief2_id=new_belief.belief_id,
                        conflict_type="content_conflict",
                        severity=self._calculate_severity(existing, new_belief),
                    )
                )

            # Check for evidence conflict
            if (
                existing.belief_id in new_belief.contradicts
                or new_belief.belief_id in existing.contradicts
            ):
                self._conflicts.append(
                    BeliefConflict(
                        belief1_id=existing_id,
                        belief2_id=new_belief.belief_id,
                        conflict_type="evidence_conflict",
                        severity="high",
                    )
                )

    def _calculate_severity(self, belief1: Belief, belief2: Belief) -> str:
        """Calculate conflict severity based on confidence levels."""
        avg_confidence = (belief1.confidence + belief2.confidence) / 2
        if avg_confidence > 0.8:
            return "high"
        elif avg_confidence > 0.5:
            return "medium"
        else:
            return "low"
