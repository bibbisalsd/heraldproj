"""Tests for Fact Anchoring (Task G) and Memory Provenance (Task P)."""
from __future__ import annotations


import pytest
from jarvis.world_model.evidence_store import EvidenceStore, Evidence, Provenance, FactAnchor
from jarvis.world_model.fact_anchoring import FactAnchoredMemory, AnchoredMemoryResult
from jarvis.brain_core.memory_service import MemoryService, MemoryRecord
import tempfile
import os


@pytest.fixture
def evidence_store():
    """Create fresh EvidenceStore for each test."""
    return EvidenceStore()


@pytest.fixture
def memory_service():
    """Create MemoryService with temp database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_memory.sqlite")
        service = MemoryService(db_path=db_path)
        yield service


@pytest.fixture
def anchored_memory(evidence_store, memory_service):
    """Create FactAnchoredMemory integration."""
    return FactAnchoredMemory(evidence_store, memory_service)


class TestFactAnchor:
    """Test FactAnchor dataclass."""

    def test_anchor_creation(self):
        """Test creating a FactAnchor."""
        anchor = FactAnchor(
            anchor_id="test_anchor_123",
            fact_key="user_name",
            evidence_id="evidence_001",
            anchor_type="direct",
            confidence=0.95,
        )
        assert anchor.anchor_id == "test_anchor_123"
        assert anchor.fact_key == "user_name"
        assert anchor.evidence_id == "evidence_001"
        assert anchor.anchor_type == "direct"
        assert anchor.confidence == 0.95

    def test_anchor_immutable(self):
        """Test that FactAnchor is frozen (immutable)."""
        anchor = FactAnchor(
            anchor_id="test_anchor_123",
            fact_key="user_name",
            evidence_id="evidence_001",
            anchor_type="direct",
            confidence=0.95,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            anchor.confidence = 0.5


class TestEvidenceStoreAnchoring:
    """Test Fact Anchoring in EvidenceStore."""

    def test_anchor_fact(self, evidence_store):
        """Test anchoring a fact to evidence."""
        # Create evidence first
        evidence = Evidence(
            evidence_id="ev_001",
            evidence_type="tool_result",
            content={"result": "success"},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.95,
            provenance=Provenance(source="calculator"),
        )
        evidence_store.add(evidence)

        # Anchor fact to evidence
        anchor = evidence_store.anchor_fact(
            fact_key="calc_result",
            evidence_id="ev_001",
            anchor_type="direct",
            confidence=0.95,
        )

        assert anchor.fact_key == "calc_result"
        assert anchor.evidence_id == "ev_001"
        assert anchor.anchor_type == "direct"

    def test_anchor_to_nonexistent_evidence(self, evidence_store):
        """Test that anchoring to non-existent evidence raises error."""
        with pytest.raises(ValueError, match="non-existent evidence"):
            evidence_store.anchor_fact(
                fact_key="orphan_fact",
                evidence_id="does_not_exist",
            )

    def test_get_fact_anchors(self, evidence_store):
        """Test retrieving anchors for a fact."""
        evidence = Evidence(
            evidence_id="ev_001",
            evidence_type="conversation",
            content="User said their name is Billy",
            source="user_input",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="user_input"),
        )
        evidence_store.add(evidence)

        # Add multiple anchors
        anchor1 = evidence_store.anchor_fact("user_name", "ev_001", "direct", 0.9)
        anchor2 = evidence_store.anchor_fact("user_name", "ev_001", "corroborated", 0.95)

        anchors = evidence_store.get_fact_anchors("user_name")
        assert len(anchors) == 2
        assert {a.anchor_id for a in anchors} == {anchor1.anchor_id, anchor2.anchor_id}

    def test_get_anchored_evidence(self, evidence_store):
        """Test retrieving evidence anchored to a fact."""
        evidence1 = Evidence(
            evidence_id="ev_001",
            evidence_type="tool_result",
            content={"name": "Billy"},
            source="memory_lookup",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="memory_lookup"),
        )
        evidence_store.add(evidence1)
        evidence_store.anchor_fact("user_name", "ev_001")

        anchored_evidence = evidence_store.get_anchored_evidence("user_name")
        assert len(anchored_evidence) == 1
        assert anchored_evidence[0].evidence_id == "ev_001"

    def test_get_fact_anchor_chain(self, evidence_store):
        """Test getting full provenance chain for a fact."""
        evidence = Evidence(
            evidence_id="ev_001",
            evidence_type="memory_operation",
            content={"key": "user_name", "value": "Billy"},
            source="conversation",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.95,
            provenance=Provenance(
                source="conversation",
                transform="memory_remember",
                result_id="turn_123",
                metadata={"utterance": "my name is Billy"},
            ),
        )
        evidence_store.add(evidence)
        evidence_store.anchor_fact("user_name", "ev_001", "direct", 0.95)

        chain = evidence_store.get_fact_anchor_chain("user_name")

        assert chain["fact_key"] == "user_name"
        assert chain["total_anchors"] == 1
        assert len(chain["anchors"]) == 1
        assert len(chain["evidence_chains"]) == 1

    def test_remove_fact_anchor(self, evidence_store):
        """Test removing a specific anchor."""
        evidence = Evidence(
            evidence_id="ev_001",
            evidence_type="test",
            content="test",
            source="test",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="test"),
        )
        evidence_store.add(evidence)
        anchor = evidence_store.anchor_fact("test_fact", "ev_001")

        # Remove the anchor
        removed = evidence_store.remove_fact_anchor("test_fact", anchor.anchor_id)
        assert removed is True

        # Verify removal
        anchors = evidence_store.get_fact_anchors("test_fact")
        assert len(anchors) == 0

    def test_get_all_anchored_facts(self, evidence_store):
        """Test listing all anchored facts."""
        ev1 = Evidence(
            evidence_id="ev_001",
            evidence_type="test",
            content="test1",
            source="test",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="test"),
        )
        ev2 = Evidence(
            evidence_id="ev_002",
            evidence_type="test",
            content="test2",
            source="test",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="test"),
        )
        evidence_store.add(ev1)
        evidence_store.add(ev2)

        evidence_store.anchor_fact("fact_a", "ev_001")
        evidence_store.anchor_fact("fact_b", "ev_002")

        facts = evidence_store.get_all_anchored_facts()
        assert set(facts) == {"fact_a", "fact_b"}


class TestMemoryProvenance:
    """Test Memory Provenance tracking."""

    def test_save_with_provenance(self, memory_service):
        """Test saving memory with provenance fields."""
        result = memory_service.save(
            key="user_name",
            value="Billy",
            confidence=0.95,
            source="conversation",
            source_id="turn_123",
            utterance="my name is Billy",
        )
        assert result is True

        # Retrieve and verify provenance
        records = memory_service.retrieve("user_name")
        assert len(records) == 1
        record = records[0]
        assert record.source == "conversation"
        assert record.source_id == "turn_123"
        assert record.utterance == "my name is Billy"

    def test_retrieve_with_provenance(self, memory_service):
        """Test retrieving memory preserves provenance."""
        memory_service.save(
            key="test_key",
            value="test_value",
            confidence=0.9,
            source="tool",
            source_id="tool_call_456",
            utterance=None,
        )

        records = memory_service.retrieve("test_key")
        assert len(records) == 1
        assert records[0].source == "tool"
        assert records[0].source_id == "tool_call_456"

    def test_search_includes_provenance(self, memory_service):
        """Test that search results include provenance when available.

        Note: This tests exact match retrieval (semantic search requires
        Ollama embedding model running). Exact matches should include provenance.
        """
        memory_service.save(
            key="user_preference",
            value="likes dark mode",
            confidence=0.85,
            source="conversation",
            source_id="turn_999",
            utterance="I prefer dark mode",
        )

        # Test exact key match (doesn't require embeddings)
        results = memory_service.search("user_preference", top_k=5)
        assert len(results) >= 1
        record = results[0]
        assert record.source == "conversation"
        assert record.source_id == "turn_999"
        assert record.utterance == "I prefer dark mode"


class TestFactAnchoredMemory:
    """Test FactAnchoredMemory integration."""

    def test_save_anchored(self, anchored_memory):
        """Test saving with automatic anchoring."""
        result = anchored_memory.save_anchored(
            key="user_name",
            value="Billy",
            confidence=0.95,
            source="conversation",
            source_id="turn_001",
            utterance="my name is Billy",
            anchor_type="direct",
        )

        assert result.success is True
        assert result.memory_key == "user_name"
        assert result.memory_value == "Billy"
        assert result.evidence_id is not None
        assert result.anchor_id is not None
        assert result.error is None

    def test_save_anchored_low_confidence(self, anchored_memory):
        """Test that low confidence fails."""
        result = anchored_memory.save_anchored(
            key="test",
            value="test",
            confidence=0.5,  # Below threshold
        )
        assert result.success is False
        assert "failed" in result.error.lower()

    def test_get_fact_provenance(self, anchored_memory):
        """Test retrieving full provenance chain."""
        anchored_memory.save_anchored(
            key="test_fact",
            value="test_value",
            confidence=0.9,
            source="test",
        )

        provenance = anchored_memory.get_fact_provenance("test_fact")
        assert provenance["fact_key"] == "test_fact"
        assert provenance["total_anchors"] >= 1
        assert "evidence_chains" in provenance

    def test_query_by_source(self, anchored_memory):
        """Test querying facts by source type."""
        anchored_memory.save_anchored(
            key="conv_fact",
            value="from conversation",
            confidence=0.9,
            source="conversation",
        )
        anchored_memory.save_anchored(
            key="tool_fact",
            value="from tool",
            confidence=0.9,
            source="tool",
        )

        conv_results = anchored_memory.query_by_source("conversation")
        tool_results = anchored_memory.query_by_source("tool")

        assert len(conv_results) >= 1
        assert len(tool_results) >= 1
        assert any(r["fact_key"] == "conv_fact" for r in conv_results)
        assert any(r["fact_key"] == "tool_fact" for r in tool_results)


class TestMemoryRecordProvenance:
    """Test MemoryRecord with provenance fields."""

    def test_memory_record_with_provenance(self):
        """Test creating MemoryRecord with provenance."""
        record = MemoryRecord(
            key="user_name",
            value="Billy",
            confidence=0.95,
            created_at="2026-04-05T00:00:00Z",
            id=1,
            source="conversation",
            source_id="turn_123",
            utterance="my name is Billy",
        )
        assert record.source == "conversation"
        assert record.source_id == "turn_123"
        assert record.utterance == "my name is Billy"

    def test_memory_record_backward_compatible(self):
        """Test MemoryRecord works without provenance (backward compat)."""
        record = MemoryRecord(
            key="old_fact",
            value="old_value",
            confidence=0.9,
            created_at="2026-04-05T00:00:00Z",
        )
        assert record.source is None
        assert record.source_id is None
        assert record.utterance is None
