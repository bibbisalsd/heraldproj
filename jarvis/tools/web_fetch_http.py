from __future__ import annotations

import socket
import random
from functools import lru_cache
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from jarvis.brain_core.network_guard import NetworkGuard

from .robots_rate_limit_guard import RobotsRateLimitGuard

_RATE_GUARD = RobotsRateLimitGuard(per_domain_requests_per_minute=20)
_DEFAULT_TIMEOUT_SECONDS = 15
_DEFAULT_MAX_BYTES = 250_000
_USER_AGENTS = [
    "JarvisCore/0.1 (+static-http-fetch)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]
_TEXT_CONTENT_PREFIXES = ("text/",)
_TEXT_CONTENT_TYPES = {
    "application/javascript",
    "application/json",
    "application/ld+json",
    "application/xhtml+xml",
    "application/xml",
}


class _NetworkSafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ok, reason = NetworkGuard().validate_url(newurl)
        if not ok:
            raise URLError(reason)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(
    url: str,
    *,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    use_playwright: bool = False,
) -> dict:
    ok, reason = NetworkGuard().validate_url(url)
    if not ok:
        return {"ok": False, "reason": reason, "url": url}

    host = (urlparse(url).hostname or "").lower()
    if host and not _RATE_GUARD.allow(host):
        return {"ok": False, "reason": "RATE_LIMITED", "url": url}

    # If explicitly requested, or as a fallback below
    if use_playwright:
        pw_res = _fetch_playwright(url, timeout_seconds=timeout_seconds)
        if pw_res.get("ok"):
            return pw_res

    try:
        res = _http_request(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
        
        # Check for bot-blocking or auth required that might be bypassed by a real browser
        if not res.get("ok") and res.get("status_code") in {403, 401}:
            # Fallback to Playwright once
            return _fetch_playwright(url, timeout_seconds=timeout_seconds)
            
        return res
    except HTTPError as exc:
        if int(exc.code) in {403, 401}:
            # Fallback to Playwright
            return _fetch_playwright(url, timeout_seconds=timeout_seconds)

        return {
            "ok": False,
            "reason": f"HTTP_{int(exc.code)}",
            "url": url,
            "status_code": int(exc.code),
            "final_url": exc.geturl(),
        }
    except (TimeoutError, socket.timeout):
        return {"ok": False, "reason": "TIMEOUT", "url": url}
    except URLError as exc:
        detail = exc.reason
        if isinstance(detail, socket.timeout):
            return {"ok": False, "reason": "TIMEOUT", "url": url}
        if isinstance(detail, str) and detail.isupper():
            reason = detail
        else:
            reason = (
                f"NETWORK_{type(detail).__name__.upper()}"
                if detail
                else "NETWORK_ERROR"
            )
        return {"ok": False, "reason": reason, "url": url}
    except Exception as exc:  # pragma: no cover - safety net
        return {
            "ok": False,
            "reason": f"FETCH_FAILED_{type(exc).__name__.upper()}",
            "url": url,
        }


def _fetch_playwright(url: str, *, timeout_seconds: int) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "reason": "PLAYWRIGHT_MISSING"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            response = page.goto(
                url, timeout=timeout_seconds * 1000, wait_until="networkidle"
            )
            if not response:
                browser.close()
                return {"ok": False, "reason": "NO_RESPONSE", "url": url}

            html = page.content()
            status = response.status
            headers = response.headers
            final_url = page.url
            browser.close()

            return {
                "ok": True,
                "reason": "OK",
                "url": url,
                "final_url": final_url,
                "status_code": status,
                "content_type": headers.get("content-type", "text/html"),
                "charset": "utf-8",
                "headers": headers,
                "text": html,
                "html": html,
                "bytes_read": len(html),
                "truncated": False,
                "engine": "playwright",
            }
    except Exception as e:
        return {"ok": False, "reason": f"PLAYWRIGHT_ERROR: {e}", "url": url}


@lru_cache(maxsize=1)
def _get_opener():
    return build_opener(_NetworkSafeRedirectHandler)


def _http_request(url: str, *, timeout_seconds: int, max_bytes: int) -> dict:
    opener = _get_opener()
    request = Request(
        url,
        headers={
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    with opener.open(request, timeout=timeout_seconds) as response:
        final_url = response.geturl()
        ok, reason = NetworkGuard().validate_url(final_url)
        if not ok:
            return {"ok": False, "reason": reason, "url": url, "final_url": final_url}

        raw = response.read(max_bytes + 1)
        truncated = len(raw) > max_bytes
        payload = raw[:max_bytes]

        headers = _select_headers(response.headers.items())
        content_type = _content_type(headers.get("content-type", ""))
        charset = _charset(headers.get("content-type", ""))

        text = ""
        if _is_textual(content_type):
            text = payload.decode(charset or "utf-8", errors="replace")

        return {
            "ok": True,
            "reason": "OK",
            "url": url,
            "final_url": final_url,
            "status_code": int(getattr(response, "status", response.getcode())),
            "content_type": content_type,
            "charset": charset or "utf-8",
            "headers": headers,
            "text": text,
            "html": text,
            "bytes_read": len(payload),
            "truncated": truncated,
            "engine": "urllib_http",
        }


def _select_headers(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    allowed = {"content-type", "content-length", "last-modified", "etag"}
    selected: dict[str, str] = {}
    for key, value in items:
        lowered = key.lower()
        if lowered in allowed:
            selected[lowered] = value
    return selected


def _content_type(raw: str) -> str:
    return raw.split(";", 1)[0].strip().lower() or "application/octet-stream"


def _charset(raw: str) -> str | None:
    for part in raw.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset":
            return value.strip().strip('"').strip("'") or None
    return None


def _is_textual(content_type: str) -> bool:
    if any(content_type.startswith(prefix) for prefix in _TEXT_CONTENT_PREFIXES):
        return True
    return content_type in _TEXT_CONTENT_TYPES
