from __future__ import annotations

import importlib.util
import os
import queue
import re
import subprocess
import sys
import threading
import time
from uuid import uuid4
from collections import deque
from pathlib import Path
from typing import Dict


class TTS:
    def __init__(self, output_device_id: str = "default") -> None:
        self.output_device_id = output_device_id
        self.model_name = os.getenv("TTS_MODEL", "Kokoro-82M")
        self.backend = os.getenv("JARVIS_TTS_BACKEND", "kokoro").lower()
        self.kokoro_pack_python = os.getenv("JARVIS_KOKORO_PYTHON", "").strip()
        default_pack_dir = Path(__file__).resolve().parent / "kokoro_pack"
        self.kokoro_pack_dir = self._resolve_kokoro_pack_dir(default_pack_dir)
        self.kokoro_pack_enabled = self._resolve_kokoro_pack_enabled()
        self.last_spoken = ""
        self.last_backend = "stub"
        self.last_error = ""
        self.state = "idle"
        self.last_delivery_ok = True
        self.last_fallback_used = False
        self.last_attempted_backends: list[str] = []
        self.last_preload_ok = False
        self.last_preload_error = ""
        self.preload_state = "not_started"
        self._state_history: deque[str] = deque(["idle"], maxlen=24)
        self._kokoro_pack_lock = threading.RLock()
        self._kokoro_pack_process: subprocess.Popen[str] | None = None
        self._kokoro_pack_output: queue.Queue[str] | None = None
        self._kokoro_pack_reader_thread: threading.Thread | None = None

    def _resolve_kokoro_pack_dir(self, default_pack_dir: Path) -> str:
        explicit_dir = os.getenv("JARVIS_KOKORO_PACK_DIR", "").strip()
        if explicit_dir:
            return explicit_dir

        if self.kokoro_pack_python:
            python_parent = Path(self.kokoro_pack_python).expanduser().resolve().parent
            adjacent_pack = python_parent / "kokoro_pack"
            if (adjacent_pack / "jarvis_launcher.py").exists():
                return str(adjacent_pack)

        return str(default_pack_dir)

    def _resolve_kokoro_pack_enabled(self) -> bool:
        explicit_flag = os.getenv("JARVIS_USE_KOKORO_PACK")
        if explicit_flag is not None and explicit_flag.strip():
            return explicit_flag.strip().lower() == "true"

        pack_dir = Path(self.kokoro_pack_dir).expanduser()
        try:
            resolved_pack_dir = pack_dir.resolve()
        except OSError:
            resolved_pack_dir = pack_dir

        if (resolved_pack_dir / "jarvis_launcher.py").exists():
            return True

        return bool(
            os.getenv("JARVIS_KOKORO_PACK_DIR", "").strip() or self.kokoro_pack_python
        )

    def preload(self, *, timeout_seconds: float = 30.0) -> Dict[str, object]:
        """Warm the preferred TTS backend without speaking audible text.

        For the bundled Kokoro pack this starts its interactive launcher once and
        keeps it alive, so later calls to ``speak`` can synthesize immediately
        instead of loading the model after the terminal line has started
        printing.
        """
        self.preload_state = "preparing"
        self.last_preload_ok = False
        self.last_preload_error = ""

        if self.backend not in {"auto", "kokoro"}:
            self.preload_state = "skipped"
            self.last_preload_error = f"backend_{self.backend}_does_not_preload"
            return self._preload_payload()

        if self.kokoro_pack_enabled:
            ok, error = self._ensure_kokoro_pack_process(
                timeout_seconds=timeout_seconds
            )
            self.last_preload_ok = ok
            self.last_preload_error = "" if ok else error
            self.preload_state = "ready" if ok else "failed"
            return self._preload_payload()

        try:
            __import__("kokoro")
        except Exception as exc:
            self.preload_state = "failed"
            self.last_preload_error = f"kokoro_import_error:{type(exc).__name__}"
            return self._preload_payload()

        self.last_preload_ok = True
        self.preload_state = "ready"
        return self._preload_payload()

    def _preload_payload(self) -> Dict[str, object]:
        return {
            "ok": self.last_preload_ok,
            "backend": self.backend,
            "state": self.preload_state,
            "error": self.last_preload_error,
            "kokoro_pack_enabled": self.kokoro_pack_enabled,
            "kokoro_pack_persistent": self._kokoro_pack_process is not None
            and self._kokoro_pack_process.poll() is None,
        }

    def speak(self, text: str) -> Dict[str, str]:
        spoken = str(text or "").strip()
        self.last_spoken = spoken
        self.last_attempted_backends = []
        self.last_fallback_used = False
        self.last_delivery_ok = False
        call_state_history: list[str] = []

        def transition(state: str) -> None:
            normalized = str(state or "").strip().lower() or "idle"
            self.state = normalized
            self._state_history.append(normalized)
            call_state_history.append(normalized)

        if not spoken:
            self.last_backend = "stub"
            self.last_error = "empty_text"
            transition("failed")
            return {
                "ok": "false",
                "text": "",
                "output_device_id": self.output_device_id,
                "backend": self.last_backend,
                "model": self.model_name,
                "error": self.last_error,
                "delivery_ok": "false",
                "fallback_used": "false",
                "state": self.state,
                "state_history": list(call_state_history),
                "attempted_backends": list(self.last_attempted_backends),
            }

        used_backend = "stub"
        error_msg = ""
        transition("preparing")

        has_kokoro = self._has_kokoro()
        attempts: list[tuple[str, callable]] = []
        if self.backend in {"auto", "kokoro"}:
            if has_kokoro:
                attempts.append(("kokoro", lambda: self._speak_kokoro(spoken)))
            elif self.backend == "kokoro":
                error_msg = "kokoro_unavailable"
        if self.backend in {"auto", "sapi"}:
            attempts.append(("sapi", lambda: self._speak_windows_sapi(spoken)))

        for index, (backend_name, runner) in enumerate(attempts):
            if index > 0:
                transition("retrying")
            self.last_attempted_backends.append(backend_name)
            ok, attempt_error = runner()
            if ok:
                transition("speaking")
                used_backend = backend_name
                self.last_backend = used_backend
                self.last_error = ""
                self.last_delivery_ok = True
                self.last_fallback_used = index > 0
                if index > 0:
                    transition("recovered")
                transition("idle")
                return {
                    "ok": "true",
                    "text": spoken,
                    "output_device_id": self.output_device_id,
                    "backend": used_backend,
                    "model": self.model_name,
                    "error": "",
                    "delivery_ok": "true",
                    "fallback_used": "true" if self.last_fallback_used else "false",
                    "state": self.state,
                    "state_history": list(call_state_history),
                    "attempted_backends": list(self.last_attempted_backends),
                }
            if self._is_stall_error(attempt_error):
                transition("stalled")
            error_msg = attempt_error or error_msg

        self.last_backend = used_backend
        self.last_error = error_msg
        self.last_delivery_ok = False
        transition("failed")
        return {
            "ok": "true",
            "text": spoken,
            "output_device_id": self.output_device_id,
            "backend": used_backend,
            "model": self.model_name,
            "error": error_msg,
            "delivery_ok": "false",
            "fallback_used": "false",
            "state": self.state,
            "state_history": list(call_state_history),
            "attempted_backends": list(self.last_attempted_backends),
        }

    def speak_reliable(self, text: str, max_retries: int = 2, timeout: float = 5.0) -> Dict[str, str]:
        """Robust wrapper around speak with retries. (P2-11)"""
        self.last_spoken = str(text or "").strip()
        last_res = {"ok": "false", "error": "not_started"}
        for attempt in range(max_retries + 1):
            try:
                # Use a threading event or similar if we wanted real timeout on the call itself,
                # but speak() involves subprocesses with their own timeouts.
                # For this wrapper, we'll just catch exceptions and retry.
                last_res = self.speak(text)
                if last_res.get("ok") == "true":
                    return last_res
                time.sleep(0.5)  # Short gap before retry
            except Exception as e:
                last_res = {"ok": "false", "error": str(e)}
                time.sleep(1.0)
        return last_res

    def health_snapshot(self) -> Dict[str, object]:
        return {
            "state": self.state,
            "last_backend": self.last_backend,
            "last_error": self.last_error,
            "delivery_ok": self.last_delivery_ok,
            "fallback_used": self.last_fallback_used,
            "attempted_backends": list(self.last_attempted_backends),
            "state_history": list(self._state_history),
            "preload_state": self.preload_state,
            "preload_ok": self.last_preload_ok,
            "preload_error": self.last_preload_error,
            "kokoro_pack_persistent": self._kokoro_pack_process is not None
            and self._kokoro_pack_process.poll() is None,
        }

    def _has_kokoro(self) -> bool:
        if self.kokoro_pack_enabled:
            launcher = Path(self.kokoro_pack_dir) / "jarvis_launcher.py"
            if launcher.exists():
                return True
        return importlib.util.find_spec("kokoro") is not None

    def _speak_kokoro(self, text: str) -> tuple[bool, str]:
        pack_error = ""
        if self.kokoro_pack_enabled:
            ok, pack_error = self._speak_kokoro_pack(text)
            if ok:
                return True, ""

        try:
            kokoro = __import__("kokoro")
        except Exception as exc:
            if pack_error:
                return False, pack_error
            return False, f"kokoro_import_error:{type(exc).__name__}"

        try:
            if hasattr(kokoro, "speak"):
                kokoro.speak(text)
                return True, ""
            if hasattr(kokoro, "tts"):
                kokoro.tts(text)
                return True, ""
            return False, pack_error or "kokoro_api_not_supported"
        except Exception as exc:
            return False, f"kokoro_runtime_error:{type(exc).__name__}"

    def _speak_kokoro_pack(self, text: str) -> tuple[bool, str]:
        if (
            self._kokoro_pack_process is not None
            and self._kokoro_pack_process.poll() is None
        ):
            return self._speak_kokoro_pack_persistent(text)

        pack_dir = Path(self.kokoro_pack_dir).expanduser().resolve()
        launcher = pack_dir / "jarvis_launcher.py"
        if not launcher.exists():
            return False, "kokoro_pack_launcher_missing"

        candidates: list[str] = []
        if self.kokoro_pack_python:
            candidates.append(self.kokoro_pack_python)

        candidates.append(sys.executable)

        ordered_candidates: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            ordered_candidates.append(candidate)

        payload = f"{text}\nexit\n"
        last_error = "kokoro_pack_unavailable"
        for python_bin in ordered_candidates:
            try:
                completed = subprocess.run(
                    [python_bin, str(launcher)],
                    input=payload,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                    check=False,
                    cwd=str(pack_dir),
                )
            except FileNotFoundError:
                last_error = f"kokoro_pack_python_not_found:{python_bin}"
                continue
            except subprocess.TimeoutExpired:
                last_error = f"kokoro_pack_timeout:{python_bin}"
                continue

            if completed.returncode == 0:
                return True, ""

            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            if stderr:
                last_error = f"kokoro_pack_failed:{stderr.splitlines()[-1][:160]}"
            elif stdout:
                last_error = f"kokoro_pack_failed:{stdout.splitlines()[-1][:160]}"
            else:
                last_error = f"kokoro_pack_failed:exit_{completed.returncode}"

        return False, last_error

    def _kokoro_pack_python_candidates(self) -> list[str]:
        candidates: list[str] = []
        if self.kokoro_pack_python:
            candidates.append(self.kokoro_pack_python)
        candidates.append(sys.executable)

        ordered_candidates: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            ordered_candidates.append(candidate)
        return ordered_candidates

    def _ensure_kokoro_pack_process(
        self, *, timeout_seconds: float = 30.0
    ) -> tuple[bool, str]:
        with self._kokoro_pack_lock:
            if (
                self._kokoro_pack_process is not None
                and self._kokoro_pack_process.poll() is None
            ):
                return True, ""

            pack_dir = Path(self.kokoro_pack_dir).expanduser().resolve()
            launcher = pack_dir / "jarvis_launcher.py"
            if not launcher.exists():
                return False, "kokoro_pack_launcher_missing"

            last_error = "kokoro_pack_unavailable"
            for python_bin in self._kokoro_pack_python_candidates():
                try:
                    process = subprocess.Popen(
                        [python_bin, "-u", str(launcher)],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        cwd=str(pack_dir),
                        bufsize=1,
                    )
                except FileNotFoundError:
                    last_error = f"kokoro_pack_python_not_found:{python_bin}"
                    continue
                except OSError as exc:
                    last_error = f"kokoro_pack_start_error:{type(exc).__name__}"
                    continue

                self._kokoro_pack_process = process
                self._kokoro_pack_output = queue.Queue()
                self._start_kokoro_pack_reader(process)
                ok, error = self._wait_for_kokoro_pack_ready(
                    timeout_seconds=timeout_seconds
                )
                if ok:
                    return True, ""

                last_error = error
                self._stop_kokoro_pack_process()

            return False, last_error

    def _start_kokoro_pack_reader(self, process: subprocess.Popen[str]) -> None:
        def _reader() -> None:
            output = self._kokoro_pack_output
            stream = process.stdout
            if output is None or stream is None:
                return
            try:
                while True:
                    chunk = stream.read(1)
                    if not chunk:
                        break
                    output.put(chunk)
            except Exception as exc:
                output.put(f"\n[kokoro_pack_reader_error:{type(exc).__name__}]\n")

        self._kokoro_pack_reader_thread = threading.Thread(
            target=_reader,
            name="jarvis-kokoro-pack-reader",
            daemon=True,
        )
        self._kokoro_pack_reader_thread.start()

    def _drain_kokoro_pack_output(self) -> str:
        output = self._kokoro_pack_output
        if output is None:
            return ""
        chunks: list[str] = []
        while True:
            try:
                chunks.append(output.get_nowait())
            except queue.Empty:
                break
        return "".join(chunks)

    def _wait_for_kokoro_pack_ready(
        self, *, timeout_seconds: float
    ) -> tuple[bool, str]:
        deadline = time.monotonic() + max(0.1, float(timeout_seconds))
        captured = ""
        while time.monotonic() < deadline:
            captured += self._drain_kokoro_pack_output()
            if "Kokoro voice is ready." in captured:
                return True, ""
            if "Failed to initialize Kokoro:" in captured:
                return False, self._kokoro_pack_error_from_output(
                    captured, "kokoro_pack_init_failed"
                )
            if "Missing Kokoro model files:" in captured:
                return False, "kokoro_pack_model_files_missing"
            if (
                self._kokoro_pack_process is not None
                and self._kokoro_pack_process.poll() is not None
            ):
                captured += self._drain_kokoro_pack_output()
                return False, self._kokoro_pack_error_from_output(
                    captured, "kokoro_pack_exited_before_ready"
                )
            time.sleep(0.01)
        return False, "kokoro_pack_preload_timeout"

    def _speak_kokoro_pack_persistent(self, text: str) -> tuple[bool, str]:
        with self._kokoro_pack_lock:
            ok, error = self._ensure_kokoro_pack_process(timeout_seconds=10.0)
            if not ok:
                return False, error

            process = self._kokoro_pack_process
            if process is None or process.stdin is None or process.poll() is not None:
                self._stop_kokoro_pack_process()
                return False, "kokoro_pack_process_unavailable"

            token = uuid4().hex
            safe_text = re.sub(r"\s+", " ", str(text or "")).strip()
            if safe_text.startswith("/"):
                safe_text = "/" + safe_text
            self._drain_kokoro_pack_output()

            try:
                process.stdin.write(f"{safe_text}\n/ping {token}\n")
                process.stdin.flush()
            except OSError as exc:
                self._stop_kokoro_pack_process()
                return False, f"kokoro_pack_stdin_error:{type(exc).__name__}"

            marker = f"JARVIS_TTS_DONE {token}"
            deadline = time.monotonic() + 180.0
            captured = ""
            while time.monotonic() < deadline:
                captured += self._drain_kokoro_pack_output()
                if marker in captured:
                    if "Synthesis failed:" in captured:
                        return False, self._kokoro_pack_error_from_output(
                            captured, "kokoro_pack_synthesis_failed"
                        )
                    return True, ""
                if process.poll() is not None:
                    captured += self._drain_kokoro_pack_output()
                    self._stop_kokoro_pack_process()
                    return False, self._kokoro_pack_error_from_output(
                        captured, "kokoro_pack_process_exited"
                    )
                time.sleep(0.01)

            self._stop_kokoro_pack_process()
            return False, "kokoro_pack_persistent_timeout"

    def _kokoro_pack_error_from_output(self, output: str, fallback: str) -> str:
        lines = [
            line.strip() for line in str(output or "").splitlines() if line.strip()
        ]
        for line in reversed(lines):
            if "Synthesis failed:" in line or "Failed to initialize Kokoro:" in line:
                return f"kokoro_pack_failed:{line[-160:]}"
            if "reader_error" in line:
                return f"kokoro_pack_failed:{line[-160:]}"
        return fallback

    def _stop_kokoro_pack_process(self) -> None:
        process = self._kokoro_pack_process
        self._kokoro_pack_process = None
        self._kokoro_pack_output = None
        if process is None:
            return
        if process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.write("exit\n")
                process.stdin.flush()
        except OSError:
            pass
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()

    def shutdown(self) -> None:
        with self._kokoro_pack_lock:
            self._stop_kokoro_pack_process()

    def _speak_espeak(self, text: str) -> tuple[bool, str]:
        if sys.platform != "linux":
            return False, "espeak_only_supported_on_linux"

        # Try to find espeak or espeak-ng
        binary = "espeak-ng"
        if (
            importlib.util.find_spec("espeak") is None
            and subprocess.run(["which", "espeak-ng"], capture_output=True).returncode
            != 0
        ):
            binary = "espeak"
            if subprocess.run(["which", "espeak"], capture_output=True).returncode != 0:
                return False, "espeak_binary_not_found"

        try:
            completed = subprocess.run(
                [binary, text],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
        except FileNotFoundError:
            return False, f"{binary}_not_found"
        except subprocess.TimeoutExpired:
            return False, "espeak_timeout"

        if completed.returncode == 0:
            return True, ""
        stderr = (completed.stderr or "").strip()
        return False, stderr or f"espeak_exit_code:{completed.returncode}"

    def _speak_windows_sapi(self, text: str) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "sapi_not_supported_on_platform"

        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$synth.SetOutputToDefaultAudioDevice();"
            "$synth.Speak($env:JARVIS_TTS_TEXT);"
        )
        env = os.environ.copy()
        env["JARVIS_TTS_TEXT"] = text
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
                env=env,
            )
        except FileNotFoundError:
            return False, "powershell_not_found"
        except subprocess.TimeoutExpired:
            return False, "sapi_timeout"

        if completed.returncode == 0:
            return True, ""
        stderr = (completed.stderr or "").strip()
        return False, stderr or f"sapi_exit_code:{completed.returncode}"

    def pre_warm(self) -> bool:
        """Synthesize a tiny silent chunk to force ONNX/backend initialization."""
        print("  [tts] Pre-warming engine with silent synthesis...", flush=True)
        # Call _speak directly or ensure speak doesn't update last_spoken for this
        old_last = self.last_spoken
        res = self.speak("...")
        self.last_spoken = old_last # Restore
        if res.get("ok") == "true":
            print("  [tts] Engine pre-warmed successfully.", flush=True)
            return True
        return False

    def _is_stall_error(self, error: str) -> bool:
        normalized = str(error or "").strip().lower()
        return (
            "timeout" in normalized or "stalled" in normalized or "hang" in normalized
        )
