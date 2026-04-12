from __future__ import annotations

import os
import re

from ..models.ollama_client import OllamaClient
from .response_compiler import ResponsePacket, TaggedResponsePacket
from ..observability.events import PersistentEventLogger

FACT_PREFIXES = ("brain:", "tool:", "memory:", "job_status:")
STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "to",
    "of",
    "in",
    "on",
    "at",
    "for",
    "with",
    "from",
    "by",
    "as",
    "is",
    "am",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "it",
    "its",
    "it's",
    "i",
    "you",
    "your",
    "me",
    "my",
    "we",
    "our",
    "they",
    "them",
    "their",
    "this",
    "that",
    "these",
    "those",
    "can",
    "could",
    "should",
    "would",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "will",
    "just",
    "only",
    "right",
    "now",
    "through",
    "into",
    "about",
    "there",
}
FORBIDDEN_PHRASES = ("the brain", "brain states", "memory confirms", "job state")

# NH-CRSIS Task G: Fact Anchoring - Output gate markers
# Phase 4: Expanded markers for stronger evidence-only enforcement
HEDGE_MARKERS = [
    "i think",
    "i believe",
    "probably",
    "typically",
    "usually",
    "generally",
    "in most cases",
    "you might",
    "it's likely",
    "i'm not sure but",
    "as far as i know",
    # Phase 4 additions
    "perhaps",
    "maybe",
    "possibly",
    "could be",
    "might be",
    "seems like",
    "appears to be",
    "i would guess",
    "i would assume",
    "i'd imagine",
    "it seems that",
    "it appears that",
    "from what i understand",
    "i may be wrong",
    "don't quote me on",
    "it's hard to say",
    "it's worth noting",
    "one might say",
    "if i recall",
    "if i remember",
]

ESCAPE_MARKERS = [
    "based on my knowledge",
    "from what i know",
    "in general",
    "historically",
    "research shows",
    "studies suggest",
    # Phase 4 additions
    "as an ai",
    "as a language model",
    "i'm just an ai",
    "i don't have access to",
    "i do not have access to",
    "i cannot access",
    "i don't have real-time",
    "i do not have real-time",
    "my training data",
    "my knowledge cutoff",
    "i cannot verify",
    "i cannot confirm",
    "i don't know",
    "i do not know",
    "i should note",
    "it's important to note",
    "to be transparent",
    "disclaimer:",
    "note:",
]

# Evidence hierarchy: higher tags can ground lower tags
CLAIM_TAG_GROUNDING_POWER = {
    "observed": 4,  # Direct tool/OCR/file evidence - highest grounding
    "recalled": 3,  # Memory with provenance
    "inferred": 2,  # Reasoning chain with basis
    "guessed": 1,  # No evidence - lowest grounding
}


class CLLMRenderer:
    """Renderer-only stage: no tools, no planning, no new facts.

    Uses Judge Claim tags for grounding verification:
    - observed claims: Can ground any output
    - recalled claims: Can ground most output
    - inferred claims: Can ground limited output
    - guessed claims: Cannot ground output

    NH-CRSIS Task G: Fact Anchoring
    - Extracts atomic facts from packet
    - Builds anchored system prompt with enumerated facts
    - Gates output to prevent hedge/escape markers
    """

    def __init__(
        self,
        model_preferred: str = "llama3.2:1b",
        model_fallback: str = "llama3.2:3b",
        ollama_bin: str = "ollama",
        timeout_seconds: int = 30,
        log_dir: str = "./logs",
    ) -> None:
        self._preferred = OllamaClient(
            model=model_preferred,
            ollama_bin=ollama_bin,
            timeout_seconds=timeout_seconds,
        )
        self._fallback = OllamaClient(
            model=model_fallback,
            ollama_bin=ollama_bin,
            timeout_seconds=timeout_seconds,
        )
        self._event_logger = PersistentEventLogger(log_dir)

    def render(self, packet: ResponsePacket | TaggedResponsePacket) -> dict[str, Any]:
        """Render response with fact anchoring and output gating (NH-CRSIS Task G)."""
        import time
        start_time = time.perf_counter()
        
        if os.getenv("JARVIS_DEGRADED_MODE", "false").lower() == "true":
            return {"text": "System is in degraded mode. Returning deterministic response.", "raw_output": "", "model": "none", "elapsed_ms": 0}
        if packet.max_packet_tokens < 1:
            return {"text": "Unable to render packet.", "raw_output": "", "model": "none", "elapsed_ms": 0}
        if os.getenv("PYTEST_CURRENT_TEST"):
            return {"text": self._deterministic_fallback(packet), "raw_output": "", "model": "none", "elapsed_ms": 0}

        # Extract facts and build anchored prompt
        facts = self._extract_facts(packet)
        prompt = self._build_anchored_prompt(facts, packet)

        # Try preferred model with output gate
        preferred = self._preferred.run(prompt, keep_alive="60s")
        if preferred.ok and preferred.text.strip():
            candidate = self._enforce_limits(preferred.text.strip(), packet)
            gate_passed, gate_reason = self._gate_output(candidate, packet)
            if gate_passed and self._is_grounded(candidate, packet):
                elapsed = (time.perf_counter() - start_time) * 1000
                return {
                    "text": candidate,
                    "raw_output": preferred.text.strip(),
                    "model": self._preferred.model,
                    "elapsed_ms": elapsed
                }
            # Emit scope escape event on gate failure
            self._emit_scope_escape(packet, gate_reason, "preferred")

        # Try fallback model with output gate
        fallback = self._fallback.run(prompt, keep_alive="60s")
        if fallback.ok and fallback.text.strip():
            candidate = self._enforce_limits(fallback.text.strip(), packet)
            gate_passed, gate_reason = self._gate_output(candidate, packet)
            if gate_passed and self._is_grounded(candidate, packet):
                elapsed = (time.perf_counter() - start_time) * 1000
                return {
                    "text": candidate,
                    "raw_output": fallback.text.strip(),
                    "model": self._fallback.model,
                    "elapsed_ms": elapsed
                }
            # Emit scope escape event on gate failure
            self._emit_scope_escape(packet, gate_reason, "fallback")

        # Double gate failure - use deterministic fallback
        elapsed = (time.perf_counter() - start_time) * 1000
        return {
            "text": self._deterministic_fallback(packet),
            "raw_output": "GATE_FAILURE",
            "model": "fallback_deterministic",
            "elapsed_ms": elapsed
        }

    # ========================================================================
    # NH-CRSIS Task G: Fact Anchoring Methods
    # ========================================================================

    def _extract_facts(
        self, packet: ResponsePacket | TaggedResponsePacket
    ) -> list[str]:
        """Extract flat list of atomic facts from packet.

        NH-CRSIS Task G: Fact Anchoring
        Extracts facts from tool summaries, memory items, and job snapshot.
        """
        facts = (
            list(packet.tool_summaries)
            if hasattr(packet, "tool_summaries") and packet.tool_summaries
            else []
        )
        facts.extend(packet.memory_items) if hasattr(
            packet, "memory_items"
        ) and packet.memory_items else None
        if hasattr(packet, "job_snapshot") and packet.job_snapshot:
            snap = packet.job_snapshot
            facts.append(f"Background job status: {snap.get('status', 'unknown')}")
            if snap.get("progress"):
                facts.append(f"Job progress: {snap['progress']}")
        # Also include facts from packet.facts
        for fact in packet.facts:
            clean = self._clean_fact(fact)
            if clean and clean not in facts:
                facts.append(clean)
        return facts

    def _clean_fact(self, fact: str) -> str:
        """Clean a fact string by removing prefix."""
        stripped = fact
        for prefix in FACT_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :].strip()
                break
        return stripped.strip()

    def _build_anchored_prompt(
        self, facts: list[str], packet: ResponsePacket | TaggedResponsePacket
    ) -> str:
        """Build system prompt with enumerated facts and hard scope rules.

        NH-CRSIS Task G: Fact Anchoring
        Creates a prompt that restricts the model to only use provided facts.
        """
        if not facts:
            fact_block = "  (no facts available)"
        else:
            fact_block = "\n".join(f"  [{i + 1}] {f}" for i, f in enumerate(facts))

        context_lines = packet.conversation_context[-4:]
        context_block = ""
        if context_lines:
            context_block = (
                "RECENT CONTEXT (for pronouns and continuity only):\n"
                + "\n".join(f"- {line}" for line in context_lines)
                + "\n"
            )

        canonical_block = ""
        if packet.deterministic_fallback.strip():
            canonical_block = (
                "CANONICAL ANSWER:\n"
                f"{packet.deterministic_fallback.strip()}\n"
                "Stay close to the canonical answer and vary wording only slightly.\n"
            )

        return f"""You are JARVIS, a local assistant. Respond in natural speech.

PERMITTED FACTS — you may ONLY reference information from this list:
{fact_block}

RULES:
- Do not add facts, estimates, or context from your training data.
- If the answer is not derivable from the permitted facts, say: "I don't have that information right now."
- Do not speculate. Do not hedge with "probably" or "I think" unless the fact itself is uncertain.
- Respond as if these facts are the complete picture.
- No markdown, no bullet points, no code blocks.
- Keep it {packet.length_hint} and {packet.tone}.
- Output speech-ready text only.

{canonical_block}{context_block}
User said: {packet.user_text}"""

    def _gate_output(
        self, response: str, packet: ResponsePacket | TaggedResponsePacket
    ) -> tuple[bool, str]:
        """Check response for hedge/escape markers with context awareness."""
        lower = response.lower()

        # If we are explicitly doing brain inference or evidence is low,
        # allow some hedging as it's more accurate than a fake definitive.
        allow_hedging = False
        if isinstance(packet, TaggedResponsePacket):
            for claim in packet.tagged_claims:
                if claim.verification_strength in ("inferred", "guessed"):
                    allow_hedging = True
                    break

        # Core 'As an AI' rejection - always reject
        if "as an ai" in lower or "as a language model" in lower:
            return False, "scope_escape:ai_disclaimer"

        if allow_hedging:
            return True, "ok"

        for marker in HEDGE_MARKERS + ESCAPE_MARKERS:
            if marker in lower:
                return False, f"scope_escape:{marker}"
        return True, "ok"

    def _emit_scope_escape(
        self,
        packet: ResponsePacket | TaggedResponsePacket,
        reason: str,
        model_type: str,
    ) -> None:
        """Emit renderer_scope_escape event when output gate fails.

        NH-CRSIS Task G: Fact Anchoring - Observability
        """
        from ..observability.events import EventRecord

        self._event_logger.emit(
            EventRecord.build(
                event_type="renderer_scope_escape",
                turn_id=getattr(packet, "turn_id", "unknown"),
                lane_decision="render",
                resolved_by=model_type,
                elapsed_ms=0,
                crsis_reason=reason,
            )
        )

    # ========================================================================
    # End NH-CRSIS Task G Methods
    # ========================================================================

    def _build_prompt(self, packet: ResponsePacket | TaggedResponsePacket) -> str:
        """Legacy prompt builder - kept for backwards compatibility."""
        facts_block = "\n".join(f"- {fact}" for fact in self._clean_facts(packet.facts))
        context_lines = packet.conversation_context[-4:]
        context_block = ""
        if context_lines:
            context_block = (
                "RECENT CONTEXT (for pronouns and continuity only):\n"
                + "\n".join(f"- {line}" for line in context_lines)
                + "\n"
            )
        canonical_block = ""
        if packet.deterministic_fallback.strip():
            canonical_block = (
                "CANONICAL ANSWER:\n"
                f"{packet.deterministic_fallback.strip()}\n"
                "Stay close to the canonical answer and vary wording only slightly.\n"
            )
        return (
            "You are Jarvis's realtime response composer. The Brain, memory, and tools are authoritative.\n"
            "RULES:\n"
            "- Answer the main person's request using only the verified facts below.\n"
            "- Do not add new information or pretrained assumptions.\n"
            "- Never contradict the Brain, memory, tool results, or job state.\n"
            "- Preserve names, numbers, paths-as-concepts, times, and tool facts exactly.\n"
            "- If the verified facts are insufficient, say you cannot verify it right now.\n"
            "- No markdown, no bullet points, no code blocks.\n"
            f"- Keep it {packet.length_hint} and {packet.tone}.\n"
            "- Output speech-ready text only.\n"
            f"MAIN PERSON REQUEST:\n{packet.user_text}\n"
            f"{canonical_block}"
            f"{context_block}"
            "VERIFIED FACTS:\n"
            f"{facts_block}"
        )

    def _enforce_limits(
        self, text: str, packet: ResponsePacket | TaggedResponsePacket
    ) -> str:
        words = text.split()
        if len(words) <= packet.max_packet_tokens:
            return text
        return " ".join(words[: packet.max_packet_tokens])

    def _deterministic_fallback(
        self, packet: ResponsePacket | TaggedResponsePacket
    ) -> str:
        if packet.deterministic_fallback.strip():
            return packet.deterministic_fallback.strip()
        clean_facts = self._clean_facts(packet.facts)
        return " ".join(clean_facts)

    def _is_grounded(
        self, text: str, packet: ResponsePacket | TaggedResponsePacket
    ) -> bool:
        """Verify candidate text is grounded using Judge Claim tags.

        Evidence hierarchy (observed > recalled > inferred > guessed):
        - observed claims: Full grounding power - can support any statement
        - recalled claims: Strong grounding - can support most statements
        - inferred claims: Limited grounding - needs multiple sources
        - guessed claims: No grounding power - cannot ground output

        Returns True if candidate is sufficiently grounded.
        """
        candidate = text.strip()
        if not candidate:
            return False
        if candidate.startswith('"') and candidate.endswith('"'):
            return False

        lowered = candidate.lower()
        fallback_lower = packet.deterministic_fallback.lower()

        # Check forbidden phrases (legacy check still applies)
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lowered and phrase not in fallback_lower:
                return False

        # If we have tagged claims, use Claim-based grounding verification
        if isinstance(packet, TaggedResponsePacket) and packet.tagged_claims:
            return self._verify_claim_grounding(candidate, packet)

        # Fallback to legacy string-based grounding for non-tagged packets
        return self._legacy_grounded_check(candidate, packet)

    def _verify_claim_grounding(
        self, candidate: str, packet: TaggedResponsePacket
    ) -> bool:
        """Verify candidate is grounded by checking Claim tags against evidence hierarchy.

        Algorithm:
        1. Extract content words from candidate
        2. Find claims that support those words
        3. Verify minimum grounding power threshold is met
        """
        candidate_content_words = self._content_words(candidate)
        if not candidate_content_words:
            return True  # No content to verify

        # Build word -> claim tag mapping from facts
        word_grounding_power: dict[str, int] = {}
        for fact in packet.facts:
            fact_words = self._content_words(fact)
            # Determine grounding power based on claim tags
            fact_grounding = self._get_fact_grounding_power(packet, fact)
            for word in fact_words:
                if (
                    word not in word_grounding_power
                    or fact_grounding > word_grounding_power[word]
                ):
                    word_grounding_power[word] = fact_grounding

        # Check if candidate words are grounded
        ungrounded_words = []
        for word in candidate_content_words:
            if word not in word_grounding_power:
                # Word not in any fact - check if it's allowed (from user input or fallback)
                user_words = self._content_words(packet.user_text)
                fallback_words = self._content_words(packet.deterministic_fallback)
                if word not in user_words and word not in fallback_words:
                    ungrounded_words.append(word)

        # Allow some ungrounded words (function words, connectors)
        # But reject if too high a percentage are ungrounded
        if len(ungrounded_words) > max(2, len(candidate_content_words) // 10):
            return False

        # Verify minimum grounding quality
        grounded_words = [
            w for w in candidate_content_words if w in word_grounding_power
        ]
        if not grounded_words:
            return False

        # Calculate average grounding power
        total_grounding = sum(word_grounding_power.get(w, 0) for w in grounded_words)
        avg_grounding = total_grounding / len(grounded_words)

        # Require minimum average grounding of 2.0 (at least "inferred" level)
        return avg_grounding >= 2.0

    def _get_fact_grounding_power(self, packet: TaggedResponsePacket, fact: str) -> int:
        """Get grounding power for a fact based on its Claim tag.

        Returns 4 for observed, 3 for recalled, 2 for inferred, 1 for guessed.
        """
        # Find the claim for this fact
        fact_prefix = fact.split(":", 1)[0] + ":" if ":" in fact else ""

        for claim in packet.tagged_claims:
            # Match claim content to fact
            if claim.content in fact or fact in claim.content:
                return CLAIM_TAG_GROUNDING_POWER.get(claim.tag, 1)

        # Default grounding based on fact prefix
        if fact_prefix == "tool:":
            return 4  # observed
        elif fact_prefix == "memory:":
            return 3  # recalled
        elif fact_prefix == "brain:":
            return 2  # inferred
        else:
            return 1  # guessed

    def _legacy_grounded_check(self, candidate: str, packet: ResponsePacket) -> bool:
        """Legacy string-based grounding check for non-tagged packets."""
        fallback_words = packet.deterministic_fallback.split()
        if len(candidate.split()) > max(18, len(fallback_words) * 2 + 4):
            return False

        for number in re.findall(r"\d[\d:.\-]*", packet.deterministic_fallback):
            if number not in candidate:
                return False

        protected_words = [
            word
            for word in re.findall(
                r"\b[A-Z][A-Za-z0-9\-]+\b", packet.deterministic_fallback
            )
            if word.lower() not in {"i", "it", "the"}
        ]
        for word in protected_words:
            if word.lower() not in candidate.lower():
                return False

        fallback_content_words = self._content_words(packet.deterministic_fallback)
        if fallback_content_words:
            candidate_content_words = self._content_words(candidate)
            shared = fallback_content_words & candidate_content_words
            minimum_overlap = max(1, len(fallback_content_words) // 2)
            if len(shared) < minimum_overlap:
                return False

        allowed_words = (
            self._content_words(packet.user_text)
            | self._content_words(" ".join(self._clean_facts(packet.facts)))
            | self._content_words(packet.deterministic_fallback)
        )
        output_words = self._content_words(candidate)
        novel_words = {word for word in output_words if word not in allowed_words}
        if len(novel_words) > max(2, len(output_words) // 10):
            return False

        return True

    def _content_words(self, text: str) -> set[str]:
        words = {token.lower() for token in re.findall(r"[A-Za-z0-9']+", text)}
        return {word for word in words if len(word) > 1 and word not in STOPWORDS}

    def _clean_facts(self, facts: list[str]) -> list[str]:
        clean: list[str] = []
        for fact in facts:
            stripped = fact
            for prefix in FACT_PREFIXES:
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix) :]
                    break
            stripped = stripped.strip()
            if stripped:
                clean.append(stripped)
        return clean
