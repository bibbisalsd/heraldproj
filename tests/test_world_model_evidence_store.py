"""Tests for EvidenceStore with provenance tracking."""
from __future__ import annotations


import pytest
from datetime import datetime, timezone

from jarvis.world_model.evidence_store import Evidence, EvidenceStore, Provenance, EvidenceQuery


class TestProvenance:
    """Test Provenance dataclass."""

    def test_create_provenance_minimal(self):
        """Test creating Provenance with minimal fields."""
        prov = Provenance(source="tool_calculator")
        assert prov.source == "tool_calculator"
        assert prov.transform is None
        assert prov.result_id is None
        assert prov.metadata == {}

    def test_create_provenance_full(self):
        """Test creating Provenance with all fields."""
        prov = Provenance(
            source="tool_calculator",
            transform="result_formatter",
            result_id="result_001",
            metadata={"elapsed_ms": 50},
        )
        assert prov.source == "tool_calculator"
        assert prov.transform == "result_formatter"
        assert prov.result_id == "result_001"
        assert prov.metadata["elapsed_ms"] == 50


class TestEvidence:
    """Test Evidence dataclass."""

    def test_create_evidence(self):
        """Test creating Evidence."""
        evidence = Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        )
        assert evidence.evidence_id == "evidence_001"
        assert evidence.evidence_type == "tool_result"
        assert evidence.content == {"result": 42}
        assert evidence.confidence == 0.9

    def test_with_transform(self):
        """Test with_transform creates derived evidence."""
        original = Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        )
        derived = original.with_transform("formatted")
        assert derived.evidence_id == "evidence_001_formatted"
        assert derived.provenance.transform == "formatted"
        assert derived.provenance.result_id == "evidence_001"


class TestEvidenceStore:
    """Test EvidenceStore operations."""

    def test_add_evidence(self):
        """Test adding evidence."""
        store = EvidenceStore()
        evidence = Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        )
        result_id = store.add(evidence)
        assert result_id == "evidence_001"

    def test_get_evidence(self):
        """Test retrieving evidence."""
        store = EvidenceStore()
        evidence = Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        )
        store.add(evidence)
        retrieved = store.get("evidence_001")
        assert retrieved is not None
        assert retrieved.evidence_id == "evidence_001"

    def test_get_missing_evidence(self):
        """Test retrieving non-existent evidence."""
        store = EvidenceStore()
        result = store.get("nonexistent")
        assert result is None

    def test_query_by_type(self):
        """Test querying evidence by type."""
        store = EvidenceStore()
        store.add(Evidence(
            evidence_id="tool_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        store.add(Evidence(
            evidence_id="file_001",
            evidence_type="file_read",
            content="file content",
            source="file_read",
            timestamp="2026-04-05T00:00:01Z",
            confidence=0.95,
            provenance=Provenance(source="file_read"),
        ))
        results = store.query(EvidenceQuery(evidence_type="tool_result"))
        assert len(results) == 1
        assert results[0].evidence_id == "tool_001"

    def test_query_by_source(self):
        """Test querying evidence by source."""
        store = EvidenceStore()
        store.add(Evidence(
            evidence_id="tool_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        store.add(Evidence(
            evidence_id="tool_002",
            evidence_type="tool_result",
            content={"result": 100},
            source="web_search",
            timestamp="2026-04-05T00:00:01Z",
            confidence=0.8,
            provenance=Provenance(source="web_search"),
        ))
        results = store.query(EvidenceQuery(source="calculator"))
        assert len(results) == 1
        assert results[0].source == "calculator"

    def test_query_by_min_confidence(self):
        """Test querying evidence by minimum confidence."""
        store = EvidenceStore()
        store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        store.add(Evidence(
            evidence_id="evidence_002",
            evidence_type="tool_result",
            content={},
            source="calculator",
            timestamp="2026-04-05T00:00:01Z",
            confidence=0.5,
            provenance=Provenance(source="calculator"),
        ))
        results = store.query(EvidenceQuery(min_confidence=0.8))
        assert len(results) == 1
        assert results[0].confidence == 0.9

    def test_query_by_time_range(self):
        """Test querying evidence by time range."""
        store = EvidenceStore()
        store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        store.add(Evidence(
            evidence_id="evidence_002",
            evidence_type="tool_result",
            content={},
            source="calculator",
            timestamp="2026-04-05T01:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        results = store.query(EvidenceQuery(
            after="2026-04-05T00:30:00Z",
            before="2026-04-05T02:00:00Z",
        ))
        assert len(results) == 1
        assert results[0].evidence_id == "evidence_002"

    def test_query_limit(self):
        """Test query limit."""
        store = EvidenceStore()
        for i in range(10):
            store.add(Evidence(
                evidence_id=f"evidence_{i:03d}",
                evidence_type="tool_result",
                content={},
                source="calculator",
                timestamp=f"2026-04-05T00:00:{i:02d}Z",
                confidence=0.9,
                provenance=Provenance(source="calculator"),
            ))
        results = store.query(EvidenceQuery(limit=5))
        assert len(results) == 5

    def test_query_sorted_by_timestamp_desc(self):
        """Test query results sorted by timestamp descending."""
        store = EvidenceStore()
        for i in range(5):
            store.add(Evidence(
                evidence_id=f"evidence_{i:03d}",
                evidence_type="tool_result",
                content={},
                source="calculator",
                timestamp=f"2026-04-05T00:00:{i:02d}Z",
                confidence=0.9,
                provenance=Provenance(source="calculator"),
            ))
        results = store.query(EvidenceQuery(limit=10))
        assert results[0].evidence_id == "evidence_004"  # Most recent first

    def test_get_provenance_chain(self):
        """Test getting provenance chain."""
        store = EvidenceStore()
        # Create chain: evidence_003 -> evidence_002 -> evidence_001
        store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"raw": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        store.add(Evidence(
            evidence_id="evidence_002",
            evidence_type="tool_result",
            content={"formatted": "42"},
            source="formatter",
            timestamp="2026-04-05T00:00:01Z",
            confidence=0.9,
            provenance=Provenance(source="formatter", result_id="evidence_001"),
        ))
        store.add(Evidence(
            evidence_id="evidence_003",
            evidence_type="tool_result",
            content={"display": "Result: 42"},
            source="display",
            timestamp="2026-04-05T00:00:02Z",
            confidence=0.9,
            provenance=Provenance(source="display", result_id="evidence_002"),
        ))
        chain = store.get_provenance_chain("evidence_003")
        assert len(chain) == 3
        assert chain[0].evidence_id == "evidence_001"  # Root first

    def test_update_source_reliability(self):
        """Test updating source reliability."""
        store = EvidenceStore()
        store.update_source_reliability("calculator", 0.95)
        assert store.get_source_reliability("calculator") == 0.95

    def test_source_reliability_default(self):
        """Test default source reliability."""
        store = EvidenceStore()
        assert store.get_source_reliability("unknown_source") == 0.5

    def test_source_reliability_validation(self):
        """Test source reliability validation."""
        store = EvidenceStore()
        with pytest.raises(ValueError):
            store.update_source_reliability("calculator", 1.5)
        with pytest.raises(ValueError):
            store.update_source_reliability("calculator", -0.1)

    def test_corroboration_tracking(self):
        """Test corroboration tracking."""
        store = EvidenceStore()
        # Add identical evidence (should corroborate)
        store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="calculator",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="calculator"),
        ))
        store.add(Evidence(
            evidence_id="evidence_002",
            evidence_type="tool_result",
            content={"result": 42},  # Same content
            source="web_search",
            timestamp="2026-04-05T00:00:01Z",
            confidence=0.8,
            provenance=Provenance(source="web_search"),
        ))
        assert store.get_corroboration_count("evidence_001") == 1

    def test_contradiction_tracking(self):
        """Test contradiction tracking."""
        store = EvidenceStore()
        store.add(Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content="true",
            source="source1",
            timestamp="2026-04-05T00:00:00Z",
            confidence=0.9,
            provenance=Provenance(source="source1"),
        ))
        store.add(Evidence(
            evidence_id="evidence_002",
            evidence_type="tool_result",
            content="false",  # Contradiction
            source="source2",
            timestamp="2026-04-05T00:00:01Z",
            confidence=0.9,
            provenance=Provenance(source="source2"),
        ))
        assert store.has_contradictions("evidence_001")
        assert "evidence_002" in store.get_contradictions("evidence_001")

    def test_get_effective_confidence(self):
        """Test effective confidence calculation."""
        store = EvidenceStore()
        store.update_source_reliability("reliable_source", 1.0)
        evidence = Evidence(
            evidence_id="evidence_001",
            evidence_type="tool_result",
            content={"result": 42},
            source="reliable_source",
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=0.9,
            provenance=Provenance(source="reliable_source"),
        )
        store.add(evidence)
        effective = store.get_effective_confidence("evidence_001")
        # Should be high due to reliable source and no contradictions
        assert effective > 0.7
