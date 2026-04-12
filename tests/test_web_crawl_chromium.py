from __future__ import annotations
from jarvis.tools.web_crawl_chromium import crawl


def test_web_crawl_chromium_returns_same_host_static_pages(monkeypatch):
    pages = {
        "https://example.com/docs": {
            "ok": True,
            "reason": "OK",
            "final_url": "https://example.com/docs",
            "html": """
                <html>
                  <head><title>Docs</title></head>
                  <body>
                    <main>Home page</main>
                    <a href="/docs/install">Install</a>
                    <a href="https://other.example.com/outside">Outside</a>
                  </body>
                </html>
            """,
        },
        "https://example.com/docs/install": {
            "ok": True,
            "reason": "OK",
            "final_url": "https://example.com/docs/install",
            "html": "<html><head><title>Install</title></head><body><main>Install steps here</main></body></html>",
        },
    }
    monkeypatch.setattr("jarvis.tools.web_crawl_chromium.fetch", lambda url: pages[url])

    result = crawl("https://example.com/docs", max_pages=3, max_depth=2)

    assert result["ok"] is True
    assert result["engine"] == "http_static"
    assert len(result["pages"]) == 2
    assert result["pages"][0]["title"] == "Docs"
    assert result["pages"][1]["title"] == "Install"
