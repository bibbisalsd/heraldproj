from __future__ import annotations
from jarvis.tools.web_scrape_chromium import scrape


def test_web_scrape_chromium_returns_static_scrape_payload(monkeypatch):
    monkeypatch.setattr(
        "jarvis.tools.web_scrape_chromium.fetch",
        lambda url: {
            "ok": True,
            "reason": "OK",
            "url": url,
            "final_url": url,
            "html": "<html><body><main>Hello from static scrape</main></body></html>",
        },
    )

    result = scrape("https://example.com/app")

    assert result["ok"] is True
    assert result["engine"] == "http_static"
    assert result["rendered"] is False
    assert "Hello from static scrape" in result["text"]
