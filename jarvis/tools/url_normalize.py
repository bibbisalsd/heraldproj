from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

_EXPLICIT_URL_PATTERN = re.compile(
    r"(?i)(?<!@)\b((?:https?://|www\.)[^\s<>'\"]+|(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?:/[^\s<>'\"]*)?)"
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_TRAILING_PUNCTUATION = ".,!?;:)]}\"'"
_DOMAIN_JOINERS = {"dot"}
_PATH_JOINERS = {"slash"}
_INLINE_JOINERS = {"dash": "-", "hyphen": "-", "minus": "-", "underscore": "_"}
_SCHEMES = {"http", "https"}
_DOMAIN_LABEL_ALIASES = {
    # Common STT confusion when someone says "Vercel dot app".
    "versal": "vercel",
    "versel": "vercel",
    "vesel": "vercel",
    "vessel": "vercel",
}
_PATH_STOP_WORDS = {
    "at",
    "check",
    "fetch",
    "inspect",
    "jarvis",
    "please",
    "look",
    "thanks",
    "thank",
    "now",
    "open",
    "read",
    "review",
    "see",
    "summarize",
    "today",
    "tonight",
    "tomorrow",
    "again",
    "later",
    "visit",
}
_DOMAIN_LEADING_STOP_WORDS = {
    "page",
    "pages",
    "site",
    "sites",
    "the",
    "url",
    "urls",
    "web",
    "webpage",
    "webpages",
    "website",
    "websites",
}


def normalize(url: str) -> str:
    raw = str(url or "").strip().rstrip(_TRAILING_PUNCTUATION)
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or ""
    query = parsed.query or ""
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_candidate(text: str) -> str | None:
    candidates = extract_candidates(text)
    if not candidates:
        return None
    return candidates[0]


def extract_candidates(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for match in _EXPLICIT_URL_PATTERN.finditer(str(text or "")):
        candidate = normalize(match.group(1).strip().rstrip(_TRAILING_PUNCTUATION))
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
        for variant in _common_stt_variants(candidate, include_fuzzy_duplicate=False):
            if variant and variant not in seen:
                seen.add(variant)
                ordered.append(variant)

    for candidate in _spoken_url_candidates(text):
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
        for variant in _common_stt_variants(candidate):
            if variant and variant not in seen:
                seen.add(variant)
                ordered.append(variant)

    return ordered


def _spoken_url_candidates(text: str) -> list[str]:
    tokens = _spoken_tokens(text)
    candidates: list[str] = []
    index = 0
    while index < len(tokens):
        start = index
        parsed = _consume_spoken_candidate(tokens, start)
        if parsed is None:
            index += 1
            continue
        consumed, candidate = parsed
        if consumed <= 0:
            index += 1
            continue
        candidates.append(candidate)
        index += consumed
    return candidates


def _spoken_tokens(text: str) -> list[str]:
    raw_tokens = [token.lower() for token in _TOKEN_PATTERN.findall(str(text or ""))]
    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        next_token = raw_tokens[index + 1] if index + 1 < len(raw_tokens) else ""
        if token == "period":
            tokens.append("dot")
            index += 1
            continue
        if token == "forward" and next_token == "slash":
            tokens.append("slash")
            index += 2
            continue
        if token == "under" and next_token == "score":
            tokens.append("underscore")
            index += 2
            continue
        if token == "double" and next_token:
            doubled = _double_spoken_fragment(next_token)
            if doubled:
                tokens.append(f"@{doubled}")
                index += 2
                continue
        if len(token) == 1 and token.isalnum():
            tokens.append(f"@{token}")
            index += 1
            continue
        tokens.append(token)
        index += 1
    return tokens


def _double_spoken_fragment(token: str) -> str:
    cleaned = str(token or "").strip().lower()
    if cleaned in {"u", "you"}:
        return "w"
    if len(cleaned) == 1 and cleaned.isalnum():
        return cleaned * 2
    return ""


def _consume_spoken_candidate(tokens: list[str], start: int) -> tuple[int, str] | None:
    scheme = ""
    index = start
    if (
        index + 3 < len(tokens)
        and tokens[index] in _SCHEMES
        and tokens[index + 1] == "colon"
        and tokens[index + 2] == "slash"
        and tokens[index + 3] == "slash"
    ):
        scheme = f"{tokens[index]}://"
        index += 4

    domain, index = _consume_domain(tokens, index)
    if not domain:
        return None

    path = ""
    while index < len(tokens) and tokens[index] in _PATH_JOINERS:
        segment, next_index = _consume_path_segment(tokens, index + 1)
        if not segment:
            break
        path += f"/{segment}"
        index = next_index

    candidate = normalize(f"{scheme}{domain}{path}")
    if not candidate:
        return None
    consumed = index - start
    return consumed, candidate


def _consume_domain(tokens: list[str], start: int) -> tuple[str, int]:
    index = start
    labels: list[str] = []
    while index < len(tokens):
        label, next_index = _consume_domain_label(tokens, index)
        if not label:
            break
        labels.append(label)
        index = next_index
        if index >= len(tokens) or tokens[index] not in _DOMAIN_JOINERS:
            break
        index += 1

    domain = ".".join(labels)
    if not _looks_like_domain(domain):
        return "", start
    return domain, index


def _consume_domain_label(tokens: list[str], start: int) -> tuple[str, int]:
    index = start
    parts: list[str] = []
    allow_plain = True
    while index < len(tokens):
        token = tokens[index]
        if token in _DOMAIN_JOINERS | _PATH_JOINERS:
            break
        if token in _PATH_STOP_WORDS:
            break
        if token in _DOMAIN_LEADING_STOP_WORDS and not parts:
            break
        repeat_instruction = _consume_repeat_letter_instruction(tokens, index)
        if repeat_instruction and parts:
            letter, total_count, next_index = repeat_instruction
            label_so_far = "".join(parts).strip("-")
            if not label_so_far:
                break
            parts = [
                _apply_repeat_letter_instruction(label_so_far, letter, total_count)
            ]
            allow_plain = False
            index = next_index
            continue
        if token in _INLINE_JOINERS:
            if not parts or allow_plain:
                return "", start
            parts.append(_INLINE_JOINERS[token])
            allow_plain = True
            index += 1
            continue
        fragment, is_spelled = _decode_fragment(token)
        if not fragment:
            break
        if not is_spelled and not allow_plain:
            break
        parts.append(fragment)
        allow_plain = False
        index += 1
    label = "".join(parts).strip("-")
    if not label or "--" in label:
        return "", start
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label):
        return "", start
    return label, index


def _consume_path_segment(tokens: list[str], start: int) -> tuple[str, int]:
    index = start
    parts: list[str] = []
    allow_plain = True
    while index < len(tokens):
        token = tokens[index]
        if token in _PATH_JOINERS:
            break
        if token in _PATH_STOP_WORDS:
            break
        if token == "dot":
            if not parts or allow_plain:
                break
            parts.append(".")
            allow_plain = True
            index += 1
            continue
        if token in _INLINE_JOINERS:
            if not parts or allow_plain:
                break
            parts.append(_INLINE_JOINERS[token])
            allow_plain = True
            index += 1
            continue
        fragment, is_spelled = _decode_fragment(token)
        if not fragment:
            break
        if not is_spelled and not allow_plain:
            break
        parts.append(fragment)
        allow_plain = False
        index += 1
    segment = "".join(parts).strip("-_.")
    return segment, index


def _decode_fragment(token: str) -> tuple[str, bool]:
    raw = str(token or "").strip().lower()
    if not raw:
        return "", False
    if raw.startswith("@") and re.fullmatch(r"[a-z0-9]+", raw[1:]):
        return raw[1:], True
    if re.fullmatch(r"[a-z0-9]+", raw):
        return raw, False
    return "", False


def _consume_repeat_letter_instruction(
    tokens: list[str], start: int
) -> tuple[str, int, int] | None:
    if start >= len(tokens) or tokens[start] != "with":
        return None
    if start + 1 >= len(tokens):
        return None

    count_token = _plain_token(tokens[start + 1])
    if (
        len(count_token) == 2
        and count_token[0] == count_token[1]
        and count_token[0].isalnum()
    ):
        return count_token[0], len(count_token), start + 2
    if count_token == "double" and start + 2 < len(tokens):
        letter = _letter_from_token(tokens[start + 2])
        if letter:
            return letter, 2, start + 3
    if count_token not in {"2", "two"} or start + 2 >= len(tokens):
        return None

    letter_token = _plain_token(tokens[start + 2])
    letter = _letter_from_plural_token(letter_token) or _letter_from_token(
        tokens[start + 2]
    )
    if not letter:
        return None

    next_index = start + 3
    if next_index < len(tokens) and _plain_token(tokens[next_index]) == "s":
        next_index += 1
    return letter, 2, next_index


def _plain_token(token: str) -> str:
    raw = str(token or "").strip().lower()
    if raw.startswith("@"):
        return raw[1:]
    return raw


def _letter_from_token(token: str) -> str:
    plain = _plain_token(token)
    if len(plain) == 1 and plain.isalnum():
        return plain
    return ""


def _letter_from_plural_token(token: str) -> str:
    plain = _plain_token(token)
    if len(plain) == 2 and plain.endswith("s") and plain[0].isalnum():
        return plain[0]
    return ""


def _apply_repeat_letter_instruction(label: str, letter: str, total_count: int) -> str:
    cleaned = str(label or "").strip("-").lower()
    repeat = str(letter or "").strip().lower()[:1]
    if not cleaned or not repeat or total_count <= 0:
        return cleaned
    trailing_count = len(cleaned) - len(cleaned.rstrip(repeat))
    if trailing_count >= total_count:
        return cleaned
    return cleaned + (repeat * (total_count - trailing_count))


def _collapse_embedded_repeat_instruction(label: str) -> str:
    raw = str(label or "").strip().lower()
    match = re.fullmatch(r"([a-z0-9-]+?)with(?:two|2)([a-z])s?", raw)
    if not match:
        return ""
    return _apply_repeat_letter_instruction(match.group(1), match.group(2), 2)


def _looks_like_domain(domain: str) -> bool:
    parts = [part for part in str(domain or "").split(".") if part]
    if len(parts) < 2:
        return False
    tld = parts[-1]
    if not re.fullmatch(r"[a-z]{2,24}", tld):
        return False
    return all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in parts
    )


def _common_stt_variants(
    candidate: str, *, include_fuzzy_duplicate: bool = True
) -> list[str]:
    parsed = urlparse(str(candidate or ""))
    labels = [label for label in (parsed.netloc or "").split(".") if label]
    if len(labels) < 2:
        return []

    variants: list[str] = []
    seen_label_sets: set[tuple[str, ...]] = {tuple(labels)}

    def add_labels(alternate_labels: list[str]) -> bool:
        key = tuple(alternate_labels)
        if key in seen_label_sets:
            return False
        seen_label_sets.add(key)
        alternate = _url_from_labels(parsed, alternate_labels)
        if alternate and alternate != candidate and alternate not in variants:
            variants.append(alternate)
            return True
        return False

    preferred_label_sets: list[list[str]] = [labels]
    for index, label in enumerate(labels[:-1]):
        sources = list(preferred_label_sets)
        for source_labels in sources:
            source_label = source_labels[index]
            for alternate_label in _preferred_domain_label_variants(source_label):
                alternate_labels = list(source_labels)
                alternate_labels[index] = alternate_label
                if add_labels(alternate_labels):
                    preferred_label_sets.append(alternate_labels)

    if include_fuzzy_duplicate:
        for source_labels in list(preferred_label_sets):
            for index, label in enumerate(source_labels[:-1]):
                alternate_label = _drop_trailing_duplicate_label(label)
                if not alternate_label:
                    continue
                alternate_labels = list(source_labels)
                alternate_labels[index] = alternate_label
                add_labels(alternate_labels)
    return variants


def _preferred_domain_label_variants(label: str) -> list[str]:
    variants: list[str] = []
    collapsed = _collapse_embedded_repeat_instruction(label)
    if collapsed and collapsed != label:
        variants.append(collapsed)
    alias = _DOMAIN_LABEL_ALIASES.get(str(label or "").lower(), "")
    if alias and alias != label and alias not in variants:
        variants.append(alias)
    return variants


def _drop_trailing_duplicate_label(label: str) -> str:
    raw = str(label or "").strip().lower()
    if len(raw) < 4 or raw[-1] != raw[-2]:
        return ""
    return raw[:-1]


def _url_from_labels(parsed: object, labels: list[str]) -> str:
    return normalize(
        urlunparse(
            (
                getattr(parsed, "scheme", "") or "https",
                ".".join(labels),
                getattr(parsed, "path", "") or "",
                "",
                getattr(parsed, "query", "") or "",
                "",
            )
        )
    )
