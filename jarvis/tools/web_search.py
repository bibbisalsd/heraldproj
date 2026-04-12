from __future__ import annotations

import re
from base64 import b64decode
from html import unescape
from urllib.parse import parse_qs, quote_plus, urlparse

from jarvis.brain_core.network_guard import NetworkGuard

from .web_fetch_http import fetch

_SEARCH_ENDPOINT = "https://www.bing.com/search?q={query}"
_DDG_RESULT_PATTERN = re.compile(
    r'<a[^>]+class="[^"]*\bresult__a\b[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_DDG_SNIPPET_PATTERN = re.compile(
    r'<(?:a|div)[^>]+class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
    re.IGNORECASE | re.DOTALL,
)
_BING_RESULT_PATTERN = re.compile(
    r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"[^>]*>.*?<h2[^>]*>\s*<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>\s*</h2>(?P<body>.*?)</li>',
    re.IGNORECASE | re.DOTALL,
)
_BING_SNIPPET_PATTERN = re.compile(
    r"<p[^>]*>(?P<snippet>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)


def search(query: str, *, max_results: int = 5) -> dict:
    normalized = " ".join(query.split())
    if not normalized:
        return {"ok": False, "reason": "empty_query", "query": query, "results": []}

    source_url = _SEARCH_ENDPOINT.format(query=quote_plus(normalized))
    fetched = fetch(source_url, max_bytes=350_000)
    if not fetched.get("ok"):
        return {
            "ok": False,
            "reason": str(fetched.get("reason", "search_fetch_failed")),
            "query": normalized,
            "results": [],
            "engine": "bing_html",
            "source_url": source_url,
        }

    html = str(fetched.get("html", "") or fetched.get("text", ""))
    results = _parse_results(html, max_results=max_results)
    return {
        "ok": True,
        "reason": "OK",
        "query": normalized,
        "results": results,
        "engine": "bing_html",
        "source_url": source_url,
    }


def _parse_results(html: str, *, max_results: int) -> list[dict]:
    parsed = _parse_bing_results(html, max_results=max_results)
    if parsed:
        return parsed
    return _parse_duckduckgo_results(html, max_results=max_results)


def _parse_bing_results(html: str, *, max_results: int) -> list[dict]:
    parsed: list[dict] = []
    for match in _BING_RESULT_PATTERN.finditer(html):
        url = _normalize_result_url(match.group("href"))
        if not url:
            continue

        ok, _ = NetworkGuard().validate_url(url)
        if not ok:
            continue

        title = _strip_html(match.group("title"))
        snippet_match = _BING_SNIPPET_PATTERN.search(match.group("body"))
        snippet = _strip_html(snippet_match.group("snippet")) if snippet_match else ""
        parsed.append(
            {
                "rank": len(parsed) + 1,
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )
        if len(parsed) >= max_results:
            break
    return parsed


def _parse_duckduckgo_results(html: str, *, max_results: int) -> list[dict]:
    parsed: list[dict] = []
    for match in _DDG_RESULT_PATTERN.finditer(html):
        url = _normalize_result_url(match.group("href"))
        if not url:
            continue

        ok, _ = NetworkGuard().validate_url(url)
        if not ok:
            continue

        title = _strip_html(match.group("title"))
        snippet_match = _DDG_SNIPPET_PATTERN.search(
            html[match.end() : match.end() + 2000]
        )
        snippet = _strip_html(snippet_match.group("snippet")) if snippet_match else ""
        parsed.append(
            {
                "rank": len(parsed) + 1,
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )
        if len(parsed) >= max_results:
            break
    return parsed


def _normalize_result_url(raw_href: str) -> str | None:
    href = unescape(raw_href).strip()
    if not href:
        return None
    parsed = urlparse(href)
    if (parsed.hostname or "").lower().endswith("bing.com") and parsed.path.startswith(
        "/ck/a"
    ):
        params = parse_qs(parsed.query)
        encoded = params.get("u", [])
        if encoded:
            decoded = _decode_bing_target(encoded[0])
            if decoded:
                return decoded
    if parsed.scheme in {"http", "https"}:
        return href
    params = parse_qs(parsed.query)
    uddg = params.get("uddg", [])
    if uddg:
        return unescape(uddg[0]).strip() or None
    return None


def _decode_bing_target(value: str) -> str | None:
    token = value.strip()
    if token.startswith("a1"):
        token = token[2:]
    padding = "=" * ((4 - (len(token) % 4)) % 4)
    try:
        decoded = b64decode(token + padding).decode("utf-8", errors="replace").strip()
    except Exception:
        return None
    if decoded.startswith(("http://", "https://")):
        return decoded
    return None


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()
