from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FallbackAction:
    strategy: str
    message: str


class FallbackPolicy:
    def resolve(
        self, component: str, error_type: str, context: dict | None = None
    ) -> FallbackAction:
        context = context or {}
        if component == "renderer":
            return FallbackAction(
                "template_response",
                "Renderer unavailable. Using deterministic fallback.",
            )
        if component == "output_sink":
            return FallbackAction(
                "next_sink", "Primary sink failed. Routing to fallback sink."
            )
        if component == "network":
            return FallbackAction(
                "retry_or_skip", "Network issue. Returning cached/partial result."
            )
        if error_type == "permission_denied":
            return FallbackAction("deny", "Action denied by permission policy.")
        return FallbackAction("template_response", "Using safe fallback response.")
