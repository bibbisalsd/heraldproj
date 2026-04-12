from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Callable
from urllib import error, request

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from ..ollama_runtime import resolve_ollama_bin


@dataclass(frozen=True)
class OllamaRunResult:
    ok: bool
    text: str
    error: str = ""


class OllamaClient:
    """Local-only Ollama wrapper with sync and async HTTP methods.

    Sync methods (chat, run, warm, generate) use stdlib urllib.
    Async methods (async_chat, async_run, async_warm) use httpx.AsyncClient.
    Both share the same availability cache and return OllamaRunResult.
    """

    def __init__(
        self,
        model: str,
        ollama_bin: str = "ollama",
        timeout_seconds: int = 300,
        host: str = "http://127.0.0.1:11434",
    ) -> None:
        self.model = model
        self.ollama_bin = resolve_ollama_bin(ollama_bin)
        self.timeout_seconds = timeout_seconds
        self.host = host.rstrip("/")
        self._availability_cache_ttl_seconds = 60.0
        self._availability_checked_at = 0.0
        self._cached_available: bool | None = None
        self._cached_installed: bool | None = None

    def health(self) -> dict:
        available, installed = self._availability()
        return {
            "ok": available and installed,
            "available": available,
            "installed": installed,
            "model": self.model,
        }

    def pull(self) -> OllamaRunResult:
        return self._run_cmd([self.ollama_bin, "pull", self.model], timeout_seconds=900)

    def generate(self, prompt: str, *, timeout_seconds: int | None = None) -> str:
        result = self.run(prompt, timeout_seconds=timeout_seconds)
        if not result.ok:
            raise RuntimeError(result.error or "ollama_run_failed")
        return result.text

    def chat(
        self,
        messages: list[dict],
        *,
        keep_alive: str | None = None,
        timeout_seconds: int | None = None,
    ) -> OllamaRunResult:
        available, installed = self._availability()
        if not available:
            return OllamaRunResult(ok=False, text="", error="ollama_not_installed")
        if not installed:
            return OllamaRunResult(
                ok=False, text="", error=f"model_not_installed:{self.model}"
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if keep_alive:
            payload["keep_alive"] = keep_alive
        
        return self._post_json("/api/chat", payload, timeout_seconds=timeout_seconds)

    def chat_stream(
        self,
        messages: list[dict],
        *,
        keep_alive: str | None = None,
        on_token: "Callable[[str], None] | None" = None,
    ) -> OllamaRunResult:
        """Streaming chat — calls on_token(str) for each token, returns full result."""
        available, installed = self._availability()
        if not available:
            return OllamaRunResult(ok=False, text="", error="ollama_not_installed")
        if not installed:
            return OllamaRunResult(
                ok=False, text="", error=f"model_not_installed:{self.model}"
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if keep_alive:
            payload["keep_alive"] = keep_alive

        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        full_text: list[str] = []
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                for line in response:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    message = chunk.get("message", {})
                    token = message.get("content", "")
                    if token:
                        full_text.append(token)
                        if on_token:
                            on_token(token)
                    if chunk.get("done", False):
                        break
        except error.HTTPError as exc:
            return OllamaRunResult(ok=False, text="", error=f"http_error:{exc.reason}")
        except error.URLError as exc:
            return OllamaRunResult(ok=False, text="", error=f"url_error:{exc.reason}")
        except TimeoutError:
            return OllamaRunResult(ok=False, text="", error="timeout")
        except Exception as exc:
            return OllamaRunResult(
                ok=False, text="", error=f"unexpected:{type(exc).__name__}"
            )

        text = "".join(full_text).strip()
        if text:
            return OllamaRunResult(ok=True, text=text)
        return OllamaRunResult(ok=False, text="", error="response_missing")

    def run(
        self,
        prompt: str,
        *,
        keep_alive: str | None = None,
        images: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> OllamaRunResult:
        available, installed = self._availability()
        if not available:
            return OllamaRunResult(ok=False, text="", error="ollama_not_installed")
        if not installed:
            return OllamaRunResult(
                ok=False, text="", error=f"model_not_installed:{self.model}"
            )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **({"keep_alive": keep_alive} if keep_alive else {}),
        }
        if images:
            payload["images"] = images

        api_result = self._post_json(
            "/api/generate",
            payload,
            timeout_seconds=timeout_seconds,
        )
        if api_result.ok:
            return api_result
        if not api_result.error.startswith(
            ("url_error:", "timeout", "invalid_json", "unexpected:")
        ):
            return api_result
        
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        return self._run_cmd(
            [self.ollama_bin, "run", self.model, prompt],
            timeout_seconds=effective_timeout,
        )

    def _check_ollama_installed(self) -> bool:
        result = self._run_cmd([self.ollama_bin, "--version"], timeout_seconds=15)
        return result.ok

    def warm(self, *, keep_alive: str = "2h") -> OllamaRunResult:
        available, installed = self._availability()
        if not available:
            return OllamaRunResult(ok=False, text="", error="ollama_not_installed")
        if not installed:
            return OllamaRunResult(
                ok=False, text="", error=f"model_not_installed:{self.model}"
            )
        result = self._post_json(
            "/api/generate",
            {
                "model": self.model,
                "prompt": "Respond with the single word ready.",
                "stream": False,
                "keep_alive": keep_alive,
                "options": {"num_predict": 1},
            },
        )
        if result.ok:
            return result
        return self._run_cmd(
            [self.ollama_bin, "run", self.model, "ready"],
            timeout_seconds=self.timeout_seconds,
        )

    def _is_model_installed(self) -> bool:
        available, installed = self._availability()
        return available and installed

    def _is_model_installed_uncached(self) -> bool:
        result = self._run_cmd([self.ollama_bin, "list"], timeout_seconds=30)
        if not result.ok:
            return False
        target = self.model.lower().strip()
        lines = [
            line.strip().lower() for line in result.text.splitlines() if line.strip()
        ]
        return any(
            line.split()[0] == target
            for line in lines
            if line and not line.startswith("name")
        )

    def _availability(self, *, force: bool = False) -> tuple[bool, bool]:
        now = time.monotonic()
        if (
            not force
            and self._cached_available is not None
            and self._cached_installed is not None
            and (now - self._availability_checked_at)
            < self._availability_cache_ttl_seconds
        ):
            return self._cached_available, self._cached_installed

        available = self._check_ollama_installed()
        installed = self._is_model_installed_uncached() if available else False
        self._cached_available = available
        self._cached_installed = installed
        self._availability_checked_at = now
        return available, installed

    def _run_cmd(self, cmd: list[str], timeout_seconds: int) -> OllamaRunResult:
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return OllamaRunResult(ok=False, text="", error="command_not_found")
        except subprocess.TimeoutExpired:
            return OllamaRunResult(ok=False, text="", error="timeout")

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        ok = completed.returncode == 0
        if ok:
            return OllamaRunResult(ok=True, text=stdout)
        return OllamaRunResult(
            ok=False, text=stdout, error=stderr or f"exit_code:{completed.returncode}"
        )

    def _post_json(self, path: str, payload: dict, timeout_seconds: int | None = None) -> OllamaRunResult:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            with request.urlopen(req, timeout=effective_timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            detail = body.strip() or exc.reason
            return OllamaRunResult(ok=False, text="", error=f"http_error:{detail}")
        except error.URLError as exc:
            return OllamaRunResult(ok=False, text="", error=f"url_error:{exc.reason}")
        except TimeoutError:
            return OllamaRunResult(ok=False, text="", error="timeout")
        except json.JSONDecodeError:
            return OllamaRunResult(ok=False, text="", error="invalid_json")
        except Exception as exc:
            return OllamaRunResult(
                ok=False, text="", error=f"unexpected:{type(exc).__name__}"
            )

        message = body.get("message")
        if isinstance(message, dict):
            content = str(message.get("content", "")).strip()
            return OllamaRunResult(ok=True, text=content)

        response_text = str(body.get("response", "")).strip()
        if response_text:
            return OllamaRunResult(ok=True, text=response_text)
        return OllamaRunResult(ok=False, text="", error="response_missing")

    # ------------------------------------------------------------------
    # Phase 9A: Async methods (require httpx)
    # ------------------------------------------------------------------

    async def async_chat(
        self, messages: list[dict], *, keep_alive: str | None = None
    ) -> OllamaRunResult:
        """Async version of chat() using httpx."""
        available, installed = self._availability()
        if not available:
            return OllamaRunResult(ok=False, text="", error="ollama_not_installed")
        if not installed:
            return OllamaRunResult(
                ok=False, text="", error=f"model_not_installed:{self.model}"
            )

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if keep_alive:
            payload["keep_alive"] = keep_alive
        return await self._async_post_json("/api/chat", payload)

    async def async_run(
        self,
        prompt: str,
        *,
        keep_alive: str | None = None,
        images: list[str] | None = None,
    ) -> OllamaRunResult:
        """Async version of run() using httpx."""
        available, installed = self._availability()
        if not available:
            return OllamaRunResult(ok=False, text="", error="ollama_not_installed")
        if not installed:
            return OllamaRunResult(
                ok=False, text="", error=f"model_not_installed:{self.model}"
            )

        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if keep_alive:
            payload["keep_alive"] = keep_alive
        if images:
            payload["images"] = images
        return await self._async_post_json("/api/generate", payload)

    async def async_warm(self, *, keep_alive: str = "2h") -> OllamaRunResult:
        """Async version of warm() using httpx."""
        available, installed = self._availability()
        if not available:
            return OllamaRunResult(ok=False, text="", error="ollama_not_installed")
        if not installed:
            return OllamaRunResult(
                ok=False, text="", error=f"model_not_installed:{self.model}"
            )
        return await self._async_post_json(
            "/api/generate",
            {
                "model": self.model,
                "prompt": "Respond with the single word ready.",
                "stream": False,
                "keep_alive": keep_alive,
                "options": {"num_predict": 1},
            },
        )

    async def _async_post_json(self, path: str, payload: dict) -> OllamaRunResult:
        """POST JSON to Ollama HTTP API using httpx.AsyncClient."""
        if httpx is None:
            return OllamaRunResult(ok=False, text="", error="httpx_not_installed")

        url = f"{self.host}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                body = resp.json()
        except httpx.HTTPStatusError as exc:
            return OllamaRunResult(
                ok=False, text="", error=f"http_error:{exc.response.status_code}"
            )
        except httpx.TimeoutException:
            return OllamaRunResult(ok=False, text="", error="timeout")
        except httpx.ConnectError:
            return OllamaRunResult(ok=False, text="", error="connection_refused")
        except Exception as exc:
            return OllamaRunResult(
                ok=False, text="", error=f"unexpected:{type(exc).__name__}"
            )

        message = body.get("message")
        if isinstance(message, dict):
            content = str(message.get("content", "")).strip()
            return OllamaRunResult(ok=True, text=content)

        response_text = str(body.get("response", "")).strip()
        if response_text:
            return OllamaRunResult(ok=True, text=response_text)
        return OllamaRunResult(ok=False, text="", error="response_missing")
