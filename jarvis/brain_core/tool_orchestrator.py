from __future__ import annotations

import copy
from time import perf_counter
from typing import Any, Callable, Dict

from .contracts import ToolResultEnvelope, VerifiedFact, LLMDerivedResult
from .guardrails import Guardrails
from jarvis.world_model.evidence_store import Evidence, EvidenceStore, Provenance
from jarvis.tools.registry import ToolRegistry
from jarvis.crsis.contracts import utc_now_iso
from jarvis.brain_core.tool_manifest import TOOL_MANIFEST
from jarvis.brain_core.tool_policy import LanePolicy, VerificationStrength


ToolFn = Callable[..., Any]


class ToolOrchestrator:
    def __init__(
        self,
        evidence_store: EvidenceStore | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._tools: Dict[str, ToolFn] = {}
        self._capabilities: Dict[str, str | None] = {}
        self._confirmation_actions: Dict[str, str | None] = {}
        self._tool_registry = tool_registry or ToolRegistry()
        self._evidence_store = evidence_store

    def register_tool(
        self,
        name: str,
        fn: ToolFn,
        *,
        capability: str | None = None,
        confirmation_action: str | None = None,
        metadata: Any = None,
        purpose: str = "",
        input_schema: dict[str, str] | None = None,
        example_queries: tuple[str, ...] | list[str] | None = None,
        safe_in_realtime: bool = False,
        safe_in_bg1: bool = True,
        verification_strength: str = "medium",
        latency_class: str = "medium",
        voice_friendly_summary_policy: str = "",
        domain_tags: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self._tools[name] = fn
        self._capabilities[name] = capability
        self._confirmation_actions[name] = confirmation_action

        target_meta = metadata
        if target_meta is None:
            if name in TOOL_MANIFEST:
                target_meta = copy.deepcopy(TOOL_MANIFEST[name])

        if target_meta is not None:
            # target_meta is a ToolMetadata from esoteric
            safe_in_rt = getattr(target_meta, "safe_in_realtime", True)
            if hasattr(target_meta, "lane_policy"):
                if target_meta.lane_policy == LanePolicy.BG1:
                    safe_in_rt = False
                elif target_meta.lane_policy == LanePolicy.REALTIME:
                    safe_in_rt = True

            safe_in_bg = getattr(target_meta, "safe_in_bg1", True)
            if (
                hasattr(target_meta, "lane_policy")
                and target_meta.lane_policy == LanePolicy.REALTIME
            ):
                safe_in_bg = False

            v_strength = getattr(
                target_meta, "verification_strength", VerificationStrength.OBSERVED
            )
            if hasattr(v_strength, "value"):
                v_strength = v_strength.value

            lat_class = getattr(target_meta, "latency_class", "medium")
            if hasattr(lat_class, "value"):
                lat_class = lat_class.value

            cap = capability or getattr(target_meta, "capability", None)
            conf_act = confirmation_action or getattr(
                target_meta, "confirmation_action", None
            )

            self._tool_registry.register(
                name,
                fn,
                purpose=getattr(target_meta, "purpose", f"Tool {name}"),
                input_schema=getattr(target_meta, "input_schema", {}),
                example_queries=getattr(target_meta, "example_queries", []),
                safe_in_realtime=safe_in_rt,
                safe_in_bg1=safe_in_bg,
                verification_strength=v_strength,
                latency_class=lat_class,
                voice_friendly_summary_policy=getattr(
                    target_meta, "voice_friendly_result_policy", ""
                ),
                domain_tags=getattr(target_meta, "domain_tags", []),
                capability=cap,
                confirmation_action=conf_act,
                executable=True,
            )
        else:
            self._tool_registry.register(
                name,
                fn,
                purpose=purpose or f"Tool {name}",
                input_schema=input_schema,
                example_queries=example_queries,
                safe_in_realtime=safe_in_realtime,
                safe_in_bg1=safe_in_bg1,
                verification_strength=verification_strength,
                latency_class=latency_class,
                voice_friendly_summary_policy=voice_friendly_summary_policy,
                domain_tags=domain_tags,
                capability=capability,
                confirmation_action=confirmation_action,
                executable=True,
            )

    def metadata(self, name: str) -> dict[str, Any]:
        meta = self._tool_registry.metadata(name)
        if meta:
            return meta
        return {
            "capability": self._capabilities.get(name),
            "confirmation_action": self._confirmation_actions.get(name),
        }

    def get_tool_metadata(self, name: str) -> Any:
        return self._tool_registry.descriptor(name)

    def get_all_metadata(self) -> dict[str, Any]:
        return {d.tool_name: d for d in self._tool_registry.list_descriptors()}

    def list_descriptors(
        self,
        *,
        lane: str | None = None,
        executable_only: bool = False,
        domain_tag: str | None = None,
    ):
        return self._tool_registry.list_descriptors(
            lane=lane,
            executable_only=executable_only,
            domain_tag=domain_tag,
        )

    def execute(
        self, name: str, *, confirmed: bool = False, **kwargs: Any
    ) -> ToolResultEnvelope:
        if name not in self._tools:
            return ToolResultEnvelope(
                ok=False,
                summary=f"Tool '{name}' is not registered.",
                retryable=False,
                safety_flags=["unknown_tool"],
            )

        # Check metadata
        desc = self._tool_registry.descriptor(name)
        confirmation_action = (
            desc.confirmation_action if desc else self._confirmation_actions.get(name)
        )

        if confirmation_action:
            confirmation = Guardrails().check_confirmation_required(confirmation_action)
            if not confirmation.allowed and not confirmed:
                return ToolResultEnvelope(
                    ok=False,
                    summary=f"Confirmation required for tool '{name}'.",
                    retryable=False,
                    safety_flags=[confirmation.reason],
                )

        start = perf_counter()
        try:
            data = self._tools[name](**kwargs)
            elapsed_ms = int((perf_counter() - start) * 1000)
            if isinstance(data, dict) and isinstance(data.get("ok"), bool):
                tool_ok = bool(data["ok"])
                safety_flags = data.get("safety_flags", [])
                if not isinstance(safety_flags, list):
                    safety_flags = []
                summary = f"{name} executed"
                if not tool_ok:
                    summary = str(
                        data.get("summary") or data.get("reason") or f"{name} failed"
                    )
                
                # Treat as LLMDerivedResult if provenance is inferred
                fact = None
                if data.get("provenance") == "inferred":
                    fact = LLMDerivedResult(
                        content=str(data.get("result", summary)),
                        source=name,
                        model=str(data.get("model", "unknown")),
                        confidence=0.8 if tool_ok else 0.3,
                        timestamp=utc_now_iso(),
                    )
                else:
                    fact = VerifiedFact(
                        content=str(data.get("result", summary)),
                        source=name,
                        confidence=0.95 if tool_ok else 0.3,
                        timestamp=utc_now_iso(),
                        verification_strength="observed",
                    )

                result = ToolResultEnvelope(
                    ok=tool_ok,
                    summary=summary,
                    data={"result": data, "fact": fact},
                    retryable=bool(data.get("retryable", False)),
                    safety_flags=[str(flag) for flag in safety_flags],
                    elapsed_ms=elapsed_ms,
                )
                self._log_to_evidence_store(name, data, elapsed_ms, success=tool_ok)
                return result
            fact = VerifiedFact(
                content=str(data),
                source=name,
                confidence=0.9,
                timestamp=utc_now_iso(),
                verification_strength="observed",
            )
            result = ToolResultEnvelope(
                ok=True,
                summary=f"{name} executed",
                data={"result": data, "fact": fact},
                retryable=False,
                elapsed_ms=elapsed_ms,
            )
            self._log_to_evidence_store(name, data, elapsed_ms, success=True)
            return result
        except Exception as exc:  # pragma: no cover - exercised in tests
            elapsed_ms = int((perf_counter() - start) * 1000)
            result = ToolResultEnvelope(
                ok=False,
                summary=str(exc),
                data={},
                retryable=False,
                safety_flags=["tool_exception"],
                elapsed_ms=elapsed_ms,
            )
            self._log_to_evidence_store(
                name, {"error": str(exc)}, elapsed_ms, success=False
            )
            return result

    def _log_to_evidence_store(
        self,
        tool_name: str,
        result_data: Any,
        elapsed_ms: int,
        success: bool,
    ) -> None:
        """Log tool result to Evidence Store with provenance tracking."""
        if self._evidence_store is None:
            return

        import uuid

        evidence_id = f"tool_{tool_name}_{uuid.uuid4().hex[:8]}"

        desc = self._tool_registry.descriptor(tool_name)
        v_strength = desc.verification_strength if desc else "medium"

        evidence = Evidence(
            evidence_id=evidence_id,
            evidence_type="tool_result",
            content=result_data,
            source=tool_name,
            timestamp=utc_now_iso(),
            confidence=0.9 if success else 0.3,
            provenance=Provenance(
                source=tool_name,
                transform=None,
                result_id=evidence_id,
                metadata={
                    "elapsed_ms": elapsed_ms,
                    "success": success,
                    "verification_strength": v_strength,
                },
            ),
        )

        self._evidence_store.add(evidence)
