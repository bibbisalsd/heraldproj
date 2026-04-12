from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str


class Guardrails:
    def check_path_safety(self, path: str, workspace_root: str) -> GuardrailDecision:
        target = Path(path).resolve()
        root = Path(workspace_root).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return GuardrailDecision(False, "path_outside_workspace")
        return GuardrailDecision(True, "ok")

    def check_confirmation_required(self, action: str) -> GuardrailDecision:
        risky = {"file_write", "code_runner", "app_ops"}
        if action in risky:
            return GuardrailDecision(False, "confirmation_required")
        return GuardrailDecision(True, "ok")
