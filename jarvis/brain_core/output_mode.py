from __future__ import annotations

from dataclasses import dataclass


ALLOWED_MODES = {"local_voice", "active_addon_text", "local_text_log"}


@dataclass(frozen=True)
class OutputModeAck:
    ok: bool
    mode: str
    message: str


class OutputModeController:
    def __init__(self, initial: str = "local_voice") -> None:
        self._mode = initial

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> OutputModeAck:
        if mode not in ALLOWED_MODES:
            return OutputModeAck(False, self._mode, "unsupported_output_mode")
        self._mode = mode
        return OutputModeAck(True, self._mode, f"output_mode_set:{mode}")
