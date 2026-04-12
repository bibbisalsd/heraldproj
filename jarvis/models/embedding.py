from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


@dataclass(frozen=True)
class EmbeddingResult:
    ok: bool
    vector: list[float]
    error: str = ""


class OllamaEmbeddingClient:
    """Local Ollama embeddings client with sync and async HTTP methods.

    Sync: embed() uses stdlib urllib.
    Async: async_embed() uses httpx.AsyncClient.
    """

    def __init__(
        self,
        model: str = "nomic-embed-text-v2-moe",
        host: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 8,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str, keep_alive: str = "2h") -> EmbeddingResult:
        if not text.strip():
            return EmbeddingResult(ok=False, vector=[], error="empty_text")

        payload = {"model": self.model, "input": text, "keep_alive": keep_alive}
        embed = self._post_json("/api/embed", payload)
        if embed.ok:
            return embed

        legacy_payload = {"model": self.model, "prompt": text, "keep_alive": keep_alive}
        legacy = self._post_json("/api/embeddings", legacy_payload)
        if legacy.ok:
            return legacy
        return EmbeddingResult(ok=False, vector=[], error=legacy.error or embed.error)

    def _post_json(self, path: str, payload: dict) -> EmbeddingResult:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                body = json.loads(raw)
        except error.URLError as exc:
            return EmbeddingResult(ok=False, vector=[], error=f"url_error:{exc.reason}")
        except TimeoutError:
            return EmbeddingResult(ok=False, vector=[], error="timeout")
        except json.JSONDecodeError:
            return EmbeddingResult(ok=False, vector=[], error="invalid_json")
        except Exception as exc:
            return EmbeddingResult(
                ok=False, vector=[], error=f"unexpected:{type(exc).__name__}"
            )

        if "embedding" in body and isinstance(body["embedding"], list):
            vector = [float(value) for value in body["embedding"]]
            return EmbeddingResult(ok=True, vector=vector)

        if (
            "embeddings" in body
            and isinstance(body["embeddings"], list)
            and body["embeddings"]
        ):
            first = body["embeddings"][0]
            if isinstance(first, list):
                vector = [float(value) for value in first]
                return EmbeddingResult(ok=True, vector=vector)

        return EmbeddingResult(ok=False, vector=[], error="embedding_missing")

    # ------------------------------------------------------------------
    # Phase 9A: Async embedding
    # ------------------------------------------------------------------

    async def async_embed(self, text: str, keep_alive: str = "2h") -> EmbeddingResult:
        """Async version of embed() using httpx."""
        if not text.strip():
            return EmbeddingResult(ok=False, vector=[], error="empty_text")

        result = await self._async_post_json(
            "/api/embed", {"model": self.model, "input": text, "keep_alive": keep_alive}
        )
        if result.ok:
            return result
        legacy = await self._async_post_json(
            "/api/embeddings",
            {"model": self.model, "prompt": text, "keep_alive": keep_alive},
        )
        if legacy.ok:
            return legacy
        return EmbeddingResult(ok=False, vector=[], error=legacy.error or result.error)

    async def _async_post_json(self, path: str, payload: dict) -> EmbeddingResult:
        """POST JSON using httpx.AsyncClient."""
        if httpx is None:
            return EmbeddingResult(ok=False, vector=[], error="httpx_not_installed")

        url = f"{self.host}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                body = resp.json()
        except httpx.TimeoutException:
            return EmbeddingResult(ok=False, vector=[], error="timeout")
        except httpx.ConnectError:
            return EmbeddingResult(ok=False, vector=[], error="connection_refused")
        except Exception as exc:
            return EmbeddingResult(
                ok=False, vector=[], error=f"unexpected:{type(exc).__name__}"
            )

        if "embedding" in body and isinstance(body["embedding"], list):
            vector = [float(v) for v in body["embedding"]]
            return EmbeddingResult(ok=True, vector=vector)

        if (
            "embeddings" in body
            and isinstance(body["embeddings"], list)
            and body["embeddings"]
        ):
            first = body["embeddings"][0]
            if isinstance(first, list):
                vector = [float(v) for v in first]
                return EmbeddingResult(ok=True, vector=vector)

        return EmbeddingResult(ok=False, vector=[], error="embedding_missing")
