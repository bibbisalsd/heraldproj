from __future__ import annotations

import hashlib
import re
from typing import Any, Callable

from jarvis.utils.time_utils import utc_now_iso
from jarvis.brain_core.deterministic_understanding import analyze_utterance
from jarvis.name_profile import first_name, normalize_title_preference
from jarvis.tools.addon_control import disable_addon, enable_addon
from jarvis.tools.app_ops import (
    launch as app_launch,
    focus as app_focus,
    list_allowed_apps,
)
from jarvis.tools import job_status_tool

WAKE_WORD_ALIASES = {
    "jarvis",
    "javis",
    "jovis",
    "javas",
    "jarviss",
    "java",
    "jabba",
    "jabbas",
}
GRATITUDE_PATTERNS = ("thank you", "thanks", "cheers")
GOODNIGHT_PATTERNS = ("good night", "goodnight")
GOODBYE_PATTERNS = ("bye", "goodbye", "see you")
FEEDBACK_NEGATIVE_PATTERNS = (
    "that was a terrible response",
    "that response could have been better",
    "your responses could be better",
    "that was not good",
    "you are making things up",
)
AFFECTION_PATTERNS = (
    "i love you",
    "i'm proud of you",
    "im proud of you",
    "very proud of you",
)
NO_SPEECH_PATTERNS = (
    "i didn't say anything",
    "i did not say anything",
    "i wasnt speaking",
    "i wasn't speaking",
)
HALLUCINATION_PATTERNS = (
    "you re making things up",
    "you are making things up",
    "you made that up",
    "that is not good",
    "thats not good",
)
UNDERSTANDING_PATTERNS = (
    "did you understand what i said",
    "do you understand what i said",
)
CONTEXT_CONTINUITY_PATTERNS = (
    "we re not starting fresh",
    "were not starting fresh",
    "we are not starting fresh",
)

Handler = Callable[[Any, Any, dict[str, Any]], Any]
PREFERRED_LINK_ORDER: dict[str, list[str]] = {
    "tool:": [
        "tool:calculator",
        "tool:local_now",
        "tool:memory",
        "tool:code_inspection",
        "tool:vision",
        "tool:job_status",
        "tool:file_write",
        "tool:code_runner",
        "tool:app_launch",
        "tool:app_focus",
        "tool:utc_now_iso",
    ],
    "module:": [
        "module:voice_runtime",
        "module:prompt_dispatcher",
        "module:intent_handlers",
        "module:main_runtime",
        "module:memory",
        "module:bg1_queue",
    ],
}


def _normalize_text(text: str) -> str:
    lowered = text.lower().replace("’", "'")
    lowered = re.sub(r"[^a-z0-9'\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _strip_wake_aliases(text: str) -> str:
    pattern = r"\b(?:" + "|".join(sorted(WAKE_WORD_ALIASES)) + r")\b"
    cleaned = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _trim_specialist_prefix(text: str) -> str:
    prefixes = ("Vision specialist result: ", "Code specialist result: ")
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text.strip()


def _extract_math_expression(text: str) -> str | None:
    lowered = _strip_wake_aliases(text.lower())
    if len(re.findall(r"\d+(?:\.\d+)?", lowered)) < 2:
        return None

    replacements = (
        (r"\bmultiplied by\b", " * "),
        (r"\btimes\b", " * "),
        (r"(?<=\d)\s*[x×]\s*(?=\d)", " * "),
        (r"\bplus\b", " + "),
        (r"\bminus\b", " - "),
        (r"\bdivided by\b", " / "),
        (r"\bover\b", " / "),
    )
    if not any(
        re.search(pattern, lowered) for pattern, _ in replacements
    ) and not re.search(r"[+\-*/]", lowered):
        return None

    candidate = lowered
    for pattern, replacement in replacements:
        candidate = re.sub(pattern, replacement, candidate)

    candidate = re.sub(r"\bwhat(?:'s| is)\b", " ", candidate)
    candidate = re.sub(
        r"\bcalculate\b|\bcompute\b|\bsolve\b|\bplease\b|\btell\b|\bme\b",
        " ",
        candidate,
    )
    candidate = re.sub(r"[^0-9+\-*/(). ]", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" ?.=,")
    if not candidate or "**" in candidate or "//" in candidate:
        return None
    if len(re.findall(r"\d+(?:\.\d+)?", candidate)) < 2:
        return None
    if not re.search(r"[+\-*/]", candidate):
        return None
    return candidate


def _format_math_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _remember_latest(
    memory: Any,
    key: str,
    value: str,
    confidence: float = 0.95,
    source_id: str | None = None,
) -> bool:
    remember_latest = getattr(memory, "remember_latest", None)
    if callable(remember_latest):
        return bool(
            remember_latest(
                key, value, confidence=confidence, source="intent_handler", source_id=source_id
            )
        )
    return bool(
        memory.remember(
            key, value, confidence=confidence, source="intent_handler", source_id=source_id
        )
    )


def _human_join(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _humanize_value(value: str) -> str:
    cleaned = str(value).replace("_", " ").strip()
    padded = f" {cleaned} "
    replacements = {
        " ai ": " AI ",
        " bg1 ": " BG1 ",
        " stt ": " STT ",
        " tts ": " TTS ",
    }
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return padded.strip()


def _select_variant(env: Any, options: list[str]) -> str:
    if not options:
        return ""
    seed_source = f"{getattr(env, 'turn_id', '')}|{getattr(env, 'text', '')}"
    digest = hashlib.sha256(seed_source.encode("utf-8")).digest()
    index = digest[0] % len(options)
    return options[index]


def _selection_roll(env: Any, salt: str = "") -> float:
    seed_source = f"{getattr(env, 'turn_id', '')}|{getattr(env, 'text', '')}|{salt}"
    digest = hashlib.sha256(seed_source.encode("utf-8")).digest()
    return digest[1] / 255.0


def _select_address_label(
    env: Any,
    memory: Any,
    *,
    personal: bool = False,
    allow_name: bool = True,
    allow_title: bool = True,
) -> str:
    given_name = (
        _compose_owner_given_name(memory) or _compose_owner_name(memory) or ""
    ).strip()
    title = (_compose_owner_title_preference(memory) or "").strip()
    roll = _selection_roll(env, "personal" if personal else "general")

    if personal:
        if allow_name and given_name and roll < 0.55:
            return given_name
        if allow_title and title and roll < 0.80:
            return title
        if allow_name and given_name and roll < 0.90:
            return given_name
        return ""

    if allow_title and title and roll < 0.50:
        return title
    if allow_name and given_name and roll >= 0.90:
        return given_name
    return ""


def _spoken_suffix(
    env: Any,
    memory: Any,
    *,
    personal: bool = False,
    allow_name: bool = True,
    allow_title: bool = True,
    comma: bool = False,
) -> str:
    label = _select_address_label(
        env,
        memory,
        personal=personal,
        allow_name=allow_name,
        allow_title=allow_title,
    )
    if not label:
        return ""
    separator = ", " if comma else " "
    return f"{separator}{label}"


def _pocket_slot_value(
    memory: Any, entity_id: str, slot_key: str, default: str = ""
) -> str:
    slot = memory.pockets.get_slot(entity_id, slot_key)
    return slot.slot_value if slot is not None else default


def _linked_entity_ids(memory: Any, entity_id: str, prefix: str) -> list[str]:
    related_ids: list[str] = []
    for related_id in memory.pockets.related_entity_ids(entity_id):
        if not related_id.startswith(prefix):
            continue
        related_ids.append(related_id)
    preferred_order = PREFERRED_LINK_ORDER.get(prefix, [])
    if preferred_order:
        order_map = {value: index for index, value in enumerate(preferred_order)}
        related_ids.sort(
            key=lambda value: (order_map.get(value, len(order_map)), value)
        )
    return related_ids


def _describe_linked_entities(
    memory: Any,
    entity_id: str,
    prefix: str,
    *,
    preferred_slot: str = "spoken_purpose",
    fallback_slot: str = "purpose",
    limit: int = 4,
) -> list[str]:
    descriptions: list[str] = []
    for related_id in _linked_entity_ids(memory, entity_id, prefix)[:limit]:
        entity = memory.pockets.get_entity(related_id)
        if entity is None:
            continue
        detail = _pocket_slot_value(
            memory, related_id, preferred_slot
        ) or _pocket_slot_value(memory, related_id, fallback_slot)
        if detail:
            descriptions.append(
                f"{entity.canonical_name} for {_humanize_value(detail)}"
            )
        else:
            descriptions.append(entity.canonical_name)
    return descriptions


def _compose_self_identity(memory: Any) -> str:
    name = _pocket_slot_value(memory, "self:jarvis", "name", "Jarvis")
    assistant_type = _humanize_value(
        _pocket_slot_value(memory, "self:jarvis", "assistant_type", "assistant")
    )
    runtime_location = _pocket_slot_value(
        memory, "self:jarvis", "runtime_location", "this computer"
    )
    version = _pocket_slot_value(memory, "self:jarvis", "version", "")
    version_str = f" version {version}" if version else ""
    return f"I am {name}{version_str}, a {assistant_type} running on {runtime_location}."


def _compose_codebase_location(memory: Any) -> str:
    repo_name = _pocket_slot_value(memory, "project:jarvis", "repo_name", "Jarviscore")
    repo_root = _pocket_slot_value(memory, "codebase:jarviscore", "repo_root")
    package_root = _pocket_slot_value(memory, "codebase:jarviscore", "package_root")
    parts = [f"My main codebase is {repo_name}"]
    if repo_root:
        parts[-1] += f" at {repo_root}"
    if package_root:
        parts.append(f"The core package is in {package_root}")
    return ". ".join(part.rstrip(".") for part in parts) + "."


def _compose_workflow(memory: Any) -> str:
    module_descriptions = _describe_linked_entities(
        memory, "codebase:jarviscore", "module:"
    )
    if module_descriptions:
        return f"I work through {_human_join(module_descriptions)}."
    fallback = _pocket_slot_value(memory, "self:jarvis", "runtime_flow_summary")
    if fallback:
        return fallback
    return "I route input deterministically first, use tools when I can verify the answer, and use the local model only when needed."


def _compose_toolset(memory: Any) -> str:
    tool_descriptions = _describe_linked_entities(
        memory, "self:jarvis", "tool:", limit=6
    )
    if tool_descriptions:
        return f"My current tool set includes {_human_join(tool_descriptions)}."
    return "I currently have a small set of local tools."


def _compose_capabilities(memory: Any) -> str:
    project_purpose = _humanize_value(
        _pocket_slot_value(memory, "project:jarvis", "spoken_purpose")
        or _pocket_slot_value(memory, "project:jarvis", "purpose", "local assistant")
    )
    tool_descriptions = _describe_linked_entities(
        memory, "self:jarvis", "tool:", limit=5
    )
    if tool_descriptions:
        return f"I am built for {project_purpose}. My core tools include {_human_join(tool_descriptions)}."
    return f"I am built for {project_purpose}."


def _compose_creator_summary(memory: Any) -> str:
    creator_ids = [
        entity_id
        for entity_id in ("person:creator_james", "person:creator_bxserkk")
        if memory.pockets.get_entity(entity_id) is not None
    ]
    creator_bits: list[str] = []
    for entity_id in creator_ids:
        if not entity_id.startswith("person:creator_"):
            continue
        entity = memory.pockets.get_entity(entity_id)
        if entity is None:
            continue
        if entity_id == "person:creator_james":
            handle = _pocket_slot_value(memory, entity_id, "handle")
            country = _pocket_slot_value(memory, entity_id, "country")
            bit = entity.canonical_name
            if handle:
                bit += f", who goes by {handle}"
            if country:
                bit += f", from the {country}"
            creator_bits.append(bit)
            continue

        handle = _pocket_slot_value(memory, entity_id, "handle", entity.canonical_name)
        spoken_name = _pocket_slot_value(memory, entity_id, "spoken_name")
        country = _pocket_slot_value(memory, entity_id, "country")
        bit = handle or entity.canonical_name
        if spoken_name:
            bit += f", referred to as {spoken_name}"
        if country:
            bit += f", from the {country}"
        creator_bits.append(bit)

    if creator_bits:
        return f"I was created by {_human_join(creator_bits)}."
    fallback = _pocket_slot_value(memory, "self:jarvis", "creator_summary")
    if fallback:
        return fallback
    return "I know my creators are stored in my protected core memory."


def _compose_architecture_summary(memory: Any) -> str:
    spoken_name = _pocket_slot_value(
        memory, "architecture:herald_skeptic", "spoken_name"
    )
    summary = ""
    if spoken_name:
        summary = f"I was created using the {spoken_name}."
    else:
        summary = _pocket_slot_value(memory, "self:jarvis", "architecture_summary", "I use a specific local architecture.")
    
    # Hardware section
    hw_bits = []
    cpu = _pocket_slot_value(memory, "self:jarvis", "cpu_cores")
    if cpu:
        hw_bits.append(f"{cpu} CPU cores")
    ram = _pocket_slot_value(memory, "self:jarvis", "ram_gb")
    if ram:
        hw_bits.append(f"{ram} GB of RAM")
    
    gpu_name = _pocket_slot_value(memory, "self:jarvis", "gpu_0_name")
    gpu_vram = _pocket_slot_value(memory, "self:jarvis", "gpu_0_vram_gb")
    if gpu_name and gpu_vram:
        hw_bits.append(f"an {gpu_name} with {gpu_vram} GB of VRAM")
    elif gpu_name:
        hw_bits.append(f"an {gpu_name} GPU")
        
    if hw_bits:
        summary += f" I am currently running on a system with {_human_join(hw_bits)}."
        
    return summary


def _owner_slot(memory: Any, slot_key: str) -> str:
    pockets = getattr(memory, "pockets", None)
    if pockets is None:
        return ""
    return _pocket_slot_value(memory, "person:owner", slot_key)


def _compose_owner_name(memory: Any) -> str | None:
    recall = getattr(memory, "recall", None)
    name_rows = recall("user_name") if callable(recall) else []
    if name_rows:
        return str(name_rows[0].value).strip()
    remembered_name = _owner_slot(memory, "name")
    return remembered_name.strip() or None


def _compose_owner_given_name(memory: Any) -> str | None:
    stored = _owner_slot(memory, "given_name")
    if stored:
        return stored.strip()
    remembered_name = _compose_owner_name(memory)
    if remembered_name:
        return first_name(remembered_name).strip() or None
    return None


def _compose_owner_gender_class(memory: Any) -> str | None:
    recall = getattr(memory, "recall", None)
    gender_rows = recall("user_name_gender") if callable(recall) else []
    if gender_rows:
        return str(gender_rows[0].value).strip().lower()
    remembered = _owner_slot(memory, "gender_class")
    return remembered.strip().lower() or None


def _compose_owner_title_preference(memory: Any) -> str | None:
    recall = getattr(memory, "recall", None)
    title_rows = recall("user_title_preference") if callable(recall) else []
    if title_rows:
        remembered = normalize_title_preference(str(title_rows[0].value))
        if remembered:
            return remembered
    remembered = normalize_title_preference(_owner_slot(memory, "title_preference"))
    if remembered:
        return remembered
    explicit_address = normalize_title_preference(
        _owner_slot(memory, "address_preference")
    )
    if explicit_address:
        return explicit_address
    return None


def _compose_owner_address_preference(memory: Any) -> str | None:
    recall = getattr(memory, "recall", None)
    preference_rows = recall("user_address_preference") if callable(recall) else []
    if preference_rows:
        return str(preference_rows[0].value).strip()
    remembered_preference = _owner_slot(memory, "address_preference")
    if remembered_preference:
        return remembered_preference.strip()
    return _compose_owner_name(memory)


def _compose_owner_age(memory: Any) -> str | None:
    recall = getattr(memory, "recall", None)
    age_rows = recall("user_age") if callable(recall) else []
    if age_rows:
        return str(age_rows[0].value).strip()
    remembered_age = _owner_slot(memory, "age")
    return remembered_age.strip() or None


def _compose_owner_fact_reply(memory: Any, slot_key: str) -> str:
    if slot_key == "name":
        remembered_name = _compose_owner_name(memory)
        if remembered_name:
            return f"I have your name as {remembered_name}."
        return "I do not have your name saved yet."
    if slot_key == "address_preference":
        preferred_name = _compose_owner_address_preference(memory)
        title_preference = _compose_owner_title_preference(memory)
        if (
            preferred_name
            and title_preference
            and preferred_name.lower() != title_preference.lower()
        ):
            return f"I currently address you as {preferred_name}, and I can also refer to you as {title_preference}."
        if preferred_name:
            return f"I currently address you as {preferred_name}."
        if title_preference:
            return f"I can refer to you as {title_preference}."
        return "I do not have a preferred form of address saved for you yet."
    if slot_key == "age":
        remembered_age = _compose_owner_age(memory)
        if remembered_age:
            return f"I have your age as {remembered_age}."
        return "I do not know your age unless you tell me."
    return "I do not have that saved yet."


def _compose_owner_summary(memory: Any) -> str:
    fragments: list[str] = []
    remembered_name = _compose_owner_name(memory)
    given_name = _compose_owner_given_name(memory)
    preferred_name = _compose_owner_address_preference(memory)
    title_preference = _compose_owner_title_preference(memory)
    gender_class = _compose_owner_gender_class(memory)
    remembered_age = _compose_owner_age(memory)

    if remembered_name:
        fragments.append(f"your name as {remembered_name}")
    if given_name and remembered_name and given_name != remembered_name:
        fragments.append(f"your given name as {given_name}")
    if preferred_name:
        if remembered_name and preferred_name == remembered_name:
            fragments.append(f"your preferred form of address as {preferred_name}")
        else:
            fragments.append(f"the name I should use for you as {preferred_name}")
    if title_preference:
        fragments.append(f"your preferred title as {title_preference}")
    if gender_class:
        fragments.append(f"your name style as {gender_class}")
    if remembered_age:
        fragments.append(f"your age as {remembered_age}")

    if not fragments:
        return "I do not have much saved about you yet."
    return f"I currently have {_human_join(fragments)}."


class IntentHandlerRegistry:
    """Registry mapping intent strings to handler functions."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._pre_intent_handlers: list[Handler] = []

    def register(self, intent: str, handler: Handler) -> None:
        self._handlers[intent] = handler

    def register_pre_intent(self, handler: Handler) -> None:
        self._pre_intent_handlers.append(handler)

    def resolve(self, env: Any, decision: Any, services: dict[str, Any]) -> Any | None:
        for handler in self._pre_intent_handlers:
            result = handler(env, decision, services)
            if result is not None:
                return result

        if decision.intent and decision.intent in self._handlers:
            return self._handlers[decision.intent](env, decision, services)

        return None


def handle_name_recognition(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    signals = analyze_utterance(env.text)
    remembered_name = signals.declared_name
    if not remembered_name:
        return None
    if not services.get("capabilities", {}).get("memory_save", True):
        return services["deny_capability"]("memory_save")
    from jarvis.main import TurnExecutionResult

    remember_owner_name = services.get("remember_owner_name")
    if callable(remember_owner_name):
        payload = remember_owner_name(remembered_name, source="name_recognition")
        return TurnExecutionResult(
            lane="realtime",
            text=str(payload.get("text", f"I have your name as {remembered_name}.")),
            resolved_by="tool_only",
            memory_items=list(
                payload.get("memory_items", [f"user_name:{remembered_name}"])
            ),
        )

    # Phase 4: Add to BeliefState instead of canonical memory immediately
    world_state = services.get("world_state")
    if world_state and hasattr(world_state, "belief_state"):
        pass  # Logic handled by state builder or explicit BeliefState update

    text = f"I inferred your name is {remembered_name}, is that correct?"

    return TurnExecutionResult(
        lane="realtime",
        text=text,
        resolved_by="tool_only",
        memory_items=[],
        # flag to prompt confirmation
        renderer_constraints=["ask_for_confirmation"],
    )


def handle_address_preference(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    normalized = _normalize_text(env.text)
    normalized_no_apostrophe = normalized.replace("'", "")
    if not services.get("capabilities", {}).get("memory_save", True):
        return None

    if signals.declared_address_preference is not None:
        primary, secondary = signals.declared_address_preference
        _remember_latest(services["memory"], "user_address_preference", primary, source_id=env.turn_id)
        if secondary:
            _remember_latest(services["memory"], "user_title_preference", secondary, source_id=env.turn_id)
        return None

    if (
        "not both of them" not in normalized
        and "dont refer me to" not in normalized_no_apostrophe
        and "do not refer me to" not in normalized
    ):
        return None

    disallowed_match = re.search(
        r"(?:dont|do not) refer me to ([a-z][a-z'\-\s]{0,39})", normalized_no_apostrophe
    )
    disallowed = disallowed_match.group(1).strip() if disallowed_match else ""
    name_rows = services["memory"].recall("user_name")
    preferred_name = str(name_rows[0].value).strip() if name_rows else ""
    if preferred_name:
        _remember_latest(
            services["memory"],
            "user_address_preference",
            preferred_name,
            confidence=0.95,
            source_id=env.turn_id,
        )
        if disallowed:
            clean_disallowed = disallowed.title().replace("  ", " ")
            return TurnExecutionResult(
                lane="realtime",
                text=f"{_compose_owner_fact_reply(services['memory'], 'address_preference')[:-1]}, not {clean_disallowed}.",
                resolved_by="tool_only",
                memory_items=[f"user_address_preference:{preferred_name}"],
            )
        return TurnExecutionResult(
            lane="realtime",
            text=_compose_owner_fact_reply(services["memory"], "address_preference"),
            resolved_by="tool_only",
            memory_items=[f"user_address_preference:{preferred_name}"],
        )

    return TurnExecutionResult(
        lane="realtime",
        text="Understood. I will avoid combining forms of address.",
        resolved_by="tool_only",
    )


def handle_wellbeing(env: Any, decision: Any, services: dict[str, Any]) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if not signals.asks_wellbeing:
        return None

    health_snapshot_fn = services.get("runtime_health")
    health = (
        health_snapshot_fn()
        if callable(health_snapshot_fn)
        else {"summary": "responding normally", "status": "good", "facts": []}
    )
    suffix = _spoken_suffix(env, services["memory"], personal=True, comma=True)
    canonical = str(
        health.get("canonical_reply")
        or f"I am good{suffix}. I am online and responding normally."
    )
    return TurnExecutionResult(
        lane="realtime",
        text=canonical,
        resolved_by="tool_only",
        brain_items=[canonical, *[str(item) for item in health.get("facts", [])]],
        tool_summaries=[f"runtime_health:{health.get('status', 'good')}"],
        job_snapshot=services["job_status_tool"].status(services["job_status"]),
        renderer_constraints=[
            "renderer_only_no_new_facts",
            "voice_friendly_output",
            "keep_health_summary_to_two_short_sentences",
        ],
    )


def handle_hearing_query(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if not signals.asks_hearing_check:
        return None

    health_snapshot_fn = services.get("runtime_health")
    health = (
        health_snapshot_fn() if callable(health_snapshot_fn) else {"status": "good"}
    )
    suffix = _spoken_suffix(env, services["memory"], personal=True, comma=True)
    status = str(health.get("status", "good"))
    if status == "good":
        text = _select_variant(
            env,
            [
                f"Yes{suffix}. I can hear you.",
                f"Yes{suffix}. I am hearing you clearly.",
                f"Yes{suffix}. I can hear you just fine.",
            ],
        )
    elif status == "minor_issue":
        text = f"Yes{suffix}. I can hear you, but speech recognition has been a little unreliable."
    else:
        text = f"I can hear you{suffix}, but there is a larger issue affecting my runtime right now."

    return TurnExecutionResult(
        lane="realtime",
        text=text,
        resolved_by="tool_only",
        brain_items=[text, *[str(item) for item in health.get("facts", [])]],
        tool_summaries=[f"runtime_health:{health.get('status', 'good')}"],
        renderer_constraints=["renderer_only_no_new_facts", "voice_friendly_output"],
    )


def handle_social_repair(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision, services
    from jarvis.main import TurnExecutionResult

    normalized = _normalize_text(env.text)

    if any(phrase in normalized for phrase in NO_SPEECH_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="Understood. I will wait for you to speak.",
            resolved_by="tool_only",
        )

    if any(phrase in normalized for phrase in GOODNIGHT_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="Goodnight.",
            resolved_by="tool_only",
        )

    if any(phrase in normalized for phrase in GRATITUDE_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="You're welcome.",
            resolved_by="tool_only",
        )

    if any(phrase in normalized for phrase in FEEDBACK_NEGATIVE_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="Understood. I will try to respond more clearly.",
            resolved_by="tool_only",
        )

    if any(phrase in normalized for phrase in AFFECTION_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="Thank you. I appreciate that.",
            resolved_by="tool_only",
        )

    if any(phrase in normalized for phrase in GOODBYE_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="Goodbye.",
            resolved_by="tool_only",
        )

    return None


def handle_grounding_correction(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision, services
    from jarvis.main import TurnExecutionResult

    normalized = _normalize_text(env.text)
    normalized_no_apostrophe = normalized.replace("'", "")

    if any(phrase in normalized for phrase in HALLUCINATION_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="Understood. I should not guess. I will stick to verified information or say I do not know.",
            resolved_by="tool_only",
        )

    if "what made you think" in normalized:
        return TurnExecutionResult(
            lane="realtime",
            text="I should not have guessed. I do not know unless you tell me or I verify it.",
            resolved_by="tool_only",
        )

    if any(phrase in normalized for phrase in UNDERSTANDING_PATTERNS):
        return TurnExecutionResult(
            lane="realtime",
            text="Not fully. Please restate the part you want me to address.",
            resolved_by="tool_only",
        )

    if any(phrase in normalized for phrase in CONTEXT_CONTINUITY_PATTERNS) or any(
        phrase in normalized_no_apostrophe for phrase in CONTEXT_CONTINUITY_PATTERNS
    ):
        return TurnExecutionResult(
            lane="realtime",
            text="Understood. I will stay with the current conversation.",
            resolved_by="tool_only",
        )

    if "what are you on about" in normalized:
        return TurnExecutionResult(
            lane="realtime",
            text="I may have answered badly. Please restate the question and I will answer it directly.",
            resolved_by="tool_only",
        )

    return None


def handle_math_query(env: Any, decision: Any, services: dict[str, Any]) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    expression = _extract_math_expression(env.text)
    if expression is None:
        return None

    tool_result = services["tool_orchestrator"].execute(
        "calculator", expression=expression
    )
    if not tool_result.ok:
        return TurnExecutionResult(
            lane="realtime",
            text="I could not calculate that right now.",
            resolved_by="fallback_template",
        )

    payload = tool_result.data.get("result", {})
    if not payload.get("ok"):
        return TurnExecutionResult(
            lane="realtime",
            text="I could not calculate that right now.",
            resolved_by="fallback_template",
        )

    value = _format_math_value(payload.get("value"))
    suffix = _spoken_suffix(
        env, services["memory"], allow_name=False, allow_title=True, comma=True
    )
    templates = [
        f"The answer is {value}{suffix}.",
        f"It comes to {value}{suffix}.",
        f"That works out to {value}{suffix}.",
    ]
    return TurnExecutionResult(
        lane="realtime",
        text=_select_variant(env, templates),
        resolved_by="tool_only",
        tool_summaries=[f"calculator:{expression}={value}"],
        tool_facts=[tool_result.data["fact"]] if "fact" in tool_result.data else [],
    )


def handle_owner_memory(env: Any, decision: Any, services: dict[str, Any]) -> Any | None:
    """Handle queries and saves related to owner's personal facts."""
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    memory = services["memory"]
    
    # Handle saves
    if signals.declared_name:
        _remember_latest(memory, "user_name", signals.declared_name, source_id=env.turn_id)
    if signals.declared_age:
        _remember_latest(memory, "user_age", signals.declared_age, source_id=env.turn_id)
    if signals.declared_address_preference:
        pref = signals.declared_address_preference
        if isinstance(pref, tuple):
            primary, secondary = pref
            _remember_latest(memory, "user_address_preference", primary, source_id=env.turn_id)
            if secondary:
                _remember_latest(memory, "user_title_preference", secondary, source_id=env.turn_id)
        else:
            _remember_latest(memory, "user_address_preference", str(pref), source_id=env.turn_id)

    # Handle recalls
    text = ""
    if signals.asks_owner_summary:
        text = _compose_owner_summary(memory)
    elif signals.asks_age_recall:
        text = _compose_owner_fact_reply(memory, "age")
    elif signals.asks_address_preference_recall:
        text = _compose_owner_fact_reply(memory, "address_preference")
    elif signals.declared_name or signals.declared_age or signals.declared_address_preference:
        # We had a save but no recall requested
        text = _compose_owner_summary(memory)
    else:
        # NO owner signal detected, let other handlers run!
        return None

    return TurnExecutionResult(
        lane="realtime",
        text=text,
        resolved_by="tool_plus_renderer",
    )


def handle_owner_summary(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if signals.asks_address_preference_recall:
        return TurnExecutionResult(
            lane="realtime",
            text=_compose_owner_fact_reply(services["memory"], "address_preference"),
            resolved_by="tool_only",
        )
    if not signals.asks_owner_summary:
        return None
    return TurnExecutionResult(
        lane="realtime",
        text=_compose_owner_summary(services["memory"]),
        resolved_by="tool_only",
    )


def handle_self_understanding(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    memory = services["memory"]
    self_knowledge = services.get("self_knowledge")

    if signals.asks_status:
        return None

    if signals.asks_identity:
        return TurnExecutionResult(
            lane="realtime",
            text=_compose_self_identity(memory),
            resolved_by="tool_only",
        )

    if signals.asks_code_location:
        # Use self-knowledge index for accurate code location
        if self_knowledge:
            answer = self_knowledge.answer_module_location(env.text)
            if answer and "couldn't find" not in answer.lower():
                return TurnExecutionResult(
                    lane="realtime", text=answer, resolved_by="tool_only"
                )
        return TurnExecutionResult(
            lane="realtime",
            text=_compose_codebase_location(memory),
            resolved_by="tool_only",
        )

    if signals.asks_architecture_info:
        # Use self-knowledge for architecture info when available
        if self_knowledge:
            answer = self_knowledge.answer_architecture_question(env.text)
            if answer:
                return TurnExecutionResult(
                    lane="realtime", text=answer, resolved_by="tool_only"
                )
        return TurnExecutionResult(
            lane="realtime",
            text=f"{_compose_architecture_summary(memory)} {_compose_creator_summary(memory)}",
            resolved_by="tool_only",
        )

    if signals.asks_workflow:
        return TurnExecutionResult(
            lane="realtime", text=_compose_workflow(memory), resolved_by="tool_only"
        )

    if signals.asks_tools:
        # Use self-knowledge for accurate tool listing
        if self_knowledge:
            answer = self_knowledge.answer_tools_question()
            if answer:
                return TurnExecutionResult(
                    lane="realtime", text=answer, resolved_by="tool_only"
                )
        return TurnExecutionResult(
            lane="realtime", text=_compose_toolset(memory), resolved_by="tool_only"
        )

    if signals.asks_creator_info:
        return TurnExecutionResult(
            lane="realtime",
            text=_compose_creator_summary(memory),
            resolved_by="tool_only",
        )

    return None


def handle_assistant_identity(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if signals.asks_runtime_location:
        runtime_location = _pocket_slot_value(
            services["memory"], "self:jarvis", "runtime_location", "this computer"
        )
        return TurnExecutionResult(
            lane="realtime",
            text=f"I am running locally on {runtime_location}.",
            resolved_by="tool_only",
        )
    if signals.asks_code_location:
        return TurnExecutionResult(
            lane="realtime",
            text="My main codebase is jarviscore, running on this machine.",
            resolved_by="tool_only",
        )
    return None


def handle_codebase_query(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if not signals.mentions_codebase:
        return None

    # Use self-knowledge index for codebase overview questions
    self_knowledge = services.get("self_knowledge")

    if not signals.wants_code_inspection:
        # Try self-knowledge first for structural questions
        if self_knowledge:
            answer = self_knowledge.answer_codebase_question()
            if answer:
                return TurnExecutionResult(
                    lane="realtime",
                    text=answer,
                    resolved_by="tool_only",
                )

        overview = _compose_codebase_location(services["memory"])
        module_descriptions = _describe_linked_entities(
            services["memory"], "codebase:jarviscore", "module:"
        )
        if module_descriptions:
            overview = (
                f"{overview} Core modules include {_human_join(module_descriptions)}."
            )
        return TurnExecutionResult(
            lane="realtime",
            text=overview,
            resolved_by="tool_only",
        )

    # For deep code inspection, try self-knowledge index first
    if self_knowledge:
        answer = self_knowledge.answer_codebase_question()
        if answer:
            return TurnExecutionResult(
                lane="realtime",
                text=answer,
                resolved_by="tool_only",
            )

    runner = services.get("run_code_specialist")
    if not callable(runner):
        return TurnExecutionResult(
            lane="realtime",
            text="I cannot inspect the codebase right now.",
            resolved_by="fallback_template",
        )

    result = runner(
        f"Inspect the local Jarvis codebase for this request and answer briefly: {env.text}"
    )
    if result.get("ok"):
        summary = _trim_specialist_prefix(str(result.get("result", "")))
        text = summary or "I inspected the local codebase."
        from .contracts import LLMDerivedResult
        fact = LLMDerivedResult(
            content=text,
            source="code_specialist",
            model=str(result.get("model", "unknown")),
            confidence=0.8,
            timestamp=utc_now_iso(),
        )
        return TurnExecutionResult(
            lane="realtime",
            text=text,
            resolved_by="tool_only",
            tool_summaries=["code_specialist:ok"],
            tool_facts=[fact],
        )

    return TurnExecutionResult(
        lane="realtime",
        text="I cannot inspect the codebase right now.",
        resolved_by="fallback_template",
    )


def handle_screen_query(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if not signals.mentions_screen:
        return None

    if not signals.wants_screen_inspection:
        return TurnExecutionResult(
            lane="realtime",
            text="I can inspect the local screen only when I capture it locally. I should not guess what is on it.",
            resolved_by="tool_only",
        )

    runner = services.get("run_vision_specialist")
    if not callable(runner):
        return TurnExecutionResult(
            lane="realtime",
            text="I cannot verify the screen right now.",
            resolved_by="fallback_template",
        )

    result = runner(env.text)
    if result.get("ok"):
        summary = _trim_specialist_prefix(str(result.get("result", "")))
        text = summary or "I inspected the screen."
        from .contracts import VerifiedFact, LLMDerivedResult
        if result.get("provenance") == "observed":
            fact = VerifiedFact(
                content=text,
                source="vision_specialist",
                confidence=0.95,
                timestamp=utc_now_iso(),
                verification_strength="observed",
            )
        else:
            fact = LLMDerivedResult(
                content=text,
                source="vision_specialist",
                model=str(result.get("model", "unknown")),
                confidence=0.8,
                timestamp=utc_now_iso(),
            )
        return TurnExecutionResult(
            lane="realtime",
            text=text,
            resolved_by="tool_only",
            tool_summaries=["vision_specialist:ok"],
            tool_facts=[fact],
        )

    return TurnExecutionResult(
        lane="realtime",
        text="I cannot verify the screen right now because local vision is unavailable.",
        resolved_by="fallback_template",
    )


def handle_time_query(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    tool_result = services["tool_orchestrator"].execute("local_now")
    if tool_result.ok:
        result = tool_result.data.get("result", {})
        spoken_time = str(
            result.get("spoken_time") or result.get("local_time", "unknown")
        ).strip()
        suffix = _spoken_suffix(
            env, services["memory"], allow_name=False, allow_title=True, comma=False
        )
        templates = [
            f"It is {spoken_time}{suffix}.",
            f"The time is {spoken_time}{suffix}.",
            f"It's {spoken_time}{suffix}.",
            f"{spoken_time.capitalize()}{suffix}.",
        ]
        return TurnExecutionResult(
            lane="realtime",
            text=_select_variant(env, templates),
            resolved_by="tool_only",
            tool_summaries=[f"local_time:{spoken_time}"],
        )
    return TurnExecutionResult(
        lane="realtime",
        text="I could not read the clock right now.",
        resolved_by="fallback_template",
    )


def handle_day_query(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    tool_result = services["tool_orchestrator"].execute("local_now")
    if tool_result.ok:
        result = tool_result.data.get("result", {})
        spoken_day = str(result.get("spoken_day") or "").strip()
        suffix = _spoken_suffix(
            env, services["memory"], allow_name=False, allow_title=True, comma=False
        )
        templates = [
            f"It is {spoken_day}{suffix}.",
            f"It's {spoken_day}{suffix}.",
            f"{spoken_day}{suffix}.",
        ]
        return TurnExecutionResult(
            lane="realtime",
            text=_select_variant(env, templates),
            resolved_by="tool_only",
            tool_summaries=[f"local_day:{spoken_day}"],
        )
    return TurnExecutionResult(
        lane="realtime",
        text="I could not read the day right now.",
        resolved_by="fallback_template",
    )


def handle_date_query(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    tool_result = services["tool_orchestrator"].execute("local_now")
    if tool_result.ok:
        result = tool_result.data.get("result", {})
        spoken_date = str(
            result.get("spoken_date") or result.get("local_date", "unknown")
        ).strip()
        suffix = _spoken_suffix(
            env, services["memory"], allow_name=False, allow_title=True, comma=False
        )
        templates = [
            f"It is {spoken_date}{suffix}.",
            f"It's {spoken_date}{suffix}.",
            f"{spoken_date.capitalize()}{suffix}.",
        ]
        return TurnExecutionResult(
            lane="realtime",
            text=_select_variant(env, templates),
            resolved_by="tool_only",
            tool_summaries=[f"local_date:{spoken_date}"],
        )
    return TurnExecutionResult(
        lane="realtime",
        text="I could not read the date right now.",
        resolved_by="fallback_template",
    )


def handle_status(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    current = services["job_status_tool"].status(services["job_status"])
    job_snapshot = {"state": current.get("state", "IDLE")}
    suffix = _spoken_suffix(
        env, services["memory"], allow_name=False, allow_title=True, comma=False
    )
    if current.get("state") == "IDLE":
        status_text = _select_variant(
            env,
            [
                f"I am online{suffix}.",
                f"I am currently online{suffix}.",
                f"I am online and ready{suffix}.",
            ],
        )
        last_result = services.get("last_bg1_result")
        if last_result:
            status_text = f"{status_text} Last heavy result: {last_result}"
    else:
        progress = float(current.get("progress", 0.0))
        status_text = _select_variant(
            env,
            [
                f"I am online{suffix}. Heavy task {current.get('job_id', 'unknown')} is {str(current.get('state', 'RUNNING')).lower()} at {progress:.0f}%.",
                f"I am currently online{suffix}. Heavy task {current.get('job_id', 'unknown')} is {str(current.get('state', 'RUNNING')).lower()} at {progress:.0f}%.",
            ],
        )
    return TurnExecutionResult(
        lane="realtime",
        text=status_text,
        resolved_by="template",
        job_snapshot=job_snapshot,
    )


def handle_bg1_busy_rejection(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle rejection when BG1 queue is full."""
    del decision
    from jarvis.main import TurnExecutionResult
    
    current = services["job_status_tool"].status(services["job_status"])
    job_snapshot = {"state": current.get("state", "RUNNING")}
    
    return TurnExecutionResult(
        lane="realtime",
        text="I'm sorry, but I'm currently busy with other background tasks. Please try again in a moment.",
        resolved_by="template",
        job_snapshot=job_snapshot,
    )


def handle_job_cancel(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    if not services.get("capabilities", {}).get("cancel_heavy_task", True):
        return services["deny_capability"]("cancel_heavy_task")

    text_lower = env.text.lower()
    force = "force" in text_lower or "hard" in text_lower
    cancel_result = services["job_status_tool"].cancel(
        services["job_status"], force=force
    )
    if cancel_result.get("ok"):
        message = "Cancellation requested for the current heavy task."
    else:
        message = "There is no active heavy task to cancel."
    return TurnExecutionResult(
        lane="realtime",
        text=message,
        resolved_by="template",
    )


def handle_notify_when_free(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    current = services["job_status"].get_current()
    if current is None:
        return TurnExecutionResult(
            lane="realtime",
            text="BG1 is already free right now.",
            resolved_by="tool_only",
        )
    services["job_status_tool"].subscribe_on_complete(
        services["job_status"],
        turn_id=env.turn_id,
        speaker_id="owner",
        channel=env.channel_id or "local",
    )
    return TurnExecutionResult(
        lane="realtime",
        text="Okay. I will notify you when the heavy task is done.",
        resolved_by="tool_only",
    )


def handle_recall_name(env: Any, decision: Any, services: dict[str, Any]) -> Any | None:
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if decision.intent != "recall_name" and not signals.asks_name_recall:
        return None
    remembered_name = _compose_owner_name(services["memory"])
    if remembered_name is not None:
        return TurnExecutionResult(
            lane="realtime",
            text=_compose_owner_fact_reply(services["memory"], "name"),
            resolved_by="tool_only",
            memory_items=[f"user_name:{remembered_name}"],
        )
    return TurnExecutionResult(
        lane="realtime",
        text="I do not have your name saved yet. Say 'my name is ...' and I will remember it.",
        resolved_by="tool_only",
    )


def handle_greeting(env: Any, decision: Any, services: dict[str, Any]) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if signals.asks_wellbeing:
        return None
    if not signals.is_greeting:
        return None
    suffix = _spoken_suffix(env, services["memory"], personal=True, comma=True)
    return TurnExecutionResult(
        lane="realtime",
        text=_select_variant(
            env,
            [
                f"Hello{suffix}. I am ready.",
                f"Hello{suffix}. Good to hear from you.",
                f"Hi{suffix}. I am here and ready.",
            ],
        ),
        resolved_by="tool_only",
    )


def handle_help(env: Any, decision: Any, services: dict[str, Any]) -> Any | None:
    del decision
    from jarvis.main import TurnExecutionResult

    signals = analyze_utterance(env.text)
    if not signals.asks_capabilities:
        return None

    # Use self-knowledge index for accurate capabilities listing
    self_knowledge = services.get("self_knowledge")
    if self_knowledge:
        answer = self_knowledge.answer_capabilities_question()
        if answer:
            return TurnExecutionResult(
                lane="realtime",
                text=answer,
                resolved_by="tool_only",
            )

    return TurnExecutionResult(
        lane="realtime",
        text=_compose_capabilities(services["memory"]),
        resolved_by="tool_only",
    )


def _infer_addon_id(env: Any, services: dict[str, Any]) -> str | None:
    text_lower = env.text.lower()
    registry = services.get("addon_registry")
    manifest_ids = list(getattr(registry, "manifests", {}).keys())
    for addon_id in manifest_ids:
        if addon_id.lower() in text_lower:
            return addon_id
    if len(manifest_ids) == 1:
        return manifest_ids[0]
    if "discord" in text_lower:
        return "discord"
    return None


def handle_addon_enable(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    if not services.get("capabilities", {}).get("addon_control", True):
        return services["deny_capability"]("addon_control")

    addon_id = _infer_addon_id(env, services)
    manager = services["addon_manager"]
    if addon_id is None:
        message = "I could not determine which addon to enable."
    else:
        state = manager.states.get(addon_id)
        if state is None:
            message = f"I could not find addon {addon_id}."
        elif state == "ENABLED":
            message = f"Addon {addon_id} is already enabled."
        else:
            result = enable_addon(manager, addon_id)
            message = (
                f"Enabled addon {addon_id}."
                if result == "enabled"
                else f"I could not enable addon {addon_id}."
            )
    return TurnExecutionResult(lane="realtime", text=message, resolved_by="tool_only")


def handle_addon_disable(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    del decision
    from jarvis.main import TurnExecutionResult

    if not services.get("capabilities", {}).get("addon_control", True):
        return services["deny_capability"]("addon_control")

    addon_id = _infer_addon_id(env, services)
    manager = services["addon_manager"]
    if addon_id is None:
        message = "I could not determine which addon to disable."
    else:
        state = manager.states.get(addon_id)
        if state is None:
            message = f"I could not find addon {addon_id}."
        elif state != "ENABLED":
            message = f"Addon {addon_id} is already disabled."
        else:
            result = disable_addon(manager, addon_id)
            message = (
                f"Disabled addon {addon_id}."
                if result == "disabled"
                else f"I could not disable addon {addon_id}."
            )
    return TurnExecutionResult(lane="realtime", text=message, resolved_by="tool_only")


def handle_addon_status(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle addon status command: 'addon status'

    Lists all addons with their current state.
    """
    from jarvis.main import TurnExecutionResult

    manager = services.get("addon_manager")
    if not manager:
        return TurnExecutionResult(
            lane="realtime",
            text="Addon manager not available.",
            resolved_by="tool_only",
        )

    summary = manager.get_health_summary()
    lines = []
    for addon_id, info in sorted(summary["addons"].items()):
        state = info["state"]
        health_ok = info["health"].get("ok", False)
        icon = "✓" if health_ok else "✗" if state != "FAULTED" else "!"
        lines.append(f"  {icon} {addon_id}: {state}")

    header = f"Addons ({summary['total']} total):"
    return TurnExecutionResult(
        lane="realtime",
        text=header + "\n" + "\n".join(lines) if lines else "  No addons discovered.",
        resolved_by="tool_only",
    )


def handle_addon_health(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle addon health command: 'addon health <addon-id>'

    Shows detailed health status for a specific addon.
    """
    from jarvis.main import TurnExecutionResult
    import re

    text = env.text.lower()

    # Extract addon ID from command
    match = re.search(r"addon\s+health\s+(\w+)", text)
    addon_id = match.group(1) if match else None

    manager = services.get("addon_manager")
    if not manager:
        return TurnExecutionResult(
            lane="realtime",
            text="Addon manager not available.",
            resolved_by="tool_only",
        )

    if addon_id is None:
        return TurnExecutionResult(
            lane="realtime",
            text="Please specify which addon to check. Usage: addon health <addon-id>",
            resolved_by="tool_only",
        )

    health = manager.healthcheck(addon_id)
    state = manager.states.get(addon_id, "UNKNOWN")

    if health.get("ok"):
        details = health.get("details", "healthy")
        return TurnExecutionResult(
            lane="realtime",
            text=f"Addon '{addon_id}' is healthy (state: {state}). {details}",
            resolved_by="tool_only",
        )
    else:
        error = health.get("error", "unknown error")
        return TurnExecutionResult(
            lane="realtime",
            text=f"Addon '{addon_id}' health check failed (state: {state}): {error}",
            resolved_by="tool_only",
        )


def handle_addon_channel(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle addon channel control: 'addon channel <addon-id> <channel> <on|off>'

    Phase 4D: Addon Operator Surface
    """
    from jarvis.main import TurnExecutionResult
    import re

    text = env.text.lower()

    # Extract addon_id, channel, and state from command
    match = re.search(r"addon\s+channel\s+(\w+)\s+(\w+)\s+(on|off)", text)
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: addon channel <addon-id> <channel> <on|off>",
            resolved_by="tool_only",
        )

    addon_id = match.group(1)
    channel_id = match.group(2)
    turn_on = match.group(3) == "on"

    manager = services.get("addon_manager")
    if not manager:
        return TurnExecutionResult(
            lane="realtime",
            text="Addon manager not available.",
            resolved_by="tool_only",
        )

    state = manager.states.get(addon_id)
    if state is None:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Addon '{addon_id}' not found.",
            resolved_by="tool_only",
        )

    # Get audio pipeline and set channel state
    pipeline = services.get("addon_audio_pipeline")
    if pipeline:
        result = pipeline.set_text_channel_enabled(f"{addon_id}_{channel_id}", turn_on)
        if result:
            action = "enabled" if turn_on else "disabled"
            return TurnExecutionResult(
                lane="realtime",
                text=f"{action.capitalize()} channel '{channel_id}' for addon '{addon_id}'.",
                resolved_by="tool_only",
            )
        else:
            return TurnExecutionResult(
                lane="realtime",
                text=f"Channel '{channel_id}' not found for addon '{addon_id}'.",
                resolved_by="tool_only",
            )

    return TurnExecutionResult(
        lane="realtime",
        text="Could not set channel state (audio pipeline not available).",
        resolved_by="tool_only",
    )


def handle_app_launch(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle application launch requests.

    Matches intents like "open notepad", "launch chrome", "start calculator"
    """
    from jarvis.main import TurnExecutionResult

    text = env.text.lower()

    # Extract app name from common patterns — use \S+[\w\s]* to capture multi-word names
    app_name = None
    for pattern in [
        r"open\s+([\w][\w\s]*)",
        r"launch\s+([\w][\w\s]*)",
        r"start\s+([\w][\w\s]*)",
        r"run\s+([\w][\w\s]*)",
    ]:
        match = re.search(pattern, text)
        if match:
            app_name = match.group(1).strip()
            break

    if not app_name:
        return TurnExecutionResult(
            lane="realtime",
            text="I'm not sure which application you want to open. Please specify an app name.",
            resolved_by="tool_only",
        )

    result = app_launch(app_name)
    if result["ok"]:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Launched {app_name}.",
            resolved_by="tool_only",
        )
    else:
        reason = result.get("reason", "unknown")
        if reason == "app_not_in_allowlist":
            allowed = list_allowed_apps()
            return TurnExecutionResult(
                lane="realtime",
                text=f"{app_name} is not in the allowed applications list. Allowed apps include: {', '.join(allowed[:8])}.",
                resolved_by="tool_only",
            )
        elif reason == "app_executable_not_found":
            return TurnExecutionResult(
                lane="realtime",
                text=f"Could not find {app_name} on this system.",
                resolved_by="tool_only",
            )
        else:
            return TurnExecutionResult(
                lane="realtime",
                text=f"Could not launch {app_name}: {reason}.",
                resolved_by="tool_only",
            )


def handle_app_focus(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle application focus requests.

    Matches intents like "focus chrome", "bring notepad to front", "switch to code"
    """
    from jarvis.main import TurnExecutionResult

    text = env.text.lower()

    # Extract app name from common patterns — capture multi-word names
    app_name = None
    for pattern in [
        r"focus\s+([\w][\w\s]*)",
        r"switch\s+to\s+([\w][\w\s]*)",
        r"bring\s+([\w][\w\s]*)\s+to",
        r"show\s+([\w][\w\s]*)",
    ]:
        match = re.search(pattern, text)
        if match:
            app_name = match.group(1).strip()
            break

    if not app_name:
        return TurnExecutionResult(
            lane="realtime",
            text="I'm not sure which application you want to focus. Please specify an app name.",
            resolved_by="tool_only",
        )

    result = app_focus(app_name)
    if result["ok"]:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Brought {app_name} to the foreground.",
            resolved_by="tool_only",
        )
    else:
        reason = result.get("reason", "unknown")
        if reason == "window_not_found":
            return TurnExecutionResult(
                lane="realtime",
                text=f"{app_name} is not currently open. Would you like me to launch it?",
                resolved_by="tool_only",
            )
        elif reason == "app_not_in_allowlist":
            list_allowed_apps()
            return TurnExecutionResult(
                lane="realtime",
                text=f"{app_name} is not in the allowed applications list.",
                resolved_by="tool_only",
            )
        else:
            return TurnExecutionResult(
                lane="realtime",
                text=f"Could not focus {app_name}: {reason}.",
                resolved_by="tool_only",
            )


# =============================================================================
# Phase 3C: Memory Productization - Intent Handlers
# =============================================================================


def handle_memory_forget_by_id(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any:
    """Handle memory forget by ID: 'forget #42', 'forget memory 42', 'memory forget #42'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import forget_by_id, inspect_by_id

    text = env.text
    match = re.search(
        r"(?:forget|delete|remove)\s*(?:memory\s*)?#?(\d+)", text, re.IGNORECASE
    )
    if not match:
        match = re.search(r"memory\s+forget\s+#?(\d+)", text, re.IGNORECASE)
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: forget #<id> — specify the memory ID number to forget.",
            resolved_by="tool_only",
        )

    memory_id = int(match.group(1))
    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))

    # Show what we're about to delete
    preview = inspect_by_id(memory_service, memory_id)
    result = forget_by_id(memory_service, memory_id)

    if result["ok"]:
        desc = ""
        if preview.get("ok") and preview.get("record"):
            rec = preview["record"]
            desc = f" ({rec['key']}: {rec['value'][:40]})"
        return TurnExecutionResult(
            lane="realtime",
            text=f"Forgotten memory #{memory_id}{desc}.",
            resolved_by="tool_only",
        )
    return TurnExecutionResult(
        lane="realtime",
        text=f"No memory found with ID #{memory_id}.",
        resolved_by="tool_only",
    )


def handle_memory_update_by_id(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any:
    """Handle memory update by ID: 'update #42 new value', 'memory update #42 new value'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import update_by_id

    text = env.text
    match = re.search(
        r"(?:update|edit|change)\s*(?:memory\s*)?#?(\d+)\s+(.+)", text, re.IGNORECASE
    )
    if not match:
        match = re.search(
            r"memory\s+(?:update|edit)\s+#?(\d+)\s+(.+)", text, re.IGNORECASE
        )
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: update #<id> <new-value> — specify the memory ID and the new value.",
            resolved_by="tool_only",
        )

    memory_id = int(match.group(1))
    new_value = match.group(2).strip()
    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = update_by_id(memory_service, memory_id, new_value)

    if result["ok"]:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Updated memory #{memory_id} to: {new_value}",
            resolved_by="tool_only",
        )
    return TurnExecutionResult(
        lane="realtime",
        text=f"No memory found with ID #{memory_id}.",
        resolved_by="tool_only",
    )


def handle_memory_inspect_by_id(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any:
    """Handle memory inspect by ID: 'inspect #42', 'memory inspect #42', 'show memory #42'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import inspect_by_id

    text = env.text
    match = re.search(
        r"(?:inspect|show|view)\s*(?:memory\s*)?#?(\d+)", text, re.IGNORECASE
    )
    if not match:
        match = re.search(r"memory\s+(?:inspect|show)\s+#?(\d+)", text, re.IGNORECASE)
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: inspect #<id> — specify the memory ID to inspect.",
            resolved_by="tool_only",
        )

    memory_id = int(match.group(1))
    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = inspect_by_id(memory_service, memory_id)

    if result["ok"]:
        rec = result["record"]
        parts = [f"Memory #{memory_id}:"]
        parts.append(f"  Key: {rec['key']}")
        parts.append(f"  Value: {rec['value']}")
        parts.append(f"  Confidence: {rec['confidence']:.0%}")
        parts.append(f"  Created: {rec['created_at'][:10]}")
        if rec.get("source"):
            parts.append(f"  Source: {rec['source']}")
        return TurnExecutionResult(
            lane="realtime",
            text="\n".join(parts),
            resolved_by="tool_only",
        )
    return TurnExecutionResult(
        lane="realtime",
        text=f"No memory found with ID #{memory_id}.",
        resolved_by="tool_only",
    )


def handle_memory_save(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle memory save command: 'save a memory that <fact>', 'remember that <fact>'"""
    from jarvis.main import TurnExecutionResult

    text = env.text.lower()
    # Patterns like "save a memory that X", "remember that X", "save that X"
    match = re.search(
        r"(?:save|remember)(?:\s+a\s+memory)?(?:\s+that)?\s+(.+)", text, re.IGNORECASE
    )
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: save a memory that <fact> — specify the fact you want me to remember.",
            resolved_by="tool_only",
        )

    fact = match.group(1).strip()
    # Simple key extraction - use first 2-3 words or a generic key
    words = fact.split()
    key = "_".join(words[:2]) if len(words) >= 2 else words[0]

    memory = services["memory"]
    ok = memory.remember(
        key, fact, confidence=0.8, source="intent_handler", source_id=env.turn_id
    )

    if ok:
        return TurnExecutionResult(
            lane="realtime",
            text=f"I have saved that to my memory under '{key}': {fact}",
            resolved_by="tool_only",
            memory_items=[f"{key}:{fact}"],
        )
    return TurnExecutionResult(
        lane="realtime",
        text="I could not save that memory right now.",
        resolved_by="fallback_template",
    )


def handle_memory_inspect(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle memory inspect command: 'memory inspect <key>'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import inspect

    text = env.text.lower()

    # Extract key from command
    match = re.search(r"memory\s+inspect\s+(\w+)", text)
    if not match:
        # No specific key — delegate to list to show all stored memories
        return handle_memory_list(env, decision, services)

    key = match.group(1)
    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = inspect(memory_service, key)

    if result["ok"]:
        records = result["records"]
        if len(records) == 1:
            return TurnExecutionResult(
                lane="realtime",
                text=f"Memory '{key}': {records[0]['value']} (confidence: {records[0]['confidence']:.0%}, created: {records[0]['created_at'][:10]})",
                resolved_by="tool_only",
            )
        else:
            values = "; ".join([f"- {r['value']}" for r in records[:3]])
            return TurnExecutionResult(
                lane="realtime",
                text=f"Found {result['count']} memories for '{key}':\n{values}",
                resolved_by="tool_only",
            )
    else:
        return TurnExecutionResult(
            lane="realtime",
            text=f"No memory found for key '{key}'.",
            resolved_by="tool_only",
        )


def handle_memory_list(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle memory list command: 'memory list [query]'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import list_memories

    text = env.text.lower()

    # Extract optional query — handles both "memory list [query]" and natural language
    # routes like "show me your memories" / "my memories" (match will be None → list all)
    explicit_match = re.search(r"memory\s+list\s*(.*)", text)
    query = (
        explicit_match.group(1).strip()
        if explicit_match and explicit_match.group(1).strip()
        else None
    )

    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = list_memories(memory_service, query)

    if result["ok"]:
        memories = result["memories"][:5]
        if not memories:
            return TurnExecutionResult(
                lane="realtime",
                text="No memories found." if query else "No memories stored.",
                resolved_by="tool_only",
            )
        lines = [
            f"- [{m['id']}] {m['key']}: {m['value'][:60]}{'...' if len(m['value']) > 60 else ''}"
            for m in memories
        ]
        return TurnExecutionResult(
            lane="realtime",
            text=f"Memories ({result['count']} total):\n" + "\n".join(lines),
            resolved_by="tool_only",
        )
    else:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Failed to list memories: {result.get('reason', 'unknown')}",
            resolved_by="tool_only",
        )


def handle_memory_edit(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle memory edit command: 'memory edit <key> <new-value>'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import edit

    text = env.text

    # Extract key and value
    match = re.search(r"memory\s+edit\s+(\w+)\s+(.+)", text, re.IGNORECASE)
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: memory edit <key> <new-value>",
            resolved_by="tool_only",
        )

    key = match.group(1)
    new_value = match.group(2).strip()

    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = edit(memory_service, key, new_value)

    if result["ok"]:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Updated memory '{key}' to: {new_value}",
            resolved_by="tool_only",
        )
    else:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Failed to update memory '{key}'.",
            resolved_by="tool_only",
        )


def handle_memory_forget(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle memory forget command: 'memory forget <key>'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import forget

    text = env.text.lower()

    # Extract key
    match = re.search(r"memory\s+forget\s+(\w+)", text)
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: memory forget <key>",
            resolved_by="tool_only",
        )

    key = match.group(1)

    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = forget(memory_service, key)

    if result["ok"]:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Forgotten {result['deleted_count']} memory(ies) for key '{key}'.",
            resolved_by="tool_only",
        )
    else:
        return TurnExecutionResult(
            lane="realtime",
            text=f"No memory found for key '{key}'.",
            resolved_by="tool_only",
        )


def handle_memory_backup(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle memory backup command: 'memory backup'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import backup

    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = backup(memory_service)

    if result["ok"]:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Memory backup created: {result['backup_path']}",
            resolved_by="tool_only",
        )
    else:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Backup failed: {result.get('reason', 'unknown')}",
            resolved_by="tool_only",
        )


def handle_memory_restore(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle memory restore command: 'memory restore <backup-path>'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import restore

    text = env.text

    # Extract backup path
    match = re.search(r"memory\s+restore\s+(.+)", text, re.IGNORECASE)
    if not match:
        return TurnExecutionResult(
            lane="realtime",
            text="Usage: memory restore <backup-path>",
            resolved_by="tool_only",
        )

    backup_path = match.group(1).strip()

    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = restore(memory_service, backup_path)

    if result["ok"]:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Memory restored from: {result['restored_from']}",
            resolved_by="tool_only",
        )
    else:
        return TurnExecutionResult(
            lane="realtime",
            text=f"Restore failed: {result.get('reason', 'Backup not found')}",
            resolved_by="tool_only",
        )


def handle_memory_list_backups(
    env: Any, decision: Any, services: dict[str, Any]
) -> Any:
    """Handle memory list backups command: 'memory backups'"""
    from pathlib import Path
    from jarvis.main import TurnExecutionResult
    from jarvis.brain_core.memory_service import MemoryService
    from jarvis.tools.memory_tool import list_backups

    db_path = services.get("memory_db", ".jarvis_memory.sqlite")
    memory_service = MemoryService(str(db_path))
    result = list_backups(memory_service)

    if result["ok"] and result["backups"]:
        backups = result["backups"][:5]
        lines = [f"- {Path(b).name}" for b in backups]
        return TurnExecutionResult(
            lane="realtime",
            text=f"Available backups ({result['count']} total):\n" + "\n".join(lines),
            resolved_by="tool_only",
        )
    else:
        return TurnExecutionResult(
            lane="realtime",
            text="No memory backups found.",
            resolved_by="tool_only",
        )


# Phase 3: Natural phrase families


def handle_performance_query(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle performance queries: 'why are you slow', 'how to improve your speed'"""
    from jarvis.main import TurnExecutionResult

    job_status = services.get("job_status")
    if job_status:
        current = job_status_tool.status(job_status)
        if current.get("active_jobs", 0) > 0:
            return TurnExecutionResult(
                lane="realtime",
                text="I'm currently processing a background task sir. Because I run models one at a time to save memory, I must finish the background job before I can dedicate full power to our conversation.",
                resolved_by="template",
                conversation_user_text=env.text,
            )

    # Check recent latency
    recent_latencies = services.get("recent_latencies", [])
    if recent_latencies:
        avg_ms = sum(recent_latencies) / len(recent_latencies)
        if avg_ms > 5000:
            return TurnExecutionResult(
                lane="realtime",
                text=f"My average response time is {avg_ms / 1000:.1f} seconds. This is often due to the cost of semantic memory retrieval or swapping heavy models in and out of your 6 gigabyte VRAM.",
                resolved_by="template",
                conversation_user_text=env.text,
            )

    return TurnExecutionResult(
        lane="realtime",
        text="I am currently running in a Sequential Relay mode to keep your system lightweight. This ensures I don't crash your computer, though it does add a few seconds of load time per turn.",
        resolved_by="template",
        conversation_user_text=env.text,
    )


def handle_bg1_update(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle BG1 update queries: 'how's the task going', 'any progress'"""
    from jarvis.main import TurnExecutionResult

    job_status = services.get("job_status")
    if not job_status:
        return TurnExecutionResult(
            lane="realtime",
            text="I'm online. I'm not currently running any long tasks.",
            resolved_by="template",
            conversation_user_text=env.text,
        )

    current = job_status_tool.status(job_status)
    state = current.get("state", "IDLE")

    if state == "IDLE":
        # No active job — check if there's a recent completed result to mention
        last_bg1 = services.get("last_bg1_result")
        if last_bg1:
            return TurnExecutionResult(
                lane="realtime",
                text="The background task is finished. Say 'tell me the results' to see the output.",
                resolved_by="template",
                conversation_user_text=env.text,
            )
        return TurnExecutionResult(
            lane="realtime",
            text="I'm online. I'm not currently running any long tasks. I'm ready for your next request.",
            resolved_by="template",
            conversation_user_text=env.text,
        )

    # Active job — report progress
    progress = current.get("progress", 0)
    stage = current.get("stage", "working")

    if state == "COMPLETED":
        return TurnExecutionResult(
            lane="realtime",
            text="The background task is complete. Say 'tell me the results' to see the output.",
            resolved_by="template",
            conversation_user_text=env.text,
        )

    progress_text = f"{progress:.0f}%" if progress > 0 else "in progress"
    return TurnExecutionResult(
        lane="realtime",
        text=f"Background task is {progress_text} — {stage}.",
        resolved_by="template",
        conversation_user_text=env.text,
    )


def handle_bg1_result(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle BG1 result queries: 'what did you find out', 'what were the results'

    Uses resolved_by='template' to pass raw result through without LLM rewriting.
    The full text is printed to terminal; voice reads only a brief summary.
    """
    from jarvis.main import TurnExecutionResult

    result_text = None

    # Try memory namespaces first (structured task results)
    memory_namespaces = services.get("memory_namespaces")
    if memory_namespaces:
        task_results = memory_namespaces.search_task_results(
            decision.normalized_text, limit=1
        )
        if task_results:
            result_text = task_results[0].result_summary
        else:
            # Fall back to most recent task result
            all_results = memory_namespaces.get_all_task_results()
            if all_results:
                result_text = all_results[-1].result_summary

    # Fall back to BG1 manager's cached last result
    if not result_text:
        result_text = services.get("last_bg1_result")

    # Fall back to memory service (legacy key)
    if not result_text:
        memory = services.get("memory")
        if memory:
            recalled = memory.recall("last_heavy_result")
            if recalled and recalled[0].value:
                result_text = recalled[0].value

    if not result_text:
        return TurnExecutionResult(
            lane="realtime",
            text="I don't have any recent research results. Would you like me to look into something?",
            resolved_by="template",
            conversation_user_text=env.text,
        )

    # Return raw result with template resolved_by — skips renderer LLM
    # Voice policy will truncate for speech; terminal gets full text via display_text
    return TurnExecutionResult(
        lane="realtime",
        text=result_text,
        resolved_by="template",
        conversation_user_text=env.text,
    )


def handle_website_check(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle website check queries: 'check this site', 'look at this website'"""
    from jarvis.main import TurnExecutionResult
    from jarvis.tools.web_fetch_extract import fetch_extract
    from jarvis.tools.url_normalize import extract_candidate

    # Extract URL from user input
    url = extract_candidate(env.text)

    if not url:
        return TurnExecutionResult(
            lane="realtime",
            text="I need a website address to check. What website would you like me to look at?",
            resolved_by="clarification",
            conversation_user_text=env.text,
        )

    # Fetch the website in realtime
    try:
        result = fetch_extract(url)
        if not result.get("ok"):
            return TurnExecutionResult(
                lane="realtime",
                text=f"I could not reach that website. The error was: {result.get('reason', 'unknown')}.",
                resolved_by="tool_only",
                tool_summaries=[f"web_fetch:{url} failed: {result.get('reason')}"],
            )

        # Extract main content summary
        text = result.get("text", "")
        structured = result.get("structured", {})
        title = structured.get("title", "")
        description = structured.get("description", "")

        # Build spoken summary
        if title and description:
            summary = (
                f"{title}. {description[:200]}"
                if len(description) > 200
                else f"{title}. {description}"
            )
        elif text:
            summary = text[:300] + "..." if len(text) > 300 else text
        else:
            summary = "The website loaded but I could not extract meaningful content."

        return TurnExecutionResult(
            lane="realtime",
            text=summary,
            resolved_by="tool_only",
            tool_summaries=[f"web_fetch:{url}"],
        )
    except Exception as e:
        return TurnExecutionResult(
            lane="realtime",
            text=f"I ran into an error checking that website: {str(e)}.",
            resolved_by="fallback_template",
        )


def handle_screen_show(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle screen show queries: 'show me my screen', 'what's on my display'"""
    from jarvis.main import TurnExecutionResult

    # Runs in realtime — use vision specialist if available
    runner = services.get("run_vision_specialist")
    if not callable(runner):
        return TurnExecutionResult(
            lane="realtime",
            text="I cannot check the screen right now. Local vision is not available.",
            resolved_by="fallback_template",
            conversation_user_text=env.text,
        )
    result = runner(env.text)
    if result.get("ok"):
        summary = _trim_specialist_prefix(str(result.get("result", "")))
        text = summary or "I checked the screen."
        from .contracts import VerifiedFact, LLMDerivedResult
        if result.get("provenance") == "observed":
            fact = VerifiedFact(
                content=text,
                source="vision_specialist",
                confidence=0.95,
                timestamp=utc_now_iso(),
                verification_strength="observed",
            )
        else:
            fact = LLMDerivedResult(
                content=text,
                source="vision_specialist",
                model=str(result.get("model", "unknown")),
                confidence=0.8,
                timestamp=utc_now_iso(),
            )
        return TurnExecutionResult(
            lane="realtime",
            text=text,
            resolved_by="tool_only",
            tool_summaries=["vision_specialist:ok"],
            tool_facts=[fact],
            conversation_user_text=env.text,
        )
    return TurnExecutionResult(
        lane="realtime",
        text="I could not read the screen right now.",
        resolved_by="fallback_template",
        conversation_user_text=env.text,
    )


def handle_health_report(env: Any, decision: Any, services: dict[str, Any]) -> Any:
    """Handle health report / dashboard queries."""
    from jarvis.main import TurnExecutionResult

    # Try to use the specialized tool if available
    tool_orchestrator = services.get("tool_orchestrator")
    if tool_orchestrator:
        # Check if intent_miss_stats or similar are registered
        stats_result = tool_orchestrator.execute("intent_miss_stats")
        if stats_result.ok:
            stats = stats_result.data.get("result", {})
            miss_count = stats.get("total_misses", 0)
            text = f"System Health: I have recorded {miss_count} intent misses. All subsystems are operational."
            return TurnExecutionResult(
                lane="realtime",
                text=text,
                resolved_by="tool_only",
            )

    return TurnExecutionResult(
        lane="realtime",
        text="All systems are nominal. Memory service is active, and background workers are ready.",
        resolved_by="template",
    )


def build_default_registry() -> IntentHandlerRegistry:
    registry = IntentHandlerRegistry()
    registry.register_pre_intent(handle_name_recognition)
    registry.register_pre_intent(handle_address_preference)
    registry.register_pre_intent(handle_hearing_query)
    registry.register_pre_intent(handle_wellbeing)
    registry.register_pre_intent(handle_social_repair)
    registry.register_pre_intent(handle_grounding_correction)
    registry.register_pre_intent(handle_math_query)
    registry.register_pre_intent(handle_owner_memory)
    registry.register_pre_intent(handle_owner_summary)
    registry.register_pre_intent(handle_self_understanding)
    registry.register_pre_intent(handle_assistant_identity)
    registry.register("time_query", handle_time_query)
    registry.register("day_query", handle_day_query)
    registry.register("date_query", handle_date_query)
    registry.register("status", handle_status)
    registry.register("job_status", handle_status)
    registry.register("bg1_busy_rejection", handle_bg1_busy_rejection)
    registry.register("job_cancel", handle_job_cancel)
    registry.register("notify_when_free", handle_notify_when_free)
    registry.register("recall_name", handle_recall_name)
    registry.register("owner_memory", handle_owner_memory)
    registry.register("addon_enable", handle_addon_enable)
    registry.register("addon_disable", handle_addon_disable)
    registry.register("addon_status", handle_addon_status)
    registry.register("addon_health", handle_addon_health)
    registry.register("addon_channel", handle_addon_channel)
    registry.register("app_launch", handle_app_launch)
    registry.register("app_focus", handle_app_focus)
    # Phase 3C: Memory Productization
    registry.register("memory_save", handle_memory_save)
    registry.register("memory_inspect", handle_memory_inspect)
    registry.register("memory_list", handle_memory_list)
    registry.register("memory_edit", handle_memory_edit)
    registry.register("memory_forget", handle_memory_forget)
    registry.register("memory_backup", handle_memory_backup)
    registry.register("memory_restore", handle_memory_restore)
    registry.register("memory_list_backups", handle_memory_list_backups)
    # Phase 3C: Granular ID-based memory operations
    registry.register("memory_forget_by_id", handle_memory_forget_by_id)
    registry.register("memory_update_by_id", handle_memory_update_by_id)
    registry.register("memory_inspect_by_id", handle_memory_inspect_by_id)
    # Phase 3: Natural phrase families
    registry.register("performance_query", handle_performance_query)
    registry.register("bg1_update", handle_bg1_update)
    registry.register("bg1_result", handle_bg1_result)
    registry.register("website_check", handle_website_check)
    registry.register("screen_show", handle_screen_show)
    registry.register("screen_query", handle_screen_query)
    registry.register("health_report", handle_health_report)
    # Phase 10: Self-knowledge aware handlers
    registry.register("greeting", handle_greeting)
    registry.register("help_query", handle_help)
    registry.register("self_query", handle_self_understanding)
    registry.register("codebase_query", handle_codebase_query)
    return registry
