"""Fact Anchoring Integration (Task G + P).

Bridges Memory operations with EvidenceStore for automatic fact anchoring.
Every memory fact gets anchored to evidence with full provenance tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from jarvis.brain_core.memory_service import MemoryService
from jarvis.world_model.evidence_store import EvidenceStore, Evidence, Provenance


@dataclass
class AnchoredMemoryResult:
    """Result of anchoring a memory fact to evidence."""

    success: bool
    memory_key: str
    memory_value: str
    evidence_id: str | None = None
    anchor_id: str | None = None
    error: str | None = None


class FactAnchoredMemory:
    """Memory wrapper that automatically anchors facts to evidence.

    Usage:
        evidence_store = EvidenceStore()
        memory_service = MemoryService(db_path)
        anchored = FactAnchoredMemory(evidence_store, memory_service)

        # Save with automatic anchoring
        result = anchored.save_anchored(
            key="user_name",
            value="Billy",
            confidence=0.95,
            source="conversation",
            source_id=turn_id,
            utterance="my name is Billy"
        )

        # Query anchored facts
        chains = anchored.get_fact_provenance("user_name")
    """

    def __init__(
        self,
        evidence_store: EvidenceStore,
        memory_service: MemoryService,
    ) -> None:
        self.evidence_store = evidence_store
        self.memory_service = memory_service

    def save_anchored(
        self,
        key: str,
        value: str,
        confidence: float,
        source: str = "conversation",
        source_id: str | None = None,
        utterance: str | None = None,
        anchor_type: str = "direct",
    ) -> AnchoredMemoryResult:
        """Save a memory fact and anchor it to evidence.

        Creates evidence from the memory operation, then anchors the fact
        to that evidence for full provenance tracking.

        Args:
            key: Memory key
            value: Memory value
            confidence: Confidence score (0.0-1.0)
            source: Source type ("conversation", "tool", "inference")
            source_id: ID of the source (turn_id, tool_call_id)
            utterance: Original utterance
            anchor_type: "direct", "inferred", or "corroborated"

        Returns:
            AnchoredMemoryResult with success status and IDs
        """
        try:
            # Step 1: Create evidence for this memory operation
            timestamp = datetime.now(timezone.utc).isoformat()
            evidence_id = f"mem_{key}_{timestamp.replace(':', '_')}"

            evidence = Evidence(
                evidence_id=evidence_id,
                evidence_type="memory_operation",
                content={"key": key, "value": value},
                source=source,
                timestamp=timestamp,
                confidence=confidence,
                provenance=Provenance(
                    source=source,
                    transform="memory_remember",
                    result_id=source_id,
                    metadata={"utterance": utterance} if utterance else {},
                ),
            )

            # Step 2: Add evidence to store
            self.evidence_store.add(evidence)

            # Step 3: Save to memory with provenance
            saved = self.memory_service.save(
                key=key,
                value=value,
                confidence=confidence,
                source=source,
                source_id=evidence_id,  # Link back to evidence
                utterance=utterance,
                replace_existing=True,
            )

            if not saved:
                return AnchoredMemoryResult(
                    success=False,
                    memory_key=key,
                    memory_value=value,
                    error="Memory service failed to save",
                )

            # Step 4: Anchor fact to evidence
            anchor = self.evidence_store.anchor_fact(
                fact_key=key,
                evidence_id=evidence_id,
                anchor_type=anchor_type,
                confidence=confidence,
                metadata={"utterance": utterance} if utterance else {},
            )

            return AnchoredMemoryResult(
                success=True,
                memory_key=key,
                memory_value=value,
                evidence_id=evidence_id,
                anchor_id=anchor.anchor_id,
            )

        except Exception as e:
            return AnchoredMemoryResult(
                success=False,
                memory_key=key,
                memory_value=value,
                error=str(e),
            )

    def get_fact_provenance(self, fact_key: str) -> dict[str, Any]:
        """Get full provenance chain for a fact."""
        return self.evidence_store.get_fact_anchor_chain(fact_key)

    def query_by_source(self, source: str) -> list[dict[str, Any]]:
        """Query all facts anchored to evidence from a specific source."""
        results = []
        for fact_key in self.evidence_store.get_all_anchored_facts():
            anchors = self.evidence_store.get_fact_anchors(fact_key)
            for anchor in anchors:
                evidence = self.evidence_store.get(anchor.evidence_id)
                if evidence and evidence.source == source:
                    results.append(
                        {
                            "fact_key": fact_key,
                            "anchor_id": anchor.anchor_id,
                            "evidence_id": anchor.evidence_id,
                            "source": source,
                            "confidence": anchor.confidence,
                        }
                    )
        return results

    def get_unanchored_facts(self) -> list[str]:
        """Find memory facts without evidence anchors.

        Compares memory contents against anchored facts to identify
        facts that were saved without going through the anchoring process.
        """
        # This would require a memory service method to list all keys
        # For now, return empty - can be extended
        return []
