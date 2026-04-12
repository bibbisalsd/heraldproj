"""BG1 Narrator: Natural spoken UX for background task execution.

This module provides natural, human-friendly narration for BG1 task
lifecycle events. It replaces raw task ID speech with conversational
updates that sound natural and informative.

Key principles:
- Never speak task IDs unless explicitly asked for debug info
- Use natural phrasing for start/update/completion
- Match tone to task type (research, code, vision, etc.)
- Provide progress information in human terms, not percentages alone
"""

from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass
class NarrationStyle:
    """Style configuration for BG1 narration."""

    formal: bool = False  # Formal vs casual tone
    include_sir: bool = False  # Add "sir" or similar address
    address_term: str | None = None  # "sir", "mate", "boss", etc.
    verbose: bool = False  # More detailed vs concise


# Natural task start phrases
TASK_START_PHRASES = [
    "Okay, I'm looking into that now.",
    "Understood. I'll check that for you now.",
    "Alright, I'm on it.",
    "Got it. Let me look into that.",
    "Right, I'm checking that now.",
    "Understood. I'm on it.",
    "Alright, let me check that for you.",
]

# Natural task start phrases with address term
TASK_START_PHRASES_WITH_ADDRESS = [
    "Okay, I'm looking into that now, {address}.",
    "Understood. I'll check that for you now, {address}.",
    "Alright, I'm on it, {address}.",
    "Got it. Let me look into that, {address}.",
    "Right, I'm checking that now, {address}.",
]


# Natural progress update phrases
PROGRESS_UPDATE_PHRASES = {
    "early": [
        "I'm still in the early stages of checking that.",
        "I've just started looking into it.",
        "I'm beginning to check that now.",
        "Still gathering information on that.",
    ],
    "mid": [
        "The check is going well. I'm about halfway through.",
        "Making good progress. I'm around the middle of the analysis.",
        "I'm making steady progress through the details.",
        "About halfway through the analysis now.",
    ],
    "late": [
        "I'm nearly done looking into that.",
        "Almost finished checking the details.",
        "Just wrapping up the final part now.",
        "I'm in the final stages of the analysis.",
    ],
}


# Natural progress update phrases with address term
PROGRESS_UPDATE_PHRASES_WITH_ADDRESS = {
    "early": [
        "I'm still in the early stages of checking that, {address}.",
        "I've just started looking into it, {address}.",
    ],
    "mid": [
        "The check is going well. I'm about halfway through, {address}.",
        "Making good progress, {address}. Around the middle of the analysis.",
    ],
    "late": [
        "I'm nearly done looking into that, {address}.",
        "Almost finished checking, {address}. Just wrapping up.",
    ],
}


# Natural completion phrases
COMPLETION_PHRASES = [
    "Okay, I've finished looking into that.",
    "I've completed the analysis.",
    "Alright, I'm done checking that for you.",
    "Finished. Here's what I found.",
    "Analysis complete. Here are the results.",
    "I've finished checking that. Here's the summary.",
]

# Natural completion phrases with address term
COMPLETION_PHRASES_WITH_ADDRESS = [
    "Okay, I've finished looking into that, {address}.",
    "I've completed the analysis, {address}.",
    "Alright, I'm done checking that for you, {address}.",
    "Finished. Here's what I found, {address}.",
]


# Task type specific narration
# Phase 5: Expanded task type prefixes for richer BG1 narration
TASK_TYPE_PREFIXES = {
    "research": "research",
    "code": "code analysis",
    "vision": "visual analysis",
    "web": "website check",
    "analysis": "analysis",
    "search": "web search",
    "download": "download",
    "scrape": "page scrape",
    "audit": "code audit",
    "file": "file operation",
    "memory": "memory operation",
    "summarize": "summary",
    "compare": "comparison",
    "monitor": "monitoring check",
    "default": "check",
}


@dataclass
class NarrationResult:
    """Result of generating a narration."""

    spoken_text: str
    display_text: str | None = None
    narration_type: str = "generic"  # start, progress, completion, error
    progress_percent: float = 0.0
    task_subject: str | None = None


class BG1Narrator:
    """Generates natural spoken narration for BG1 task lifecycle.

    The narrator produces human-friendly messages for:
    - Task start (acknowledgment)
    - Progress updates (checkpoint-based)
    - Near completion (optional advance notice)
    - Task completion (result summary intro)
    - Error/failure (graceful degradation)

    Task IDs are kept internal and only exposed in display_text
    when explicitly requested for debug purposes.
    """

    def __init__(self, style: NarrationStyle | None = None) -> None:
        self.style = style or NarrationStyle()

    def narrate_start(
        self,
        task_subject: str | None = None,
        task_type: str = "default",
    ) -> NarrationResult:
        """Generate natural task start narration.

        Args:
            task_subject: Optional subject of the task (e.g., "France", "the codebase")
            task_type: type of task (research, code, vision, web, analysis)

        Returns:
            NarrationResult with spoken and display text
        """
        # Select base phrase
        phrases = (
            TASK_START_PHRASES_WITH_ADDRESS
            if self.style.address_term
            else TASK_START_PHRASES
        )
        base = random.choice(phrases)

        # Format with address term if applicable
        if self.style.address_term:
            spoken = base.format(address=self.style.address_term)
        else:
            spoken = base

        # Add subject context if available
        if task_subject:
            task_name = TASK_TYPE_PREFIXES.get(task_type, TASK_TYPE_PREFIXES["default"])
            spoken = f"{spoken} I'm {task_name} {task_subject}."

        return NarrationResult(
            spoken_text=spoken,
            display_text=spoken,
            narration_type="start",
            task_subject=task_subject,
        )

    def narrate_progress(
        self,
        progress_percent: float,
        task_subject: str | None = None,
        task_type: str = "default",
    ) -> NarrationResult:
        """Generate natural progress update narration.

        Args:
            progress_percent: Progress percentage (0-100)
            task_subject: Optional subject of the task
            task_type: type of task

        Returns:
            NarrationResult with spoken and display text
        """
        # Determine progress stage
        if progress_percent < 35:
            stage = "early"
        elif progress_percent < 75:
            stage = "mid"
        else:
            stage = "late"

        # Select phrase
        phrases = (
            PROGRESS_UPDATE_PHRASES_WITH_ADDRESS
            if self.style.address_term
            else PROGRESS_UPDATE_PHRASES
        )
        base_list = phrases.get(stage, phrases["mid"])
        base = random.choice(base_list)

        # Format with address term
        if self.style.address_term:
            spoken = base.format(address=self.style.address_term)
        else:
            spoken = base

        # Add subject context
        if task_subject:
            task_name = TASK_TYPE_PREFIXES.get(task_type, TASK_TYPE_PREFIXES["default"])
            if stage == "late":
                spoken = (
                    f"{spoken} Just finishing up the {task_name} of {task_subject}."
                )
            elif stage == "mid":
                spoken = (
                    f"{spoken} Still working through the {task_name} of {task_subject}."
                )

        return NarrationResult(
            spoken_text=spoken,
            display_text=spoken,
            narration_type="progress",
            progress_percent=progress_percent,
            task_subject=task_subject,
        )

    def narrate_completion(
        self,
        result_summary: str | None = None,
        task_subject: str | None = None,
        task_type: str = "default",
    ) -> NarrationResult:
        """Generate natural task completion narration.

        Args:
            result_summary: Optional brief summary of results
            task_subject: Optional subject of the task
            task_type: type of task

        Returns:
            NarrationResult with spoken and display text
        """
        # Select base phrase
        phrases = (
            COMPLETION_PHRASES_WITH_ADDRESS
            if self.style.address_term
            else COMPLETION_PHRASES
        )
        base = random.choice(phrases)

        # Format with address term
        if self.style.address_term:
            spoken = base.format(address=self.style.address_term)
        else:
            spoken = base

        # Add result summary if available
        if result_summary:
            spoken = f"{spoken} {result_summary}"
        elif task_subject:
            task_name = TASK_TYPE_PREFIXES.get(task_type, TASK_TYPE_PREFIXES["default"])
            spoken = f"{spoken} The {task_name} of {task_subject} is complete."

        return NarrationResult(
            spoken_text=spoken,
            display_text=spoken,
            narration_type="completion",
            task_subject=task_subject,
        )

    def narrate_error(
        self,
        error_type: str = "unknown",
        task_subject: str | None = None,
        retry_available: bool = True,
    ) -> NarrationResult:
        """Generate natural error/failure narration.

        Args:
            error_type: type of error (timeout, unavailable, failed, unknown)
            task_subject: Optional subject of the task
            retry_available: Whether retry is possible

        Returns:
            NarrationResult with spoken and display text
        """
        error_phrases = {
            "timeout": "That's taking longer than expected. The operation timed out.",
            "unavailable": "I wasn't able to complete that. The required service is unavailable.",
            "failed": "I ran into an issue while checking that.",
            "unknown": "Something unexpected came up while I was looking into that.",
        }

        base = error_phrases.get(error_type, error_phrases["unknown"])

        # Add address term if applicable
        if self.style.address_term:
            spoken = f"{base} Sorry about that, {self.style.address_term}."
        else:
            spoken = base

        # Add retry option if available
        if retry_available:
            spoken = f"{spoken} Would you like me to try again?"

        # Add subject context
        if task_subject:
            spoken = f"{spoken} The check of {task_subject} couldn't be completed."

        return NarrationResult(
            spoken_text=spoken,
            display_text=spoken,
            narration_type="error",
        )

    def narrate_progress_checkpoint(
        self,
        progress_percent: float,
        task_subject: str | None = None,
        task_type: str = "default",
        checkpoint_thresholds: list[float] | None = None,
    ) -> NarrationResult | None:
        """Generate progress narration at standard checkpoints.

        Only produces narration at 15%, 60%, 95% checkpoints
        (or custom thresholds).

        Args:
            progress_percent: Current progress (0-100)
            task_subject: Optional subject of the task
            task_type: type of task
            checkpoint_thresholds: Custom checkpoint percentages

        Returns:
            NarrationResult if at checkpoint, None otherwise
        """
        thresholds = checkpoint_thresholds or [15.0, 60.0, 95.0]

        # Check if at a checkpoint
        at_checkpoint = any(
            abs(progress_percent - threshold) < 5.0  # 5% tolerance
            for threshold in thresholds
        )

        if not at_checkpoint:
            return None

        return self.narrate_progress(
            progress_percent=progress_percent,
            task_subject=task_subject,
            task_type=task_type,
        )


# Default narrator instance
_default_narrator: BG1Narrator | None = None


def get_narrator(style: NarrationStyle | None = None) -> BG1Narrator:
    """Get or create the default narrator instance."""
    global _default_narrator
    if _default_narrator is None or (style and _default_narrator.style != style):
        _default_narrator = BG1Narrator(style=style)
    return _default_narrator


def narrate_start(
    task_subject: str | None = None,
    task_type: str = "default",
    style: NarrationStyle | None = None,
) -> NarrationResult:
    """Convenience function for task start narration."""
    return get_narrator(style).narrate_start(task_subject, task_type)


def narrate_progress(
    progress_percent: float,
    task_subject: str | None = None,
    task_type: str = "default",
    style: NarrationStyle | None = None,
) -> NarrationResult:
    """Convenience function for progress narration."""
    return get_narrator(style).narrate_progress(
        progress_percent, task_subject, task_type
    )


def narrate_completion(
    result_summary: str | None = None,
    task_subject: str | None = None,
    task_type: str = "default",
    style: NarrationStyle | None = None,
) -> NarrationResult:
    """Convenience function for completion narration."""
    return get_narrator(style).narrate_completion(
        result_summary, task_subject, task_type
    )


def narrate_error(
    error_type: str = "unknown",
    task_subject: str | None = None,
    retry_available: bool = True,
    style: NarrationStyle | None = None,
) -> NarrationResult:
    """Convenience function for error narration."""
    return get_narrator(style).narrate_error(error_type, task_subject, retry_available)
