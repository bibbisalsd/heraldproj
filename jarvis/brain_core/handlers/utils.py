from __future__ import annotations

import hashlib
import re
from typing import Any

WAKE_WORD_ALIASES = {
    "jarvis", "javis", "jovis", "javas", "jarviss", "java", "jabba", "jabbas",
}

def _normalize_text(text: str) -> str:
    lowered = text.lower().replace("’", "'")
    lowered = re.sub(r"[^a-z0-9'\\s]", " ", lowered)
    lowered = re.sub(r"\\s+", " ", lowered).strip()
    return lowered

def _strip_wake_aliases(text: str) -> str:
    pattern = r"\\b(?:" + "|".join(sorted(WAKE_WORD_ALIASES)) + r")\\b"
    cleaned = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return re.sub(r"\\s+", " ", cleaned).strip()

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
