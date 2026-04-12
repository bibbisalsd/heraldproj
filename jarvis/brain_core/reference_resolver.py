"""Reference Resolver: Resolve vague references like it/that/they/why.

This module resolves vague pronominal and adverbial references in follow-up
utterances using structured context from previous turns.

Examples:
- "why are they slower" → "why are your responses slower"
- "what is it" → "what is france" (if France was the active subject)
- "what did you find out" → "what did you find out about the heavy task on America"
- "go on" → continue explaining the active topic
- "tell me more about that" → expand on the active subject
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .turn_context import TurnContextPacket, ActiveContext


# Vague pronominal references
PRONOUN_IT = {"it", "its", "it's"}
PRONOUN_THAT = {"that", "thats", "that's"}
PRONOUN_THIS = {"this", "this's"}  # rare but possible
PRONOUN_THEY = {"they", "them", "their", "theirs"}
PRONOUN_THOSE = {"those"}
PRONOUN_WHICH = {"which", "what"}  # "what" in context of "what about what"

# Adverbial references (why/where/when/how follow-ups)
ADVERB_WHY = {"why"}
ADVERB_WHERE = {"where", "whereabouts"}
ADVERB_WHEN = {"when", "what time"}
ADVERB_HOW = {"how", "how far", "how long", "how much", "how many"}

# Continuation phrases (implied "tell me more")
CONTINUATION_PHRASES = {
    "go on",
    "go on then",
    "continue",
    "carry on",
    "tell me more",
    "say more",
    "elaborate",
    "expand",
    "what else",
    "anything else",
    "and",
    "and then",
    "so",
    "so what",
}

# Correction phrases
CORRECTION_PHRASES = {
    "no",
    "no,",
    "not that",
    "that's wrong",
    "thats wrong",
    "that was wrong",
    "that is wrong",
    "wrong",
    "incorrect",
    "try again",
    "that's not right",
    "thats not right",
    "you mean",
}

# Acceptance/continuation signals
ACCEPTANCE_PHRASES = {
    "okay",
    "ok",
    "alright",
    "right",
    "yes",
    "yeah",
    "sure",
    "got it",
    "understood",
    "i see",
    "makes sense",
}

# Abandonment signals
ABANDONMENT_PHRASES = {
    "never mind",
    "forget it",
    "doesn't matter",
    "dont matter",
    "no worries",
    "its fine",
    "that's fine",
    "thats fine",
    "leave it",
}


@dataclass
class ReferenceResolution:
    """Result of resolving a vague reference."""

    original_phrase: str
    resolved_reference: str
    resolution_reason: str
    confidence: float
    source: str  # context, memory, default, failed


@dataclass
class ContextualRewrite:
    """Result of contextual rewrite of an utterance."""

    original: str
    rewritten: str
    reason: str
    resolutions: list[ReferenceResolution] = field(default_factory=list)
    confidence: float = 1.0


class ReferenceResolver:
    """Resolves vague references using active context and memory.

    The resolver uses:
    1. Active context (topic/subject from recent turns)
    2. Session memory (recent turn artifacts)
    3. Task context (active BG1 task subject)
    4. Linguistic patterns (pronoun resolution rules)

    Resolution priority:
    1. Explicit subject in utterance (no resolution needed)
    2. Active context subject (highest confidence)
    3. Active context topic (medium confidence)
    4. Recent turn subject (lower confidence)
    5. Default/fallback (lowest confidence)
    """

    def __init__(
        self,
        active_context: ActiveContext | None = None,
        recent_subjects: list[str] | None = None,
        active_task_subject: str | None = None,
    ) -> None:
        self.active_context = active_context or ActiveContext()
        self.recent_subjects = recent_subjects or []
        self.active_task_subject = active_task_subject

    def resolve(
        self,
        normalized_text: str,
        tokens: list[str],
    ) -> ContextualRewrite:
        """Resolve vague references in the utterance.

        Args:
            normalized_text: Lowercase, cleaned utterance text
            tokens: Tokenized utterance

        Returns:
            ContextualRewrite with resolved references
        """
        resolutions: list[ReferenceResolution] = []
        rewritten = normalized_text
        reasons: list[str] = []

        # Check for pronoun references
        pronoun_resolutions = self._resolve_pronouns(tokens, normalized_text)
        resolutions.extend(pronoun_resolutions.resolutions)
        if pronoun_resolutions.rewritten != normalized_text:
            rewritten = pronoun_resolutions.rewritten
            reasons.append(pronoun_resolutions.reason)

        # Check for adverbial references (why/where/when/how)
        adverb_resolutions = self._resolve_adverbs(tokens, normalized_text, rewritten)
        resolutions.extend(adverb_resolutions.resolutions)
        if adverb_resolutions.rewritten != rewritten:
            rewritten = adverb_resolutions.rewritten
            reasons.append(adverb_resolutions.reason)

        # Check for continuation phrases
        continuation_resolutions = self._resolve_continuation(
            tokens, normalized_text, rewritten
        )
        resolutions.extend(continuation_resolutions.resolutions)
        if continuation_resolutions.rewritten != rewritten:
            rewritten = continuation_resolutions.rewritten
            reasons.append(continuation_resolutions.reason)

        # Build reason string
        reason = "; ".join(reasons) if reasons else "no resolution needed"

        # Calculate confidence
        confidence = 1.0
        if not resolutions:
            confidence = 1.0  # No resolution needed = full confidence
        elif any(r.source == "failed" for r in resolutions):
            confidence = 0.3
        elif any(r.source == "context" for r in resolutions):
            confidence = 0.85
        elif any(r.source == "memory" for r in resolutions):
            confidence = 0.7
        else:
            confidence = 0.5

        return ContextualRewrite(
            original=normalized_text,
            rewritten=rewritten,
            reason=reason,
            resolutions=resolutions,
            confidence=confidence,
        )

    def _resolve_pronouns(
        self,
        tokens: list[str],
        text: str,
    ) -> ContextualRewrite:
        """Resolve pronominal references (it/that/this/they/those)."""
        resolutions: list[ReferenceResolution] = []
        rewritten = text

        # Find pronoun occurrences
        pronoun_positions: list[tuple[int, str]] = []
        for i, token in enumerate(tokens):
            if token in PRONOUN_IT:
                pronoun_positions.append((i, "it"))
            elif token in PRONOUN_THAT:
                pronoun_positions.append((i, "that"))
            elif token in PRONOUN_THIS:
                pronoun_positions.append((i, "this"))
            elif token in PRONOUN_THEY:
                pronoun_positions.append((i, "they"))
            elif token in PRONOUN_THOSE:
                pronoun_positions.append((i, "those"))

        if not pronoun_positions:
            return ContextualRewrite(
                original=text, rewritten=text, reason="no pronouns"
            )

        # Resolve each pronoun
        for pos, pronoun in pronoun_positions:
            resolution = self._resolve_single_pronoun(pronoun, pos, tokens)
            if resolution:
                resolutions.append(resolution)
                # Replace in text (case-insensitive, word boundary)
                rewritten = re.sub(
                    rf"\b{re.escape(pronoun)}\b",
                    resolution.resolved_reference,
                    rewritten,
                    flags=re.IGNORECASE,
                    count=1,
                )

        reason = f"resolved {len(resolutions)} pronoun(s) from context"
        return ContextualRewrite(
            original=text,
            rewritten=rewritten,
            reason=reason,
            resolutions=resolutions,
        )

    def _resolve_single_pronoun(
        self,
        pronoun: str,
        position: int,
        tokens: list[str],
    ) -> ReferenceResolution | None:
        """Resolve a single pronoun at a given position.

        Resolution priority with confidence scoring:
        1. Active context subject (fresh) - 0.95
        2. Active context subject (stale) - 0.7
        3. Active task subject - 0.75
        4. Active context topic (fresh) - 0.65
        5. Recent turn subject (1st) - 0.5
        6. Recent turn subject (2nd-3rd) - 0.35
        7. Failed - 0.2
        """
        # Priority 1: Active context subject (fresh)
        if self.active_context.subject and self.active_context.is_fresh():
            return ReferenceResolution(
                original_phrase=pronoun,
                resolved_reference=self.active_context.subject,
                resolution_reason=f"active context subject (fresh): {self.active_context.subject}",
                confidence=0.95,
                source="context",
            )

        # Priority 2: Active context subject (may be stale)
        if self.active_context.subject:
            return ReferenceResolution(
                original_phrase=pronoun,
                resolved_reference=self.active_context.subject,
                resolution_reason=f"active context subject (stale): {self.active_context.subject}",
                confidence=0.7,
                source="context",
            )

        # Priority 3: Active task subject
        if self.active_task_subject:
            return ReferenceResolution(
                original_phrase=pronoun,
                resolved_reference=self.active_task_subject,
                resolution_reason=f"active task subject: {self.active_task_subject}",
                confidence=0.75,
                source="context",
            )

        # Priority 4: Active context topic (fresh)
        if self.active_context.topic and self.active_context.is_fresh():
            return ReferenceResolution(
                original_phrase=pronoun,
                resolved_reference=self.active_context.topic,
                resolution_reason=f"active context topic (fresh): {self.active_context.topic}",
                confidence=0.65,
                source="context",
            )

        # Priority 5: Recent subjects (ranked by recency)
        if self.recent_subjects:
            confidence = 0.5 if len(self.recent_subjects) == 1 else 0.35
            return ReferenceResolution(
                original_phrase=pronoun,
                resolved_reference=self.recent_subjects[0],
                resolution_reason=f"recent subject (rank 1): {self.recent_subjects[0]}",
                confidence=confidence,
                source="memory",
            )

        # Failed to resolve
        return ReferenceResolution(
            original_phrase=pronoun,
            resolved_reference=pronoun,  # Keep original
            resolution_reason="no context available for resolution",
            confidence=0.2,
            source="failed",
        )

    def _resolve_adverbs(
        self,
        tokens: list[str],
        original: str,
        current_rewrite: str,
    ) -> ContextualRewrite:
        """Resolve adverbial references (why/where/when/how)."""
        resolutions: list[ReferenceResolution] = []

        # Check for "why" questions about active subject
        if tokens and tokens[0] in ADVERB_WHY:
            # "why are they..." -> "why are [active subject]..."
            # "why is it..." -> "why is [active subject]..."
            if len(tokens) >= 3 and tokens[1] in {"are", "is", "do", "does"}:
                pronoun = None
                for t in tokens[2:5]:
                    if t in PRONOUN_THEY:
                        pronoun = "they"
                        break
                    elif t in PRONOUN_IT:
                        pronoun = "it"
                        break

                if pronoun:
                    resolution = self._resolve_single_pronoun(
                        pronoun, tokens.index(pronoun), tokens
                    )
                    if resolution and resolution.source != "failed":
                        resolutions.append(resolution)
                        # Apply resolution to the rewrite
                        current_rewrite = re.sub(
                            rf"\b{re.escape(pronoun)}\b",
                            resolution.resolved_reference,
                            current_rewrite,
                            flags=re.IGNORECASE,
                            count=1,
                        )

        reason = (
            f"resolved {len(resolutions)} adverb reference(s)"
            if resolutions
            else "no adverb resolution needed"
        )
        return ContextualRewrite(
            original=original,
            rewritten=current_rewrite,
            reason=reason,
            resolutions=resolutions,
        )

    def _resolve_continuation(
        self,
        tokens: list[str],
        original: str,
        current_rewrite: str,
    ) -> ContextualRewrite:
        """Resolve continuation phrases (go on, tell me more, etc.)."""
        resolutions: list[ReferenceResolution] = []

        # Check for continuation phrases
        text = " ".join(tokens)
        for phrase in CONTINUATION_PHRASES:
            if phrase in text:
                # Continuation implies "tell me more about [active subject]"
                if self.active_context.subject:
                    resolutions.append(
                        ReferenceResolution(
                            original_phrase=phrase,
                            resolved_reference=f"tell me more about {self.active_context.subject}",
                            resolution_reason=f"continuation of active subject: {self.active_context.subject}",
                            confidence=0.8,
                            source="context",
                        )
                    )
                elif self.active_context.topic:
                    resolutions.append(
                        ReferenceResolution(
                            original_phrase=phrase,
                            resolved_reference=f"tell me more about {self.active_context.topic}",
                            resolution_reason=f"continuation of active topic: {self.active_context.topic}",
                            confidence=0.6,
                            source="context",
                        )
                    )
                break

        reason = (
            f"resolved {len(resolutions)} continuation phrase(s)"
            if resolutions
            else "no continuation detected"
        )
        return ContextualRewrite(
            original=original,
            rewritten=current_rewrite,
            reason=reason,
            resolutions=resolutions,
        )


def resolve_references(
    normalized_text: str,
    context: TurnContextPacket | None = None,
    recent_subjects: list[str] | None = None,
    active_task_subject: str | None = None,
) -> ContextualRewrite:
    """Convenience function to resolve references in an utterance.

    Args:
        normalized_text: Lowercase, cleaned utterance text
        context: Optional turn context packet with active context
        recent_subjects: Optional list of recent subjects from memory
        active_task_subject: Optional active BG1 task subject

    Returns:
        ContextualRewrite with resolved references
    """
    # Tokenize
    tokens = normalized_text.lower().split()

    # Extract active context
    active_context = context.active_context if context else ActiveContext()

    # Create resolver
    resolver = ReferenceResolver(
        active_context=active_context,
        recent_subjects=recent_subjects or [],
        active_task_subject=active_task_subject,
    )

    # Resolve
    return resolver.resolve(normalized_text, tokens)
