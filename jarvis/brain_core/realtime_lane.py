from __future__ import annotations

from dataclasses import dataclass

from .contracts import IngressEnvelope


@dataclass
class RealtimeResponse:
    text: str
    resolved_by: str = "template"


class RealtimeLane:
    def handle(self, envelope: IngressEnvelope) -> RealtimeResponse:
        text = envelope.text.lower().strip()
        if "status" in text:
            return RealtimeResponse(
                text="I am currently online.", resolved_by="template"
            )
        if text in {"hello", "hi", "hey"}:
            return RealtimeResponse(text="Hello. I am ready.", resolved_by="template")
        if "how are you" in text:
            return RealtimeResponse(
                text="I am online and ready to help.", resolved_by="template"
            )
        if "cancel current heavy task" in text:
            return RealtimeResponse(
                text="Cancelling current heavy task.", resolved_by="tool_only"
            )

        # Performance info
        if any(
            x in text
            for x in ("why are you slow", "why are responses slow", "latency", "lag")
        ):
            return RealtimeResponse(
                text="I am processing heavy background tasks or loading models sir. I will be with you shortly.",
                resolved_by="template",
            )

        return RealtimeResponse(
            text="I'm here. I didn't quite catch a specific command, but I'm listening.",
            resolved_by="template",
        )
