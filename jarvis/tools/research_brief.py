from __future__ import annotations

from .source_cite_builder import build_citations


def build(topic: str, findings: list[str], urls: list[str]) -> dict:
    return {
        "ok": True,
        "topic": topic,
        "summary": " ".join(findings[:5]),
        "citations": build_citations(urls),
        "summary_source": "input_findings",
        "finding_count": len(findings),
    }
