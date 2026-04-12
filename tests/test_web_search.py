from __future__ import annotations
from jarvis.tools.web_search import search


def test_web_search_rejects_empty_query():
    result = search("   ")

    assert result["ok"] is False
    assert result["reason"] == "empty_query"
    assert result["results"] == []


def test_web_search_parses_duckduckgo_html_results(monkeypatch):
    monkeypatch.setattr(
        "jarvis.tools.web_search.fetch",
        lambda url, **kwargs: {
            "ok": True,
            "reason": "OK",
            "url": url,
            "html": """
                <html><body>
                  <div class="result">
                    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs">Example Docs</a>
                    <div class="result__snippet">A helpful documentation page.</div>
                  </div>
                </body></html>
            """,
        },
    )

    result = search("jarvis docs")

    assert result["ok"] is True
    assert result["engine"] == "bing_html"
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Example Docs"
    assert result["results"][0]["url"] == "https://example.com/docs"
    assert "helpful documentation" in result["results"][0]["snippet"]
