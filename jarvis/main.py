from __future__ import annotations

import json
import logging
import os
import threading
import sys
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .brain_core.admission_control import AdmissionControl
from .brain_core.addon_audio_pipeline import AddonAudioChannel, AddonAudioPipeline
from .brain_core.addon_channel_state import AddonChannelState
from .brain_core.addon_manager import AddonManager
from .brain_core.addon_registry import AddonRegistry
from .brain_core.bg1_queue import BG1Queue
from .brain_core.cllm_renderer import CLLMRenderer
from .brain_core.conversation_buffer import ConversationBuffer
from .brain_core.fallback_policy import FallbackPolicy
from .brain_core.ingress_hub import IngressHub
from .brain_core.ingress_normalizer import IngressNormalizer
from .brain_core.intent_handlers import (
    build_default_registry,
    handle_greeting,
    handle_help,
    handle_recall_name,
)
from .brain_core.contracts import (
    TurnArtifact,
    VerifiedFact,
    LLMDerivedResult,
)
from .brain_core.job_status_service import JobStatusService
from .brain_core.lane_coordinator import LaneCoordinator
from .brain_core.output_coordinator import OutputCoordinator
from .brain_core.prompt_dispatcher import PromptDispatcher, TaskDecision
from .brain_core.response_compiler import ResponseCompiler
from .brain_core.realtime_lane import RealtimeLane
from .brain_core.speech_formatter import SpeechFormatter
from .brain_core.tool_orchestrator import ToolOrchestrator
from .brain_core.runtime_v2 import RuntimeV2Mixin
from .brain_core.tool_router import ToolRouter
from .brain_core.route_trace import RouteTraceLogger
from .brain_core.voice_response_policy import VoiceResponsePolicy
from .config import build_default_config, capability_map
from .crsis.engine import CRSISEngine
from .memory import Memory
from .models.workspace_inputs import resolve_workspace_root
from .models.ollama_client import OllamaClient
from .observability.events import EventRecord, PersistentEventLogger
from .specialists.specialist_code import run as run_specialist_code
from .specialists.specialist_vision import run as run_specialist_vision
from .tools.sys_info import get_hardware_info
from .tools.app_ops import focus as focus_app
from .tools.app_ops import launch as launch_app
from .tools.volume_control import set_volume, get_volume
from .tools.system_health import get_thermal_status
from .tools.web_scrape_chromium import scrape as scrape_chromium
from .tools.web_crawl_chromium import crawl as crawl_chromium
from .tools.calculator import evaluate as calculate_expression
from .tools.code_runner import run_python
from .tools.file_write import write as write_file
from .tools import job_status_tool
from .tools.time_tool import local_now, utc_now_iso
from .voice.tts import TTS
from .brain_core.contracts import RawEvent
from .world_model import (
    WorldState,
    StateBuilder,
    EvidenceStore,
    Judge,
    BeliefState,
    Planner,
    UserProfile,
    DeviceStatus,
)
from .crsis.satisfaction_detector import SatisfactionDetector
from .crsis.detectors.intent_miss import IntentMissDetector


logger = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    started: bool = False
    shutdown: bool = False
    degraded_mode: bool = False


@dataclass
class PendingMemoryWipe:
    stage: int = 1
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class PendingTitleClarification:
    name: str
    gender_class: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class TurnExecutionResult:
    lane: str
    text: str
    resolved_by: str
    brain_items: list[str] = field(default_factory=list)
    tool_summaries: list[str] = field(default_factory=list)
    tool_facts: list[VerifiedFact | LLMDerivedResult] = field(default_factory=list)
    memory_items: list[str] = field(default_factory=list)
    job_snapshot: dict | None = None
    renderer_constraints: list[str] = field(default_factory=list)
    renderer_tone: str = "helpful"
    renderer_length_hint: str = "short"
    conversation_user_text: str | None = None
    sensitive_input: bool = False


class JarvisRuntime(RuntimeV2Mixin):
    def __init__(self) -> None:
        # Config first - needed by Phase 2 mixin
        self.config = build_default_config()
        self.state = RuntimeState()
        self.events = PersistentEventLogger(log_dir=self.config.events_log_dir)
        self.conversation_buffer = ConversationBuffer(
            max_turns=self.config.conversation_buffer_max_turns
        )
        self.ingress_hub = IngressHub()
        self.normalizer = IngressNormalizer(profile_mapper=self._resolve_profile)
        self.lane_coordinator = LaneCoordinator()
        self.admission_control = AdmissionControl(
            max_active_jobs=self.config.bg1_max_active_jobs,
            max_queue_length=self.config.bg1_max_queue_length,
        )
        self.bg1_queue = BG1Queue(
            max_active=self.config.bg1_max_active_jobs,
            max_queue=self.config.bg1_max_queue_length,
            ttl_seconds=self.config.bg1_queue_ttl_seconds,
        )
        self.realtime_lane = RealtimeLane()
        self.intent_registry = build_default_registry()
        self.job_status = JobStatusService()
        self.memory = Memory(db_path=self.config.memory_db_path)

        # CRSIS Concept D integration - WorldState and state management (must be before ResponseCompiler/ToolOrchestrator)
        self._world_state_lock = threading.Lock()
        self._world_state = self._create_initial_world_state()
        self._state_builder = StateBuilder()
        self._evidence_store = EvidenceStore()
        self._judge = Judge()
        self._belief_state = BeliefState()
        self._planner = Planner()
        self._satisfaction_detector = SatisfactionDetector()
        self._intent_miss_detector = IntentMissDetector()
        self._crsis_engine = CRSISEngine()

        self.response_compiler = ResponseCompiler(
            max_packet_tokens=self.config.renderer_max_packet_tokens,
            judge=self._judge,
            evidence_store=self._evidence_store,
        )
        self.speech_formatter = SpeechFormatter()
        self.renderer = CLLMRenderer(
            model_preferred=self.config.renderer_model_preferred,
            model_fallback=self.config.renderer_model_fallback,
        )
        self.realtime_reasoner_preferred = OllamaClient(
            model=self.config.renderer_model_preferred,
            timeout_seconds=30,
        )
        self.realtime_reasoner_fallback = OllamaClient(
            model=self.config.renderer_model_fallback,
            timeout_seconds=30,
        )
        self.fallback_policy = FallbackPolicy()
        self.tool_orchestrator = ToolOrchestrator(evidence_store=self._evidence_store)
        self.dispatcher = PromptDispatcher(
            wake_word=self.config.wake_word_phrase,
            wake_word_enabled=self.config.wake_word_enabled,
            tool_registry=self.tool_orchestrator._tool_registry,
        )

        # Initialize Phase 2 components (debug_trace, bg1_narrator, memory_namespaces, tool_policy)
        RuntimeV2Mixin._init_phase2_components(self)

        self._register_default_tools()
        self._register_intent_miss_tool()
        self.output_coordinator = OutputCoordinator()
        self.tts = TTS(output_device_id=self.config.audio_output_device_id)
        self.addon_registry = AddonRegistry()
        self.addon_manager = AddonManager(self.addon_registry)
        self.addon_channel_state = AddonChannelState()
        self.addon_audio_pipeline = AddonAudioPipeline(
            self.ingress_hub.accept_raw_event
        )
        self._bootstrap_reference_addons()
        self._register_default_addon_channel()
        # Phase 8: Init TTS state machine (wraps self.tts with watchdog/retry)
        self._init_tts_state_machine()
        # Phase 10: Build self-knowledge index
        try:
            self.self_knowledge.build()
        except Exception as e:
            self.debug_trace.log(
                "startup",
                "error",
                {"message": "Self-knowledge index build failed", "error": str(e)},
            )
        # Phase 3: Tool-first router (consults ToolPolicy for routing)
        self.tool_router = ToolRouter(tool_policy=self.tool_policy)
        # Phase 9: Route trace logger for observability
        self.route_trace_logger = RouteTraceLogger(
            log_dir=getattr(self.config, "logs_dir", "./logs"),
        )
        # Phase 6: Voice response policy for spoken output shaping
        self.voice_response_policy = VoiceResponsePolicy()
        from jarvis.brain_core.conversation_manager import ConversationManager

        self.conversation = ConversationManager(self)
        from jarvis.brain_core.turn_pipeline import TurnPipeline

        self.turn_pipeline = TurnPipeline(self)
        from jarvis.brain_core.bg1_manager import BG1Manager

        self.bg1_manager = BG1Manager(self)
        from jarvis.observability.health_monitor import HealthMonitor

        self.health_monitor = HealthMonitor(self)
        self._model_keepalive_stop = threading.Event()
        self._model_keepalive_thread: threading.Thread | None = None
        self._renderer_model_preloaded = False
        self._last_turn_latency_ms = 0.0
        self._recent_turn_latency_ms: list[float] = []

    def _register_default_tools(self) -> None:
        self.tool_orchestrator.register_tool("local_now", local_now)
        self.tool_orchestrator.register_tool("utc_now_iso", utc_now_iso)
        self.tool_orchestrator.register_tool("calculator", calculate_expression)

        def run_web_fetch(url: str) -> str:
            from jarvis.tools.browser_runtime import fetch_rendered_page

            return str(fetch_rendered_page(url))

        self.tool_orchestrator.register_tool(
            "web_fetch", run_web_fetch, capability="browser_runtime"
        )

    def _register_intent_miss_tool(self) -> None:
        """Register tools for querying intent miss data (Task J)."""

        def _get_intent_misses(limit: int = 20) -> dict:
            """Get recent intent misses."""
            misses = self._intent_miss_detector.get_misses(limit=limit)
            return {
                "ok": True,
                "misses": [
                    {
                        "turn_id": m.turn_id,
                        "utterance": m.utterance,
                        "routed_intent": m.routed_intent,
                        "miss_reason": m.miss_reason,
                        "timestamp": m.timestamp,
                    }
                    for m in misses
                ],
                "count": len(misses),
            }

        def _get_intent_miss_stats() -> dict:
            """Get intent miss statistics."""
            return {"ok": True, **self._intent_miss_detector.get_stats()}

        def _get_intent_miss_patterns(min_count: int = 3) -> dict:
            """Get aggregated intent miss patterns."""
            patterns = self._intent_miss_detector.get_patterns(min_count=min_count)
            return {
                "ok": True,
                "patterns": [
                    {
                        "pattern_id": p.pattern_id,
                        "utterance_pattern": p.utterance_pattern,
                        "miss_count": p.miss_count,
                        "severity": p.severity,
                        "expected_intent": p.expected_intent,
                    }
                    for p in patterns
                ],
                "count": len(patterns),
            }

        self.tool_orchestrator.register_tool("intent_miss_get", _get_intent_misses)
        self.tool_orchestrator.register_tool(
            "intent_miss_stats", _get_intent_miss_stats
        )
        self.tool_orchestrator.register_tool(
            "intent_miss_patterns", _get_intent_miss_patterns
        )

        def _file_write_tool(
            path: str, content: str, workspace_root: str | None = None
        ) -> dict:
            root = workspace_root or str(resolve_workspace_root())
            return write_file(path, content, workspace_root=root)

        self.tool_orchestrator.register_tool(
            "file_write",
            _file_write_tool,
            capability="file_write",
            confirmation_action="file_write",
        )
        self.tool_orchestrator.register_tool(
            "code_runner",
            run_python,
            capability="code_runner",
            confirmation_action="code_runner",
        )
        self.tool_orchestrator.register_tool(
            "app_launch",
            launch_app,
            capability="app_ops",
            confirmation_action="app_ops",
        )
        self.tool_orchestrator.register_tool(
            "app_focus",
            focus_app,
            capability="app_ops",
            confirmation_action="app_ops",
        )
        self.tool_orchestrator.register_tool("set_volume", set_volume)
        self.tool_orchestrator.register_tool("get_volume", get_volume)
        self.tool_orchestrator.register_tool("get_thermal_status", get_thermal_status)
        self.tool_orchestrator.register_tool("web_scrape_chromium", scrape_chromium)
        self.tool_orchestrator.register_tool("web_crawl_chromium", crawl_chromium)

    def _bootstrap_reference_addons(self) -> None:
        try:
            from addons.discord_addon.manifest import (
                build_manifest as build_discord_manifest,
            )
        except Exception as e:
            self.debug_trace.log(
                "addon_bootstrap",
                "error",
                {"message": "Discord addon manifest load failed", "error": str(e)},
            )
            return

        try:
            from addons.discord_addon.permissions import (
                map_identity_to_profile as discord_permission_mapper,
            )
        except Exception as e:
            self.debug_trace.log(
                "addon_bootstrap",
                "error",
                {"message": "Discord permission mapper load failed", "error": str(e)},
            )
            discord_permission_mapper = None

        manifest = build_discord_manifest()
        self.addon_manager.discover([manifest])
        self.addon_manager.load(manifest.addon_id)
        for sink_id in manifest.output_sinks:
            self.addon_registry.register_output_sink(
                sink_id, {"addon_id": manifest.addon_id, "sink_id": sink_id}
            )
        for channel_id in manifest.audio_channels:
            self.addon_registry.register_audio_channel(
                channel_id, {"addon_id": manifest.addon_id, "channel_id": channel_id}
            )
        if discord_permission_mapper is not None:
            self.addon_registry.register_permission_mapper(
                manifest.addon_id, discord_permission_mapper
            )

    def _register_default_addon_channel(self) -> None:
        channel = AddonAudioChannel(
            channel_id="addon_channel_1",
            addon_id="system",
            enabled=False,
            listening=False,
        )
        self.addon_audio_pipeline.register_channel(channel)

    def _create_initial_world_state(self) -> WorldState:
        """Create initial WorldState with default user profile and device status."""
        from jarvis.crsis.contracts import utc_now_iso

        return WorldState(
            timestamp=utc_now_iso(),
            user_profile=UserProfile(user_id="default"),
            task_stack=[],
            open_bg1_jobs=[],
            tool_availability={},
            model_availability={},
            device_status=DeviceStatus.all_inactive(),
            recent_turn_confidences=[],
            aggregate_confidence=1.0,
            failure_log=[],
        )

    def startup(self, model_ready: bool = True) -> RuntimeState:
        self.state.started = True
        if not model_ready:
            self.state.degraded_mode = True
            os.environ["JARVIS_DEGRADED_MODE"] = "true"
        else:
            self.state.degraded_mode = False
            os.environ["JARVIS_DEGRADED_MODE"] = "false"
            self.turn_pipeline._preload_realtime_model()
            self.turn_pipeline._start_model_keepalive()
        
        self._seed_hardware_info()
        
        crsis = self.turn_pipeline._evaluate_and_persist_crsis(
            source="runtime_startup",
            turn_id="startup",
            lane_decision="n/a",
            resolved_by="template",
        )
        self.events.emit(
            EventRecord.build(
                event_type="runtime_startup",
                turn_id="startup",
                lane_decision="n/a",
                resolved_by="template",
                elapsed_ms=1,
                degraded_mode_active=self.state.degraded_mode,
                crsis_status=crsis["status"],
                crsis_findings=crsis["findings"],
                crsis_snapshot_jsonl=crsis["jsonl_path"],
                crsis_snapshot_latest=crsis["latest_path"],
            )
        )
        return self.state

    def run_turn(self, text: str, source: str = "local_mic") -> dict:
        return self.turn_pipeline.run_turn(text, source)

    def shutdown(self) -> RuntimeState:
        self.state.shutdown = True
        self.bg1_manager.join(timeout=2.0)
        active_thread = None
        self._model_keepalive_stop.set()
        if (
            self._model_keepalive_thread is not None
            and self._model_keepalive_thread.is_alive()
        ):
            self._model_keepalive_thread.join(timeout=2.0)
        if active_thread is not None and active_thread.is_alive():
            active_thread.join(timeout=2.0)
        for channel_id in list(self.addon_audio_pipeline.channels.keys()):
            self.addon_audio_pipeline.set_channel_enabled(channel_id, False)
        for addon_id in list(self.addon_manager.states.keys()):
            self.addon_manager.disable(addon_id)
            self.addon_manager.unload(addon_id)
        crsis = self.turn_pipeline._evaluate_and_persist_crsis(
            source="runtime_shutdown",
            turn_id="shutdown",
            lane_decision="n/a",
            resolved_by="template",
        )
        self.events.emit(
            EventRecord.build(
                event_type="runtime_shutdown",
                turn_id="shutdown",
                lane_decision="n/a",
                resolved_by="template",
                elapsed_ms=1,
                degraded_mode_active=self.state.degraded_mode,
                crsis_status=crsis["status"],
                crsis_findings=crsis["findings"],
                crsis_snapshot_jsonl=crsis["jsonl_path"],
                crsis_snapshot_latest=crsis["latest_path"],
            )
        )
        return self.state

    def invoke_tool(
        self, name: str, *, profile: str = "owner", confirmed: bool = False, **kwargs
    ) -> dict:
        metadata = self.tool_orchestrator.metadata(name)
        capability = metadata.get("capability")
        if capability and not self._capabilities_for_profile(profile).get(
            capability, False
        ):
            return {
                "ok": False,
                "reason": "capability_denied",
                "profile": profile,
                "capability": capability,
            }

        result = self.tool_orchestrator.execute(name, confirmed=confirmed, **kwargs)
        return {
            "ok": result.ok,
            "summary": result.summary,
            "data": result.data,
            "retryable": result.retryable,
            "safety_flags": result.safety_flags,
            "elapsed_ms": result.elapsed_ms,
        }

    def _execute_realtime(self, env, decision: TaskDecision) -> TurnExecutionResult:
        capabilities = self._capabilities_for_profile(env.profile)
        services = {
            "memory": self.memory_namespaces,
            "tool_orchestrator": self.tool_orchestrator,

            "job_status": self.job_status,
            "job_status_tool": job_status_tool,
            "realtime_lane": self.realtime_lane,
            "last_bg1_result": self.bg1_manager.get_last_result(),
            "addon_manager": self.addon_manager,
            "addon_registry": self.addon_registry,
            "profile": env.profile,
            "capabilities": capabilities,
            "deny_capability": self._deny_capability,
            "run_code_specialist": lambda task: run_specialist_code(
                task, model=self.config.code_bg1_model
            ),
            "run_vision_specialist": lambda task: run_specialist_vision(
                task, model=self.config.vision_lite_model
            ),
            "remember_owner_name": self.conversation._remember_owner_name_profile,
            "runtime_health": self.runtime_health_snapshot,
            # Phase 10: Self-knowledge index for tool/codebase/architecture queries
            "self_knowledge": self.self_knowledge,
            # Phase 5: Memory namespaces for task result retrieval
            "memory_namespaces": self.memory_namespaces,
            # Phase 9: Recent latencies for performance queries
            "recent_latencies": list(self._recent_turn_latency_ms),
        }

        pending_wipe = self.conversation.handle_memory_wipe_flow(env, services)
        if pending_wipe is not None:
            return pending_wipe

        pending_creator = self.conversation.handle_creator_verification_flow(env)
        if pending_creator is not None:
            return pending_creator

        pending_title = self.conversation.handle_title_clarification_flow(env, services)
        if pending_title is not None:
            return pending_title

        onboarding = self.conversation.handle_owner_onboarding(env, services)
        if onboarding is not None:
            return onboarding

        creator_claim = self.conversation.handle_creator_claim(env)
        if creator_claim is not None:
            return creator_claim

        creator_context = self.conversation.handle_creator_context(env)
        if creator_context is not None:
            return creator_context

        # Phase 1a: _handle_performance_context bypass REMOVED.
        # Performance queries now route through the intent registry to
        # handle_performance_query in intent_handlers.py, which checks
        # job status, reads actual latency data, and returns richer answers.

        result = self.intent_registry.resolve(env, decision, services)
        if result is not None:
            return self._maybe_promote_to_renderer(result, decision)

        text_lower = env.text.lower()

        if decision.intent == "recall_name" or "my name" in text_lower:
            recall_result = handle_recall_name(env, decision, services)
            if recall_result is not None:
                return self._maybe_promote_to_renderer(recall_result, decision)

        greeting_result = handle_greeting(env, decision, services)
        if greeting_result is not None:
            return greeting_result

        help_result = handle_help(env, decision, services)
        if help_result is not None:
            return self._maybe_promote_to_renderer(help_result, decision)

        if decision.intent == "general_chat":
            answer = self.turn_pipeline._generate_general_chat_reply(env.text)
            if answer:
                return TurnExecutionResult(
                    lane="realtime",
                    text=answer,
                    resolved_by="model_reasoning",
                )

        realtime = self.realtime_lane.handle(env)
        return TurnExecutionResult(
            lane="realtime",
            text=realtime.text,
            resolved_by=realtime.resolved_by,
        )

    def _execute_heavy(self, env, decision: TaskDecision) -> TurnExecutionResult:
        return self.bg1_manager.execute_heavy(env, decision)

    def _maybe_promote_to_renderer(
        self, result: TurnExecutionResult, decision: TaskDecision
    ) -> TurnExecutionResult:
        # ONLY promote if it's currently tool_only. 
        # If it's already template or something else, leave it alone.
        if result.resolved_by != "tool_only":
            return result
        has_owner_memory = any(
            item.startswith(
                (
                    "user_name:",
                    "user_age:",
                    "user_address_preference:",
                    "user_name_gender:",
                    "user_title_preference:",
                )
            )
            for item in result.memory_items
        )
        if (
            decision.intent
            not in {
                "owner_memory",
                "help_query",
                "self_query",
                "codebase_query",
                "screen_query",
                "wellbeing_query",
                "recall_name",
                "greeting",
            }
        ):
            return result
        return TurnExecutionResult(
            lane=result.lane,
            text=result.text,
            resolved_by="tool_plus_renderer",
            brain_items=result.brain_items or [result.text],
            tool_summaries=result.tool_summaries,
            memory_items=result.memory_items,
            job_snapshot=result.job_snapshot,
            renderer_constraints=result.renderer_constraints,
            renderer_tone=result.renderer_tone,
            renderer_length_hint=result.renderer_length_hint,
            conversation_user_text=result.conversation_user_text,
            sensitive_input=result.sensitive_input,
        )

    def record_voice_observation(
        self,
        *,
        audio_capture_ok: bool | None,
        transcribe_ok: bool | None,
        fallback_reason: str = "",
    ) -> None:
        self.health_monitor.record_voice_observation(
            audio_capture_ok=audio_capture_ok,
            transcribe_ok=transcribe_ok,
            fallback_reason=fallback_reason,
        )

    def runtime_health_snapshot(self) -> dict[str, object]:
        return self.health_monitor.runtime_health_snapshot()

    def _resolve_profile(self, raw_event: RawEvent) -> str:
        if raw_event.source == "local_mic":
            return "owner"

        if raw_event.addon_id:
            mapper = self.addon_registry.permission_mappers.get(raw_event.addon_id)
            if mapper is not None:
                try:
                    profile = str(mapper(raw_event.speaker_id))
                except Exception as e:
                    self.debug_trace.log(
                        "profile",
                        "error",
                        {
                            "message": "Addon permission mapper call failed",
                            "error": str(e),
                        },
                    )
                    profile = "guest"
                if profile in self.config.permission_profiles:
                    return profile
                return "guest"

        if raw_event.source == "addon":
            return "guest"
        return "guest"

    def _capabilities_for_profile(self, profile: str) -> dict[str, bool]:
        all_caps = capability_map()
        return dict(all_caps.get(profile, all_caps["guest"]))

    def _deny_capability(self, capability: str) -> TurnExecutionResult:
        messages = {
            "memory_save": "I cannot save memories from your current permission profile.",
            "addon_control": "I cannot change addon state from your current permission profile.",
            "cancel_heavy_task": "I cannot cancel heavy tasks from your current permission profile.",
            "heavy_tasks": "I cannot start heavy tasks from your current permission profile.",
        }
        text = messages.get(
            capability,
            "That action is not allowed from your current permission profile.",
        )
        return TurnExecutionResult(
            lane="realtime",
            text=text,
            resolved_by="tool_only",
        )

    def _build_sink_status(
        self,
        *,
        source: str,
        addon_id: str | None = None,
        channel_id: str | None = None,
    ) -> dict[str, bool]:
        return {
            "local_voice": self._local_voice_sink_available(),
            "discord_voice": self._discord_voice_sink_available(source=source),
            "discord_text": self._discord_text_sink_available(
                source=source, addon_id=addon_id
            ),
            "active_addon_text": self._active_addon_text_sink_available(
                channel_id=channel_id
            ),
            "local_text_log": self._local_text_log_sink_available(),
        }

    def _select_sink(self, source: str) -> str:
        sink_by_source = {
            "local_mic": "local_voice",
            "local_text": "local_text_log",
            "discord_voice": "discord_voice",
            "discord_text": "discord_text",
        }
        return sink_by_source.get(source, "local_voice")

    def _local_voice_sink_available(self) -> bool:
        return self.state.started and not self.state.shutdown and self.tts is not None

    def _discord_voice_sink_available(self, *, source: str) -> bool:
        if source == "discord_voice":
            return True

        channel = self.addon_audio_pipeline.channels.get("discord_voice")
        if channel is None:
            return False
        return (
            channel.enabled
            and self.addon_manager.states.get(channel.addon_id) == "ENABLED"
        )

    def _discord_text_sink_available(
        self, *, source: str, addon_id: str | None
    ) -> bool:
        if source == "discord_text" or addon_id == "discord":
            return True

        sink_registered = "discord_text_sink" in self.addon_registry.output_sinks
        return sink_registered and self.addon_manager.states.get("discord") == "ENABLED"

    def _active_addon_text_sink_available(self, *, channel_id: str | None) -> bool:
        snapshot = self.addon_channel_state.snapshot()
        if channel_id and channel_id in snapshot:
            channel = snapshot[channel_id]
            return (
                bool(channel.get("enabled"))
                and channel.get("output_target") == "active_addon_text"
            )

        return any(
            bool(channel.get("enabled"))
            and channel.get("output_target") == "active_addon_text"
            for channel in snapshot.values()
        )

    def _local_text_log_sink_available(self) -> bool:
        path = self._local_text_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8"):
                pass
        except OSError:
            return False
        return True

    def _local_text_log_path(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return Path(self.config.events_log_dir) / f"jarvis_output_{stamp}.jsonl"

    def _append_local_text_log(self, *, text: str, turn_id: str, source: str) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "turn_id": turn_id,
            "source": source,
            "sink": "local_text_log",
            "text": text,
        }
        path = self._local_text_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _bg1_is_busy(self) -> bool:
        return self.bg1_queue.is_busy() or self.job_status.get_current() is not None

    def _bg1_is_saturated(self) -> bool:
        return self.bg1_manager.is_busy()

    def _conversation_context_lines(self, limit: int = 5) -> list[str]:
        recent_turns = self.conversation_buffer.recent(limit)
        return [
            f"user:{turn.user_text} | intent:{turn.intent} | assistant:{turn.response_summary}"
            for turn in recent_turns
        ]

    def _summarize_for_context(self, text: str, max_words: int = 18) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]) + "..."

    def _compute_turn_confidence(self, resolved_by: str, lane: str) -> float:
        """Compute confidence score for a turn based on resolution and lane."""
        # Higher confidence for successful resolutions
        confidence_map = {
            "tool_plus_renderer": 0.9,
            "tool_only": 0.85,
            "fallback_template": 0.4,
            "fallback_policy": 0.5,
        }
        base_confidence = confidence_map.get(resolved_by, 0.5)

        # Lane adjustment - realtime is more predictable
        lane_adjustment = 0.05 if lane == "realtime" else -0.05

        return max(0.0, min(1.0, base_confidence + lane_adjustment))

    def _extract_tool_name(self, summary: str) -> str | None:
        """Extract tool name from tool summary string."""
        # Simple extraction: assume format "tool_name executed"
        parts = summary.split()
        if parts:
            return parts[0]
        return None

    def _update_belief_state(
        self,
        turn_id: str,
        intent: str,
        resolved_by: str,
        tool_summaries: list[str],
        memory_items: list[str],
    ) -> None:
        """Update BeliefState with new inferences and detect conflicts.

        Creates beliefs from:
        - Intent classifications (inference beliefs)
        - Tool results (observed beliefs)
        - Memory recalls (recalled beliefs)
        """
        from jarvis.world_model.belief_state import Belief

        # Create belief from intent classification
        intent_belief = Belief(
            belief_id=f"belief_intent_{turn_id}",
            content=f"User intent classified as '{intent}'",
            belief_type="inference",
            confidence=0.8
            if resolved_by in ("tool_plus_renderer", "tool_only")
            else 0.5,
            basis=[f"evidence_intent_{turn_id}"],
            contradicts=[],
            expires_at=None,
        )
        self._belief_state.add(intent_belief)

        # Create beliefs from tool results (observed)
        for i, summary in enumerate(tool_summaries):
            tool_belief = Belief(
                belief_id=f"belief_tool_{turn_id}_{i}",
                content=summary,
                belief_type="inference",
                confidence=0.9,
                basis=[f"evidence_tool_{turn_id}_{i}"],
                contradicts=[],
            )
            self._belief_state.add(tool_belief)

        # Create beliefs from memory recalls
        for i, item in enumerate(memory_items):
            memory_belief = Belief(
                belief_id=f"belief_memory_{turn_id}_{i}",
                content=item,
                belief_type="inference",
                confidence=0.7,
                basis=[f"evidence_memory_{turn_id}_{i}"],
                contradicts=[],
            )
            self._belief_state.add(memory_belief)

        # Check for conflicts and log if found
        conflicts = self._belief_state.get_conflicts()
        if conflicts:
            for conflict in conflicts:
                logger.warning(
                    f"Belief conflict detected ({conflict.severity}): {conflict.conflict_type} "
                    f"between {conflict.belief1_id} and {conflict.belief2_id} (Turn {turn_id})"
                )

    def _generate_and_execute_plan(
        self,
        turn_id: str,
        intent: str,
    ) -> None:
        """Generate action plan from WorldState using Planner.

        Phase 5C: Single-action, realtime-lane tool_call plans are now
        executed deterministically.  Multi-action or bg1-only plans are
        still only logged.
        """

        # Only plan for heavy intents or when tasks are pending
        if intent not in ("heavy", "bg1") and not self._world_state.task_stack:
            return

        # Build planning context
        class SimplePlanningContext:
            def __init__(self, world_state, jarvis):
                self.world_state = world_state
                self.available_tools = list(jarvis.tool_orchestrator._tools.keys())
                self.available_models = ["llama3.2:1b", "llama3.2:3b"]

        context = SimplePlanningContext(self._world_state, self)

        # Generate plan
        plan = self._planner.generate_plan(context)

        if not plan.actions:
            return

        # Log plan for observability
        action_summary = [
            (a.action_id, a.action_type, a.target) for a in plan.get_ordered_actions()
        ]
        self.events.emit(
            EventRecord.build(
                event_type="plan_generated",
                turn_id=turn_id,
                plan_id=f"plan_{turn_id}",
                actions=action_summary,
                estimated_duration_ms=int(
                    plan.estimated_duration.total_seconds() * 1000
                ),
            )
        )

        # Phase 5C: Execute single-action realtime tool_call plans
        if len(plan.actions) == 1:
            action = plan.actions[0]
            if (
                action.action_type == "tool_call"
                and action.target in self.tool_orchestrator._tools
            ):
                meta = self.tool_orchestrator.get_tool_metadata(action.target)
                if meta and meta.safe_in_realtime and not meta.requires_confirmation:
                    result = self.tool_orchestrator.execute(
                        action.target, **action.payload
                    )
                    self.events.emit(
                        EventRecord.build(
                            event_type="plan_action_executed",
                            turn_id=turn_id,
                            action_id=action.action_id,
                            tool_name=action.target,
                            ok=result.ok,
                            summary=result.summary[:200],
                        )
                    )

    def _detect_and_log_satisfaction(
        self,
        user_message: str,
        turn_id: str,
        follow_up_window_active: bool,
    ) -> None:
        """Detect user satisfaction signals and log to event stream."""
        # Build conversation history for context
        conversation_history = []
        for turn in self.conversation_buffer.recent(6):
            conversation_history.append({"role": "user", "content": turn.user_text})
            conversation_history.append(
                {"role": "assistant", "content": turn.response_summary}
            )

        # Detect satisfaction signal
        result = self._satisfaction_detector.detect(
            user_message=user_message,
            conversation_history=conversation_history,
            follow_up_window_active=follow_up_window_active,
        )

        if result.signal:
            # Log satisfaction signal to event stream
            from jarvis.world_model.state_builder import (
                EventRecord as StateBuilderEvent,
            )
            from jarvis.crsis.contracts import utc_now_iso

            self._state_builder.store_event(
                StateBuilderEvent(
                    event_id=f"satisfaction_{utc_now_iso()}_{turn_id}",
                    event_type="satisfaction_signal",
                    payload={
                        "turn_id": turn_id,
                        "signal_type": result.signal.signal_type,
                        "confidence": result.signal.confidence,
                        "evidence": result.signal.evidence,
                        "raw_indicators": result.raw_indicators,
                    },
                    timestamp=utc_now_iso(),
                    turn_id=turn_id,
                )
            )

            # Update WorldState with satisfaction event
            with self._world_state_lock:
                self._world_state = self._state_builder.reconstruct_state(self._world_state)

    def run_crsis_loop(
        self,
        analysis_window_hours: int = 24,
        auto_apply_threshold: float = 0.95,
        dry_run: bool = False,
        require_approval: bool = True,
    ) -> dict:
        """Run the CRSIS self-improvement loop.

        This is the entry point for manual CRSIS loop execution via CLI.

        Args:
            analysis_window_hours: Hours of logs to analyze (default: 24)
            auto_apply_threshold: Confidence threshold for auto-apply (default: 0.95)
            dry_run: Generate proposals without applying (default: False)
            require_approval: Require human approval before applying (default: True)

        Returns: dict with loop execution statistics
        """
        from jarvis.maintenance.crsis_automation import CRSISAutomation, CRSISLoopConfig
        from pathlib import Path

        config = CRSISLoopConfig(
            analysis_window_hours=analysis_window_hours,
            auto_apply_threshold=auto_apply_threshold,
            dry_run=dry_run,
            require_approval=require_approval,
        )

        # Pass the event logger to CRSIS automation
        automation = CRSISAutomation(
            project_root=Path.cwd(),
            event_log=self.events,
        )

        result = automation.run_loop(config)

        return {
            "patterns_detected": result.patterns_detected,
            "proposals_generated": result.proposals_generated,
            "auto_applied": result.auto_applied,
            "applied_successfully": result.applied_successfully,
            "rolled_back": result.rolled_back,
        }

    def _seed_hardware_info(self) -> None:
        """Collect and store hardware and system facts in memory."""
        try:
            # System basic info
            self.memory.pockets.set_slot("self:jarvis", "python_version", sys.version.split()[0])
            self.memory.pockets.set_slot("self:jarvis", "os_platform", sys.platform)
            
            # Hardware discovery
            hw = get_hardware_info()
            if hw.get("cpu_cores"):
                self.memory.pockets.set_slot("self:jarvis", "cpu_cores", str(hw["cpu_cores"]))
            if hw.get("ram_total_gb"):
                self.memory.pockets.set_slot("self:jarvis", "ram_gb", str(hw["ram_total_gb"]))
            
            # GPU info
            for i, gpu in enumerate(hw.get("gpus", [])):
                self.memory.pockets.set_slot("self:jarvis", f"gpu_{i}_name", gpu["name"])
                self.memory.pockets.set_slot("self:jarvis", f"gpu_{i}_vram_gb", str(gpu["vram_total_gb"]))
                
        except Exception as e:
            logger.error(f"Failed to seed hardware info: {e}")

    def get_world_state(self) -> WorldState:
        """Get the current WorldState."""
        return self._world_state

    def get_evidence_store(self) -> EvidenceStore:
        """Get the EvidenceStore."""
        return self._evidence_store

    def get_judge(self) -> Judge:
        """Get the Judge."""
        return self._judge

    def get_belief_state(self) -> BeliefState:
        """Get the BeliefState."""
        return self._belief_state

    def get_planner(self) -> Planner:
        """Get the Planner."""
        return self._planner
