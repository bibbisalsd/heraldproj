"""Tests for Phase 9A: Async OllamaClient and OllamaEmbeddingClient.

All tests are lightweight — no real Ollama server, fully mocked HTTP.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.models.ollama_client import OllamaClient, OllamaRunResult
from jarvis.models.embedding import OllamaEmbeddingClient, EmbeddingResult

import httpx as real_httpx


def _mock_httpx_module():
    """Create a mock httpx module with real exception classes."""
    mock = MagicMock()
    mock.HTTPStatusError = real_httpx.HTTPStatusError
    mock.TimeoutException = real_httpx.TimeoutException
    mock.ConnectError = real_httpx.ConnectError
    return mock


def _make_mock_async_client(response_json):
    """Build a mock httpx.AsyncClient that returns a fixed JSON response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_json
    mock_resp.raise_for_status = MagicMock()

    ac = AsyncMock()
    ac.__aenter__ = AsyncMock(return_value=ac)
    ac.__aexit__ = AsyncMock(return_value=False)
    ac.post = AsyncMock(return_value=mock_resp)
    return ac


def _make_client() -> OllamaClient:
    """Create an OllamaClient with cached availability (no real checks)."""
    import time
    client = OllamaClient.__new__(OllamaClient)
    client.model = "llama3.2:1b"
    client.ollama_bin = "ollama"
    client.timeout_seconds = 10
    client.host = "http://127.0.0.1:11434"
    client._availability_cache_ttl_seconds = 60.0
    client._availability_checked_at = time.monotonic()  # fresh cache
    client._cached_available = True
    client._cached_installed = True
    return client


# ---------------------------------------------------------------------------
# OllamaClient async methods
# ---------------------------------------------------------------------------

class TestAsyncOllamaClient:

    @pytest.mark.asyncio
    async def test_async_chat_success(self):
        client = _make_client()
        ac = _make_mock_async_client({"message": {"content": "Hello there!"}})
        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.ollama_client.httpx", mock_mod):
            result = await client.async_chat([{"role": "user", "content": "Hi"}])

        assert result.ok is True
        assert result.text == "Hello there!"

    @pytest.mark.asyncio
    async def test_async_chat_not_installed(self):
        client = _make_client()
        client._cached_available = False
        result = await client.async_chat([{"role": "user", "content": "Hi"}])
        assert result.ok is False
        assert "not_installed" in result.error

    @pytest.mark.asyncio
    async def test_async_chat_model_not_installed(self):
        client = _make_client()
        client._cached_installed = False
        result = await client.async_chat([{"role": "user", "content": "Hi"}])
        assert result.ok is False
        assert "model_not_installed" in result.error

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        client = _make_client()
        ac = _make_mock_async_client({"response": "42"})
        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.ollama_client.httpx", mock_mod):
            result = await client.async_run("What is 6*7?")

        assert result.ok is True
        assert result.text == "42"

    @pytest.mark.asyncio
    async def test_async_warm_success(self):
        client = _make_client()
        ac = _make_mock_async_client({"response": "ready"})
        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.ollama_client.httpx", mock_mod):
            result = await client.async_warm()

        assert result.ok is True

    @pytest.mark.asyncio
    async def test_async_chat_timeout(self):
        client = _make_client()
        ac = AsyncMock()
        ac.__aenter__ = AsyncMock(return_value=ac)
        ac.__aexit__ = AsyncMock(return_value=False)
        ac.post = AsyncMock(side_effect=real_httpx.TimeoutException("timed out"))

        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.ollama_client.httpx", mock_mod):
            result = await client.async_chat([{"role": "user", "content": "Hi"}])

        assert result.ok is False
        assert result.error == "timeout"

    @pytest.mark.asyncio
    async def test_async_chat_connection_refused(self):
        client = _make_client()
        ac = AsyncMock()
        ac.__aenter__ = AsyncMock(return_value=ac)
        ac.__aexit__ = AsyncMock(return_value=False)
        ac.post = AsyncMock(side_effect=real_httpx.ConnectError("refused"))

        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.ollama_client.httpx", mock_mod):
            result = await client.async_chat([{"role": "user", "content": "Hi"}])

        assert result.ok is False
        assert result.error == "connection_refused"

    @pytest.mark.asyncio
    async def test_async_chat_with_keep_alive(self):
        client = _make_client()
        ac = _make_mock_async_client({"message": {"content": "ok"}})
        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.ollama_client.httpx", mock_mod):
            result = await client.async_chat(
                [{"role": "user", "content": "Hi"}],
                keep_alive="2h",
            )

        assert result.ok is True
        # Verify keep_alive was included in the payload
        call_args = ac.post.call_args
        sent_json = call_args.kwargs.get("json") or call_args[1].get("json")
        assert sent_json["keep_alive"] == "2h"

    @pytest.mark.asyncio
    async def test_async_run_with_images(self):
        client = _make_client()
        ac = _make_mock_async_client({"response": "I see a cat"})
        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.ollama_client.httpx", mock_mod):
            result = await client.async_run("describe", images=["base64data"])

        assert result.ok is True
        call_args = ac.post.call_args
        sent_json = call_args.kwargs.get("json") or call_args[1].get("json")
        assert sent_json["images"] == ["base64data"]

    @pytest.mark.asyncio
    async def test_async_httpx_not_installed(self):
        client = _make_client()
        with patch("jarvis.models.ollama_client.httpx", None):
            result = await client.async_chat([{"role": "user", "content": "Hi"}])
        assert result.ok is False
        assert result.error == "httpx_not_installed"

    def test_sync_chat_unchanged(self):
        """Verify sync chat() still works (backwards compat)."""
        client = _make_client()
        client._cached_available = False
        result = client.chat([{"role": "user", "content": "Hi"}])
        assert result.ok is False
        assert "not_installed" in result.error


# ---------------------------------------------------------------------------
# OllamaEmbeddingClient async
# ---------------------------------------------------------------------------

class TestAsyncEmbeddingClient:

    @pytest.mark.asyncio
    async def test_async_embed_success(self):
        client = OllamaEmbeddingClient(model="nomic-embed-text-v2-moe")
        ac = _make_mock_async_client({"embeddings": [[0.1, 0.2, 0.3]]})
        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.embedding.httpx", mock_mod):
            result = await client.async_embed("hello world")

        assert result.ok is True
        assert result.vector == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_async_embed_empty_text(self):
        client = OllamaEmbeddingClient()
        result = await client.async_embed("")
        assert result.ok is False
        assert result.error == "empty_text"

    @pytest.mark.asyncio
    async def test_async_embed_legacy_format(self):
        """Test fallback to legacy /api/embeddings endpoint."""
        client = OllamaEmbeddingClient()

        # First call returns empty (new API miss), second returns legacy format
        resp_miss = MagicMock()
        resp_miss.json.return_value = {}
        resp_miss.raise_for_status = MagicMock()

        resp_ok = MagicMock()
        resp_ok.json.return_value = {"embedding": [0.5, 0.6]}
        resp_ok.raise_for_status = MagicMock()

        ac = AsyncMock()
        ac.__aenter__ = AsyncMock(return_value=ac)
        ac.__aexit__ = AsyncMock(return_value=False)
        ac.post = AsyncMock(side_effect=[resp_miss, resp_ok])

        mock_mod = _mock_httpx_module()
        mock_mod.AsyncClient.return_value = ac

        with patch("jarvis.models.embedding.httpx", mock_mod):
            result = await client.async_embed("test")

        assert result.ok is True
        assert result.vector == [0.5, 0.6]

    @pytest.mark.asyncio
    async def test_async_embed_httpx_not_installed(self):
        client = OllamaEmbeddingClient()
        with patch("jarvis.models.embedding.httpx", None):
            result = await client.async_embed("test")
        assert result.ok is False
        assert result.error == "httpx_not_installed"

    def test_sync_embed_unchanged(self):
        """Verify sync embed() interface is unchanged (backwards compat)."""
        client = OllamaEmbeddingClient()
        result = client.embed("")
        assert result.ok is False
        assert result.error == "empty_text"


# ---------------------------------------------------------------------------
# Concurrency sanity check
# ---------------------------------------------------------------------------

class TestAsyncConcurrency:

    @pytest.mark.asyncio
    async def test_gather_multiple_clients(self):
        """asyncio.gather with multiple async calls works."""
        client = _make_client()
        client._cached_available = False

        # Both return immediately with not_installed — no real HTTP
        r1, r2 = await asyncio.gather(
            client.async_chat([{"role": "user", "content": "a"}]),
            client.async_run("b"),
        )
        assert r1.ok is False
        assert r2.ok is False

    @pytest.mark.asyncio
    async def test_gather_chat_and_embed(self):
        """Chat + embed can run concurrently."""
        ollama = _make_client()
        ollama._cached_available = False
        embed_client = OllamaEmbeddingClient()

        r1, r2 = await asyncio.gather(
            ollama.async_chat([{"role": "user", "content": "hi"}]),
            embed_client.async_embed(""),
        )
        assert r1.ok is False
        assert r2.ok is False
