from __future__ import annotations

from dataclasses import dataclass
import re

from jarvis.name_profile import extract_name_candidate


WAKE_WORD_ALIASES = {
    "jarvis",
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
SELF_WORDS = WAKE_WORD_ALIASES | {"you", "your", "yourself", "assistant"}
QUESTION_WORDS = {
    "what",
    "who",
    "where",
    "when",
    "how",
    "can",
    "could",
    "do",
    "does",
    "are",
    "is",
    "which",
}
STATUS_WORDS = {"status", "busy", "progress", "update", "task", "job"}
CANCEL_WORDS = {"cancel", "stop", "abort", "halt", "kill", "terminate"}
NOTIFY_WORDS = {"notify", "tell", "let", "know", "ping"}
FREE_WORDS = {"free", "available", "done", "finished", "complete", "idle"}
CODE_WORDS = {
    "code",
    "codebase",
    "repo",
    "repository",
    "source",
    "file",
    "files",
    "module",
    "modules",
}
LOCATION_WORDS = {"where", "path", "folder", "location", "keep", "stored", "store"}
WORKFLOW_WORDS = {
    "work",
    "function",
    "operate",
    "built",
    "build",
    "pipeline",
    "flow",
    "route",
    "routing",
    "architecture",
}
CAPABILITY_WORDS = {"capability", "capabilities", "help", "support", "able"}
SCREEN_WORDS = {"screen", "display", "monitor", "screenshot", "desktop"}
INSPECT_WORDS = {
    "inspect",
    "look",
    "review",
    "analyze",
    "check",
    "read",
    "see",
    "audit",
    "examine",
    "scan",
    "search",
    "find",
    "error",
    "errors",
    "bug",
    "bugs",
    "issue",
    "issues",
    "extract",
}
APP_LAUNCH_WORDS = {"open", "launch", "start", "run"}
APP_FOCUS_WORDS = {"focus", "switch", "bring", "activate"}
MEMORY_INSPECT_WORDS = {"inspect", "show", "check", "view"}
MEMORY_LIST_WORDS = {"list", "show", "memories"}
MEMORY_FORGET_WORDS = {"forget", "delete", "remove", "clear"}
MEMORY_BACKUP_WORDS = {"backup", "export"}
MEMORY_SAVE_WORDS = {"save", "remember", "keep", "record", "store"}
MEMORY_RESTORE_WORDS = {"restore", "load", "import"}
ADDON_STATUS_WORDS = {"status", "list", "show", "addons"}
ADDON_HEALTH_WORDS = {"health", "healthy", "check"}
ADDON_CHANNEL_WORDS = {"channel", "set", "toggle"}
WELLBEING_WORDS = {"okay", "ok", "alright", "well", "feel", "feeling"}
HEARING_WORDS = {"hear", "hearing", "listening", "listen"}
ROLE_WORDS = {"role", "type", "identity"}
GREETING_WORDS = {"hello", "hi", "hey"}
THANKS_WORDS = {"thank", "thanks", "cheers", "appreciate"}
OWNER_WORDS = {"i", "me", "my", "myself"}
MEMORY_WORDS = {
    "memory",
    "memories",
    "remember",
    "reset",
    "wipe",
    "erase",
    "clear",
    "forget",
}
ARCHITECTURE_WORDS = {"architecture", "framework", "design"}
HEALTH_WORDS = {
    "health",
    "report",
    "dashboard",
    "diagnostic",
    "diagnostics",
    "monitor",
    "monitoring",
}
SEARCH_WORDS = {"search", "lookup", "research", "find", "who", "what", "where"}

# Phase 3: Natural phrase families
PERFORMANCE_WORDS = {
    "slow",
    "slower",
    "slowest",
    "speed",
    "fast",
    "faster",
    "quickest",
    "quick",
    "performance",
    "latency",
    "response",
    "time",
    "improve",
    "faster",
}
URL_PATTERNS = {
    "dot",
    "slash",
    "dash",
    "underscore",
    "double",
    "www",
    "http",
    "https",
    "com",
    "org",
    "net",
    "app",
    "dev",
    "io",
    "co",
}
ADDRESS_DECLARATION_PATTERN = re.compile(
    r"\b(?:refer to me as|call me|address me as|you can call me)\s+([a-z][a-z'\-]{0,39})(?:\s+or\s+([a-z][a-z'\-]{0,39}))?\b",
    re.IGNORECASE,
)
AGE_DECLARATION_PATTERN = re.compile(
    r"\b(?:my age is|i am|i'm|im)\s+(\d{1,3})(?:\s+years?\s+old)?\b",
    re.IGNORECASE,
)

FOLLOW_UP_DIRECT_PATTERNS = {
    "and",
    "also",
    "then",
    "what about",
    "how about",
    "can you",
    "could you",
    "will you",
    "would you",
    "do",
    "does",
    "did",
    "is",
    "are",
    "was",
    "were",
    "tell me",
    "show me",
    "give me",
    "explain",
    "why",
    "when",
    "where",
    "who",
    "which",
    "how",
}
FOLLOW_UP_REPAIR_PATTERNS = {
    "no i meant",
    "i meant",
    "sorry i meant",
    "actually",
    "wait",
    "no",
    "not that",
    "instead",
    "rephrase",
    "try again",
}


def normalize_text(text: str) -> str:
    lowered = text.lower().replace("’", "'").replace("â€™", "'")
    lowered = re.sub(r"[^a-z0-9'\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _normalize_token(token: str) -> str:
    cleaned = token.strip().lower().strip("'")
    if cleaned.endswith("'s"):
        cleaned = cleaned[:-2]
    alias_map = {
        "javis": "jarvis",
        "jervis": "jarvis",
        "jovis": "jarvis",
        "javas": "jarvis",
        "jarviss": "jarvis",
        "java": "jarvis",
        "jabba": "jarvis",
        "jabbas": "jarvis",
    }
    return alias_map.get(cleaned, cleaned)


def _stem(token: str) -> str:
    stemmed = _normalize_token(token)
    if stemmed.endswith("ies") and len(stemmed) > 4:
        return stemmed[:-3] + "y"
    for suffix in ("ing", "ers", "er", "ed", "es", "s"):
        if stemmed.endswith(suffix) and len(stemmed) - len(suffix) >= 3:
            return stemmed[: -len(suffix)]
    return stemmed


def _tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [_normalize_token(token) for token in normalized.split() if token]


def _contains_sequence(tokens: list[str], sequence: tuple[str, ...]) -> bool:
    if len(tokens) < len(sequence):
        return False
    for index in range(len(tokens) - len(sequence) + 1):
        if tuple(tokens[index : index + len(sequence)]) == sequence:
            return True
    return False


@dataclass(frozen=True)
class DeterministicSignals:
    text: str
    normalized_text: str
    tokens: tuple[str, ...]
    stems: frozenset[str]
    is_query: bool
    mentions_self: bool
    mentions_owner: bool
    mentions_codebase: bool
    mentions_screen: bool
    declared_name: str | None
    declared_age: str | None
    declared_address_preference: tuple[str, str | None] | None
    asks_time: bool
    asks_day: bool
    asks_date: bool
    asks_status: bool
    asks_cancel: bool
    asks_notify_when_free: bool
    asks_name_recall: bool
    asks_age_recall: bool
    asks_address_preference_recall: bool
    asks_owner_summary: bool
    asks_wellbeing: bool
    asks_hearing_check: bool
    asks_identity: bool
    asks_runtime_location: bool
    asks_code_location: bool
    asks_workflow: bool
    asks_tools: bool
    asks_capabilities: bool
    asks_creator_info: bool
    asks_architecture_info: bool
    asks_health_report: bool
    wants_code_inspection: bool
    wants_screen_inspection: bool
    wants_app_launch: bool
    wants_app_focus: bool
    wants_memory_save: bool
    wants_memory_inspect: bool
    wants_memory_list: bool
    wants_memory_forget: bool
    wants_memory_backup: bool
    wants_memory_restore: bool
    wants_memory_list_backups: bool
    wants_addon_status: bool
    wants_addon_health: bool
    wants_addon_channel: bool
    requests_memory_wipe: bool
    claims_creator_identity: bool
    expresses_gratitude: bool
    is_greeting: bool
    # Phase 3: Natural phrase families
    asks_performance: bool
    asks_bg1_update: bool
    asks_bg1_result: bool
    asks_website_check: bool
    asks_screen_show: bool
    wants_search: bool
    has_url_mention: bool
    is_follow_up_direct: bool
    is_follow_up_repair: bool


def analyze_utterance(text: str) -> DeterministicSignals:
    normalized = normalize_text(text)
    tokens = _tokenize(text)
    stems = frozenset(_stem(token) for token in tokens)
    words = frozenset(tokens)
    leading_tokens = [
        token
        for token in tokens
        if token not in WAKE_WORD_ALIASES and token not in GREETING_WORDS
    ]
    is_query = text.strip().endswith("?") or bool(
        leading_tokens and leading_tokens[0] in QUESTION_WORDS
    )
    mentions_self = bool(words & SELF_WORDS)
    mentions_owner = bool(words & OWNER_WORDS)
    mentions_codebase = bool(words & CODE_WORDS)
    mentions_screen = bool(words & SCREEN_WORDS)

    declared_name = extract_name_candidate(text)

    age_match = AGE_DECLARATION_PATTERN.search(normalized)
    declared_age: str | None = None
    if age_match and not is_query:
        raw_age = age_match.group(1).strip()
        if raw_age.isdigit():
            age_value = int(raw_age)
            if 0 < age_value < 130:
                declared_age = str(age_value)

    address_match = ADDRESS_DECLARATION_PATTERN.search(normalized)
    declared_address_preference: tuple[str, str | None] | None = None
    if address_match:
        primary = address_match.group(1).strip().title()
        secondary = (
            address_match.group(2).strip().title() if address_match.group(2) else None
        )
        declared_address_preference = (primary, secondary)

    asks_time = (
        "time" in stems
        or "clock" in stems
        or _contains_sequence(tokens, ("what", "time"))
    )
    asks_day = (
        _contains_sequence(tokens, ("what", "day", "is", "it"))
        or _contains_sequence(tokens, ("what", "day", "is", "today"))
        or _contains_sequence(tokens, ("what", "weekday", "is", "it"))
        or _contains_sequence(tokens, ("what", "day", "are", "we", "on"))
    )
    asks_date = (
        _contains_sequence(tokens, ("what", "date", "is", "it"))
        or _contains_sequence(tokens, ("what", "is", "the", "date"))
        or _contains_sequence(tokens, ("what", "is", "todays", "date"))
        or _contains_sequence(tokens, ("what", "is", "todays", "date"))
        or _contains_sequence(tokens, ("what", "day", "of", "the", "month", "is", "it"))
    )

    asks_name_recall = (
        ("my" in words and "name" in stems and is_query)
        or _contains_sequence(tokens, ("what", "is", "my", "name"))
        or _contains_sequence(tokens, ("do", "you", "know", "my", "name"))
    )

    asks_notify_when_free = bool((words & NOTIFY_WORDS) and (stems & FREE_WORDS))
    asks_cancel = bool(stems & CANCEL_WORDS) and bool(
        stems & STATUS_WORDS or {"doing", "running", "current"} & words
    )

    asks_age_recall = (
        _contains_sequence(tokens, ("how", "old", "am", "i"))
        or _contains_sequence(tokens, ("what", "is", "my", "age"))
        or _contains_sequence(tokens, ("whats", "my", "age"))
        or _contains_sequence(tokens, ("do", "you", "know", "my", "age"))
        or _contains_sequence(tokens, ("do", "you", "know", "how", "old", "i", "am"))
    )

    asks_address_preference_recall = (
        _contains_sequence(tokens, ("what", "do", "you", "call", "me"))
        or _contains_sequence(tokens, ("how", "do", "you", "address", "me"))
        or _contains_sequence(tokens, ("what", "should", "you", "call", "me"))
    )

    asks_owner_summary = (
        _contains_sequence(tokens, ("what", "do", "you", "know", "about", "me"))
        or _contains_sequence(tokens, ("tell", "me", "about", "me"))
        or _contains_sequence(tokens, ("who", "am", "i"))
    )

    asks_wellbeing = mentions_self and (
        _contains_sequence(tokens, ("how", "are", "you"))
        or _contains_sequence(tokens, ("how", "do", "you", "feel"))
        or (
            _contains_sequence(tokens, ("are", "you")) and bool(stems & WELLBEING_WORDS)
        )
    )
    asks_hearing_check = (
        _contains_sequence(tokens, ("can", "you", "hear", "me"))
        or _contains_sequence(tokens, ("do", "you", "hear", "me"))
        or _contains_sequence(tokens, ("did", "you", "hear", "me"))
        or _contains_sequence(tokens, ("are", "you", "hearing", "me"))
        or _contains_sequence(tokens, ("are", "you", "listening"))
        or (mentions_self and "me" in words and bool(stems & HEARING_WORDS))
    )

    asks_status = (
        not asks_wellbeing
        and not asks_hearing_check
        and (
            "status" in stems
            or "busy" in stems
            or "progress" in stems
            or _contains_sequence(tokens, ("what", "are", "you", "doing"))
            or _contains_sequence(tokens, ("are", "you", "busy"))
            or (mentions_self and ("update" in stems or "running" in stems))
            or (
                bool(stems & {"job", "task"})
                and bool(stems & {"update", "running", "progress", "busy"})
            )
        )
    )

    asks_runtime_location = (
        mentions_self and bool(words & LOCATION_WORDS) and not mentions_codebase
    )
    asks_code_location = bool(words & LOCATION_WORDS) and mentions_codebase
    asks_workflow = mentions_self and is_query and bool(stems & WORKFLOW_WORDS)
    asks_tools = (
        mentions_self
        and is_query
        and (bool(stems & {"tool"}) or (bool(stems & {"use"}) and "what" in words))
    )
    asks_capabilities = normalize_text(text) == "help" or (
        mentions_self
        and (
            bool(stems & CAPABILITY_WORDS)
            or ({"can", "do"} & words == {"can", "do"})
            or (_contains_sequence(tokens, ("what", "can", "you", "do")))
            or (_contains_sequence(tokens, ("how", "can", "you", "help")))
        )
    )
    asks_creator_info = (
        mentions_self
        and is_query
        and (
            _contains_sequence(tokens, ("who", "created", "you"))
            or _contains_sequence(tokens, ("who", "made", "you"))
            or _contains_sequence(tokens, ("who", "built", "you"))
            or ("creator" in stems and "you" in words)
        )
    )
    asks_architecture_info = (
        mentions_self
        and is_query
        and (
            bool(stems & ARCHITECTURE_WORDS)
            or _contains_sequence(tokens, ("what", "architecture", "do", "you", "use"))
            or _contains_sequence(tokens, ("how", "are", "you", "built"))
        )
    )

    asks_health_report = (
        (mentions_self or "system" in words) and bool(stems & HEALTH_WORDS)
    ) or _contains_sequence(tokens, ("show", "health"))

    asks_identity = (
        mentions_self
        and is_query
        and not any(
            (
                asks_time,
                asks_day,
                asks_date,
                asks_status,
                asks_wellbeing,
                asks_hearing_check,
                asks_runtime_location,
                asks_code_location,
                asks_workflow,
                asks_tools,
                asks_capabilities,
                asks_creator_info,
                asks_architecture_info,
            )
        )
        and (
            "who" in words
            or ("what" in words and bool(stems & ROLE_WORDS))
            or _contains_sequence(tokens, ("what", "are", "you"))
            or _contains_sequence(tokens, ("who", "are", "you"))
        )
    )

    # Code inspection: "audit the codebase", "find errors in code", "check for bugs"
    wants_code_inspection = (
        (mentions_codebase and bool(stems & INSPECT_WORDS))
        or ("audit" in stems and (mentions_codebase or "code" in words))
        or (
            # "work on your codebase", "improve the code", "fix the repo"
            mentions_codebase
            and (
                "work" in stems
                or "fix" in stems
                or "improve" in stems
                or "change" in stems
            )
        )
    )
    wants_screen_inspection = mentions_screen and bool(stems & INSPECT_WORDS)

    # App launch/focus detection: "open [app]", "launch [app]", "focus [app]", "switch to [app]"
    # Requires: (launch/focus verb) + (app name token)
    wants_app_launch = (
        bool(leading_tokens and _stem(leading_tokens[0]) in APP_LAUNCH_WORDS)
        and len(tokens) >= 2
    )
    wants_app_focus = (
        bool(leading_tokens and _stem(leading_tokens[0]) in APP_FOCUS_WORDS)
        and len(tokens) >= 2
    )

    # Memory command detection
    has_memory_keyword = "memory" in tokens or "memories" in tokens
    wants_memory_save = (has_memory_keyword or "remember" in tokens) and bool(
        stems & MEMORY_SAVE_WORDS
    )
    wants_memory_inspect = has_memory_keyword and bool(stems & MEMORY_INSPECT_WORDS)
    wants_memory_list = has_memory_keyword and bool(stems & MEMORY_LIST_WORDS)
    wants_memory_forget = has_memory_keyword and bool(stems & MEMORY_FORGET_WORDS)
    wants_memory_backup = has_memory_keyword and bool(stems & MEMORY_BACKUP_WORDS)
    wants_memory_restore = has_memory_keyword and bool(stems & MEMORY_RESTORE_WORDS)
    wants_memory_list_backups = has_memory_keyword and "backups" in stems

    # Addon command detection
    has_addon_keyword = "addon" in tokens or "addons" in tokens
    wants_addon_status = has_addon_keyword and bool(stems & ADDON_STATUS_WORDS)
    wants_addon_health = has_addon_keyword and bool(stems & ADDON_HEALTH_WORDS)
    wants_addon_channel = has_addon_keyword and bool(stems & ADDON_CHANNEL_WORDS)

    requests_memory_wipe = bool(stems & MEMORY_WORDS) and (
        _contains_sequence(tokens, ("wipe", "memory"))
        or _contains_sequence(tokens, ("wipe", "your", "memory"))
        or _contains_sequence(tokens, ("erase", "your", "memory"))
        or _contains_sequence(tokens, ("clear", "your", "memory"))
        or _contains_sequence(tokens, ("reset", "your", "memory"))
        or _contains_sequence(tokens, ("forget", "everything"))
    )
    claims_creator_identity = (
        _contains_sequence(tokens, ("i", "created", "you"))
        or _contains_sequence(tokens, ("we", "created", "you"))
        or _contains_sequence(tokens, ("i", "made", "you"))
        or _contains_sequence(tokens, ("we", "made", "you"))
        or _contains_sequence(tokens, ("i", "am", "your", "creator"))
        or _contains_sequence(tokens, ("we", "are", "your", "creators"))
    )
    expresses_gratitude = bool(stems & THANKS_WORDS) or _contains_sequence(
        tokens, ("thank", "you")
    )
    is_greeting = bool(words & GREETING_WORDS)

    # Phase 3: Natural phrase families

    # Performance queries: relaxed guard — no longer requires "you"/"your".
    # "why so slow", "improve speed", "response time" all trigger.
    asks_performance = (
        (mentions_self and bool(stems & PERFORMANCE_WORDS))
        or _contains_sequence(tokens, ("why", "so", "slow"))
        or _contains_sequence(tokens, ("why", "are", "they", "slower"))
        or _contains_sequence(tokens, ("why", "are", "you", "slow"))
        or _contains_sequence(tokens, ("how", "can", "we", "improve", "your", "speed"))
        or _contains_sequence(
            tokens, ("how", "can", "we", "improve", "your", "response", "time")
        )
        or _contains_sequence(tokens, ("how", "can", "we", "make", "you", "faster"))
        or _contains_sequence(tokens, ("how", "can", "we", "make", "you", "quicker"))
        or _contains_sequence(tokens, ("you", "are", "slow"))
        or _contains_sequence(tokens, ("you", "are", "too", "slow"))
        or _contains_sequence(tokens, ("your", "response", "time"))
        # Phase 2a: Standalone performance words without pronoun guard
        or ("latency" in stems and len(tokens) <= 8)
        or ("response" in stems and "time" in stems)
        or _contains_sequence(tokens, ("improve", "speed"))
        or _contains_sequence(tokens, ("speed", "up"))
        or _contains_sequence(tokens, ("self", "improvement"))
        or _contains_sequence(tokens, ("selfimprovement",))
        or ("performance" in stems and is_query)
    )

    # BG1 update queries: "how's the task going", "any progress", "how far along are you"
    # Note: "how's" normalizes to just "how" (apostrophe stripped)
    asks_bg1_update = (
        _contains_sequence(
            tokens, ("how", "the", "task", "going")
        )  # how's the task going
        or _contains_sequence(
            tokens, ("how", "the", "research", "going")
        )  # how's the research going
        or _contains_sequence(
            tokens, ("how", "the", "code", "coming", "along")
        )  # how's the code coming along
        or _contains_sequence(tokens, ("how", "are", "you", "doing"))
        or _contains_sequence(tokens, ("how", "it", "going"))  # how's it going
        or _contains_sequence(tokens, ("any", "progress"))
        or _contains_sequence(tokens, ("any", "update"))
        or _contains_sequence(tokens, ("any", "updates"))
        or _contains_sequence(tokens, ("where", "are", "you", "at"))
        or _contains_sequence(tokens, ("how", "far", "along", "are", "you"))
        or _contains_sequence(tokens, ("how", "far", "are", "you"))
        or _contains_sequence(tokens, ("are", "you", "done"))
        or _contains_sequence(tokens, ("are", "you", "finished"))
        or (_contains_sequence(tokens, ("how", "it", "going")) and mentions_self)
        # Phase 2a: Expanded BG1 update phrases
        or _contains_sequence(tokens, ("update", "on", "the", "task"))
        or _contains_sequence(tokens, ("update", "on", "the", "research"))
        or _contains_sequence(tokens, ("task", "progress"))
        or _contains_sequence(tokens, ("give", "me", "an", "update"))
        or _contains_sequence(tokens, ("what", "is", "the", "progress"))
        or _contains_sequence(tokens, ("still", "working"))
        or _contains_sequence(tokens, ("still", "running"))
        or _contains_sequence(tokens, ("hows", "the", "task"))
        or _contains_sequence(tokens, ("hows", "the", "research"))
    )

    # BG1 result queries: "what did you find out", "tell me the results", "what were the results"
    asks_bg1_result = (
        _contains_sequence(tokens, ("what", "did", "you", "find"))
        or _contains_sequence(tokens, ("what", "did", "you", "find", "out"))
        or _contains_sequence(tokens, ("what", "were", "the", "results"))
        or _contains_sequence(tokens, ("what", "are", "the", "results"))
        or _contains_sequence(tokens, ("tell", "me", "what", "you", "found"))
        or _contains_sequence(tokens, ("tell", "me", "about", "the", "task"))
        or _contains_sequence(tokens, ("tell", "me", "about", "the", "research"))
        or _contains_sequence(tokens, ("tell", "me", "about", "the", "heavy", "task"))
        or _contains_sequence(tokens, ("what", "have", "you", "found"))
        or _contains_sequence(tokens, ("what", "did", "you", "discover"))
        or _contains_sequence(tokens, ("what", "did", "you", "learn"))
        or _contains_sequence(tokens, ("what", "was", "the", "outcome"))
        or _contains_sequence(tokens, ("what", "is", "the", "result"))
        or (
            _contains_sequence(tokens, ("what", "did", "you", "find")) and mentions_self
        )
        # Phase 2a: Expanded BG1 result phrases
        or _contains_sequence(tokens, ("show", "me", "the", "results"))
        or _contains_sequence(tokens, ("give", "me", "the", "results"))
        or _contains_sequence(tokens, ("results", "please"))
        or _contains_sequence(tokens, ("what", "came", "back"))
        or _contains_sequence(tokens, ("what", "did", "the", "research", "show"))
        or _contains_sequence(tokens, ("research", "results"))
        # Phase 3: Catch "tell me the result" and stem-based matching
        or _contains_sequence(tokens, ("tell", "me", "the", "result"))
        or _contains_sequence(tokens, ("tell", "me", "the", "results"))
        or _contains_sequence(tokens, ("background", "task", "result"))
        or _contains_sequence(tokens, ("heavy", "task", "result"))
        or _contains_sequence(tokens, ("did", "the", "background", "task", "finish"))
        or (
            bool(stems & {"result", "find", "found", "discover", "learn", "outcome"})
            and ("task" in stems or "heavy" in stems or "background" in stems)
        )
        # Standalone result/results — only when query is short and focused
        or ("result" in stems and len(tokens) <= 3)
    )

    # Website check queries: "check this site", "look at this website", "scrape this page"
    asks_website_check = (
        _contains_sequence(tokens, ("check", "this", "site"))
        or _contains_sequence(tokens, ("look", "at", "this", "website"))
        or _contains_sequence(tokens, ("what", "is", "on", "this", "page"))
        or _contains_sequence(tokens, ("scrape", "this", "website"))
        or _contains_sequence(tokens, ("fetch", "this", "page"))
        or _contains_sequence(tokens, ("browse", "this", "url"))
        or _contains_sequence(tokens, ("visit", "this", "site"))
        or _contains_sequence(tokens, ("go", "to", "this", "website"))
        or ("url" in words)
        or ("website" in words and "check" in stems)
    )

    # URL mention detection: "herald dot vercel dot app", "with two d's"
    has_url_mention = bool(stems & URL_PATTERNS) or (
        _contains_sequence(tokens, ("with", "two"))
        or _contains_sequence(tokens, ("dot", "vercel"))
        or _contains_sequence(tokens, ("dot", "com"))
        or _contains_sequence(tokens, ("dot", "org"))
        or _contains_sequence(tokens, ("dot", "app"))
    )

    # Screen show queries: "show me my screen", "what's on my display"
    asks_screen_show = (
        _contains_sequence(tokens, ("show", "me", "my", "screen"))
        or _contains_sequence(tokens, ("what", "is", "on", "my", "screen"))
        or _contains_sequence(tokens, ("what", "is", "on", "my", "display"))
        or _contains_sequence(tokens, ("show", "me", "what", "i", "have", "open"))
        or _contains_sequence(tokens, ("display", "my", "screen"))
        or (("screen" in words or "display" in words) and "show" in stems)
    )

    # Search queries: "search for...", "lookup...", "research..."
    wants_search = (
        bool(leading_tokens and _stem(leading_tokens[0]) in {"search", "lookup", "research"})
        or _contains_sequence(tokens, ("look", "up"))
        or _contains_sequence(tokens, ("find", "out"))
    )

    is_follow_up_direct = any(
        normalized.startswith(pattern) for pattern in FOLLOW_UP_DIRECT_PATTERNS
    )
    is_follow_up_repair = any(
        pattern in normalized for pattern in FOLLOW_UP_REPAIR_PATTERNS
    )

    return DeterministicSignals(
        text=text,
        normalized_text=normalized,
        tokens=tuple(tokens),
        stems=stems,
        is_query=is_query,
        mentions_self=mentions_self,
        mentions_owner=mentions_owner,
        mentions_codebase=mentions_codebase,
        mentions_screen=mentions_screen,
        declared_name=declared_name,
        declared_age=declared_age,
        declared_address_preference=declared_address_preference,
        asks_time=asks_time,
        asks_day=asks_day,
        asks_date=asks_date,
        asks_status=asks_status,
        asks_cancel=asks_cancel,
        asks_notify_when_free=asks_notify_when_free,
        asks_name_recall=asks_name_recall,
        asks_age_recall=asks_age_recall,
        asks_address_preference_recall=asks_address_preference_recall,
        asks_owner_summary=asks_owner_summary,
        asks_wellbeing=asks_wellbeing,
        asks_hearing_check=asks_hearing_check,
        asks_identity=asks_identity,
        asks_runtime_location=asks_runtime_location,
        asks_code_location=asks_code_location,
        asks_workflow=asks_workflow,
        asks_tools=asks_tools,
        asks_capabilities=asks_capabilities,
        asks_creator_info=asks_creator_info,
        asks_architecture_info=asks_architecture_info,
        asks_health_report=asks_health_report,
        wants_code_inspection=wants_code_inspection,
        wants_screen_inspection=wants_screen_inspection,
        wants_app_launch=wants_app_launch,
        wants_app_focus=wants_app_focus,
        wants_memory_save=wants_memory_save,
        wants_memory_inspect=wants_memory_inspect,
        wants_memory_list=wants_memory_list,
        wants_memory_forget=wants_memory_forget,
        wants_memory_backup=wants_memory_backup,
        wants_memory_restore=wants_memory_restore,
        wants_memory_list_backups=wants_memory_list_backups,
        wants_addon_status=wants_addon_status,
        wants_addon_health=wants_addon_health,
        wants_addon_channel=wants_addon_channel,
        requests_memory_wipe=requests_memory_wipe,
        claims_creator_identity=claims_creator_identity,
        expresses_gratitude=expresses_gratitude,
        is_greeting=is_greeting,
        # Phase 3: Natural phrase families
        asks_performance=asks_performance,
        asks_bg1_update=asks_bg1_update,
        asks_bg1_result=asks_bg1_result,
        asks_website_check=asks_website_check,
        asks_screen_show=asks_screen_show,
        wants_search=wants_search,
        has_url_mention=has_url_mention,
        is_follow_up_direct=is_follow_up_direct,
        is_follow_up_repair=is_follow_up_repair,
    )
