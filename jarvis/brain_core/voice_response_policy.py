"""Voice Response Policy: Formal rules for voice-friendly output.

Governs how responses are shaped for spoken delivery:
- Length limits per intent type
- Confidence-based hedging thresholds
- Abbreviation expansion rules
- Internal ID suppression
- Spoken number formatting
- Follow-up prompt injection
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoicePolicy:
    """Policy for a specific response type."""

    max_spoken_chars: int = 500
    max_spoken_sentences: int = 4
    hedge_below_confidence: float = 0.7
    strong_hedge_below: float = 0.5
    suppress_internal_ids: bool = True
    expand_abbreviations: bool = True
    format_numbers_spoken: bool = True
    allow_follow_up_prompt: bool = True
    tone: str = "helpful"  # helpful, concise, technical, casual


# ── Per-intent voice policies ───────────────────────────────────────

INTENT_POLICIES: dict[str, VoicePolicy] = {
    # Fast deterministic responses — keep very short
    "time_query": VoicePolicy(
        max_spoken_chars=80,
        max_spoken_sentences=1,
        hedge_below_confidence=0.0,  # Never hedge time
        allow_follow_up_prompt=False,
        tone="concise",
    ),
    "day_query": VoicePolicy(
        max_spoken_chars=80,
        max_spoken_sentences=1,
        hedge_below_confidence=0.0,
        allow_follow_up_prompt=False,
        tone="concise",
    ),
    "date_query": VoicePolicy(
        max_spoken_chars=100,
        max_spoken_sentences=1,
        hedge_below_confidence=0.0,
        allow_follow_up_prompt=False,
        tone="concise",
    ),
    "math_query": VoicePolicy(
        max_spoken_chars=120,
        max_spoken_sentences=1,
        hedge_below_confidence=0.0,
        allow_follow_up_prompt=False,
        tone="concise",
    ),
    # Status and system queries — moderate length
    "status": VoicePolicy(
        max_spoken_chars=250,
        max_spoken_sentences=3,
        suppress_internal_ids=True,
        tone="helpful",
    ),
    "job_status": VoicePolicy(
        max_spoken_chars=250,
        max_spoken_sentences=3,
        suppress_internal_ids=True,
        tone="helpful",
    ),
    "bg1_update": VoicePolicy(
        max_spoken_chars=200,
        max_spoken_sentences=2,
        suppress_internal_ids=True,
        tone="helpful",
    ),
    "bg1_result": VoicePolicy(
        max_spoken_chars=120,
        max_spoken_sentences=1,
        suppress_internal_ids=True,
        tone="helpful",
    ),
    # Self-knowledge queries — moderate length
    "self_query": VoicePolicy(
        max_spoken_chars=350,
        max_spoken_sentences=3,
        tone="helpful",
    ),
    "help_query": VoicePolicy(
        max_spoken_chars=400,
        max_spoken_sentences=4,
        tone="helpful",
    ),
    "codebase_query": VoicePolicy(
        max_spoken_chars=350,
        max_spoken_sentences=3,
        tone="technical",
    ),
    # Memory queries
    "recall_name": VoicePolicy(
        max_spoken_chars=120,
        max_spoken_sentences=1,
        hedge_below_confidence=0.0,
        tone="concise",
    ),
    "owner_memory": VoicePolicy(
        max_spoken_chars=200,
        max_spoken_sentences=2,
        tone="helpful",
    ),
    # Social / greetings — keep natural
    "greeting": VoicePolicy(
        max_spoken_chars=150,
        max_spoken_sentences=2,
        hedge_below_confidence=0.0,
        allow_follow_up_prompt=False,
        tone="casual",
    ),
    "wellbeing_query": VoicePolicy(
        max_spoken_chars=150,
        max_spoken_sentences=2,
        tone="casual",
    ),
    "hearing_query": VoicePolicy(
        max_spoken_chars=100,
        max_spoken_sentences=1,
        tone="casual",
    ),
    # Website / research — allow longer for content
    "website_check": VoicePolicy(
        max_spoken_chars=400,
        max_spoken_sentences=4,
        tone="helpful",
    ),
    # General chat — default policy
    "general_chat": VoicePolicy(
        max_spoken_chars=500,
        max_spoken_sentences=4,
        hedge_below_confidence=0.7,
        strong_hedge_below=0.5,
        tone="helpful",
    ),
    # Performance query
    "performance_query": VoicePolicy(
        max_spoken_chars=250,
        max_spoken_sentences=3,
        tone="helpful",
    ),
}

# Default policy for unrecognized intents
DEFAULT_VOICE_POLICY = VoicePolicy()


class VoiceResponsePolicy:
    """Manages voice response policies per intent type.

    Provides:
    - Policy lookup by intent
    - Confidence-based hedging decisions
    - Length enforcement
    - Follow-up prompt decisions
    """

    def __init__(
        self,
        custom_policies: dict[str, VoicePolicy] | None = None,
    ) -> None:
        self._policies = dict(INTENT_POLICIES)
        if custom_policies:
            self._policies.update(custom_policies)

    def get_policy(self, intent: str) -> VoicePolicy:
        """Get voice policy for an intent."""
        return self._policies.get(intent, DEFAULT_VOICE_POLICY)

    def should_hedge(self, intent: str, confidence: float) -> str | None:
        """Determine if hedging is needed.

        Returns:
            'strong' for very low confidence, 'mild' for low confidence,
            None for no hedging needed.
        """
        policy = self.get_policy(intent)
        if confidence < policy.strong_hedge_below:
            return "strong"
        if confidence < policy.hedge_below_confidence:
            return "mild"
        return None

    def get_constraints(self, intent: str) -> list[str]:
        """Get renderer constraints for an intent.

        Returns: list of constraint strings for the response compiler.
        """
        policy = self.get_policy(intent)
        constraints = ["renderer_only_no_new_facts", "voice_friendly_output"]

        if policy.max_spoken_sentences <= 2:
            constraints.append("keep_to_two_short_sentences")
        elif policy.max_spoken_sentences <= 3:
            constraints.append("keep_to_three_sentences")

        if policy.suppress_internal_ids:
            constraints.append("suppress_internal_ids")

        if policy.tone == "concise":
            constraints.append("concise_direct_answer")
        elif policy.tone == "technical":
            constraints.append("allow_technical_terms")
        elif policy.tone == "casual":
            constraints.append("casual_friendly_tone")

        return constraints

    def get_length_hint(self, intent: str) -> str:
        """Get length hint for an intent."""
        policy = self.get_policy(intent)
        if policy.max_spoken_chars <= 120:
            return "very_short"
        if policy.max_spoken_chars <= 250:
            return "short"
        if policy.max_spoken_chars <= 400:
            return "medium"
        return "long"

    def truncate_for_voice(self, text: str, intent: str) -> str:
        """Truncate text to fit voice policy limits.

        Args:
            text: Text to potentially truncate
            intent: Intent type for policy lookup

        Returns:
            Truncated text fitting the policy limits
        """
        policy = self.get_policy(intent)
        if len(text) <= policy.max_spoken_chars:
            return text

        # Split into sentences and take up to max
        sentences = text.replace("! ", ". ").split(". ")
        kept: list[str] = []
        length = 0

        for sentence in sentences[: policy.max_spoken_sentences]:
            candidate_len = length + len(sentence) + 2
            if candidate_len > policy.max_spoken_chars and kept:
                break
            kept.append(sentence)
            length = candidate_len

        if kept:
            result = ". ".join(kept)
            if not result.endswith("."):
                result += "."
            return result

        # Fallback: hard truncate
        return text[: policy.max_spoken_chars - 3] + "..."

    def should_add_follow_up_prompt(self, intent: str) -> bool:
        """Check if a follow-up prompt should be appended."""
        return self.get_policy(intent).allow_follow_up_prompt
