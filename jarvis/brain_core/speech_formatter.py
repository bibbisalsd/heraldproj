"""Speech Formatter: Voice-friendly text transformation.

Handles:
- Spoken vs display text differentiation
- Markdown stripping for TTS
- Internal token removal (tool:, memory:, job_status:)
- Path sanitization
- Number and abbreviation expansion for TTS
- Confidence-based answer shaping
- URL spoken formatting
"""

from __future__ import annotations

import re
from dataclasses import dataclass


WINDOWS_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s]+")
LINUX_PATH_PATTERN = re.compile(r"(?:/[a-zA-Z0-9_\-.]+){3,}")
LEADING_USER_PREFIX = re.compile(r"^\s*user:\s*", re.IGNORECASE)
INTERNAL_FACT_TOKEN = re.compile(r"\b(?:tool|memory|job_status):\S+\b", re.IGNORECASE)
TIME_MERIDIEM_PATTERN = re.compile(r"(?<=\d)\s*(a\.?m\.?|p\.?m\.?)\b", re.IGNORECASE)

# Markdown formatting patterns
MARKDOWN_BOLD = re.compile(r"\*\*([^*]+)\*\*")
MARKDOWN_ITALIC = re.compile(r"\*([^*]+)\*|_([^_]+)_")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MARKDOWN_LIST = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
MARKDOWN_CODE = re.compile(r"`([^`]+)`")
MARKDOWN_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
MARKDOWN_HORIZONTAL_RULE = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
MARKDOWN_BLOCKQUOTE = re.compile(r"^>\s+", re.MULTILINE)

# URL pattern for spoken formatting
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")

# Internal IDs and trace labels that should never be spoken
INTERNAL_ID_PATTERNS = [
    re.compile(r"\b[a-f0-9]{8,32}\b"),  # hex IDs
    re.compile(
        r"\b(?:job|task|turn|user|evidence|profile)_[a-f0-9]+\b"
    ),  # underscore IDs
    re.compile(r"\b(?:job|task|turn|user|evidence|profile)-[a-f0-9]+\b"),  # dash IDs
    re.compile(
        r"\[(?:timing|trace|memory|tool|cognition|debug|info|warn|error|fact|evidence)\]",
        re.IGNORECASE,
    ),  # trace labels
]

# Abbreviation expansion for TTS
ABBREVIATION_MAP: dict[str, str] = {
    "BG1": "background lane",
    "bg1": "background lane",
    "BG-1": "background lane",
    "TTS": "text to speech",
    "STT": "speech to text",
    "LLM": "language model",
    "API": "A P I",
    "URL": "U R L",
    "CRSIS": "crisis",
    "JSON": "jason",
    "JSONL": "jason L",
    "HTML": "H T M L",
    "CSS": "C S S",
    "HTTP": "H T T P",
    "HTTPS": "H T T P S",
    "CPU": "C P U",
    "GPU": "G P U",
    "RAM": "ram",
    "SSD": "S S D",
    "USB": "U S B",
    "AI": "A I",
    "ML": "M L",
    "NLP": "N L P",
    "OCR": "O C R",
    "PDF": "P D F",
    "SQL": "sequel",
    "CLI": "C L I",
    "IDE": "I D E",
    "UI": "U I",
    "UX": "U X",
}

# Number formatting for TTS
LARGE_NUMBER_PATTERN = re.compile(r"\b(\d{1,3}(?:,\d{3})+)\b")
DECIMAL_PATTERN = re.compile(r"(\d+)\.(\d+)")
PERCENTAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass
class FormattedOutput:
    """Differentiated spoken and display text."""

    spoken: str
    display: str
    confidence_level: str = "high"  # high, medium, low, uncertain


class SpeechFormatter:
    """Format text for voice-friendly TTS output.

    Produces both spoken (TTS-optimized) and display (screen-optimized)
    versions of text. Spoken text has markdown stripped, abbreviations
    expanded, and internal tokens removed.
    """

    def format(self, text: str) -> str:
        """Format text for TTS (backward compatible).

        Args:
            text: Raw text to format

        Returns:
            Voice-friendly string
        """
        return self.format_for_speech(text).spoken

    def format_for_speech(self, text: str, confidence: float = 1.0) -> FormattedOutput:
        """Format text into spoken and display variants.

        Args:
            text: Raw text to format
            confidence: Confidence level (0.0-1.0) for answer shaping

        Returns:
            FormattedOutput with spoken and display text
        """
        display = self._format_display(text)
        spoken = self._format_spoken(text)

        # Confidence-based answer shaping
        confidence_level = "high"
        if confidence < 0.5:
            confidence_level = "uncertain"
            spoken = self._add_uncertainty_hedge(spoken)
        elif confidence < 0.7:
            confidence_level = "low"
            spoken = self._add_low_confidence_hedge(spoken)
        elif confidence < 0.85:
            confidence_level = "medium"

        return FormattedOutput(
            spoken=spoken,
            display=display,
            confidence_level=confidence_level,
        )

    def _format_display(self, text: str) -> str:
        """Format text for screen display (minimal changes)."""
        formatted = LEADING_USER_PREFIX.sub("", text)
        formatted = INTERNAL_FACT_TOKEN.sub("", formatted)

        # Remove internal IDs from display text
        for pattern in INTERNAL_ID_PATTERNS:
            formatted = pattern.sub("", formatted)

        formatted = re.sub(r"\s+", " ", formatted).strip()
        return formatted

    def _format_spoken(self, text: str) -> str:
        """Format text for TTS speech."""
        formatted = LEADING_USER_PREFIX.sub("", text)
        formatted = INTERNAL_FACT_TOKEN.sub("", formatted)

        # Remove internal IDs
        for pattern in INTERNAL_ID_PATTERNS:
            formatted = pattern.sub("", formatted)

        # Sanitize paths
        formatted = WINDOWS_PATH_PATTERN.sub("your local folder", formatted)
        formatted = LINUX_PATH_PATTERN.sub("a local path", formatted)

        # Replace internal strings
        formatted = formatted.replace(
            "BG1_BUSY_ACTIVE", "the heavy task lane is currently busy"
        )

        # Format time meridiem
        formatted = TIME_MERIDIEM_PATTERN.sub(
            lambda match: " A M" if match.group(1).lower().startswith("a") else " P M",
            formatted,
        )

        # Strip markdown code blocks first (before other markdown)
        formatted = MARKDOWN_CODE_BLOCK.sub("", formatted)

        # Strip markdown formatting
        formatted = MARKDOWN_HEADING.sub("", formatted)
        formatted = MARKDOWN_BOLD.sub(r"\1", formatted)
        formatted = MARKDOWN_ITALIC.sub(lambda m: m.group(1) or m.group(2), formatted)
        formatted = MARKDOWN_LINK.sub(r"\1", formatted)
        formatted = MARKDOWN_CODE.sub(r"\1", formatted)
        formatted = MARKDOWN_LIST.sub("", formatted)
        formatted = MARKDOWN_HORIZONTAL_RULE.sub("", formatted)
        formatted = MARKDOWN_BLOCKQUOTE.sub("", formatted)

        # Format URLs for speech
        formatted = URL_PATTERN.sub(self._url_to_speech, formatted)

        # Expand abbreviations
        for abbrev, expansion in ABBREVIATION_MAP.items():
            formatted = re.sub(r"\b" + re.escape(abbrev) + r"\b", expansion, formatted)

        # Format percentages
        formatted = PERCENTAGE_PATTERN.sub(r"\1 percent", formatted)

        # Format large numbers (remove commas for speech)
        formatted = LARGE_NUMBER_PATTERN.sub(
            lambda m: m.group(0).replace(",", ""), formatted
        )

        # Format decimal numbers
        formatted = DECIMAL_PATTERN.sub(r"\1 point \2", formatted)

        # Clean up whitespace
        formatted = re.sub(r"\s+", " ", formatted).strip()

        # Truncate very long responses for voice
        if len(formatted) > 500:
            sentences = formatted.split(". ")
            truncated = []
            length = 0
            for sentence in sentences:
                if length + len(sentence) > 450:
                    break
                truncated.append(sentence)
                length += len(sentence) + 2
            if truncated:
                formatted = ". ".join(truncated) + "."
            else:
                formatted = formatted[:450] + "."

        return formatted

    @staticmethod
    def _url_to_speech(match: re.Match) -> str:
        """Convert URL to speech-friendly format."""
        url = match.group(0)
        # Extract domain for speech
        domain_match = re.search(r"https?://(?:www\.)?([^/\s]+)", url)
        if domain_match:
            domain = domain_match.group(1)
            # Speak dots as "dot"
            spoken_domain = domain.replace(".", " dot ")
            return spoken_domain
        return "a web address"

    @staticmethod
    def _add_uncertainty_hedge(text: str) -> str:
        """Add uncertainty hedge for low-confidence answers."""
        hedges = [
            "I'm not entirely sure, but ",
            "I may not have this right, but ",
        ]
        # Use first character hash for deterministic selection
        idx = ord(text[0]) % len(hedges) if text else 0
        return hedges[idx] + text[0].lower() + text[1:] if text else text

    @staticmethod
    def _add_low_confidence_hedge(text: str) -> str:
        """Add mild hedge for medium-confidence answers."""
        hedges = [
            "Based on what I have, ",
            "From what I can tell, ",
        ]
        idx = ord(text[0]) % len(hedges) if text else 0
        return hedges[idx] + text[0].lower() + text[1:] if text else text
