from __future__ import annotations
import logging
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)


def fetch_rendered_page(url: str) -> Optional[str]:
    """
    Fetches the textual content of a page after executing JavaScript.
    Uses playwright's synchronous API.
    """
    # Defensive check against non-http/https schemes
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        logger.error(f"Invalid URL scheme: {parsed.scheme}")
        return None

    try:
        from playwright.sync_api import (
            sync_playwright,
            TimeoutError as PlaywrightTimeoutError,
        )
    except ImportError:
        logger.error("Playwright not installed. Check requirements-browser.txt")
        return "Browser wrapper unavailable. Playwright is not installed."

    try:
        with sync_playwright() as p:
            # use chromium, headless
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                # Wait for network idle to ensure JS rendering
                page.goto(url, wait_until="networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning(
                    f"Timeout waiting for networkidle on {url}. Proceeding with what we have."
                )

            # Extract only visible text, removing excessive whitespace
            text_content = page.evaluate("document.body.innerText")
            browser.close()

            return text_content if text_content else "No visible text extracted."
    except Exception as e:
        logger.error(f"Playwright fetch failed for {url}: {e}")
        return None
