"""Response Compiler: Assembles evidence packets for LLM response compilation.

This module compiles structured evidence packets that are sent to the LLM.
The LLM's role is strictly to compile natural language responses from the
provided evidence - it cannot add facts, call tools, or make claims without
evidence backing.

Key principles:
- The brain gathers and verifies facts first
- The LLM compiles the answer second
- If evidence is insufficient, ask a clarifying question
- All claims are tagged with verification strength
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from jarvis.world_model.judge import Judge, Claim, ClaimContext
from jarvis.world_model.evidence_store import EvidenceStore

from .contracts import (
    EvidencePacket,
    MemoryInfo,
    TaskInfo,
    VerifiedFact,
    StylePolicy,
    TaggedFact,
)


@dataclass(frozen=True)
class TaggedResponsePacket:
    """Response packet with tagged claims for verification."""

    user_text: str
    facts: list[str]
    constraints: list[str]
    tone: str
    length_hint: str
    max_packet_tokens: int = 384
    overflowed: bool = False
    conversation_context: list[str] = field(default_factory=list)
    deterministic_fallback: str = ""
    tagged_claims: list[Claim] = field(default_factory=list)
    # NH-CRSIS Task G: Fact Anchoring fields
    tool_summaries: list[str] = field(default_factory=list)
    memory_items: list[str] = field(default_factory=list)
    job_snapshot: Optional[dict] = None
    # New evidence packet
    evidence_packet: Optional[EvidencePacket] = None


@dataclass(frozen=True)
class ResponsePacket:
    """Standard response packet (legacy compatibility)."""

    user_text: str
    facts: list[str]
    constraints: list[str]
    tone: str
    length_hint: str
    max_packet_tokens: int = 384
    overflowed: bool = False
    conversation_context: list[str] = field(default_factory=list)
    deterministic_fallback: str = ""
    tool_summaries: list[str] = field(default_factory=list)
    memory_items: list[str] = field(default_factory=list)
    job_snapshot: Optional[dict] = None


class ResponseCompiler:
    """Compiles structured evidence packets for LLM response generation.

    The compiler:
    1. Gathers facts from brain items, tool results, memory, and job status
    2. Tags each claim with verification strength (observed/recalled/inferred/guessed)
    3. Builds an EvidencePacket with strict structure
    4. Optionally produces legacy TaggedResponsePacket for compatibility

    The EvidencePacket can be converted to prompt text that instructs the LLM
    to compile responses from evidence only.
    """

    def __init__(
        self,
        max_packet_tokens: int = 384,
        judge: Judge | None = None,
        evidence_store: EvidenceStore | None = None,
    ) -> None:
        self.max_packet_tokens = max_packet_tokens
        self._judge = judge
        self._evidence_store = evidence_store

    def compile(
        self,
        evidence_packet: EvidencePacket,
        conversation_items: Iterable[str] | None = None,
        constraints: Iterable[str] | None = None,
        tone: str = "helpful",
        length_hint: str = "short",
        deterministic_fallback: str = "",
    ) -> TaggedResponsePacket:
        """Compile an evidence packet for LLM response generation.

        Args:
            evidence_packet: Verified evidence packet to compile from
            conversation_items: Recent conversation context
            constraints: Output constraints for the LLM
            tone: Output tone (helpful, concise, technical, casual)
            length_hint: Length hint (short, medium, long)
            deterministic_fallback: Fallback response if LLM unavailable

        Returns:
            TaggedResponsePacket with evidence and tagged claims
        """
        conversation_items = list(conversation_items or [])
        constraints = list(
            constraints or ["renderer_only_no_new_facts", "voice_friendly_output"]
        )

        # Extract items from evidence packet for legacy compatibility
        tool_summaries = evidence_packet.tool_results
        memory_items = [f"{m.key}:{m.value}" for m in evidence_packet.memory_info]
        job_snapshot = None
        if evidence_packet.task_info:
            job_snapshot = {
                "state": evidence_packet.task_info.state,
                "progress": evidence_packet.task_info.progress_percent,
            }

        # Build facts list (legacy format)
        facts: list[str] = []
        for vfact in evidence_packet.verified_facts:
            facts.append(f"{vfact.source}:{vfact.content}")
        if job_snapshot:
            facts.append(f"job_status:{job_snapshot.get('state', 'unknown')}")

        # Tag claims using Judge if available
        tagged_claims: list[Claim] = []

        if self._judge is not None:
            for item in tool_summaries:
                claim = self._judge.tag_claim(
                    claim_content=item,
                    context=ClaimContext(source="tool", has_evidence=True),
                )
                tagged_claims.append(claim)

            for item in memory_items:
                claim = self._judge.tag_claim(
                    claim_content=item,
                    context=ClaimContext(
                        source="memory",
                        from_memory=True,
                        memory_provenance="persistent",
                    ),
                )
                tagged_claims.append(claim)

        # Build legacy packet for compatibility
        packet = TaggedResponsePacket(
            user_text=evidence_packet.latest_user_message,
            facts=facts,
            constraints=constraints,
            tone=tone,
            length_hint=length_hint,
            max_packet_tokens=self.max_packet_tokens,
            overflowed=False,
            conversation_context=conversation_items,
            deterministic_fallback=deterministic_fallback,
            tagged_claims=tagged_claims,
            tool_summaries=list(tool_summaries),
            memory_items=list(memory_items),
            job_snapshot=job_snapshot,
            evidence_packet=evidence_packet,
        )

        # Check token budget
        token_estimate = self._estimate_tokens(packet)
        if token_estimate > self.max_packet_tokens:
            return self._truncate(packet)
        return packet

    def compile_evidence_only(
        self,
        user_text: str,
        verified_facts: list[TaggedFact | str],
        memory_info: list[MemoryInfo] | None = None,
        task_info: TaskInfo | None = None,
        resolved_reference_map: dict[str, str] | None = None,
        active_topic: str | None = None,
        active_subject: str | None = None,
        previous_message_context: str | None = None,
        tone: str = "helpful",
        length_hint: str = "short",
        address_preference: str | None = None,
    ) -> EvidencePacket:
        """Compile a strict evidence-only packet.

        This method produces an EvidencePacket without legacy compatibility.
        Use this for new code paths that don't need the old TaggedResponsePacket.

        Args:
            user_text: Original user input text
            verified_facts: list of verified facts (TaggedFact or string)
            memory_info: Optional memory information
            task_info: Optional task information
            resolved_reference_map: Map of resolved vague references
            active_topic: Current active topic
            active_subject: Current active subject
            previous_message_context: Previous turn context
            tone: Output tone
            length_hint: Length hint
            address_preference: User's preferred address term

        Returns:
            EvidencePacket ready for prompt conversion
        """
        # Build verified facts with provenance
        _verified_facts = []
        for fact in verified_facts:
            if hasattr(fact, "content") and hasattr(fact, "strength"):
                # It's a TaggedFact or similar
                _verified_facts.append(
                    VerifiedFact(
                        content=fact.content,
                        source=getattr(fact, "source", "provided"),
                        confidence=getattr(fact, "confidence", 0.95),
                        timestamp="",
                        verification_strength=fact.strength,
                    )
                )
            else:
                # It's a raw string
                _verified_facts.append(
                    VerifiedFact(
                        content=str(fact),
                        source="provided",
                        confidence=0.9,
                        timestamp="",
                        verification_strength="observed",
                    )
                )

        style_policy = StylePolicy(
            tone=tone,
            length_hint=length_hint,
            spoken_friendly=True,
            avoid_internal_ids=True,
            address_preference=address_preference,
        )

        return EvidencePacket(
            latest_user_message=user_text,
            resolved_intent="user_query",
            active_topic=active_topic,
            active_subject=active_subject,
            resolved_reference_map=resolved_reference_map or {},
            memory_info=memory_info or [],
            previous_message_context=previous_message_context,
            task_info=task_info,
            tools_used=[],
            tool_results=[],
            verified_facts=_verified_facts,
            inference_policy="evidence_only",
            style_policy=style_policy,
        )

    def _estimate_tokens(self, packet: ResponsePacket | TaggedResponsePacket) -> int:
        """Estimate token count for a packet."""
        total_text = " ".join(
            [packet.user_text]
            + packet.facts
            + packet.constraints
            + packet.conversation_context
        )
        return max(1, len(total_text.split()))

    def _truncate(self, packet: TaggedResponsePacket) -> TaggedResponsePacket:
        """Truncate packet to fit within token budget."""
        keep: list[str] = []
        for fact in packet.facts:
            candidate = TaggedResponsePacket(
                user_text=packet.user_text,
                facts=keep + [fact],
                constraints=packet.constraints,
                tone=packet.tone,
                length_hint=packet.length_hint,
                max_packet_tokens=packet.max_packet_tokens,
                conversation_context=packet.conversation_context,
                deterministic_fallback=packet.deterministic_fallback,
                tagged_claims=packet.tagged_claims,
                tool_summaries=packet.tool_summaries,
                memory_items=packet.memory_items,
                job_snapshot=packet.job_snapshot,
                evidence_packet=packet.evidence_packet,
            )
            if self._estimate_tokens(candidate) > packet.max_packet_tokens:
                break
            keep.append(fact)

        if not keep:
            keep = ["brain:request_received"]
        return TaggedResponsePacket(
            user_text=packet.user_text,
            facts=keep,
            constraints=packet.constraints,
            tone=packet.tone,
            length_hint=packet.length_hint,
            max_packet_tokens=packet.max_packet_tokens,
            overflowed=True,
            conversation_context=packet.conversation_context,
            deterministic_fallback=packet.deterministic_fallback,
            tagged_claims=packet.tagged_claims,
            tool_summaries=packet.tool_summaries,
            memory_items=packet.memory_items,
            job_snapshot=packet.job_snapshot,
            evidence_packet=packet.evidence_packet,
        )
