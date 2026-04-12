"""Tests for BeliefState with uncertainty tracking and conflict detection."""
from __future__ import annotations


import pytest
from datetime import datetime, timezone, timedelta

from jarvis.world_model.belief_state import Belief, BeliefState, BeliefConflict


class TestBelief:
    """Test Belief dataclass."""

    def test_create_belief(self):
        """Test creating Belief."""
        belief = Belief(
            belief_id="belief_001",
            content="User prefers dark mode",
            belief_type="inference",
            confidence=0.8,
            basis=["evidence_001"],
            contradicts=[],
        )
        assert belief.belief_id == "belief_001"
        assert belief.content == "User prefers dark mode"
        assert belief.belief_type == "inference"
        assert belief.confidence == 0.8
        assert "evidence_001" in belief.basis

    def test_belief_with_expiry(self):
        """Test creating Belief with expiry."""
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        belief = Belief(
            belief_id="belief_001",
            content="Temporary belief",
            belief_type="hunch",
            confidence=0.5,
            basis=[],
            contradicts=[],
            expires_at=expires,
        )
        assert belief.expires_at is not None
        assert belief.is_expired() is False

    def test_belief_expired(self):
        """Test checking if belief is expired."""
        expired = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        belief = Belief(
            belief_id="belief_001",
            content="Expired belief",
            belief_type="hunch",
            confidence=0.5,
            basis=[],
            contradicts=[],
            expires_at=expired,
        )
        assert belief.is_expired() is True

    def test_belief_no_expiry(self):
        """Test belief without expiry never expires."""
        belief = Belief(
            belief_id="belief_001",
            content="Permanent belief",
            belief_type="inference",
            confidence=0.8,
            basis=[],
            contradicts=[],
            expires_at=None,
        )
        assert belief.is_expired() is False

    def test_with_confidence(self):
        """Test with_confidence returns new belief."""
        original = Belief(
            belief_id="belief_001",
            content="Test belief",
            belief_type="inference",
            confidence=0.5,
            basis=[],
            contradicts=[],
        )
        updated = original.with_confidence(0.9)
        assert original.confidence == 0.5
        assert updated.confidence == 0.9

    def test_with_confidence_validation(self):
        """Test confidence validation."""
        belief = Belief(
            belief_id="belief_001",
            content="Test",
            belief_type="inference",
            confidence=0.5,
            basis=[],
            contradicts=[],
        )
        with pytest.raises(ValueError):
            belief.with_confidence(1.5)
        with pytest.raises(ValueError):
            belief.with_confidence(-0.1)

    def test_add_basis(self):
        """Test adding basis evidence."""
        belief = Belief(
            belief_id="belief_001",
            content="Test",
            belief_type="inference",
            confidence=0.5,
            basis=["evidence_001"],
            contradicts=[],
        )
        updated = belief.add_basis("evidence_002")
        assert len(belief.basis) == 1  # Original unchanged
        assert len(updated.basis) == 2
        assert "evidence_002" in updated.basis

    def test_add_contradiction(self):
        """Test adding contradicting evidence."""
        belief = Belief(
            belief_id="belief_001",
            content="Test",
            belief_type="inference",
            confidence=0.5,
            basis=[],
            contradicts=["evidence_001"],
        )
        updated = belief.add_contradiction("evidence_002")
        assert len(belief.contradicts) == 1
        assert len(updated.contradicts) == 2


class TestBeliefConflict:
    """Test BeliefConflict dataclass."""

    def test_create_conflict(self):
        """Test creating BeliefConflict."""
        conflict = BeliefConflict(
            belief1_id="belief_001",
            belief2_id="belief_002",
            conflict_type="content_conflict",
            severity="high",
        )
        assert conflict.belief1_id == "belief_001"
        assert conflict.belief2_id == "belief_002"
        assert conflict.conflict_type == "content_conflict"
        assert conflict.severity == "high"


class TestBeliefState:
    """Test BeliefState operations."""

    def test_add_belief(self):
        """Test adding belief."""
        state = BeliefState()
        belief = Belief(
            belief_id="belief_001",
            content="User prefers dark mode",
            belief_type="inference",
            confidence=0.8,
            basis=["evidence_001"],
            contradicts=[],
        )
        result_id = state.add(belief)
        assert result_id == "belief_001"

    def test_get_belief(self):
        """Test retrieving belief."""
        state = BeliefState()
        belief = Belief(
            belief_id="belief_001",
            content="Test",
            belief_type="inference",
            confidence=0.8,
            basis=[],
            contradicts=[],
        )
        state.add(belief)
        retrieved = state.get("belief_001")
        assert retrieved is not None
        assert retrieved.belief_id == "belief_001"

    def test_get_missing_belief(self):
        """Test retrieving non-existent belief."""
        state = BeliefState()
        result = state.get("nonexistent")
        assert result is None

    def test_query_by_type(self):
        """Test querying beliefs by type."""
        state = BeliefState()
        state.add(Belief(
            belief_id="belief_001",
            content="Inference 1",
            belief_type="inference",
            confidence=0.8,
            basis=[],
            contradicts=[],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Hunch 1",
            belief_type="hunch",
            confidence=0.4,
            basis=[],
            contradicts=[],
        ))
        results = state.query(belief_type="inference")
        assert len(results) == 1
        assert results[0].belief_id == "belief_001"

    def test_query_by_min_confidence(self):
        """Test querying beliefs by minimum confidence."""
        state = BeliefState()
        state.add(Belief(
            belief_id="belief_001",
            content="High confidence",
            belief_type="inference",
            confidence=0.9,
            basis=[],
            contradicts=[],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Low confidence",
            belief_type="hunch",
            confidence=0.3,
            basis=[],
            contradicts=[],
        ))
        results = state.query(min_confidence=0.5)
        assert len(results) == 1
        assert results[0].confidence == 0.9

    def test_query_exclude_expired(self):
        """Test querying with expired exclusion."""
        state = BeliefState()
        expired = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        valid = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        state.add(Belief(
            belief_id="belief_001",
            content="Valid",
            belief_type="inference",
            confidence=0.8,
            basis=[],
            contradicts=[],
            expires_at=valid,
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Expired",
            belief_type="hunch",
            confidence=0.8,
            basis=[],
            contradicts=[],
            expires_at=expired,
        ))
        results = state.query(exclude_expired=True)
        assert len(results) == 1
        assert results[0].belief_id == "belief_001"

    def test_update_belief(self):
        """Test updating belief."""
        state = BeliefState()
        belief = Belief(
            belief_id="belief_001",
            content="Original",
            belief_type="inference",
            confidence=0.5,
            basis=[],
            contradicts=[],
        )
        state.add(belief)
        result = state.update("belief_001", content="Updated", confidence=0.9)
        assert result is True
        updated = state.get("belief_001")
        assert updated.content == "Updated"
        assert updated.confidence == 0.9

    def test_update_missing_belief(self):
        """Test updating non-existent belief."""
        state = BeliefState()
        result = state.update("nonexistent", content="Updated")
        assert result is False

    def test_remove_belief(self):
        """Test removing belief."""
        state = BeliefState()
        belief = Belief(
            belief_id="belief_001",
            content="Test",
            belief_type="inference",
            confidence=0.8,
            basis=[],
            contradicts=[],
        )
        state.add(belief)
        result = state.remove("belief_001")
        assert result is True
        assert state.get("belief_001") is None

    def test_remove_missing_belief(self):
        """Test removing non-existent belief."""
        state = BeliefState()
        result = state.remove("nonexistent")
        assert result is False

    def test_get_by_basis(self):
        """Test getting beliefs by basis evidence."""
        state = BeliefState()
        state.add(Belief(
            belief_id="belief_001",
            content="Based on evidence",
            belief_type="inference",
            confidence=0.8,
            basis=["evidence_001", "evidence_002"],
            contradicts=[],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Different basis",
            belief_type="hunch",
            confidence=0.5,
            basis=["evidence_003"],
            contradicts=[],
        ))
        results = state.get_by_basis("evidence_001")
        assert len(results) == 1
        assert results[0].belief_id == "belief_001"

    def test_get_conflicting_beliefs(self):
        """Test getting beliefs that contradict evidence."""
        state = BeliefState()
        state.add(Belief(
            belief_id="belief_001",
            content="Contradicts evidence",
            belief_type="hunch",
            confidence=0.5,
            basis=[],
            contradicts=["evidence_001"],
        ))
        results = state.get_conflicting_beliefs("evidence_001")
        assert len(results) == 1
        assert results[0].belief_id == "belief_001"

    def test_conflict_detection_content(self):
        """Test automatic conflict detection for same content with different confidence."""
        state = BeliefState()
        state.add(Belief(
            belief_id="belief_001",
            content="Same content",
            belief_type="inference",
            confidence=0.9,
            basis=[],
            contradicts=[],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Same content",
            belief_type="hunch",
            confidence=0.4,  # Different by > 0.3
            basis=[],
            contradicts=[],
        ))
        conflicts = state.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "content_conflict"

    def test_conflict_no_detection_similar_confidence(self):
        """Test no conflict for similar confidence levels."""
        state = BeliefState()
        state.add(Belief(
            belief_id="belief_001",
            content="Same content",
            belief_type="inference",
            confidence=0.9,
            basis=[],
            contradicts=[],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Same content",
            belief_type="inference",
            confidence=0.85,  # Different by < 0.3
            basis=[],
            contradicts=[],
        ))
        conflicts = state.get_conflicts()
        assert len(conflicts) == 0

    def test_conflict_detection_evidence(self):
        """Test conflict detection via evidence."""
        state = BeliefState()
        state.add(Belief(
            belief_id="belief_001",
            content="Belief 1",
            belief_type="inference",
            confidence=0.8,
            basis=[],
            contradicts=["belief_002"],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Belief 2",
            belief_type="inference",
            confidence=0.8,
            basis=[],
            contradicts=[],
        ))
        conflicts = state.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "evidence_conflict"
        assert conflicts[0].severity == "high"

    def test_conflict_severity_calculation(self):
        """Test conflict severity based on confidence."""
        state = BeliefState()
        # High confidence conflict = high severity
        state.add(Belief(
            belief_id="belief_001",
            content="Same",
            belief_type="inference",
            confidence=0.95,
            basis=[],
            contradicts=[],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Same",
            belief_type="hunch",
            confidence=0.4,
            basis=[],
            contradicts=[],
        ))
        conflicts = state.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].severity == "medium"  # Avg confidence (0.95+0.4)/2 = 0.675

    def test_get_conflicts_excludes_expired(self):
        """Test that expired beliefs are excluded from active conflicts."""
        state = BeliefState()
        expired = (datetime.utcnow() - timedelta(hours=1)).isoformat()

        state.add(Belief(
            belief_id="belief_001",
            content="Active",
            belief_type="inference",
            confidence=0.9,
            basis=[],
            contradicts=[],
        ))
        state.add(Belief(
            belief_id="belief_002",
            content="Same",
            belief_type="hunch",
            confidence=0.4,
            basis=[],
            contradicts=[],
            expires_at=expired,
        ))
        conflicts = state.get_conflicts()
        # Conflict should not appear because one belief is expired
        assert len(conflicts) == 0
