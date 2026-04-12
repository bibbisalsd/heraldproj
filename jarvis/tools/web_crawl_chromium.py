from __future__ import annotations

import re
import threading
from collections import deque
from html import unescape
from urllib.parse import urljoin, urlparse

from jarvis.brain_core.network_guard import NetworkGuard

from .web_extract_main_text import extract_main_text
from .web_fetch_http import fetch

_HREF_PATTERN = re.compile(r'href=["\'](?P<href>[^"\']+)["\']', re.IGNORECASE)
_TITLE_PATTERN = re.compile(
    r"<title[^>]*>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL
)


def crawl(
    seed_url: str, max_pages: int = 20, max_depth: int = 2, max_total_seconds: int = 60
) -> dict:
    ok, reason = NetworkGuard().validate_url(seed_url)
    if not ok:
        return {"ok": False, "reason": reason, "seed_url": seed_url, "pages": []}

    seed_host = (urlparse(seed_url).hostname or "").lower()
    queue: deque[tuple[str, int]] = deque([(seed_url, 0)])
    seen: set[str] = set()
    pages: list[dict] = []

    # cancellation Event for timeout (P3-8)
    cancel_event = threading.Event()
    timer = threading.Timer(max_total_seconds, cancel_event.set)
    timer.start()

    try:
        while queue and len(pages) < max_pages and not cancel_event.is_set():
            current_url, depth = queue.popleft()
            canonical = _canonicalize(current_url)
            if canonical in seen:
                continue
            seen.add(canonical)

            fetched = fetch(current_url)
            if not fetched.get("ok"):
                if not pages:
                    return {
                        "ok": False,
                        "reason": fetched.get("reason", "fetch_failed"),
                        "seed_url": seed_url,
                        "pages": [],
                        "max_pages": max_pages,
                        "max_depth": max_depth,
                    }
                pages.append(
                    {
                        "url": current_url,
                        "depth": depth,
                        "ok": False,
                        "reason": fetched.get("reason", "fetch_failed"),
                    }
                )
                continue

            final_url = str(fetched.get("final_url", current_url))
            html = str(fetched.get("html", ""))
            main = extract_main_text(html)
            page = {
                "url": final_url,
                "depth": depth,
                "ok": bool(main.get("ok")),
                "title": _extract_title(html),
            }
            if main.get("ok"):
                text = str(main.get("text", ""))
                page["text_excerpt"] = text[:280]
            else:
                page["reason"] = main.get("reason", "extract_failed")
            pages.append(page)

            if depth >= max_depth:
                continue

            for link in _extract_links(html, base_url=final_url, expected_host=seed_host):
                candidate = _canonicalize(link)
                if candidate not in seen:
                    queue.append((link, depth + 1))
    finally:
        timer.cancel()

    reason = "OK"
    if cancel_event.is_set():
        reason = f"Crawl timed out after {max_total_seconds} seconds"

    return {
        "ok": True,
        "reason": reason,
        "seed_url": seed_url,
        "pages": pages,
        "max_pages": max_pages,
        "max_depth": max_depth,
        "engine": "http_static",
        "timed_out": cancel_event.is_set(),
    }


def _extract_links(html: str, *, base_url: str, expected_host: str) -> list[str]:
    links: list[str] = []
    for match in _HREF_PATTERN.finditer(html):
        href = unescape(match.group("href")).strip()
        if not href or href.startswith("#"):
            continue
        candidate = urljoin(base_url, href)
        parsed = urlparse(candidate)
        if (parsed.hostname or "").lower() != expected_host:
            continue
        ok, _ = NetworkGuard().validate_url(candidate)
        if not ok:
            continue
        if candidate not in links:
            links.append(candidate)
    return links


def _extract_title(html: str) -> str:
    match = _TITLE_PATTERN.search(html)
    if not match:
        return ""
    title = re.sub(r"<[^>]+>", " ", match.group("title"))
    return re.sub(r"\s+", " ", unescape(title)).strip()


def _canonicalize(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return f"{scheme}://{netloc}{path}"
