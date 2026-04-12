from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


ToolFn = Callable[..., object]


@dataclass(frozen=True)
class ToolDescriptor:
    tool_name: str
    purpose: str = ""
    input_schema: dict[str, str] = field(default_factory=dict)
    example_queries: tuple[str, ...] = ()
    safe_in_realtime: bool = False
    safe_in_bg1: bool = True
    verification_strength: str = "medium"
    latency_class: str = "medium"
    voice_friendly_summary_policy: str = ""
    domain_tags: tuple[str, ...] = ()
    capability: str | None = None
    confirmation_action: str | None = None
    executable: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolFn | None] = {}
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def register(
        self,
        name: str,
        fn: ToolFn | None = None,
        *,
        purpose: str = "",
        input_schema: dict[str, str] | None = None,
        example_queries: tuple[str, ...] | list[str] | None = None,
        safe_in_realtime: bool = False,
        safe_in_bg1: bool = True,
        verification_strength: str = "medium",
        latency_class: str = "medium",
        voice_friendly_summary_policy: str = "",
        domain_tags: tuple[str, ...] | list[str] | None = None,
        capability: str | None = None,
        confirmation_action: str | None = None,
        executable: bool | None = None,
    ) -> None:
        executable_flag = (
            bool(fn is not None) if executable is None else bool(executable)
        )
        self._tools[name] = fn
        self._descriptors[name] = ToolDescriptor(
            tool_name=name,
            purpose=purpose,
            input_schema=dict(input_schema or {}),
            example_queries=tuple(example_queries or ()),
            safe_in_realtime=safe_in_realtime,
            safe_in_bg1=safe_in_bg1,
            verification_strength=verification_strength,
            latency_class=latency_class,
            voice_friendly_summary_policy=voice_friendly_summary_policy,
            domain_tags=tuple(domain_tags or ()),
            capability=capability,
            confirmation_action=confirmation_action,
            executable=executable_flag,
        )
        self._version += 1

    def register_descriptor(
        self, descriptor: ToolDescriptor, fn: ToolFn | None = None
    ) -> None:
        self._tools[descriptor.tool_name] = fn
        self._descriptors[descriptor.tool_name] = descriptor
        self._version += 1

    def get(self, name: str) -> ToolFn | None:
        return self._tools.get(name)

    def descriptor(self, name: str) -> ToolDescriptor | None:
        return self._descriptors.get(name)

    def metadata(self, name: str) -> dict[str, Any]:
        descriptor = self.descriptor(name)
        if descriptor is None:
            return {}
        return {
            "tool_name": descriptor.tool_name,
            "purpose": descriptor.purpose,
            "input_schema": dict(descriptor.input_schema),
            "example_queries": list(descriptor.example_queries),
            "safe_in_realtime": descriptor.safe_in_realtime,
            "safe_in_bg1": descriptor.safe_in_bg1,
            "verification_strength": descriptor.verification_strength,
            "latency_class": descriptor.latency_class,
            "voice_friendly_summary_policy": descriptor.voice_friendly_summary_policy,
            "domain_tags": list(descriptor.domain_tags),
            "capability": descriptor.capability,
            "confirmation_action": descriptor.confirmation_action,
            "executable": descriptor.executable,
        }

    def list_tools(
        self,
        *,
        lane: str | None = None,
        executable_only: bool = False,
        domain_tag: str | None = None,
    ) -> list[str]:
        names: list[str] = []
        for descriptor in self.list_descriptors(
            lane=lane, executable_only=executable_only, domain_tag=domain_tag
        ):
            names.append(descriptor.tool_name)
        return names

    def list_descriptors(
        self,
        *,
        lane: str | None = None,
        executable_only: bool = False,
        domain_tag: str | None = None,
    ) -> list[ToolDescriptor]:
        descriptors = list(self._descriptors.values())
        if lane == "realtime":
            descriptors = [item for item in descriptors if item.safe_in_realtime]
        elif lane == "bg1":
            descriptors = [item for item in descriptors if item.safe_in_bg1]
        if executable_only:
            descriptors = [item for item in descriptors if item.executable]
        if domain_tag:
            normalized_tag = domain_tag.strip().lower()
            descriptors = [
                item
                for item in descriptors
                if any(tag.lower() == normalized_tag for tag in item.domain_tags)
            ]
        return sorted(descriptors, key=lambda item: item.tool_name)
