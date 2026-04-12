from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path


class STT:
    def __init__(self, model_name: str = "small.en") -> None:
        self.model_name = os.getenv("STT_MODEL", model_name)
        self.device = os.getenv("JARVIS_STT_DEVICE", "cuda" if self._has_nvidia_gpu() else "cpu")
        self.compute_type = os.getenv("JARVIS_STT_COMPUTE_TYPE", "float16" if self.device == "cuda" else "int8")
        self._whisper_model = None
        self.last_error = ""
        self._warmed = False

    def _has_nvidia_gpu(self) -> bool:
        """Check if an NVIDIA GPU is available via nvidia-smi."""
        try:
            import subprocess
            return subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
        except Exception:
            return False

    def warm(self) -> bool:
        """Preload the Whisper model to avoid cold-start latency.

        Returns True if model loaded successfully, False otherwise.
        Safe to call multiple times (no-op if already loaded).
        """
        if self._whisper_model is not None:
            self._warmed = True
            return True

        if not self._is_whisper_available():
            return False

        try:
            from faster_whisper import WhisperModel  # type: ignore

            try:
                self._whisper_model = WhisperModel(
                    self.model_name, device=self.device, compute_type=self.compute_type
                )
            except Exception as cuda_exc:
                if self.device == "cuda":
                    # Fallback to CPU if CUDA fails (e.g. missing libraries)
                    print(f"STT: CUDA initialization failed ({cuda_exc}). Falling back to CPU.", flush=True)
                    self._whisper_model = WhisperModel(
                        self.model_name, device="cpu", compute_type="int8"
                    )
                else:
                    raise cuda_exc
            
            self._warmed = True
            return True
        except Exception as exc:
            self.last_error = f"warm_failed:{type(exc).__name__}: {exc}"
            return False

    def transcribe(self, audio_bytes: bytes) -> str:
        self.last_error = ""
        if not audio_bytes:
            return ""

        decoded = self._decode_text_if_probable(audio_bytes)
        if decoded:
            return decoded

        if not self._is_whisper_available():
            return ""

        try:
            if self._whisper_model is None:
                self.warm()
                if self._whisper_model is None:
                    return ""

            tmp_path = self._write_temp_audio(audio_bytes)
            try:
                segments, _ = self._whisper_model.transcribe(str(tmp_path), beam_size=1)
                text = " ".join(
                    seg.text.strip() for seg in segments if seg.text.strip()
                )
                return text.strip()
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise

    def _is_whisper_available(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _decode_text_if_probable(self, raw: bytes) -> str:
        # Preserve fast test/dev path for plain text payloads while
        # avoiding false positives for binary audio blobs.
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ""

        stripped = decoded.strip()
        if not stripped:
            return ""
        if "\x00" in decoded:
            return ""

        printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
        ratio = printable / max(1, len(decoded))
        return stripped if ratio >= 0.98 else ""

    def _write_temp_audio(self, audio_bytes: bytes) -> Path:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        try:
            tmp.write(audio_bytes)
            tmp.flush()
            return Path(tmp.name)
        finally:
            tmp.close()
