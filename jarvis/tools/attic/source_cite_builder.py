from __future__ import annotations


def build_citations(urls: list[str]) -> list[dict]:
    return [{"id": idx + 1, "url": url} for idx, url in enumerate(urls)]
