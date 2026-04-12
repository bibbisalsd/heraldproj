from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys
import shutil
import subprocess

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

try:
    import winsound
except ImportError:
    winsound = None


PRESETS = {
    "balanced": {"speed": 0.90},
    "natural": {"speed": 0.87},
    "fast": {"speed": 1.00},
    "calm": {"speed": 0.82},
    "butler": {"speed": 0.86},
    "clone": {"speed": 0.87},
}

CUSTOM_VOICE_MIXES = {
    # Deeper Jarvis-style blend.
    "jarvis": [("bm_lewis", 0.70), ("bm_daniel", 0.20), ("am_michael", 0.10)],
    # British butler style blend with formal RP-like tone.
    "butler": [("bm_lewis", 0.65), ("bm_daniel", 0.25), ("bm_fable", 0.10)],
    # Clone-oriented profile tuned for crisp, lower male delivery.
    "jarvis_clone": [
        ("bm_lewis", 0.75),
        ("bm_daniel", 0.15),
        ("am_michael", 0.10),
    ],
}

JARVIS_PROFILE_PRIORITY = (
    "jarvis_clone_from_piper",
    "jarvis_clone_pro",
    "jarvis_clone",
    "jarvis",
)

DEFAULT_VOICE = "jarvis_clone_from_piper"
DEFAULT_LANG = "en-gb"
OUTPUT_WAV_NAME = "jarvis_output.wav"
CUSTOM_VOICE_PROFILE_FILE = "custom_voice_profiles.json"
CUSTOM_VOICE_VECTOR_FILE = "custom_voice_vectors.npz"
SHORTFORM_EXPANSIONS_FILE = "shortform_expansions.json"

PHRASE_REPLACEMENTS = {
    "i'm": "i am",
    "i've": "i have",
    "you're": "you are",
    "you've": "you have",
    "we're": "we are",
    "we've": "we have",
    "they're": "they are",
    "they've": "they have",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "don't": "do not",
    "didn't": "did not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "wouldn't": "would not",
    "can't": "cannot",
    "won't": "will not",
    "shan't": "shall not",
    "ain't": "is not",
    "it's": "it is",
    "that's": "that is",
    "there's": "there is",
    "here's": "here is",
    "what's": "what is",
    "who's": "who is",
    "where's": "where is",
    "when's": "when is",
    "why's": "why is",
    "how's": "how is",
    "he's": "he is",
    "she's": "she is",
    "let's": "let us",
}

MISSPELLED_CONTRACTIONS = {
    "im": "i am",
    "ive": "i have",
    "youre": "you are",
    "youve": "you have",
    "weve": "we have",
    "theyre": "they are",
    "theyve": "they have",
    "dont": "do not",
    "didnt": "did not",
    "cant": "cannot",
    "wont": "will not",
    "isnt": "is not",
    "arent": "are not",
    "couldnt": "could not",
    "shouldnt": "should not",
    "wouldnt": "would not",
}

SYMBOL_REPLACEMENTS = [
    (r"(?<=\w)\s*&\s*(?=\w)", " and "),
    (r"(?<=\w)\s*\+\s*(?=\w)", " plus "),
    (r"(?<=\w)\s*@\s*(?=\w)", " at "),
    (r"(?<=\d)\s*%", " percent"),
]

APOSTROPHE_PATTERN = r"['\u2019\u2018\u02BC\uFF07?]"
NUMBER_UNIT_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s*)(ns|us|µs|μs|ms|s|sec|secs|second|seconds|min|mins|minute|minutes|h|hr|hrs|hour|hours|hz|khz|mhz|ghz|kb|mb|gb|tb|kib|mib|gib|tib|fps|rpm)\b",
    re.IGNORECASE,
)
STANDALONE_NUMBER_PATTERN = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
VERSION_PATTERN = re.compile(r"\bv(\d+(?:\.\d+)+)\b", re.IGNORECASE)
DOTTED_ACRONYM_PATTERN = re.compile(r"\b(?:[A-Za-z]\.){2,}[A-Za-z]?\.?")

UNIT_WORDS = {
    "ns": ("nanosecond", "nanoseconds"),
    "us": ("microsecond", "microseconds"),
    "µs": ("microsecond", "microseconds"),
    "μs": ("microsecond", "microseconds"),
    "ms": ("millisecond", "milliseconds"),
    "s": ("second", "seconds"),
    "sec": ("second", "seconds"),
    "secs": ("second", "seconds"),
    "second": ("second", "seconds"),
    "seconds": ("second", "seconds"),
    "min": ("minute", "minutes"),
    "mins": ("minute", "minutes"),
    "minute": ("minute", "minutes"),
    "minutes": ("minute", "minutes"),
    "h": ("hour", "hours"),
    "hr": ("hour", "hours"),
    "hrs": ("hour", "hours"),
    "hour": ("hour", "hours"),
    "hours": ("hour", "hours"),
    "hz": ("hertz", "hertz"),
    "khz": ("kilohertz", "kilohertz"),
    "mhz": ("megahertz", "megahertz"),
    "ghz": ("gigahertz", "gigahertz"),
    "kb": ("kilobyte", "kilobytes"),
    "mb": ("megabyte", "megabytes"),
    "gb": ("gigabyte", "gigabytes"),
    "tb": ("terabyte", "terabytes"),
    "kib": ("kibibyte", "kibibytes"),
    "mib": ("mebibyte", "mebibytes"),
    "gib": ("gibibyte", "gibibytes"),
    "tib": ("tebibyte", "tebibytes"),
    "fps": ("frame per second", "frames per second"),
    "rpm": ("revolution per minute", "revolutions per minute"),
}

QUICK_ACRONYM_WORDS = {
    "cpu": "CeePeeYou",
    "gpu": "GeePeeYou",
}

SHORTFORM_EXPANSIONS = {
    "wdym": "what do you mean",
    "wdum": "what do you mean",
    "wym": "what do you mean",
    "idk": "i do not know",
    "idc": "i do not care",
    "ik": "i know",
    "ikr": "i know right",
    "imk": "in my knowledge",
    "iirc": "if i remember correctly",
    "afaik": "as far as i know",
    "fwiw": "for what it is worth",
    "imo": "in my opinion",
    "imho": "in my honest opinion",
    "tbh": "to be honest",
    "tbf": "to be fair",
    "ngl": "not gonna lie",
    "smh": "shaking my head",
    "iykyk": "if you know you know",
    "jk": "just kidding",
    "jkjk": "just kidding",
    "js": "just saying",
    "jsyk": "just so you know",
    "rn": "right now",
    "atm": "at the moment",
    "btw": "by the way",
    "fyi": "for your information",
    "icymi": "in case you missed it",
    "asap": "as soon as possible",
    "eta": "estimated time of arrival",
    "eod": "end of day",
    "eow": "end of week",
    "ooo": "out of office",
    "wfh": "working from home",
    "tba": "to be announced",
    "tbd": "to be determined",
    "tbc": "to be confirmed",
    "brb": "be right back",
    "bbl": "be back later",
    "bbs": "be back soon",
    "bbiab": "be back in a bit",
    "gtg": "got to go",
    "g2g": "got to go",
    "ttyl": "talk to you later",
    "ttys": "talk to you soon",
    "cu": "see you",
    "cya": "see you",
    "l8r": "later",
    "afk": "away from keyboard",
    "lmk": "let me know",
    "hmu": "hit me up",
    "hbu": "how about you",
    "wbu": "what about you",
    "wyd": "what are you doing",
    "wya": "where are you",
    "wru": "where are you",
    "wsg": "what is good",
    "wsp": "what is up",
    "sup": "what is up",
    "nm": "not much",
    "np": "no problem",
    "nvm": "never mind",
    "dw": "do not worry",
    "yw": "you are welcome",
    "bc": "because",
    "bcs": "because",
    "cuz": "because",
    "coz": "because",
    "irl": "in real life",
    "omw": "on my way",
    "dm": "direct message",
    "dms": "direct messages",
    "pm": "private message",
    "pms": "private messages",
    "msg": "message",
    "pov": "point of view",
    "tldr": "too long did not read",
    "faq": "frequently asked questions",
    "faqs": "frequently asked questions",
    "kpi": "k p i",
    "okr": "o k r",
    "lol": "laughing out loud",
    "lmao": "laughing my ass off",
    "lmfao": "laughing my fucking ass off",
    "rofl": "rolling on the floor laughing",
    "ftw": "for the win",
    "ffs": "for fucks sake",
    "fml": "fuck my life",
    "wtf": "what the fuck",
    "wth": "what the hell",
    "omg": "oh my god",
    "omfg": "oh my fucking god",
    "fr": "for real",
    "frfr": "for real",
    "fomo": "fear of missing out",
    "yolo": "you only live once",
    "goat": "greatest of all time",
    "gg": "good game",
    "gl": "good luck",
    "hf": "have fun",
    "wp": "well played",
    "gn": "good night",
    "gm": "good morning",
    "ge": "good evening",
    "pls": "please",
    "plz": "please",
    "thx": "thank you",
    "ty": "thank you",
    "tysm": "thank you so much",
    "tyvm": "thank you very much",
    "sry": "sorry",
    "soz": "sorry",
    "mb": "my bad",
    "ily": "i love you",
    "ilu": "i love you",
    "ilysm": "i love you so much",
    "xoxo": "hugs and kisses",
    "bff": "best friend forever",
    "bffs": "best friends forever",
    "bday": "birthday",
    "hbd": "happy birthday",
    "gr8": "great",
    "ppl": "people",
    "prob": "probably",
    "tmr": "tomorrow",
    "tmrw": "tomorrow",
    "2day": "today",
    "2moro": "tomorrow",
    "2nite": "tonight",
    "b4": "before",
}

ONES = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
}
TEENS = {
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
}
TENS = {
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
}


def _match_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source and source[0].isupper():
        return replacement.capitalize()
    return replacement


def _match_phrase_case(source: str, replacement: str) -> str:
    if source and source[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _replace_slash(match: re.Match) -> str:
    left = match.group(1)
    right = match.group(2)
    if left.isdigit() and right.isdigit():
        return f"{left} over {right}"
    return f"{left} or {right}"


def _int_to_words(value: int) -> str:
    if value < 0:
        return f"minus {_int_to_words(abs(value))}"
    if value < 10:
        return ONES[value]
    if value < 20:
        return TEENS[value]
    if value < 100:
        tens = (value // 10) * 10
        rem = value % 10
        return TENS[tens] if rem == 0 else f"{TENS[tens]} {ONES[rem]}"
    if value < 1000:
        hundreds = value // 100
        rem = value % 100
        return (
            f"{ONES[hundreds]} hundred"
            if rem == 0
            else f"{ONES[hundreds]} hundred {_int_to_words(rem)}"
        )
    if value < 1_000_000:
        thousands = value // 1000
        rem = value % 1000
        return (
            f"{_int_to_words(thousands)} thousand"
            if rem == 0
            else f"{_int_to_words(thousands)} thousand {_int_to_words(rem)}"
        )
    if value < 1_000_000_000:
        millions = value // 1_000_000
        rem = value % 1_000_000
        return (
            f"{_int_to_words(millions)} million"
            if rem == 0
            else f"{_int_to_words(millions)} million {_int_to_words(rem)}"
        )
    billions = value // 1_000_000_000
    rem = value % 1_000_000_000
    return (
        f"{_int_to_words(billions)} billion"
        if rem == 0
        else f"{_int_to_words(billions)} billion {_int_to_words(rem)}"
    )


def _number_to_words(number_text: str) -> str:
    if "." in number_text:
        whole, frac = number_text.split(".", 1)
        whole_words = _int_to_words(int(whole)) if whole else "zero"
        frac_words = " ".join(ONES[int(ch)] for ch in frac if ch.isdigit())
        if not frac_words:
            return whole_words
        return f"{whole_words} point {frac_words}"
    return _int_to_words(int(number_text))


def _expand_numeric_unit(match: re.Match) -> str:
    number_text = match.group(1)
    unit_token = match.group(2).lower()
    singular, plural = UNIT_WORDS[unit_token]
    value = float(number_text)
    unit_word = singular if value == 1 else plural
    return f"{_number_to_words(number_text)} {unit_word}"


def _expand_version(match: re.Match) -> str:
    version = match.group(1)
    parts = version.split(".")
    return "version " + " point ".join(_number_to_words(part) for part in parts)


def _expand_dotted_acronym(match: re.Match) -> str:
    letters = re.findall(r"[A-Za-z]", match.group(0))
    return " ".join(letter.upper() for letter in letters)


def ensure_overrides_file(path: Path) -> None:
    if path.exists():
        return
    path.write_text(
        "# Optional custom pronunciation overrides\n"
        "# Format: text = replacement\n"
        "# Example:\n"
        "# TTS = tee tee ess\n"
        "# LLC = L L C\n"
        "# Russian = Rushan\n",
        encoding="utf-8",
    )


def load_overrides(path: Path) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if not path.exists():
        return overrides

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        src, dst = stripped.split("=", 1)
        src = src.strip()
        dst = dst.strip()
        if src and dst:
            overrides[src] = dst
    return overrides


def load_shortform_expansions(path: Path) -> dict[str, str]:
    merged = {key.lower(): value for key, value in SHORTFORM_EXPANSIONS.items()}
    if not path.exists():
        return merged

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return merged

    if not isinstance(payload, dict):
        return merged

    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        stripped_key = key.strip().lower()
        stripped_value = value.strip()
        if stripped_key and stripped_value:
            merged[stripped_key] = stripped_value
    return merged


def normalize_tts_text(
    text: str,
    overrides: dict[str, str],
    shortform_expansions: dict[str, str] | None = None,
) -> str:
    normalized = text.replace("\u2019", "'")
    normalized = normalized.replace("\u2018", "'")
    normalized = normalized.replace("\u02bc", "'")
    normalized = normalized.replace("\uff07", "'")
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    expansions = shortform_expansions or SHORTFORM_EXPANSIONS

    protected: list[str] = []

    def _protect(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"__PROTECTED_{len(protected) - 1}__"

    normalized = re.sub(r"https?://\S+", _protect, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b[A-Za-z]:[/\\]\S+", _protect, normalized)

    normalized = re.sub(
        r"\b([A-Za-z0-9]{1,20})\s*(?<!:)/(?!/)\s*([A-Za-z0-9]{1,20})\b",
        _replace_slash,
        normalized,
    )

    for pattern, replacement in SYMBOL_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized)

    normalized = DOTTED_ACRONYM_PATTERN.sub(_expand_dotted_acronym, normalized)
    normalized = VERSION_PATTERN.sub(_expand_version, normalized)
    normalized = NUMBER_UNIT_PATTERN.sub(_expand_numeric_unit, normalized)

    for token, spoken in expansions.items():
        pattern = re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
        normalized = pattern.sub(
            lambda m: _match_phrase_case(m.group(0), spoken),
            normalized,
        )

    for token, spoken in QUICK_ACRONYM_WORDS.items():
        pattern = re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
        normalized = pattern.sub(spoken, normalized)

    for phrase, replacement in PHRASE_REPLACEMENTS.items():
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        normalized = pattern.sub(
            lambda m: _match_case(m.group(0), replacement),
            normalized,
        )

    for phrase, replacement in MISSPELLED_CONTRACTIONS.items():
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        normalized = pattern.sub(
            lambda m: _match_case(m.group(0), replacement),
            normalized,
        )

    normalized = re.sub(
        rf"\b([A-Za-z]+){APOSTROPHE_PATTERN}m\b",
        lambda m: f"{m.group(1)} am",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        rf"\b([A-Za-z]+){APOSTROPHE_PATTERN}ve\b",
        lambda m: f"{m.group(1)} have",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        rf"\b([A-Za-z]+){APOSTROPHE_PATTERN}re\b",
        lambda m: f"{m.group(1)} are",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        rf"\b([A-Za-z]+){APOSTROPHE_PATTERN}ll\b",
        lambda m: f"{m.group(1)} will",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        rf"\b([A-Za-z]+){APOSTROPHE_PATTERN}d\b",
        lambda m: f"{m.group(1)} would",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        rf"\b([A-Za-z]+)n{APOSTROPHE_PATTERN}t\b",
        lambda m: f"{m.group(1)} not",
        normalized,
        flags=re.IGNORECASE,
    )

    normalized = STANDALONE_NUMBER_PATTERN.sub(
        lambda m: _number_to_words(m.group(1)),
        normalized,
    )

    for source, target in sorted(
        overrides.items(), key=lambda item: len(item[0]), reverse=True
    ):
        pattern = re.compile(rf"(?<!\w){re.escape(source)}(?!\w)", re.IGNORECASE)
        normalized = pattern.sub(
            lambda m: _match_case(m.group(0), target),
            normalized,
        )

    # Improve pronunciation for short uppercase acronyms (CPU -> C P U).
    normalized = re.sub(
        r"\b[A-Z]{2,5}\b",
        lambda m: " ".join(list(m.group(0))),
        normalized,
    )

    for i, value in enumerate(protected):
        normalized = normalized.replace(f"__PROTECTED_{i}__", value)

    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    if normalized and normalized[-1] not in ".!?":
        normalized = f"{normalized}."
    return normalized


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_profile_voice_data(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    voices_payload = payload.get("voices", payload)
    if not isinstance(voices_payload, dict):
        return {}

    profile_data: dict[str, dict[str, object]] = {}

    for voice_name, data in voices_payload.items():
        if not isinstance(data, dict):
            continue

        parsed_mix: list[tuple[str, float]] = []
        mix_entries = data.get("mix")
        if isinstance(mix_entries, list):
            for entry in mix_entries:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    continue
                base_name, weight = entry
                try:
                    parsed_mix.append((str(base_name), float(weight)))
                except (TypeError, ValueError):
                    continue

        lang = data.get("lang")
        parsed_lang = (
            str(lang).strip().lower()
            if isinstance(lang, str) and lang.strip()
            else None
        )

        profile_data[str(voice_name)] = {
            "mix": parsed_mix,
            "speed": _coerce_float(data.get("speed")),
            "lang": parsed_lang,
            "objective_score": _coerce_float(data.get("objective_score")),
            "vector_profile": bool(data.get("vector_profile")),
            "preferred": bool(data.get("preferred")),
            "vector_blend": _coerce_float(data.get("vector_blend")),
        }

    return profile_data


def load_profile_voice_mixes(
    path: Path,
) -> tuple[dict[str, list[tuple[str, float]]], dict[str, float]]:
    profile_data = load_profile_voice_data(path)
    mixes: dict[str, list[tuple[str, float]]] = {}
    speeds: dict[str, float] = {}

    for voice_name, data in profile_data.items():
        mix = data.get("mix")
        if isinstance(mix, list) and mix:
            mixes[voice_name] = mix

        speed = data.get("speed")
        if isinstance(speed, float):
            speeds[voice_name] = speed

    return mixes, speeds


def select_best_profile_voice(
    profile_data: dict[str, dict[str, object]],
    available_voice_names: list[str],
) -> str | None:
    available = set(available_voice_names)

    preferred = {
        voice_name
        for voice_name, data in profile_data.items()
        if voice_name in available and bool(data.get("preferred"))
    }
    for voice_name in JARVIS_PROFILE_PRIORITY:
        if voice_name in preferred:
            return voice_name
    if preferred:
        return sorted(preferred)[0]

    for voice_name in JARVIS_PROFILE_PRIORITY:
        if voice_name in available:
            return voice_name

    scored: list[tuple[float, str]] = []

    for voice_name, data in profile_data.items():
        if voice_name not in available:
            continue
        score = data.get("objective_score")
        if not isinstance(score, float) or score <= 0.0:
            continue
        scored.append((score, voice_name))

    if not scored:
        return None

    scored.sort(key=lambda entry: (entry[0], entry[1]))
    return scored[0][1]


def vector_blend_ratio(
    mix_vector: np.ndarray,
    profile_vector: np.ndarray,
    objective_score: float | None,
) -> float:
    ratio = 0.30
    if objective_score is not None:
        if objective_score <= 0.70:
            ratio = 0.65
        elif objective_score <= 1.00:
            ratio = 0.50
        elif objective_score <= 1.60:
            ratio = 0.40
        elif objective_score <= 2.20:
            ratio = 0.30
        else:
            ratio = 0.20

    mix_norm = float(np.linalg.norm(mix_vector)) + 1e-6
    profile_norm = float(np.linalg.norm(profile_vector))
    norm_ratio = profile_norm / mix_norm
    delta_ratio = float(np.linalg.norm(profile_vector - mix_vector)) / mix_norm

    if norm_ratio > 2.30 or delta_ratio > 1.70:
        ratio = min(ratio, 0.25)
    elif norm_ratio > 1.70 or delta_ratio > 1.20:
        ratio = min(ratio, 0.40)
    elif norm_ratio > 1.35 or delta_ratio > 0.90:
        ratio = min(ratio, 0.50)

    if objective_score is None and (norm_ratio > 2.80 or delta_ratio > 2.00):
        ratio = 0.0

    return float(np.clip(ratio, 0.0, 1.0))


def merge_profile_vectors(
    custom_voices: dict[str, np.ndarray],
    profile_vectors: dict[str, np.ndarray],
    profile_data: dict[str, dict[str, object]],
) -> tuple[dict[str, float], list[str]]:
    applied: dict[str, float] = {}
    fallbacks: list[str] = []

    for voice_name, profile_vector in profile_vectors.items():
        profile = profile_data.get(voice_name, {})
        objective_score = profile.get("objective_score")
        score = objective_score if isinstance(objective_score, float) else None
        explicit_blend = profile.get("vector_blend")
        configured_blend = explicit_blend if isinstance(explicit_blend, float) else None

        mix_vector = custom_voices.get(voice_name)
        if mix_vector is None:
            custom_voices[voice_name] = np.array(profile_vector, dtype=np.float32)
            applied[voice_name] = 1.0
            continue

        if configured_blend is not None:
            ratio = float(np.clip(configured_blend, 0.0, 1.0))
        else:
            ratio = vector_blend_ratio(
                np.array(mix_vector, dtype=np.float32),
                np.array(profile_vector, dtype=np.float32),
                score,
            )
        applied[voice_name] = ratio
        if ratio <= 0.0:
            fallbacks.append(voice_name)
            continue

        custom_voices[voice_name] = (
            (1.0 - ratio) * np.array(mix_vector, dtype=np.float32)
            + ratio * np.array(profile_vector, dtype=np.float32)
        ).astype(np.float32)

    return applied, fallbacks


def load_profile_voice_vectors(
    path: Path,
    expected_shape: tuple[int, ...],
) -> dict[str, np.ndarray]:
    vectors: dict[str, np.ndarray] = {}
    if not path.exists():
        return vectors

    try:
        with np.load(path) as payload:
            for voice_name in payload.files:
                array = np.array(payload[voice_name], dtype=np.float32)
                if tuple(array.shape) != expected_shape:
                    continue
                vectors[str(voice_name)] = array
    except Exception:
        return {}

    return vectors


def build_custom_voices(
    voice_bank: dict[str, np.ndarray],
    mix_map: dict[str, list[tuple[str, float]]] | None = None,
) -> dict[str, np.ndarray]:
    custom_voices: dict[str, np.ndarray] = {}
    if mix_map is None:
        mix_map = CUSTOM_VOICE_MIXES

    for custom_name, mix in mix_map.items():
        missing = [base_name for base_name, _ in mix if base_name not in voice_bank]
        if missing:
            continue
        base_shape = np.array(voice_bank[mix[0][0]]).shape
        merged = np.zeros(base_shape, dtype=np.float32)
        total_weight = 0.0
        for base_name, weight in mix:
            total_weight += float(weight)
            merged += np.array(voice_bank[base_name], dtype=np.float32) * float(weight)
        if total_weight > 0:
            merged /= total_weight
        custom_voices[custom_name] = merged
    return custom_voices


def print_settings(settings: dict) -> None:
    print(
        "Current settings:"
        f" voice={settings['voice']}"
        f", lang={settings['lang']}"
        f", preset={settings['preset']}"
        f", speed={settings['speed']:.2f}"
    )


def print_help() -> None:
    print("Commands:")
    print("  /preset balanced|natural|fast|calm|butler|clone")
    print("  /speed <0.50-2.00>      (lower = slower)")
    print("  /voice <voice_name>     (includes custom: jarvis, butler, jarvis_clone)")
    print("  /voices [filter]")
    print("  /lang <code>            (example: en-gb, en-us)")
    print("  /preview <text>         (show normalized speech text)")
    print("  /shortforms")
    print("  /shortforms reload")
    print("  /overrides")
    print("  /overrides reload")
    print("  /show")
    print("  /help")
    print("  //text                  (speak text that starts with /)")
    print("  exit")


def handle_command(
    text: str,
    settings: dict,
    voice_names: list[str],
    voice_speeds: dict[str, float],
    shortform_expansions: dict[str, str],
    shortforms_path: Path,
    overrides: dict[str, str],
    overrides_path: Path,
) -> bool:
    parts = text.split()
    cmd = parts[0].lower()

    if cmd == "/help":
        print_help()
        return True

    if cmd == "/show":
        print_settings(settings)
        return True

    if cmd == "/preset":
        if len(parts) != 2 or parts[1].lower() not in PRESETS:
            print("Usage: /preset balanced|natural|fast|calm|butler|clone")
            return True
        preset = parts[1].lower()
        settings["preset"] = preset
        settings["speed"] = PRESETS[preset]["speed"]
        print_settings(settings)
        return True

    if cmd == "/speed":
        if len(parts) != 2:
            print("Usage: /speed <0.50-2.00>")
            return True
        try:
            speed = float(parts[1])
        except ValueError:
            print("Speed must be a number, e.g. /speed 0.95")
            return True
        if speed < 0.50 or speed > 2.00:
            print("Speed must be between 0.50 and 2.00")
            return True
        settings["preset"] = "custom"
        settings["speed"] = speed
        print_settings(settings)
        return True

    if cmd == "/voice":
        if len(parts) != 2:
            print("Usage: /voice <voice_name>")
            return True
        voice = parts[1]
        if voice not in voice_names:
            print("Voice not found. Use /voices to list available names.")
            return True
        settings["voice"] = voice
        if voice in voice_speeds:
            settings["preset"] = "custom"
            settings["speed"] = voice_speeds[voice]
        print_settings(settings)
        return True

    if cmd == "/voices":
        filter_text = parts[1].lower() if len(parts) > 1 else ""
        filtered = [v for v in voice_names if filter_text in v.lower()]
        if not filtered:
            print("No matching voices.")
            return True
        print(", ".join(filtered))
        return True

    if cmd == "/lang":
        if len(parts) != 2:
            print("Usage: /lang <code>")
            return True
        settings["lang"] = parts[1].lower()
        print_settings(settings)
        return True

    if cmd == "/preview":
        preview_text = text[len("/preview") :].strip()
        if not preview_text:
            print("Usage: /preview <text>")
            return True
        print(
            normalize_tts_text(
                preview_text,
                overrides,
                shortform_expansions=shortform_expansions,
            )
        )
        return True

    if cmd == "/shortforms":
        if len(parts) == 2 and parts[1].lower() == "reload":
            shortform_expansions.clear()
            shortform_expansions.update(load_shortform_expansions(shortforms_path))
            print(
                f"Shortforms reloaded: {len(shortform_expansions)} entries "
                f"from {shortforms_path.name}"
            )
            return True
        print(
            f"Shortforms loaded: {len(shortform_expansions)} entries from "
            f"{shortforms_path.name}. Use '/shortforms reload' after editing the file."
        )
        return True

    if cmd == "/overrides":
        if len(parts) == 2 and parts[1].lower() == "reload":
            overrides.clear()
            overrides.update(load_overrides(overrides_path))
            print(
                f"Overrides reloaded: {len(overrides)} entries from {overrides_path.name}"
            )
            return True
        print(
            f"Overrides loaded: {len(overrides)} entries from {overrides_path.name}. "
            f"Use '/overrides reload' after editing the file."
        )
        return True

    print("Unknown command. Type /help for options.")
    return True


def main() -> int:
    import sys

    # Check for persistent mode flag
    persistent_mode = "--persistent" in sys.argv

    root = Path(__file__).resolve().parent
    model_path = root / "kokoro" / "kokoro-v1.0.onnx"
    voices_path = root / "kokoro" / "voices-v1.0.bin"
    output_wav = root / OUTPUT_WAV_NAME
    overrides_path = root / "pronunciation_overrides.txt"
    shortforms_path = root / SHORTFORM_EXPANSIONS_FILE
    profile_path = root / "kokoro" / CUSTOM_VOICE_PROFILE_FILE
    vector_profile_path = root / "kokoro" / CUSTOM_VOICE_VECTOR_FILE

    ensure_overrides_file(overrides_path)
    overrides = load_overrides(overrides_path)
    shortform_expansions = load_shortform_expansions(shortforms_path)

    missing = [path for path in (model_path, voices_path) if not path.exists()]
    if missing:
        print("Missing Kokoro model files:")
        for path in missing:
            print(f" - {path}")
        return 1

    try:
        kokoro = Kokoro(str(model_path), str(voices_path))
    except Exception as exc:
        print(f"Failed to initialize Kokoro: {exc}")
        return 1

    # Persistent mode: initialize once, then process stdin line by line
    if persistent_mode:
        # Pre-build voice data (same as interactive mode)
        native_voice_names = sorted(list(kokoro.voices.keys()))
        profile_data = load_profile_voice_data(profile_path)
        profile_mixes = {
            voice_name: mix
            for voice_name, data in profile_data.items()
            for mix in [data.get("mix")]
            if isinstance(mix, list) and mix
        }
        profile_speeds = {
            voice_name: speed
            for voice_name, data in profile_data.items()
            for speed in [data.get("speed")]
            if isinstance(speed, float)
        }
        all_mix_map = {**CUSTOM_VOICE_MIXES, **profile_mixes}
        custom_voices = build_custom_voices(kokoro.voices, all_mix_map)
        first_native = np.array(kokoro.voices[native_voice_names[0]], dtype=np.float32)
        profile_vectors = load_profile_voice_vectors(
            vector_profile_path, tuple(first_native.shape)
        )
        vector_blends, vector_fallbacks = merge_profile_vectors(
            custom_voices,
            profile_vectors,
            profile_data,
        )
        voice_names = sorted(list(custom_voices.keys())) + native_voice_names
        voice_speeds = {**profile_speeds}
        best_profile_voice = select_best_profile_voice(profile_data, voice_names)
        default_voice = best_profile_voice or (
            DEFAULT_VOICE if DEFAULT_VOICE in voice_names else voice_names[0]
        )
        default_lang = DEFAULT_LANG
        selected_profile = profile_data.get(default_voice)
        if selected_profile is not None:
            lang = selected_profile.get("lang")
            if isinstance(lang, str) and lang:
                default_lang = lang

        settings = {
            "voice": default_voice,
            "lang": default_lang,
            "preset": "clone",
            "speed": PRESETS["clone"]["speed"],
        }
        if default_voice in voice_speeds:
            settings["preset"] = "custom"
            settings["speed"] = voice_speeds[default_voice]

        # Signal ready
        print("READY", flush=True)

        # Process lines from stdin
        for line in sys.stdin:
            text = line.strip()
            if not text:
                print("OK", flush=True)
                continue
            if text.lower() in {"exit", "quit"}:
                print("OK", flush=True)
                break

            if text.startswith("/ping "):
                token = text[len("/ping ") :].strip()
                print(f"JARVIS_TTS_DONE {token}", flush=True)
                continue

            speak_text = normalize_tts_text(
                text,
                overrides,
                shortform_expansions=shortform_expansions,
            )
            try:
                selected_voice = custom_voices.get(settings["voice"], settings["voice"])
                audio, sample_rate = kokoro.create(
                    speak_text,
                    voice=selected_voice,
                    speed=settings["speed"],
                    lang=settings["lang"],
                )
                sf.write(str(output_wav), audio, sample_rate, subtype="PCM_16")
                if winsound is not None:
                    winsound.PlaySound(str(output_wav), winsound.SND_FILENAME)  # type: ignore
                elif sys.platform.startswith("linux"):
                    # Use desktop audio routing for reliable playback on Linux
                    # Try PulseAudio/Pipewire native players first, then general purpose mpv/aplay
                    played = False
                    players = ["pw-play", "paplay", "mpv", "aplay"]
                    for player in players:
                        if shutil.which(player):
                            cmd = [player, str(output_wav)]
                            if player == "mpv":
                                cmd = [
                                    "mpv",
                                    "--no-terminal",
                                    "--no-video",
                                    str(output_wav),
                                ]
                            elif player == "aplay":
                                cmd = ["aplay", "-q", str(output_wav)]

                            try:
                                # debug
                                # print(f"DEBUG: Trying player {player} with cmd {cmd}", file=sys.stderr, flush=True)
                                subprocess.run(cmd, check=True, capture_output=True)
                                played = True
                                break
                            except Exception:
                                # print(f"DEBUG: Player {player} failed: {e}", file=sys.stderr, flush=True)
                                continue

                    if not played:
                        print(
                            f"Synthesis failed: No Linux audio player found among {players} or all failed",
                            flush=True,
                        )
                else:
                    import sounddevice as sd

                    device_str = os.getenv("JARVIS_TTS_OUTPUT_DEVICE", "default")
                    device_id = None if device_str == "default" else device_str
                    try:
                        if device_id and device_id.isdigit():
                            device_id = int(device_id)
                        sd.play(audio, samplerate=sample_rate, device=device_id)
                    except Exception as e:
                        print(f"Device error: {e}", file=sys.stderr)
                        sd.play(audio, samplerate=sample_rate)
                    sd.wait()
                print("OK", flush=True)
            except Exception as exc:
                print(f"Synthesis failed: {exc}", flush=True)

        return 0

    native_voice_names = sorted(list(kokoro.voices.keys()))
    profile_data = load_profile_voice_data(profile_path)
    profile_mixes = {
        voice_name: mix
        for voice_name, data in profile_data.items()
        for mix in [data.get("mix")]
        if isinstance(mix, list) and mix
    }
    profile_speeds = {
        voice_name: speed
        for voice_name, data in profile_data.items()
        for speed in [data.get("speed")]
        if isinstance(speed, float)
    }
    all_mix_map = {**CUSTOM_VOICE_MIXES, **profile_mixes}
    custom_voices = build_custom_voices(kokoro.voices, all_mix_map)
    first_native = np.array(kokoro.voices[native_voice_names[0]], dtype=np.float32)
    profile_vectors = load_profile_voice_vectors(
        vector_profile_path, tuple(first_native.shape)
    )
    vector_blends, vector_fallbacks = merge_profile_vectors(
        custom_voices,
        profile_vectors,
        profile_data,
    )
    voice_names = sorted(list(custom_voices.keys())) + native_voice_names
    voice_speeds = {**profile_speeds}
    best_profile_voice = select_best_profile_voice(profile_data, voice_names)
    default_voice = best_profile_voice or (
        DEFAULT_VOICE if DEFAULT_VOICE in voice_names else voice_names[0]
    )
    default_lang = DEFAULT_LANG
    selected_profile = profile_data.get(default_voice)
    if selected_profile is not None:
        lang = selected_profile.get("lang")
        if isinstance(lang, str) and lang:
            default_lang = lang

    settings = {
        "voice": default_voice,
        "lang": default_lang,
        "preset": "clone",
        "speed": PRESETS["clone"]["speed"],
    }
    if default_voice in voice_speeds:
        settings["preset"] = "custom"
        settings["speed"] = voice_speeds[default_voice]

    print("Kokoro voice is ready.")
    print("Type text and press Enter. Type /help for controls. Type 'exit' to quit.")
    if overrides:
        print(f"Loaded {len(overrides)} pronunciation override(s).")
    print(f"Loaded {len(shortform_expansions)} shortform expansion(s).")
    if profile_mixes:
        print(
            f"Loaded {len(profile_mixes)} fitted voice profile(s) from {profile_path.name}."
        )
    if profile_vectors:
        print(
            f"Loaded {len(profile_vectors)} fitted voice vector(s) from {vector_profile_path.name}."
        )
    if best_profile_voice:
        score = profile_data.get(best_profile_voice, {}).get("objective_score")
        if isinstance(score, float):
            print(
                f"Auto-selected best fitted voice: {best_profile_voice} "
                f"(objective score {score:.4f}, lower is better)."
            )
    if vector_blends:
        fallback_count = len(vector_fallbacks)
        blended_count = sum(1 for ratio in vector_blends.values() if 0.0 < ratio < 1.0)
        print(
            f"Applied vector safety blend to {blended_count} profile(s); "
            f"{fallback_count} used mix-only fallback."
        )
    print_settings(settings)

    while True:
        try:
            text = input("Jarvis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break
        if text.startswith("//"):
            text = text[1:]
        elif text.startswith("/"):
            handle_command(
                text,
                settings,
                voice_names,
                voice_speeds,
                shortform_expansions,
                shortforms_path,
                overrides,
                overrides_path,
            )
            continue

        speak_text = normalize_tts_text(
            text,
            overrides,
            shortform_expansions=shortform_expansions,
        )
        try:
            selected_voice = custom_voices.get(settings["voice"], settings["voice"])
            audio, sample_rate = kokoro.create(
                speak_text,
                voice=selected_voice,
                speed=settings["speed"],
                lang=settings["lang"],
            )
            sf.write(str(output_wav), audio, sample_rate, subtype="PCM_16")
            if winsound is not None:
                winsound.PlaySound(str(output_wav), winsound.SND_FILENAME)  # type: ignore
            else:
                import sounddevice as sd

                sd.play(audio, samplerate=sample_rate)
                sd.wait()
        except Exception as exc:
            print(f"Synthesis failed: {exc}")
            continue

    return 0


if __name__ == "__main__":
    sys.exit(main())
