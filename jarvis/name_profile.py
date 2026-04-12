from __future__ import annotations

from dataclasses import dataclass
import re


WAKE_ALIASES = {
    "jarvis",
    "javis",
    "jervis",
    "jovis",
    "javas",
    "jarviss",
    "java",
    "jabba",
    "jabbas",
}
NAME_BLOCKLIST = {
    "assistant",
    "afraid",
    "busy",
    "cancel",
    "clock",
    "confirm",
    "creator",
    "date",
    "day",
    "fine",
    "glad",
    "gonna",
    "good",
    "great",
    "hello",
    "help",
    "hey",
    "hi",
    "memory",
    "online",
    "okay",
    "ok",
    "ready",
    "sleep",
    "sorry",
    "status",
    "time",
    "today",
    "tomorrow",
    "unknown",
    "very",
    "well",
    "wipe",
    "yes",
    "no",
}
NAME_TERMINATORS = {
    *WAKE_ALIASES,
    "again",
    "am",
    "and",
    "because",
    "but",
    "creator",
    "for",
    "from",
    "here",
    "i",
    "im",
    "i'm",
    "main",
    "okay",
    "please",
    "right",
    "speaking",
    "thanks",
    "thank",
    "today",
    "tomorrow",
    "tonight",
    "your",
}
NAME_CONNECTORS = {
    "de",
    "del",
    "da",
    "di",
    "du",
    "la",
    "le",
    "van",
    "von",
    "bin",
    "al",
    "st",
    "saint",
}
INTRO_PATTERNS = (
    r"\bmy name is\s+(.+)$",
    r"\b(?:i am|i'm|im|this is|it is|it's)\s+(.+)$",
)
TITLE_ALIASES = {
    "sir": "sir",
    "madam": "madam",
    "maam": "madam",
    "ma'am": "madam",
}

COMMON_MALE_NAMES = {
    "aaron",
    "adam",
    "adrian",
    "alan",
    "alexander",
    "andrew",
    "anthony",
    "ben",
    "benjamin",
    "blake",
    "bradley",
    "brian",
    "callum",
    "cameron",
    "charles",
    "christopher",
    "connor",
    "daniel",
    "david",
    "declan",
    "dominic",
    "edward",
    "elliot",
    "ethan",
    "finley",
    "francis",
    "gabriel",
    "george",
    "harry",
    "henry",
    "jack",
    "jacob",
    "james",
    "jamie",
    "jason",
    "john",
    "jordan",
    "joseph",
    "joshua",
    "liam",
    "logan",
    "louis",
    "lucas",
    "mason",
    "matthew",
    "max",
    "michael",
    "nathan",
    "nicholas",
    "noah",
    "oliver",
    "oscar",
    "owen",
    "patrick",
    "peter",
    "ryan",
    "samuel",
    "scott",
    "sebastian",
    "thomas",
    "timothy",
    "william",
}
COMMON_FEMALE_NAMES = {
    "abigail",
    "alice",
    "amelia",
    "amy",
    "anna",
    "aria",
    "ava",
    "bella",
    "beth",
    "brooke",
    "charlotte",
    "chloe",
    "claire",
    "danielle",
    "ella",
    "ellie",
    "emily",
    "emma",
    "eva",
    "eve",
    "faith",
    "florence",
    "freya",
    "georgia",
    "grace",
    "hannah",
    "harper",
    "hazel",
    "holly",
    "isabella",
    "isla",
    "ivy",
    "jasmine",
    "jessica",
    "kate",
    "katie",
    "laura",
    "lily",
    "lucy",
    "madeline",
    "madison",
    "mary",
    "mia",
    "natalie",
    "olivia",
    "phoebe",
    "poppy",
    "rachel",
    "ruby",
    "sarah",
    "scarlett",
    "sophia",
    "sophie",
    "stella",
    "victoria",
    "violet",
    "zoe",
}
COMMON_UNISEX_NAMES = {
    "alex",
    "avery",
    "bailey",
    "billie",
    "blair",
    "casey",
    "charlie",
    "dakota",
    "drew",
    "elliot",
    "emerson",
    "finley",
    "frankie",
    "harley",
    "hayden",
    "jamie",
    "jessie",
    "jordan",
    "kai",
    "logan",
    "morgan",
    "parker",
    "quinn",
    "reese",
    "riley",
    "river",
    "robin",
    "rowan",
    "sage",
    "sam",
    "skyler",
    "taylor",
}


@dataclass(frozen=True)
class NameProfile:
    full_name: str
    given_name: str
    gender_class: str

    @property
    def preferred_title(self) -> str | None:
        if self.gender_class == "male":
            return "sir"
        if self.gender_class == "female":
            return "madam"
        return None

    @property
    def needs_title_confirmation(self) -> bool:
        return self.gender_class in {"unisex", "unknown"}


def normalize_title_preference(text: str) -> str | None:
    normalized = re.sub(r"[^a-z']", "", str(text or "").strip().lower())
    return TITLE_ALIASES.get(normalized)


def first_name(name: str) -> str:
    parts = [part for part in re.split(r"\s+", str(name or "").strip()) if part]
    return parts[0] if parts else ""


def extract_name_candidate(text: str) -> str | None:
    original = str(text or "").replace("’", "'").strip()
    if not original:
        return None

    for pattern in INTRO_PATTERNS:
        match = re.search(pattern, original, flags=re.IGNORECASE)
        if not match:
            continue
        raw_candidate = match.group(1)
        candidate = _clean_candidate(raw_candidate)
        if not candidate:
            continue
        if pattern.startswith(r"\bmy name is"):
            return candidate
        profile = build_name_profile(candidate)
        fragments = re.findall(
            r"[A-Za-z][A-Za-z'\-]{0,39}", raw_candidate.replace("â€™", "'")
        )
        first_is_capitalized = bool(fragments and fragments[0][:1].isupper())
        trailing_hint = (
            raw_candidate.lower()
            .strip()
            .startswith(("your creator", "creator", "speaking", "here", "again"))
        )
        if profile is not None and (
            profile.gender_class != "unknown" or first_is_capitalized or trailing_hint
        ):
            return candidate
    return None


def extract_bare_name_candidate(text: str) -> str | None:
    original = str(text or "").replace("’", "'").strip()
    if not re.fullmatch(
        r"[A-Za-z][A-Za-z'\-]{1,39}(?:\s+[A-Za-z][A-Za-z'\-]{1,39}){0,2}", original
    ):
        return None
    return _clean_candidate(original)


def build_name_profile(name: str) -> NameProfile | None:
    cleaned = _clean_candidate(name)
    if not cleaned:
        return None
    given = first_name(cleaned)
    return NameProfile(
        full_name=cleaned,
        given_name=given,
        gender_class=infer_gender_class(given),
    )


def infer_gender_class(name: str) -> str:
    token = first_name(name).lower()
    if not token:
        return "unknown"
    if token in COMMON_UNISEX_NAMES:
        return "unisex"
    if token in COMMON_MALE_NAMES and token not in COMMON_FEMALE_NAMES:
        return "male"
    if token in COMMON_FEMALE_NAMES and token not in COMMON_MALE_NAMES:
        return "female"
    if token in COMMON_MALE_NAMES and token in COMMON_FEMALE_NAMES:
        return "unisex"

    if len(token) <= 2:
        return "unknown"

    female_suffixes = ("ella", "etta", "ina", "lyn", "lynn", "a", "ia")
    male_suffixes = ("son", "ton", "dan", "ian", "er", "o")

    if token.endswith(female_suffixes) and not token.endswith(("sa", "ta")):
        return "female"
    if token.endswith(male_suffixes):
        return "male"
    return "unknown"


def _clean_candidate(candidate: str) -> str | None:
    pieces = re.findall(r"[A-Za-z][A-Za-z'\-]{0,39}", candidate.replace("’", "'"))
    if not pieces:
        return None

    kept: list[str] = []
    for piece in pieces:
        lowered = piece.lower()
        if not kept and lowered in NAME_BLOCKLIST:
            return None
        if kept and lowered in NAME_TERMINATORS:
            break
        if lowered in NAME_BLOCKLIST and lowered not in NAME_CONNECTORS:
            break
        kept.append(piece)
        if len(kept) >= 3:
            break

    if not kept:
        return None

    if kept[0].lower() in NAME_BLOCKLIST | WAKE_ALIASES:
        return None

    cleaned = " ".join(_smart_title(part) for part in kept if part)
    return cleaned.strip() or None


def _smart_title(part: str) -> str:
    def _title_fragment(fragment: str) -> str:
        return fragment[:1].upper() + fragment[1:].lower()

    apostrophe_parts = [_title_fragment(fragment) for fragment in part.split("'")]
    combined = "'".join(apostrophe_parts)
    hyphen_parts = [_title_fragment(fragment) for fragment in combined.split("-")]
    return "-".join(hyphen_parts)
