from __future__ import annotations

from .web_extract_main_text import extract_main_text
from .web_fetch_http import fetch
from .web_structured_extract import structured_extract


def scrape(url: str) -> dict:
    fetched = fetch(url)
    if not fetched.get("ok"):
        return fetched

    html = str(fetched.get("html", ""))
    main = extract_main_text(html)
    if not main.get("ok"):
        return {
            "ok": False,
            "reason": main.get("reason", "extract_failed"),
            "url": url,
            "final_url": fetched.get("final_url", url),
            "engine": "http_static",
            "html": html,
        }

    text = str(main.get("text", ""))
    return {
        "ok": True,
        "reason": "OK",
        "url": url,
        "final_url": fetched.get("final_url", url),
        "engine": "http_static",
        "rendered": False,
        "html": html,
        "text": text,
        "structured": structured_extract(text),
    }
