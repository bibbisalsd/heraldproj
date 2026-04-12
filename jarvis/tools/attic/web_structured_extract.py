from __future__ import annotations

import re


def structured_extract(text: str) -> dict:
    words = [w for w in re.split(r"\W+", text) if w]
    top = words[:20]
    return {
        "ok": True,
        "summary": " ".join(top),
        "word_count": len(words),
    }
