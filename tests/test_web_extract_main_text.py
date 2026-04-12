from __future__ import annotations
from jarvis.tools.web_extract_main_text import extract_main_text


def test_web_extract_main_text_extracts_plain_content():
    html = "<html><body><main>Hello world</main></body></html>"
    result = extract_main_text(html)
    assert result["ok"] is True
    assert "Hello world" in result["text"]


def test_web_extract_main_text_detects_js_shell():
    html = "<html><script src='bundle.js'></script></html>"
    result = extract_main_text(html)
    assert result["ok"] is False
    assert result["reason"] == "JS_SHELL_DETECTED"
