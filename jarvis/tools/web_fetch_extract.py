from __future__ import annotations

from .web_extract_main_text import extract_main_text
from .web_fetch_http import fetch
from .web_structured_extract import structured_extract


def fetch_extract(url: str) -> dict:
    fetched = fetch(url)
    if not fetched.get("ok"):
        return fetched

    main = extract_main_text(fetched["html"])
    if not main.get("ok"):
        return {"ok": False, "reason": main["reason"], "url": url}

    structured = structured_extract(main["text"])
    return {
        "ok": True,
        "url": url,
        "text": main["text"],
        "structured": structured,
    }
