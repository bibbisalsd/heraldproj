from __future__ import annotations
from jarvis.tools.web_structured_extract import structured_extract


def test_web_structured_extract_returns_summary_and_count():
    result = structured_extract("one two three four")
    assert result["ok"] is True
    assert result["word_count"] == 4
    assert result["summary"] == "one two three four"
