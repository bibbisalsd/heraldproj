from __future__ import annotations


def detect(html: str) -> dict:
    lowered = html.lower()
    found = (
        ("captcha" in lowered) or ("recaptcha" in lowered) or ("hcaptcha" in lowered)
    )
    return {"ok": True, "captcha_detected": found}
