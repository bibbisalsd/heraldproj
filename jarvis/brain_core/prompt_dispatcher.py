from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.world_model.state import WorldState

from .deterministic_understanding import analyze_utterance
from .semantic_command_match import SemanticCommandMatcher
from ..observability.intent_miss_logger import IntentMissLogger

HEAVY_PHRASES = (
    "research", "scrape", "crawl", "look up", "search for", "search the web",
    "google for", "find online", "find out", "tell me everything about",
    "deep dive", "deep analysis", "in depth", "in-depth", "comprehensive",
    "thorough", "generate code", "write code", "write me", "build me",
    "create a script", "refactor", "debug", "analyze code", "review code",
    "code review", "analyze image", "analyze this image", "look at this",
    "look at my screen", "what's on my screen", "what is on screen",
    "screen query", "summarize file", "summarize this", "summarize document",
    "read this file", "analyze file", "view website", "view my website",
    "open website", "open my website", "load website", "load my website",
    "fetch website", "fetch my website", "check website", "go to website",
    "help me understand", "explain in detail", "compare", "contrast",
    "evaluate", "investigate",
)

class TaskClassifier:
    def classify(self, text: str) -> "TaskDecision":
        lowered = text.lower().strip()
        if any(phrase in lowered for phrase in HEAVY_PHRASES):
            return TaskDecision(lane="bg1", reason="heavy_match", match_type="classifier", intent="heavy_task", normalized_text=lowered)

        if re.search(
            r"\b(?:dot|point)\s*(?:com|org|net|io|co|us|gov|edu)\b", lowered
        ) or re.search(r"\bhttps?://", lowered):
            return TaskDecision(lane="bg1", reason="url_detected", match_type="classifier", intent="heavy_task", normalized_text=lowered)

        word_count = len(lowered.split())
        if word_count > 25:
            chat_indicators = {
                "story", "poem", "joke", "tale", "fiction",
                "was thinking", "wanted to tell you",
            }
            if any(w in lowered for w in chat_indicators):
                return TaskDecision(lane="realtime", reason="general_match", match_type="classifier", intent="general_chat", normalized_text=lowered)

            import logging
            logging.getLogger(__name__).debug(
                f"TaskClassifier: complex request detected (word_count={word_count})"
            )
            return TaskDecision(lane="bg1", reason="complex_request", match_type="classifier", intent="heavy_task", normalized_text=lowered)

        return TaskDecision(lane="realtime", reason="general_match", match_type="classifier", intent="general_chat", normalized_text=lowered)



# Phase 3: Tool-first decision policy
# Queries that should ALWAYS go to tools first (before LLM/BG1)
TOOL_FIRST_INTENTS = {
    "time_query": True,  # local_now tool
    "day_query": True,  # local_now tool
    "date_query": True,  # local_now tool
    "math_query": True,  # calculator tool
    "file_write": True,  # file_write tool
    "code_run": True,  # code_runner tool
    "memory_inspect": True,  # memory service
    "memory_list": True,  # memory service
    "memory_edit": True,  # memory service
    "memory_forget": True,  # memory service
    "app_launch": True,  # app_ops tool
    "app_focus": True,  # app_ops tool
    "greeting": True,
    # Phase 2b: Performance & BG1 queries always route to handler, never LLM
    "performance_query": True,
    "bg1_update": True,
    "bg1_result": True,
    "owner_memory": True,
    "self_query": True,
    "codebase_query": True,
}

# Intents that can be tool-first OR LLM depending on complexity
TOOL_OPTIONAL_INTENTS = {
    "website_check": True,  # Can use web_fetch (realtime) or BG1 for multi-page
    "screen_show": True,  # Can use screen capture (realtime) or BG1
}


def _compact(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


EXACT_INTENTS = {
    "status": {
        "status",
        "are you online",
        "are you there",
    },
    "time_query": {
        "what time is it",
        "whats the time",
        "what s the time",
        "what is the time",
        "time now",
        "current time",
    },
    "day_query": {
        "what day is it",
        "what day is today",
        "what weekday is it",
        "what day are we on",
    },
    "date_query": {
        "what date is it",
        "what is the date",
        "what s the date",
        "whats the date",
        "what is today's date",
        "what is todays date",
        "what day of the month is it",
    },
    "job_cancel": {
        "cancel current heavy task",
        "stop heavy task",
        "cancel heavy",
    },
    "notify_when_free": {
        "notify me when free",
        "let me know when free",
        "tell me when free",
    },
    "recall_name": {
        "what is my name",
        "whats my name",
        "what s my name",
        "do you know my name",
    },
    "app_launch": {
        "open notepad",
        "open calculator",
        "open chrome",
        "open edge",
        "open firefox",
        "open explorer",
        "launch notepad",
        "launch calculator",
        "launch chrome",
        "start notepad",
        "start calculator",
        "start chrome",
    },
    "app_focus": {
        "focus chrome",
        "focus notepad",
        "focus calculator",
        "switch to chrome",
        "switch to notepad",
        "bring chrome to front",
        "bring notepad to front",
    },
    "memory_inspect": {
        "memory inspect",
        "check memory",
    },
    "memory_list": {
        "memory list",
        "list memories",
        "show memories",
        "show memory",
        "my memories",
    },
    "memory_edit": {
        "memory edit",
        "edit memory",
        "update memory",
        "change memory",
    },
    "memory_forget": {
        "memory forget",
        "delete memory",
        "remove memory",
    },
    "memory_backup": {
        "memory backup",
        "backup memory",
        "save memory backup",
    },
    "memory_restore": {
        "memory restore",
        "restore memory",
        "restore from backup",
    },
    "memory_list_backups": {
        "memory backups",
        "list backups",
        "show backups",
    },
    "memory_save": {
        "save memory",
        "remember that",
        "save that",
        "save a memory",
    },
    "health_report": {
        "health",
        "health report",
        "system health",
        "health dashboard",
        "dashboard",
        "diagnostics",
    },
    "addon_status": {
        "addon status",
        "addons status",
        "list addons",
        "show addons",
        "what addons are installed",
    },
    "addon_health": {
        "addon health",
        "check addon health",
        "is addon healthy",
    },
    "addon_channel": {
        "addon channel",
        "set addon channel",
        "toggle addon channel",
    },
    # Phase 2b: Performance & BG1 exact matches
    "performance_query": {
        "why are you slow",
        "why are you so slow",
        "why are responses slow",
        "why so slow",
        "how can i make you faster",
        "how to improve your speed",
        "improve speed",
        "speed up",
        "response time",
        "your response time",
        "you are slow",
        "you are too slow",
        "performance",
    },
    "bg1_update": {
        "any progress",
        "any update",
        "any updates",
        "task progress",
        "how is the task going",
        "how is the research going",
        "are you done",
        "are you finished",
        "still working",
        "still running",
        "give me an update",
        "update on the task",
        "what are you doing",
        "what are you doin",
        "what are you doig",
        "whats happening",
        "what is happening",
    },
    "bg1_result": {
        "what did you find",
        "what did you find out",
        "what were the results",
        "what are the results",
        "show me the results",
        "give me the results",
        "results please",
        "what came back",
        "research results",
        "what did you learn",
        "what did you discover",
    },
}


@dataclass(frozen=True)
class TaskDecision:
    lane: str
    reason: str
    match_type: str
    intent: str | None
    normalized_text: str
    idempotency_key: str | None = None
    needs_job_status_context: bool = False
    needs_memory_context: bool = False


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance implementation."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    previous_row = range(len(b) + 1)
    for i, c1 in enumerate(a):
        current_row = [i + 1]
        for j, c2 in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


class PromptDispatcher:
    def __init__(
        self,
        wake_word: str = "jarvis",
        wake_word_enabled: bool = True,
        tool_registry: Any | None = None,
    ) -> None:
        self.wake_word = wake_word
        self.wake_word_enabled = wake_word_enabled
        self.semantic_matcher = SemanticCommandMatcher()
        self.task_classifier = TaskClassifier()
        self.miss_logger = IntentMissLogger()
        self.tool_registry = tool_registry

    def normalize_text(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"(?:^|\s)[,:\-!?\.]+(?=\s|$)", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,:-!?._")
        return cleaned or text.strip()

    def contains_wake_word(self, text: str) -> bool:
        if not self.wake_word_enabled or not self.wake_word:
            return True
        for token in re.split(r"\s+", text.strip()):
            cleaned = re.sub(r"[^a-z0-9]", "", token.lower())
            if cleaned and self._looks_like_wake_word(cleaned):
                return True
        return False

    def _determine_lane(self, intent: str, default_lane: str = "realtime") -> str:
        if self.tool_registry:
            desc = self.tool_registry.descriptor(intent)
            if desc:
                if desc.safe_in_realtime:
                    return "realtime"
                if desc.safe_in_bg1:
                    return "bg1"
        return default_lane

    def route(
        self,
        text: str,
        bg1_busy: bool = False,
        elapsed_ms: float = 0.0,
        world_state: WorldState | None = None,
    ) -> TaskDecision:
        normalized_text = self.normalize_text(text)
        key = _compact(normalized_text)
        signals = analyze_utterance(normalized_text)
        tokens = set(key.split())

        # Stage 0: Priority specialist triggers (Code/Vision)
        # Check this BEFORE deterministic clock/time to avoid misrouting "time complexity"
        code_gen_words = {
            "write",
            "create",
            "generate",
            "build",
            "program",
        }
        if any(w in tokens for w in code_gen_words) and any(
            w in tokens
            for w in (
                "code",
                "script",
                "function",
                "class",
                "python",
                "html",
                "css",
                "component",
                "rust",
                "go",
                "java",
                "javascript",
                "typescript",
                "c",
                "cpp",
                "assembly",
                "kotlin",
                "swift",
                "implementation",
                "algorithm",
                "library",
                "module",
            )
        ):
            return TaskDecision(
                lane="bg1",
                reason="natural_code_request",
                match_type="deterministic",
                intent="heavy_task",
                normalized_text=normalized_text,
                idempotency_key=self._idempotency_key(key),
            )

        exact_intent = self._match_exact(key)
        if exact_intent is not None:
            return TaskDecision(
                lane="realtime",
                reason=f"exact_{exact_intent}",
                match_type="exact",
                intent=exact_intent,
                normalized_text=normalized_text,
                needs_job_status_context=exact_intent
                in {"status", "job_cancel", "notify_when_free"},
                needs_memory_context=exact_intent == "recall_name",
            )

        strict_deterministic_intent = self._match_strict_deterministic(signals)
        if strict_deterministic_intent is not None:
            return TaskDecision(
                lane="realtime",
                reason=f"deterministic_{strict_deterministic_intent}",
                match_type="deterministic",
                intent=strict_deterministic_intent,
                normalized_text=normalized_text,
                needs_job_status_context=strict_deterministic_intent
                in {"job_status", "job_cancel", "notify_when_free"},
                needs_memory_context=strict_deterministic_intent == "recall_name",
            )

        soft_deterministic_intent = self._match_soft_deterministic(signals)
        if soft_deterministic_intent is not None:
            # Phase 3: Tool-first decision policy
            # Check if this intent should go to a tool first
            lane = self._determine_lane(soft_deterministic_intent, "realtime")
            reason = f"deterministic_{soft_deterministic_intent}"

            if TOOL_FIRST_INTENTS.get(soft_deterministic_intent):
                lane = "realtime"
                reason = f"tool_first_{soft_deterministic_intent}"
                # If tool has recent failures, drop tool-first routing
                if (
                    world_state is not None
                    and soft_deterministic_intent in world_state.tool_availability
                ):
                    th = world_state.tool_availability[soft_deterministic_intent]
                    if th.error_count > 2:
                        reason = f"tool_fault_fallback_{soft_deterministic_intent}"
                        # Demote to LLM handling
                        soft_deterministic_intent = None

            elif TOOL_OPTIONAL_INTENTS.get(soft_deterministic_intent):
                lane = self._determine_lane(soft_deterministic_intent, "realtime")
                reason = f"tool_preferred_{soft_deterministic_intent}"

            if soft_deterministic_intent is not None:
                return TaskDecision(
                    lane=lane,
                    reason=reason,
                    match_type="deterministic",
                    intent=soft_deterministic_intent,
                    normalized_text=normalized_text,
                )

        # WorldState bias: Open BG1 jobs + ambiguous intent -> bias toward 'bg1_update'
        if world_state is not None and world_state.open_bg1_jobs:
            # Stage 4: Lexical bias only (before semantic match)
            if signals.asks_bg1_update or ("update" in key and len(key.split()) < 4):
                return TaskDecision(
                    lane="realtime",
                    reason="worldstate_bg1_bias",
                    match_type="deterministic",
                    intent="bg1_update",
                    normalized_text=normalized_text,
                )

        if not self._looks_like_command(key):
            semantic = None
        elif elapsed_ms > 500.0:
            semantic = None
        else:
            semantic = self.semantic_matcher.match(key)

        if (
            semantic is not None
            and semantic.intent is not None
            and self._semantic_intent_allowed(semantic.intent, key)
        ):
            lane = self._determine_lane(semantic.intent, "realtime")
            if TOOL_FIRST_INTENTS.get(semantic.intent):
                lane = "realtime"

            if lane == "bg1" and bg1_busy:
                return TaskDecision(
                    lane="realtime",
                    reason="BG1_BUSY_ACTIVE",
                    match_type="semantic",
                    intent="bg1_busy_rejection",
                    normalized_text=normalized_text,
                    needs_job_status_context=True,
                )
            return TaskDecision(
                lane=lane,
                reason=f"semantic_{semantic.intent}",
                match_type="semantic",
                intent=semantic.intent,
                normalized_text=normalized_text,
                needs_job_status_context=semantic.intent
                in {"job_status", "job_cancel", "notify_when_free"},
                needs_memory_context=False,
            )

        # Route stories/poems/jokes to general_chat (renderer) instead of missing
        story_words = {"story", "poem", "joke", "tale", "fiction"}
        if any(w in tokens for w in story_words):
            return TaskDecision(
                lane="realtime",
                reason="story_request",
                match_type="deterministic",
                intent="general_chat",
                normalized_text=normalized_text,
                needs_memory_context=True,
            )

        # We classify as an intent miss because it slipped past strict/semantic matchers
        # and has to rely on the general LLM fallback classifiers.
        self.miss_logger.log_miss(text, normalized_text)

        classifier = self.task_classifier.classify(key)
        if classifier.lane == "bg1":
            if bg1_busy:
                return TaskDecision(
                    lane="realtime",
                    reason="BG1_BUSY_ACTIVE",
                    match_type="classifier",
                    intent="bg1_busy_rejection",
                    normalized_text=normalized_text,
                    needs_job_status_context=True,
                )
            return TaskDecision(
                lane="bg1",
                reason="heavy_request",
                match_type="classifier",
                intent="heavy_task",
                normalized_text=normalized_text,
                idempotency_key=self._idempotency_key(key),
            )

        # WorldState bias: Low aggregate confidence -> prefer deterministic routes over LLM fallback
        if world_state is not None and world_state.aggregate_confidence < 0.5:
            # Fallback to deterministic generic catchall instead of deep LLM invocation
            return TaskDecision(
                lane="realtime",
                reason="low_confidence_fallback",
                match_type="deterministic",
                intent="general_chat",
                normalized_text=normalized_text,
                needs_memory_context=False,
            )

        return TaskDecision(
            lane="realtime",
            reason="quick_or_general",
            match_type="classifier",
            intent="general_chat",
            normalized_text=normalized_text,
            needs_memory_context=True,
        )

    def _semantic_intent_allowed(self, intent: str, key: str) -> bool:
        tokens = {token for token in key.split() if token}
        if intent == "time_query":
            return bool(tokens & {"time", "clock", "hour"})
        if intent == "day_query":
            return bool(tokens & {"day", "weekday", "today"})
        if intent == "date_query":
            return bool(tokens & {"date", "month", "year", "today", "todays"})
        if intent == "job_status":
            status_tokens = {
                "status",
                "busy",
                "doing",
                "running",
                "happening",
                "progress",
                "update",
                "job",
                "task",
                "work",
            }
            return bool(tokens & status_tokens)
        if intent == "notify_when_free":
            availability_tokens = {
                "free",
                "available",
                "done",
                "finished",
                "complete",
                "idle",
                "busy",
            }
            task_tokens = {
                "task",
                "job",
                "heavy",
                "work",
                "progress",
                "running",
                "doing",
            }
            return bool(tokens & availability_tokens) or bool(tokens & task_tokens)
        return True

    def _looks_like_command(self, key: str) -> bool:
        """Check if utterance has command-like keywords that warrant semantic matching.

        This is a cheap gate to avoid warming up the embedding model for open-ended
        questions like 'tell me when christmas is' or 'what is a dog'.
        """
        tokens = set(key.split())

        # Command intent keywords - specific system commands only
        # These match the INTENT_PHRASES in semantic_command_match.py
        command_tokens = {
            # Job status / task management
            "status",
            "busy",
            "progress",
            "cancel",
            "stop",
            "doing",
            "age",
            "old",
            "name",
            "call",
            "job",
            "task",
            "code",
            "codebase",
            "repo",
            "repository",
            # Job cancel
            "cancel",
            "abort",
            "kill",
            "halt",
            "terminate",
            # Notify when free (only when about task completion)
            "notify",
            "ping",
            # Time / date queries (specific)
            "time",
            "clock",
            "weekday",
            "date",
            # Addon control
            "addon",
            "enable",
            "disable",
            "activate",
            "deactivate",
        }

        # Also check for command-like phrases
        key_lower = key.lower()
        command_phrases = [
            "what are you doing",
            "how are you doing",
            "whats happening",
            "any progress",
            "whats going on",
            "stop what",
            "abort what",
        ]
        for phrase in command_phrases:
            if phrase in key_lower:
                return True

        # "notify/tell/let me when" only matches if followed by free/done/available
        if any(
            x in key_lower
            for x in ["notify me when", "tell me when", "let me know when"]
        ):
            if any(
                x in key_lower
                for x in ["free", "done", "finished", "available", "complete"]
            ):
                return True

        # Phase 2: Fuzzy check for status words to handle typos like 'doig'
        status_triggers = {"doing", "happening", "running", "going", "status", "progress"}
        for token in tokens:
            for trigger in status_triggers:
                if len(token) >= 4 and _levenshtein(token, trigger) <= 1:
                    return True

        # If no command keywords present, skip semantic matching
        return bool(tokens & command_tokens)

    def _match_exact(self, key: str) -> str | None:
        for intent, phrases in EXACT_INTENTS.items():
            if key in phrases:
                return intent
        return None

    def _match_strict_deterministic(self, signals) -> str | None:
        if signals.asks_time:
            return "time_query"
        if signals.asks_day:
            return "day_query"
        if signals.asks_date:
            return "date_query"
        if signals.asks_name_recall:
            return "recall_name"
        if signals.asks_cancel:
            return "job_cancel"
        if signals.asks_notify_when_free:
            return "notify_when_free"
        if signals.asks_status:
            return "job_status"
        if (
            signals.asks_age_recall
            or signals.asks_address_preference_recall
            or signals.asks_owner_summary
        ):
            return "owner_memory"
        return None

    def _match_soft_deterministic(self, signals) -> str | None:
        """Second-stage deterministic matcher for non-exact signals."""
        
        # 1. Identity and Code Location (High priority)
        if (
            signals.asks_identity
            or signals.asks_runtime_location
            or signals.asks_code_location
            or signals.asks_tools
            or signals.asks_workflow
        ):
            return "self_query"

        # 2. Greetings and Help
        if signals.is_greeting:
            return "greeting"
        if signals.asks_capabilities:
            return "help_query"

        # 3. System Management
        if signals.asks_performance:
            return "performance_query"
        if signals.asks_health_report:
            return "health_report"
        if signals.asks_bg1_update:
            return "bg1_update"
        if signals.asks_bg1_result:
            return "bg1_result"

        # 4. Codebase/Screen (after identity check)
        if signals.mentions_codebase:
            if signals.asks_code_location or signals.asks_identity:
                return "self_query"
            return "codebase_query"
        if signals.mentions_screen:
            # If it's a query like "what's on my screen", use screen_query
            # If it's a command like "show me my screen", use screen_show
            if signals.wants_screen_inspection:
                return "screen_query"
            return "screen_show"
        if signals.asks_screen_show:
            return "screen_show"
        if signals.asks_website_check or signals.has_url_mention:
            return "website_check"

        # 5. App Controls
        if signals.wants_app_launch:
            return "app_launch"
        if signals.wants_app_focus:
            return "app_focus"

        # 6. Memory Operations
        if signals.wants_memory_list:
            return "memory_list"
        if signals.wants_memory_inspect:
            return "memory_inspect"
        if signals.wants_memory_forget:
            return "memory_forget"
        if signals.wants_memory_backup:
            return "memory_backup"
        if signals.wants_memory_restore:
            return "memory_restore"
        if signals.wants_memory_list_backups:
            return "memory_list_backups"

        # 7. Addon Controls
        if signals.wants_addon_status:
            return "addon_status"
        if signals.wants_addon_health:
            return "addon_health"
        if signals.wants_addon_channel:
            return "addon_channel"

        # 8. Personal Info (Recall/Save)
        if (
            signals.declared_name
            or signals.declared_age
            or signals.declared_address_preference is not None
            or signals.asks_age_recall
            or signals.asks_address_preference_recall
            or signals.asks_owner_summary
        ):
            return "owner_memory"

        # 9. Other deterministic queries
        if signals.asks_hearing_check:
            return "hearing_query"
        if signals.asks_wellbeing:
            return "wellbeing_query"

        return None

    def _idempotency_key(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def _wake_word_aliases(self) -> set[str]:
        normalized = re.sub(r"[^a-z0-9]", "", self.wake_word.lower())
        aliases = {normalized} if normalized else set()
        if normalized == "jarvis":
            aliases.update(
                {
                    "javis",
                    "jervis",
                    "jovis",
                    "javas",
                    "jarviss",
                    "java",
                    "jabba",
                    "jabbas",
                    "travis",
                    "javos",
                }
            )
        return aliases

    def _looks_like_wake_word(self, token: str) -> bool:
        return token in self._wake_word_aliases()
