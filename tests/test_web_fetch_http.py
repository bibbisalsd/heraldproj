from __future__ import annotations
from jarvis.tools.web_fetch_http import fetch


def test_web_fetch_http_rejects_private_target():
    result = fetch("http://127.0.0.1")
    assert result["ok"] is False
    assert result["reason"] == "DISALLOWED_TARGET"


def test_web_fetch_http_returns_html_for_public_url(monkeypatch):
    monkeypatch.setattr(
        "jarvis.tools.web_fetch_http._http_request",
        lambda url, **kwargs: {
            "ok": True,
            "reason": "OK",
            "url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "charset": "utf-8",
            "headers": {"content-type": "text/html; charset=utf-8"},
            "text": "<html><body>Hello world</body></html>",
            "html": "<html><body>Hello world</body></html>",
            "bytes_read": 37,
            "truncated": False,
            "engine": "urllib_http",
        },
    )

    result = fetch("https://example.com/page")

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["engine"] == "urllib_http"
    assert "<html>" in result["html"]
