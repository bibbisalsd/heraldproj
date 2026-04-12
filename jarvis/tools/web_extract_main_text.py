from __future__ import annotations

import re


# Block only truly JS-heavy sites (SPA bundles), not sites with simple scripts
SCRIPT_HEAVY_MARKERS = (
    "webpack",
    "bundle.js",
    "_next/static",
    ".chunk.js",
    "react-dom",
    "vendor.js",
)


def extract_main_text(html: str) -> dict:
    lowered = html.lower()

    # Only block if JS bundle markers are present (not just any <script> tag)
    if any(marker in lowered for marker in SCRIPT_HEAVY_MARKERS):
        # Check if there's actual content anyway - some sites have both SSR + hydration
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        # If we got meaningful content (>50 chars after cleanup), return it
        if len(text) > 50:
            return {"ok": True, "reason": "OK_PARTIAL", "text": text}
        return {"ok": False, "reason": "JS_SHELL_DETECTED", "text": ""}

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return {"ok": True, "reason": "OK", "text": text}
