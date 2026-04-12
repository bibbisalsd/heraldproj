"""Ingress Normalizer: Input normalization with STT correction and profile mapping.

Handles:
- Profile mapping (local_mic → owner, addon → trusted, etc.)
- STT mishear correction (common voice recognition errors)
- Whitespace and punctuation cleanup
- Number word expansion
- Filler word removal
"""

from __future__ import annotations

import re
from typing import Callable

from .contracts import IngressEnvelope, RawEvent


DEFAULT_PROFILE_MAP = {
    "local_mic": "owner",
    "addon": "trusted",
}


# ── STT Mishear Correction Table ─────────────────────────────────
# Common voice recognition mistakes mapped to intended text.
# Applied as case-insensitive whole-word replacements.
STT_CORRECTIONS: dict[str, str] = {
    # Wake word mishears (handled elsewhere but included for completeness)
    "travis": "jarvis",
    "javos": "jarvis",
    "javas": "jarvis",
    "jovis": "jarvis",
    "jervis": "jarvis",
    # Common command mishears
    "cancel current heavy": "cancel current task",
    "heavy task": "background task",
    "be g one": "bg1",
    "b g one": "bg1",
    "bee gee one": "bg1",
    "bee g 1": "bg1",
    # Number word corrections
    "to": "two",  # Only in numeric contexts (handled carefully)
    # Technical term mishears
    "python": "python",  # Ensure casing is normalized
    "java script": "javascript",
    "fire fox": "firefox",
    "note pad": "notepad",
    "spread sheet": "spreadsheet",
    "data base": "database",
    "web sight": "website",
    "web site": "website",
    # Common phrase corrections
    "what's": "what is",
    "it's": "it is",
    "i'm": "i am",
    "can't": "cannot",
    "don't": "do not",
    "won't": "will not",
    "didn't": "did not",
    "doesn't": "does not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "haven't": "have not",
    "hasn't": "has not",
    "wouldn't": "would not",
    "couldn't": "could not",
    "shouldn't": "should not",
    # URL-related mishears
    "dot com": ".com",
    "dot org": ".org",
    "dot net": ".net",
    "dot io": ".io",
    "dot dev": ".dev",
    "dot app": ".app",
    "h t t p": "http",
    "h t t p s": "https",
    # Phase 3: Expanded domain & TLD mishear corrections
    "dot calm": ".com",
    "dot ai": ".ai",
    "dot co": ".co",
    "dot versal": ".vercel",
    "dot versel": ".vercel",
    "versel": "vercel",
    "vercelle": "vercel",
    "vercell": "vercel",
    "git hub": "github",
    "stack overflow": "stackoverflow",
    "stack over flow": "stackoverflow",
    "red it": "reddit",
    "you tube": "youtube",
    "linked in": "linkedin",
    "fire base": "firebase",
    "cloud flare": "cloudflare",
    "net lify": "netlify",
    "supa base": "supabase",
    "mongo db": "mongodb",
    "my sequel": "mysql",
    "post gres": "postgres",
    # Time-related mishears
    "a m": "am",
    "p m": "pm",
    "o'clock": "o clock",
}

# Multi-word STT corrections (phrase-level fixes)
STT_PHRASE_CORRECTIONS: list[tuple[str, str]] = [
    (r"\bcancel current heavy task\b", "cancel current task"),
    (r"\bheavy task lane\b", "background task lane"),
    (r"\bwhat are you working on\b", "what are you doing"),
    (r"\bare you still working\b", "what is the progress"),
    (r"\bhow far along\b", "what is the progress"),
    (r"\bhow is that going\b", "what is the progress"),
    (r"\bare you done yet\b", "what is the progress"),
]

# Filler words to strip (common in spoken input)
FILLER_WORDS = re.compile(
    r"\b(?:um+|uh+|er+|ah+|like|you know|basically|actually|so basically|well basically)\b",
    re.IGNORECASE,
)

# Repeated words (stuttering from STT)
REPEATED_WORDS = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


class IngressNormalizer:
    """Normalize raw input events with STT correction and profile mapping."""

    def __init__(
        self,
        profile_mapper: Callable[[RawEvent], str] | None = None,
        enable_stt_corrections: bool = True,
        enable_filler_removal: bool = True,
    ) -> None:
        self._profile_mapper = profile_mapper
        self._enable_stt_corrections = enable_stt_corrections
        self._enable_filler_removal = enable_filler_removal

    def normalize(self, raw_event: RawEvent) -> IngressEnvelope:
        """Normalize a raw event into an IngressEnvelope.

        Applies:
        1. Profile mapping (source → security profile)
        2. STT correction (voice mishear fixes)
        3. Filler removal (um, uh, er, etc.)
        4. Whitespace cleanup
        """
        profile = self._map_profile(raw_event)
        metadata: dict[str, str] = {"normalized": "true"}
        metadata.update({k: str(v) for k, v in raw_event.metadata.items()})

        # Apply text corrections for voice input
        corrected_text = raw_event.payload
        if raw_event.source == "local_mic":
            corrected_text = self.correct_stt_text(corrected_text)
            metadata["stt_corrected"] = "true"

        envelope = IngressEnvelope.from_raw(raw_event, profile=profile)
        # Replace text with corrected version
        if corrected_text != raw_event.payload:
            envelope = envelope.replace(text=corrected_text, metadata=metadata)
        else:
            envelope = envelope.replace(metadata=metadata)

        return envelope

    def correct_stt_text(self, text: str) -> str:
        """Apply STT corrections to raw voice text.

        Args:
            text: Raw STT output

        Returns:
            Corrected text
        """
        corrected = text

        # 1. Apply filler word removal
        if self._enable_filler_removal:
            corrected = FILLER_WORDS.sub("", corrected)

        # 2. Apply phrase-level corrections first (longer patterns)
        if self._enable_stt_corrections:
            for pattern, replacement in STT_PHRASE_CORRECTIONS:
                corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)

        # 3. Apply word-level corrections
        if self._enable_stt_corrections:
            for wrong, right in STT_CORRECTIONS.items():
                # Only replace as whole words to avoid partial matches
                pattern = r"\b" + re.escape(wrong) + r"\b"
                corrected = re.sub(pattern, right, corrected, flags=re.IGNORECASE)

        # 4. Fix repeated words (STT stutter)
        corrected = REPEATED_WORDS.sub(r"\1", corrected)

        # 5. Normalize whitespace
        corrected = re.sub(r"\s+", " ", corrected).strip()

        return corrected

    def _map_profile(self, raw_event: RawEvent) -> str:
        """Map event source to security profile."""
        if self._profile_mapper is not None:
            return self._profile_mapper(raw_event)
        return DEFAULT_PROFILE_MAP.get(raw_event.source, "guest")
