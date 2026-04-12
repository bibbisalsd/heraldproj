"""EvidenceStore - Store tool results, file reads, OCR results with provenance.

Supports Fact Anchoring (Task G):
- All facts anchored to specific evidence sources
- Traceable provenance chains
- Source reliability scoring
"""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class Provenance:
    """Full provenance chain: source → transform → result."""

    source: str
    transform: str | None = None
    result_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactAnchor:
    """Anchors a fact to its evidence source with full traceability.

    Fact Anchoring (Task G) primitive:
    - Every fact must have at least one anchor
    - Anchors are immutable once created
    - Anchors can be chained (derived facts)
    """

    anchor_id: str
    fact_key: str  # The fact being anchored
    evidence_id: str  # The evidence supporting this fact
    anchor_type: str  # "direct", "inferred", "corroborated"
    confidence: float
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    """Evidence item with full provenance tracking."""

    evidence_id: str
    evidence_type: str  # "tool_result", "file_read", "ocr_result", "screen_capture"
    content: Any
    source: str
    timestamp: str
    confidence: float
    provenance: Provenance

    def with_transform(self, transform: str) -> "Evidence":
        """Create derived evidence with a transform applied."""
        return Evidence(
            evidence_id=f"{self.evidence_id}_{transform}",
            evidence_type=self.evidence_type,
            content=self.content,
            source=self.source,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=self.confidence,
            provenance=Provenance(
                source=self.provenance.source,
                transform=transform,
                result_id=self.evidence_id,
                metadata=self.provenance.metadata,
            ),
        )


class EvidenceFilters(Protocol):
    """Protocol for evidence query filters."""

    evidence_type: str | None
    source: str | None
    min_confidence: float
    after: str | None
    before: str | None


@dataclass(frozen=True)
class EvidenceQuery:
    """Query filters for evidence."""

    evidence_type: str | None = None
    source: str | None = None
    min_confidence: float = 0.0
    after: str | None = None
    before: str | None = None
    limit: int = 100


class EvidenceStore:
    """Store evidence with full provenance tracking.

    Supports multi-dimensional uncertainty:
    - Source reliability score (0.0-1.0)
    - Recency decay factor
    - Corroboration count
    - Contradiction flags
    - Fact Anchoring (Task G): anchor facts to evidence sources
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._evidence: dict[str, Evidence] = {}
        self._source_reliability: dict[str, float] = {}
        self._corroboration: dict[
            str, list[str]
        ] = {}  # evidence_id -> supporting evidence_ids
        self._contradictions: dict[
            str, list[str]
        ] = {}  # evidence_id -> contradicting evidence_ids
        self._fact_anchors: dict[str, list[FactAnchor]] = {}  # fact_key -> anchors
        self._max_size = max_size

    def _evict_if_needed(self) -> None:
        """Evict oldest evidence if store exceeds max_size."""
        if len(self._evidence) <= self._max_size:
            return

        # Sort evidence by timestamp
        sorted_ids = sorted(
            self._evidence.keys(), key=lambda eid: self._evidence[eid].timestamp
        )

        # Evict oldest 10%
        to_evict = sorted_ids[: max(1, self._max_size // 10)]
        for eid in to_evict:
            self._evidence.pop(eid, None)
            self._corroboration.pop(eid, None)
            self._contradictions.pop(eid, None)
            # Remove from other items' corroboration/contradiction lists
            for other_list in self._corroboration.values():
                if eid in other_list:
                    other_list.remove(eid)
            for other_list in self._contradictions.values():
                if eid in other_list:
                    other_list.remove(eid)
            # Fact anchors might still point to evicted evidence - we keep them for history
            # but they will return None in get_anchored_evidence

    def ingest_packet(self, packet: Any) -> list[str]:
        """Ingest a verified EvidencePacket into the EvidenceStore."""
        evidence_ids = []
        if hasattr(packet, "tool_results"):
            for i, res in enumerate(packet.tool_results):
                evidence = Evidence(
                    evidence_id=f"packet_tool_{i}_{hash(str(res)) % 10000}",
                    evidence_type="tool_result",
                    content=res,
                    source="tool_orchestrator",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    confidence=0.95,
                    provenance=Provenance(source="tool_orchestrator"),
                )
                evidence_ids.append(self.add(evidence))
        if hasattr(packet, "verified_facts"):
            for i, fact in enumerate(packet.verified_facts):
                content = getattr(fact, "content", str(fact))
                source = getattr(fact, "source", "inference")
                evidence = Evidence(
                    evidence_id=f"packet_fact_{i}_{hash(str(content)) % 10000}",
                    evidence_type="verified_fact",
                    content=content,
                    source=source,
                    timestamp=getattr(fact, "timestamp", None) or datetime.now(timezone.utc).isoformat(),
                    confidence=getattr(fact, "confidence", 0.8),
                    provenance=Provenance(source="response_compiler"),
                )
                evidence_ids.append(self.add(evidence))
        return evidence_ids

    def add(self, evidence: Evidence) -> str:
        """Add evidence and return evidence_id."""
        self._evict_if_needed()
        self._evidence[evidence.evidence_id] = evidence

        # Initialize corroboration and contradiction tracking
        self._corroboration[evidence.evidence_id] = []
        self._contradictions[evidence.evidence_id] = []

        # Check for corroboration/contradiction with existing evidence
        for existing_id, existing in self._evidence.items():
            if existing_id == evidence.evidence_id:
                continue
            # Simple content-based corroboration check
            if self._content_matches(evidence.content, existing.content):
                self._corroboration[existing_id].append(evidence.evidence_id)
                self._corroboration[evidence.evidence_id].append(existing_id)
            elif self._content_contradicts(evidence.content, existing.content):
                self._contradictions[existing_id].append(evidence.evidence_id)
                self._contradictions[evidence.evidence_id].append(existing_id)

        return evidence.evidence_id

    def get(self, evidence_id: str) -> Evidence | None:
        """Get evidence by ID."""
        return self._evidence.get(evidence_id)

    def query(self, filters: EvidenceQuery) -> list[Evidence]:
        """Query evidence with filters."""
        results = []
        for evidence in self._evidence.values():
            # Filter by type
            if (
                filters.evidence_type
                and evidence.evidence_type != filters.evidence_type
            ):
                continue
            # Filter by source
            if filters.source and evidence.source != filters.source:
                continue
            # Filter by confidence
            if evidence.confidence < filters.min_confidence:
                continue
            # Filter by time range
            if filters.after and evidence.timestamp < filters.after:
                continue
            if filters.before and evidence.timestamp > filters.before:
                continue
            results.append(evidence)

        # Sort by timestamp descending (most recent first)
        results.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply limit
        return results[: filters.limit]

    def get_provenance_chain(self, evidence_id: str) -> list[Evidence]:
        """Get the full provenance chain for an evidence item."""
        chain = []
        current_id = evidence_id
        visited = set()

        while current_id and current_id not in visited:
            visited.add(current_id)
            evidence = self._evidence.get(current_id)
            if not evidence:
                break
            chain.append(evidence)
            current_id = evidence.provenance.result_id

        return list(reversed(chain))

    def update_source_reliability(self, source: str, reliability: float) -> None:
        """Update reliability score for a source."""
        if not 0.0 <= reliability <= 1.0:
            raise ValueError(
                f"Reliability must be between 0.0 and 1.0, got {reliability}"
            )
        self._source_reliability[source] = reliability

    def get_source_reliability(self, source: str) -> float:
        """Get reliability score for a source."""
        return self._source_reliability.get(source, 0.5)  # Default to 0.5

    def get_corroboration_count(self, evidence_id: str) -> int:
        """Get number of corroborating evidence items."""
        return len(self._corroboration.get(evidence_id, []))

    def has_contradictions(self, evidence_id: str) -> bool:
        """Check if evidence has any contradictions."""
        return len(self._contradictions.get(evidence_id, [])) > 0

    def get_contradictions(self, evidence_id: str) -> list[str]:
        """Get list of contradicting evidence IDs."""
        return list(self._contradictions.get(evidence_id, []))

    def get_effective_confidence(self, evidence_id: str) -> float:
        """Calculate effective confidence considering all factors."""
        evidence = self._evidence.get(evidence_id)
        if not evidence:
            return 0.0

        # Start with base confidence
        confidence = evidence.confidence

        # Apply source reliability
        source_rel = self.get_source_reliability(evidence.source)
        confidence *= source_rel

        # Apply recency decay (older evidence = lower confidence)
        evidence_time = datetime.fromisoformat(evidence.timestamp)
        # Handle timezone-aware and naive datetimes
        now = datetime.now(timezone.utc)
        if evidence_time.tzinfo is None:
            evidence_time = evidence_time.replace(tzinfo=timezone.utc)
        age_hours = (now - evidence_time).total_seconds() / 3600
        recency_decay = max(0.5, 1.0 - (age_hours / 24))  # Decay to 0.5 over 24 hours
        confidence *= recency_decay

        # Apply corroboration boost
        corrob_count = self.get_corroboration_count(evidence_id)
        corrob_boost = min(1.0, 1.0 + (corrob_count * 0.1))  # +10% per corrob, max +50%
        confidence *= corrob_boost

        # Apply contradiction penalty
        if self.has_contradictions(evidence_id):
            confidence *= 0.7  # -30% for contradictions

        return max(0.0, min(1.0, confidence))

    def _content_matches(self, content1: Any, content2: Any) -> bool:
        """Check if two content items corroborate each other."""
        # Simple string-based matching
        if isinstance(content1, str) and isinstance(content2, str):
            return content1.strip().lower() == content2.strip().lower()
        # Dict matching - check for overlapping key-value pairs
        if isinstance(content1, dict) and isinstance(content2, dict):
            common_keys = set(content1.keys()) & set(content2.keys())
            if not common_keys:
                return False
            # Check if values match for common keys
            matches = sum(1 for k in common_keys if content1[k] == content2[k])
            # Require at least 80% overlap on common keys to corroborate
            return (matches / len(common_keys)) >= 0.8
        return False

    def _content_contradicts(self, content1: Any, content2: Any) -> bool:
        """Check if two content items contradict each other."""
        # Simple contradiction detection
        if isinstance(content1, str) and isinstance(content2, str):
            # Check for explicit negation patterns
            negations = [
                ("true", "false"),
                ("yes", "no"),
                ("enabled", "disabled"),
                ("on", "off"),
                ("started", "stopped"),
                ("ok", "failed"),
                ("active", "inactive"),
                ("valid", "invalid"),
            ]
            c1_lower = content1.lower().strip()
            c2_lower = content2.lower().strip()
            for pos, neg in negations:
                if (pos == c1_lower and neg == c2_lower) or (
                    neg == c1_lower and pos == c2_lower
                ):
                    return True
        # Dict contradiction - same key, different value
        if isinstance(content1, dict) and isinstance(content2, dict):
            common_keys = set(content1.keys()) & set(content2.keys())
            for k in common_keys:
                if content1[k] != content2[k]:
                    # For boolean/status fields, this is a strong contradiction
                    v1, v2 = str(content1[k]).lower(), str(content2[k]).lower()
                    status_words = {
                        "true",
                        "false",
                        "ok",
                        "failed",
                        "active",
                        "inactive",
                    }
                    if v1 in status_words and v2 in status_words and v1 != v2:
                        return True
        return False

    # === Fact Anchoring (Task G) ===

    def anchor_fact(
        self,
        fact_key: str,
        evidence_id: str,
        anchor_type: str = "direct",
        confidence: float = 0.9,
        metadata: dict[str, Any] | None = None,
    ) -> FactAnchor:
        """Anchor a fact to specific evidence.

        Fact Anchoring ensures every fact has a traceable provenance chain.

        Args:
            fact_key: The fact being anchored (e.g., memory key, belief content)
            evidence_id: ID of supporting evidence in this store
            anchor_type: "direct" (tool output), "inferred" (reasoning), "corroborated" (multiple sources)
            confidence: Anchor confidence (0.0-1.0)
            metadata: Additional anchor metadata

        Returns:
            FactAnchor instance

        Raises:
            ValueError: If evidence_id doesn't exist in store
        """
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            raise ValueError(
                f"Cannot anchor fact to non-existent evidence: {evidence_id}"
            )

        import hashlib

        anchor_id = hashlib.sha256(
            f"{fact_key}:{evidence_id}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        anchor = FactAnchor(
            anchor_id=anchor_id,
            fact_key=fact_key,
            evidence_id=evidence_id,
            anchor_type=anchor_type,
            confidence=confidence,
            metadata=metadata or {},
        )

        if fact_key not in self._fact_anchors:
            self._fact_anchors[fact_key] = []
        self._fact_anchors[fact_key].append(anchor)

        return anchor

    def get_fact_anchors(self, fact_key: str) -> list[FactAnchor]:
        """Get all anchors for a fact."""
        return list(self._fact_anchors.get(fact_key, []))

    def get_anchored_evidence(self, fact_key: str) -> list[Evidence]:
        """Get all evidence anchored to a fact."""
        anchors = self.get_fact_anchors(fact_key)
        evidence_list: list[Evidence] = []
        for anchor in anchors:
            ev = self._evidence.get(anchor.evidence_id)
            if ev:
                evidence_list.append(ev)
        return evidence_list

    def get_fact_anchor_chain(self, fact_key: str) -> dict[str, Any]:
        """Get full provenance chain for a fact including all anchored evidence.

        Returns: dict with fact_key, anchors, and evidence_provenance_chains
        """
        anchors = self.get_fact_anchors(fact_key)
        evidence_chains = []

        for anchor in anchors:
            evidence = self._evidence.get(anchor.evidence_id)
            if evidence:
                provenance_chain = self.get_provenance_chain(anchor.evidence_id)
                evidence_chains.append(
                    {
                        "anchor": {
                            "anchor_id": anchor.anchor_id,
                            "anchor_type": anchor.anchor_type,
                            "confidence": anchor.confidence,
                            "created_at": anchor.created_at,
                        },
                        "evidence": {
                            "evidence_id": evidence.evidence_id,
                            "evidence_type": evidence.evidence_type,
                            "source": evidence.source,
                            "content": str(evidence.content)[
                                :200
                            ],  # Truncate for readability
                        },
                        "provenance_chain": [
                            {
                                "evidence_id": ev.evidence_id,
                                "source": ev.source,
                                "transform": ev.provenance.transform,
                            }
                            for ev in provenance_chain
                        ],
                    }
                )

        return {
            "fact_key": fact_key,
            "total_anchors": len(anchors),
            "anchors": [
                {
                    "anchor_id": a.anchor_id,
                    "anchor_type": a.anchor_type,
                    "confidence": a.confidence,
                    "evidence_id": a.evidence_id,
                }
                for a in anchors
            ],
            "evidence_chains": evidence_chains,
        }

    def remove_fact_anchor(self, fact_key: str, anchor_id: str) -> bool:
        """Remove a specific anchor for a fact."""
        if fact_key not in self._fact_anchors:
            return False

        original_count = len(self._fact_anchors[fact_key])
        self._fact_anchors[fact_key] = [
            a for a in self._fact_anchors[fact_key] if a.anchor_id != anchor_id
        ]

        # Clean up empty anchor lists
        if not self._fact_anchors[fact_key]:
            del self._fact_anchors[fact_key]

        return len(self._fact_anchors.get(fact_key, [])) < original_count

    def get_all_anchored_facts(self) -> list[str]:
        """Get list of all facts that have at least one anchor."""
        return list(self._fact_anchors.keys())

    def get_facts_without_anchors(self) -> list[str]:
        """Get facts that have no anchors (potential data integrity issue).

        Note: This requires external tracking of all facts.
        For now, returns empty list - can be extended if needed.
        """
        return []
