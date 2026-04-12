from __future__ import annotations
import asyncio
import threading
import time
import os
from datetime import datetime, timezone
from dataclasses import asdict
from jarvis.crsis.contracts import CRSISSignal
from jarvis.crsis.engine import persist_snapshot
from jarvis.brain_core.turn_state_machine import TurnStateMachine
from jarvis.brain_core.contracts import RawEvent
from jarvis.brain_core.contracts import RenderedReply
from jarvis.brain_core.route_trace import RouteDecisionRecord, RouteCandidateRecord
from jarvis.brain_core.conversation_buffer import TurnSummary
from jarvis.observability.events import EventRecord

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.main import JarvisRuntime


class TurnPipeline:
    def __init__(self, runtime: JarvisRuntime):
        self.runtime = runtime

    def run_turn(self, text: str, source: str = "local_mic") -> dict:
        turn_started = time.monotonic()
        turn_start_perf = time.perf_counter()
        sm = TurnStateMachine()
        _timing_verbose = os.environ.get("JARVIS_TIMING_VERBOSE", "") == "1"

        def _ts(msg):
            elapsed = (time.perf_counter() - turn_start_perf) * 1000
            self.runtime.debug_trace.log(
                "timing",
                "stage_complete",
                {"message": msg, "elapsed_ms": round(elapsed, 1)},
            )
            if _timing_verbose:
                print(f"  [timing] {elapsed:7.0f}ms | {msg}", flush=True)

        _ts(f"=== TURN START: {text[:50]} ===")
        env = self.runtime.normalizer.normalize(
            RawEvent(source=source, speaker_id="owner", channel="local", payload=text)
        )
        artifact = self.runtime._start_turn_v2(
            turn_id=env.turn_id, raw_text=text, source=source
        )
        sm.transition("INGRESS_RECEIVED")
        _ts("After normalize/_start_turn_v2")
        stage_start = time.monotonic() * 1000
        ingress_end = time.perf_counter()
        _ts(f"Ingress/normalize: {(ingress_end - turn_start_perf) * 1000:.0f}ms")
        self.runtime.ingress_hub.accept_raw_event(
            RawEvent(source=source, speaker_id="owner", channel="local", payload=text)
        )
        self.runtime._record_stage_v2(
            "ingress", stage_start, time.monotonic() * 1000, {"source": source}
        )
        stage_start = time.monotonic() * 1000
        artifact.normalized_text = env.text
        artifact.canonical_text = env.text
        self.runtime._record_stage_v2(
            "normalize", stage_start, time.monotonic() * 1000, {"normalized": env.text}
        )
        stage_start = time.monotonic() * 1000
        tokens = env.text.split()
        rewrite = self.runtime._resolve_references_v2(
            normalized_text=env.text, tokens=tokens
        )
        artifact.context_rewrite = rewrite.rewritten
        artifact.context_rewrite_reason = rewrite.reason
        self.runtime._record_stage_v2(
            "resolve",
            stage_start,
            time.monotonic() * 1000,
            {"rewritten": rewrite.rewritten},
        )
        routing_text = rewrite.rewritten if rewrite.rewritten else env.text
        cached_decision = self.runtime._check_route_cache_v2(
            routing_text, bg1_busy=self.runtime._bg1_is_saturated()
        )
        if cached_decision is not None:
            decision = cached_decision
            route_cache_hit = True
        else:
            elapsed = (time.monotonic() - turn_started) * 1000
            decision = self.runtime.dispatcher.route(
                text,
                bg1_busy=self.runtime._bg1_is_saturated(),
                elapsed_ms=elapsed,
                world_state=self.runtime.get_world_state(),
            )
            self.runtime._cache_route_decision_v2(
                routing_text, self.runtime._bg1_is_saturated(), decision
            )
            route_cache_hit = False
        tool_route = self.runtime.tool_router.check_tool_first(routing_text)
        if (
            tool_route.matched
            and tool_route.confidence > 0.8
            and (decision.intent == "general_chat")
        ):
            self.runtime._trace_tool_decision(
                tool_name=tool_route.tool_name or "unknown",
                decision="tool_first_override",
                reason=f"confidence={tool_route.confidence:.2f}, overrode general_chat",
            )
        if decision.intent == "general_chat" or decision.reason.startswith(
            "quick_or_general"
        ):
            self.runtime._intent_miss_detector.log_miss(
                turn_id=env.turn_id,
                utterance=env.text,
                normalized_text=decision.normalized_text,
                routed_intent=decision.intent or "unknown",
                match_type=decision.match_type,
                lane=decision.lane,
                miss_reason="fallback_to_general",
                confidence=0.0,
                metadata={"route_reason": decision.reason},
            )
        env = env.replace(
            text=decision.normalized_text,
            metadata={
                **env.metadata,
                "match_type": decision.match_type,
                "route_reason": decision.reason,
                "intent": decision.intent or "",
            },
        )
        artifact.intent = decision.intent or ""
        artifact.chosen_route = decision.lane
        _ts(f"After dispatcher.route (intent={decision.intent}, lane={decision.lane})")
        try:
            route_record = RouteDecisionRecord(
                turn_id=env.turn_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                query=text[:200],
                normalized_query=routing_text[:200],
                selected_source=decision.match_type or "classifier",
                selected_intent=decision.intent or "general_chat",
                selected_lane=decision.lane,
                selected_confidence=tool_route.confidence
                if tool_route.matched
                else 0.5,
                cache_hit=route_cache_hit,
                context_rewrite=rewrite.rewritten
                if rewrite.rewritten != env.text
                else None,
                bg1_busy=self.runtime._bg1_is_saturated(),
            )
            if tool_route.matched:
                route_record.candidates.append(
                    RouteCandidateRecord(
                        source="tool_first",
                        intent=tool_route.reason,
                        lane=tool_route.lane,
                        confidence=tool_route.confidence,
                        reason=tool_route.reason,
                        tool_name=tool_route.tool_name,
                    )
                )
            route_record.candidates.append(
                RouteCandidateRecord(
                    source=decision.match_type or "classifier",
                    intent=decision.intent or "general_chat",
                    lane=decision.lane,
                    confidence=0.5,
                    reason=decision.reason,
                )
            )
            self.runtime.route_trace_logger.record(route_record)
            self.runtime.debug_trace.log_route_decision(
                selected_intent=decision.intent or "general_chat",
                selected_lane=decision.lane,
                selected_source=decision.match_type or "classifier",
                confidence=tool_route.confidence if tool_route.matched else 0.5,
                candidates_count=len(route_record.candidates),
                cache_hit=route_cache_hit,
            )
        except Exception as e:
            self.runtime.debug_trace.log(
                "route", "error", {"message": "Route logging failed", "error": str(e)}
            )
        self.runtime._record_stage_v2(
            "route",
            stage_start,
            time.monotonic() * 1000,
            {"lane": decision.lane, "intent": decision.intent},
        )
        stage_start = time.monotonic() * 1000
        memory_hits = self.runtime._retrieve_memory_v2(query=routing_text, top_k=6)
        artifact.memory_hits = memory_hits
        memory_items = [f"{h.key}: {h.value}" for h in memory_hits]
        _ts(f"After memory retrieval ({len(memory_hits)} hits)")
        self.runtime._record_stage_v2(
            "memory",
            stage_start,
            time.monotonic() * 1000,
            {"hit_count": len(memory_hits)},
        )
        if self.runtime._current_context:
            self.runtime._current_context.chosen_route = decision.lane
            self.runtime._current_context.intent = decision.intent or ""
        sm.transition("ROUTED")
        sm.transition("RUNNING")
        _ts("After ROUTED->RUNNING transitions")
        stage_start = time.monotonic() * 1000
        exec_start = time.perf_counter()
        if decision.lane == "realtime":
            execution = self.runtime._execute_realtime(env, decision)
        else:
            bg1_start = self.runtime._narrate_bg1_start_v2(
                task_subject=artifact.subject, task_type="research"
            )
            if bg1_start:
                self.runtime._append_local_text_log(
                    text=bg1_start, turn_id=env.turn_id, source=env.source
                )
                self.runtime.tts.speak(bg1_start)
            execution = self.runtime._execute_heavy(env, decision)
        exec_elapsed = time.perf_counter() - exec_start
        _ts(f"Lane execution: {exec_elapsed * 1000:.0f}ms (lane={decision.lane})")
        self.runtime._record_stage_v2(
            "tool_exec",
            stage_start,
            time.monotonic() * 1000,
            {"resolved_by": execution.resolved_by},
        )
        artifact.tools_used = (
            execution.tool_summaries if execution.tool_summaries else []
        )
        artifact.tool_summaries = (
            execution.tool_summaries if execution.tool_summaries else []
        )
        stage_start = time.monotonic() * 1000
        llm_start = time.perf_counter()
        conversation_items = self.runtime._conversation_context_lines(limit=5)
        brain_items = (
            execution.brain_items or [execution.text] if execution.text else []
        )
        if execution.resolved_by == "tool_plus_renderer":
            evidence_packet = self.runtime._build_evidence_packet_v2(
                user_text=env.text,
                brain_items=brain_items,
                tool_summaries=execution.tool_summaries or [],
                memory_hits=memory_hits,
                job_snapshot=execution.job_snapshot,
                tool_facts=getattr(execution, "tool_facts", []),
            )
            artifact.evidence_summary = str(evidence_packet)
            artifact.evidence_packet = evidence_packet
            compiled = self.runtime.response_compiler.compile(
                evidence_packet=evidence_packet,
                conversation_items=conversation_items,
                constraints=execution.renderer_constraints,
                tone=execution.renderer_tone,
                length_hint=execution.renderer_length_hint,
                deterministic_fallback=execution.text,
            )
            render_start = time.perf_counter()
            render_result = self.runtime.renderer.render(compiled)
            rendered = render_result["text"]
            artifact.llm_used = render_result["model"]
            
            render_elapsed = time.perf_counter() - render_start
            self.runtime.debug_trace.log(
                "timing",
                "stage_complete",
                {
                    "message": f"LLM render: {render_elapsed * 1000:.0f}ms",
                    "elapsed_ms": round(render_elapsed * 1000, 1),
                },
            )
            if _timing_verbose:
                print(
                    f"  [timing] LLM render: {render_elapsed * 1000:.0f}ms", flush=True
                )
            if decision.lane != "realtime" and execution.job_snapshot:
                bg1_complete = self.runtime._narrate_bg1_completion_v2(
                    result_summary=execution.text,
                    task_subject=artifact.subject,
                    task_type="research",
                )
                if bg1_complete:
                    rendered = bg1_complete + " " + rendered
        else:
            self.runtime.health_monitor.recent_renderer_fallbacks.append(False)
            rendered = execution.text
            render_result = {"text": rendered, "raw_output": "", "model": "none", "elapsed_ms": 0}
        
        llm_elapsed = time.perf_counter() - llm_start
        self.runtime.debug_trace.log(
            "timing",
            "stage_complete",
            {
                "message": f"LLM stage: {llm_elapsed * 1000:.0f}ms (resolved_by={execution.resolved_by})",
                "elapsed_ms": round(llm_elapsed * 1000, 1),
            },
        )
        if _timing_verbose:
            print(
                f"  [timing] LLM stage: {llm_elapsed * 1000:.0f}ms (resolved_by={execution.resolved_by})",
                flush=True,
            )
        resolved_by = execution.resolved_by
        artifact.resolved_by = resolved_by
        self.runtime._record_stage_v2(
            "llm",
            stage_start,
            time.monotonic() * 1000,
            {"compiled": rendered[:100] if rendered else ""},
        )
        stage_start = time.monotonic() * 1000
        tts_start = time.perf_counter()
        spoken = self.runtime.speech_formatter.format(rendered)
        intent_for_policy = decision.intent or "general_chat"
        spoken = self.runtime.voice_response_policy.truncate_for_voice(
            spoken, intent_for_policy
        )
        format_elapsed = time.perf_counter() - tts_start
        self.runtime.debug_trace.log(
            "timing",
            "stage_complete",
            {
                "message": f"Speech format: {format_elapsed * 1000:.0f}ms",
                "elapsed_ms": round(format_elapsed * 1000, 1),
            },
        )
        if _timing_verbose:
            print(
                f"  [timing] Speech format: {format_elapsed * 1000:.0f}ms", flush=True
            )
        artifact.spoken_text = spoken
        artifact.display_text = rendered
        sm.transition("RENDERED")
        delivery = self.runtime.output_coordinator.deliver(
            reply=RenderedReply(
                text=spoken, sink=self.runtime._select_sink(env.source)
            ),
            sink_status=self.runtime._build_sink_status(
                source=env.source, addon_id=env.addon_id, channel_id=env.channel_id
            ),
        )
        deliver_elapsed = time.perf_counter() - tts_start
        self.runtime.debug_trace.log(
            "timing",
            "stage_complete",
            {
                "message": f"Delivery setup: {deliver_elapsed * 1000:.0f}ms (sink={delivery.sink})",
                "elapsed_ms": round(deliver_elapsed * 1000, 1),
            },
        )
        if _timing_verbose:
            print(
                f"  [timing] Delivery setup: {deliver_elapsed * 1000:.0f}ms (sink={delivery.sink})",
                flush=True,
            )
        if delivery.sink == "local_voice":
            self.runtime._append_local_text_log(
                text=spoken, turn_id=env.turn_id, source=env.source
            )
            tts_speak_start = time.perf_counter()
            self.runtime.tts.speak_reliable(spoken)
            tts_elapsed = time.perf_counter() - tts_speak_start
            self.runtime.debug_trace.log(
                "timing",
                "stage_complete",
                {
                    "message": f"TTS speak: {tts_elapsed * 1000:.0f}ms",
                    "elapsed_ms": round(tts_elapsed * 1000, 1),
                },
            )
            if _timing_verbose:
                print(f"  [timing] TTS speak: {tts_elapsed * 1000:.0f}ms", flush=True)
        elif delivery.sink == "local_text_log":
            self.runtime._append_local_text_log(
                text=spoken, turn_id=env.turn_id, source=env.source
            )
        sm.transition("DELIVERED")
        self.runtime._record_stage_v2(
            "tts", stage_start, time.monotonic() * 1000, {"sink": delivery.sink}
        )
        if source == "local_mic" and spoken.strip():
            self.runtime.conversation.activate_follow_up_window()
        total_ms = (time.monotonic() - turn_started) * 1000.0
        self.runtime._last_turn_latency_ms = max(0.0, total_ms)
        self.runtime.health_monitor.recent_turn_latency_ms.append(
            self.runtime._last_turn_latency_ms
        )
        artifact = self.runtime._finalize_turn_v2(
            spoken_text=spoken,
            display_text=rendered,
            resolved_by=resolved_by,
            total_ms=total_ms,
        )
        crsis = self._evaluate_and_persist_crsis(
            source="turn_complete",
            turn_id=env.turn_id,
            lane_decision=execution.lane,
            resolved_by=resolved_by,
        )
        event = EventRecord.build(
            event_type="turn_complete",
            turn_id=env.turn_id,
            lane_decision=execution.lane,
            resolved_by=resolved_by,
            elapsed_ms=1,
            addon_id=env.addon_id,
            channel_id=env.channel_id,
            degraded_mode_active=self.runtime.state.degraded_mode,
            crsis_status=str(crsis.get("status", "")),
            crsis_findings=int(str(crsis.get("findings", 0) or 0)),
            crsis_snapshot_jsonl=str(crsis.get("jsonl_path", "")),
            crsis_snapshot_latest=str(crsis.get("latest_path", "")),
            turn_artifact=asdict(artifact),
        )
        self.runtime.events.emit(event)
        self._emit_state_builder_events(
            turn_id=env.turn_id,
            lane=execution.lane,
            resolved_by=resolved_by,
            tool_summaries=execution.tool_summaries,
            latency_ms=self.runtime._last_turn_latency_ms,
        )
        self.runtime._update_belief_state(
            turn_id=env.turn_id,
            intent=decision.intent or "unknown",
            resolved_by=resolved_by,
            tool_summaries=execution.tool_summaries,
            memory_items=memory_items,
        )
        self.runtime._generate_and_execute_plan(
            turn_id=env.turn_id, intent=decision.intent or "unknown"
        )
        self.runtime._detect_and_log_satisfaction(
            user_message=text,
            turn_id=env.turn_id,
            follow_up_window_active=self.runtime.conversation.expects_follow_up_without_wake_word(),
        )
        self.runtime.conversation_buffer.append(
            TurnSummary(
                user_text=execution.conversation_user_text or env.text,
                intent=decision.intent or "unknown",
                response_summary=self.runtime._summarize_for_context(spoken),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        return {
            "turn_id": env.turn_id,
            "state": sm.state,
            "lane": execution.lane,
            "text": spoken,
            "display_text": rendered,
            "resolved_by": resolved_by,
            "sink": delivery.sink,
            "intent": decision.intent,
            "match_type": decision.match_type,
            "route_reason": decision.reason,
            "sensitive_input": execution.sensitive_input,
            "job_snapshot": execution.job_snapshot,
            "tool_summaries": execution.tool_summaries,
            "memory_items": execution.memory_items,
            "evidence_packet": artifact.evidence_packet,
            "raw_llm_output": render_result["raw_output"],
            "llm_model": render_result["model"],
            "llm_elapsed_ms": render_result["elapsed_ms"],
            "tool_results": getattr(execution, "tool_results", []),
        }

    def _render_with_fallback(self, compiled) -> str:
        try:
            render_result = self.runtime.renderer.render(compiled)
            rendered = render_result["text"]
            fallback_used = bool(
                compiled.deterministic_fallback.strip()
                and rendered.strip() == compiled.deterministic_fallback.strip()
            )
            self.runtime.health_monitor.recent_renderer_fallbacks.append(fallback_used)
            return rendered
        except Exception as e:
            self.runtime.debug_trace.log(
                "renderer",
                "error",
                {"message": "Renderer failed, using fallback", "error": str(e)},
            )
            fallback = self.runtime.fallback_policy.resolve(
                component="renderer", error_type="renderer_error"
            )
            self.runtime.health_monitor.recent_renderer_fallbacks.append(True)
            return compiled.deterministic_fallback or fallback.message

    def _preload_realtime_model(self) -> None:
        try:
            self.runtime._renderer_model_preloaded = bool(
                self.runtime.realtime_reasoner_preferred.warm(keep_alive="2h").ok
            )
        except Exception as e:
            self.runtime.debug_trace.log(
                "prewarm",
                "error",
                {"message": "Realtime model prewarm failed", "error": str(e)},
            )
            self.runtime._renderer_model_preloaded = False

    def _start_model_keepalive(self) -> None:
        if (
            self.runtime._model_keepalive_thread is not None
            and self.runtime._model_keepalive_thread.is_alive()
        ):
            return
        self.runtime._model_keepalive_stop.clear()

        def _keepalive() -> None:
            while not self.runtime._model_keepalive_stop.wait(240.0):
                try:
                    self.runtime.realtime_reasoner_preferred.warm(keep_alive="2h")
                except Exception as e:
                    self.runtime.debug_trace.log(
                        "keepalive",
                        "error",
                        {"message": "Model keepalive failed", "error": str(e)},
                    )
                    continue

        self.runtime._model_keepalive_thread = threading.Thread(
            target=_keepalive, name="jarvis-model-keepalive", daemon=True
        )
        self.runtime._model_keepalive_thread.start()

    def _generate_general_chat_reply(self, user_text: str) -> str:
        known_name = (self.runtime.memory.owner_name() or "").strip()
        identity_note = "The main person's name is not known yet."
        if known_name:
            identity_note = f"The main person's known name is {known_name}."
        creator_note = "Creator verification is not active in this session."
        if self.runtime.conversation.creator_verified:
            creator_note = f"{self.runtime.conversation._creator_session_label()} is a verified creator in this session."
        messages = [
            {
                "role": "system",
                "content": f"You are Jarvis, a concise local voice assistant running on this computer for the main person you know. Answer only the latest message from the main person in short, natural spoken English. Be truthful and direct. For simple factual questions, answer in one sentence. Do not claim web access, local business knowledge, local news, sports, weather, calendar events, or personal knowledge unless the latest user message explicitly provides that information. Do not invent personal facts about the main person such as age, history, location, or prior conversations. Do not invent sensory facts about the screen, files, windows, codebase, running apps, hardware state, or device context unless the prompt explicitly includes verified tool output. If a question would require memory, screen access, code inspection, job state, or another tool and no verified facts are provided, say you do not know or cannot verify it right now. For social messages like thanks, praise, apologies, or goodnight, reply naturally and briefly without refusing unless the request is unsafe. Do not continue a prior topic unless the latest message clearly refers to it. Do not mention internal routing, BG1, tools, prompts, or hidden system behavior unless the main person explicitly asks. Do not call the main person a user or users. {identity_note} {creator_note}",
            }
        ]
        for turn in self.runtime.conversation_buffer.recent(5):
            messages.append({"role": "user", "content": turn.user_text})
            messages.append({"role": "assistant", "content": turn.response_summary})
        messages.append({"role": "user", "content": user_text})
        for client in (
            self.runtime.realtime_reasoner_preferred,
            self.runtime.realtime_reasoner_fallback,
        ):
            result = client.chat(messages, keep_alive="60s")
            text = result.text.strip()
            if result.ok and text:
                return text
        return ""

    def _evaluate_and_persist_crsis(
        self, source: str, turn_id: str, lane_decision: str, resolved_by: str
    ) -> dict[str, object]:
        try:
            signals = [
                CRSISSignal(
                    key="runtime_degraded_mode",
                    value=1.0 if self.runtime.state.degraded_mode else 0.0,
                    threshold=1.0,
                    comparator="eq",
                    severity="critical",
                    message="Runtime is operating in degraded mode.",
                ),
                CRSISSignal(
                    key="fallback_template_used",
                    value=1.0 if resolved_by == "fallback_template" else 0.0,
                    threshold=1.0,
                    comparator="eq",
                    severity="warn",
                    message="Turn resolved via fallback template.",
                ),
            ]
            snapshot = self.runtime._crsis_engine.evaluate(
                signals=signals,
                source=source,
                metadata={
                    "turn_id": turn_id,
                    "lane_decision": lane_decision,
                    "resolved_by": resolved_by,
                },
            )
            files = persist_snapshot(
                snapshot, log_dir=self.runtime.config.events_log_dir
            )
            return {
                "status": snapshot.status,
                "findings": len(snapshot.findings),
                "jsonl_path": files.get("jsonl_path"),
                "latest_path": files.get("latest_path"),
            }
        except Exception as e:
            self.runtime.debug_trace.log(
                "crsis",
                "error",
                {"message": "CRSIS evaluation failed", "error": str(e)},
            )
            return {
                "status": "warn",
                "findings": 0,
                "jsonl_path": None,
                "latest_path": None,
            }

    def _emit_state_builder_events(
        self,
        turn_id: str,
        lane: str,
        resolved_by: str,
        tool_summaries: list[str],
        latency_ms: float,
    ) -> None:
        """Emit events to StateBuilder and update WorldState."""
        from jarvis.world_model.state_builder import EventRecord as StateBuilderEvent
        from jarvis.crsis.contracts import utc_now_iso

        confidence = self.runtime._compute_turn_confidence(resolved_by, lane)
        self.runtime._state_builder.store_event(
            StateBuilderEvent(
                event_id=f"event_{utc_now_iso()}_{turn_id}",
                event_type="turn_confidence",
                payload={
                    "turn_id": turn_id,
                    "confidence": confidence,
                    "factors": {"resolved_by": resolved_by, "lane": lane},
                },
                timestamp=utc_now_iso(),
                turn_id=turn_id,
            )
        )
        for summary in tool_summaries:
            tool_name = self.runtime._extract_tool_name(summary)
            if tool_name:
                self.runtime._state_builder.store_event(
                    StateBuilderEvent(
                        event_id=f"event_{utc_now_iso()}_{turn_id}_{tool_name}",
                        event_type="tool_call",
                        payload={
                            "tool_name": tool_name,
                            "success": True,
                            "latency_ms": int(latency_ms),
                        },
                        timestamp=utc_now_iso(),
                        turn_id=turn_id,
                    )
                )
        self.runtime._world_state = self.runtime._state_builder.reconstruct_state(
            self.runtime._world_state
        )

    # ------------------------------------------------------------------
    # Phase 9B: Async turn pipeline with concurrent routing + memory
    # ------------------------------------------------------------------

    async def async_run_turn(self, text: str, source: str = "local_mic") -> dict:
        """Async version of run_turn with concurrent route + memory + prewarm.

        The three independent I/O-bound stages that previously ran sequentially
        (routing via embedding model, memory retrieval via SQLite/semantic search,
        and model pre-warming via Ollama keepalive) now run concurrently using
        asyncio.to_thread().  Everything after the concurrent block is identical
        to the sync pipeline.
        """
        turn_started = time.monotonic()
        turn_start_perf = time.perf_counter()
        sm = TurnStateMachine()
        _timing_verbose = os.environ.get("JARVIS_TIMING_VERBOSE", "") == "1"

        def _ts(msg):
            elapsed = (time.perf_counter() - turn_start_perf) * 1000
            self.runtime.debug_trace.log(
                "timing",
                "stage_complete",
                {"message": msg, "elapsed_ms": round(elapsed, 1)},
            )
            if _timing_verbose:
                print(f"  [timing] {elapsed:7.0f}ms | {msg}", flush=True)

        _ts(f"=== ASYNC TURN START: {text[:50]} ===")

        # ---- Ingress / normalize (cheap, always sequential) ----
        env = self.runtime.normalizer.normalize(
            RawEvent(source=source, speaker_id="owner", channel="local", payload=text)
        )
        artifact = self.runtime._start_turn_v2(
            turn_id=env.turn_id, raw_text=text, source=source
        )
        sm.transition("INGRESS_RECEIVED")
        stage_start = time.monotonic() * 1000
        self.runtime.ingress_hub.accept_raw_event(
            RawEvent(source=source, speaker_id="owner", channel="local", payload=text)
        )
        self.runtime._record_stage_v2(
            "ingress", stage_start, time.monotonic() * 1000, {"source": source}
        )
        stage_start = time.monotonic() * 1000
        artifact.normalized_text = env.text
        artifact.canonical_text = env.text
        self.runtime._record_stage_v2(
            "normalize", stage_start, time.monotonic() * 1000, {"normalized": env.text}
        )

        # ---- Resolve references (cheap, sequential) ----
        stage_start = time.monotonic() * 1000
        tokens = env.text.split()
        rewrite = self.runtime._resolve_references_v2(
            normalized_text=env.text, tokens=tokens
        )
        artifact.context_rewrite = rewrite.rewritten
        artifact.context_rewrite_reason = rewrite.reason
        self.runtime._record_stage_v2(
            "resolve",
            stage_start,
            time.monotonic() * 1000,
            {"rewritten": rewrite.rewritten},
        )
        routing_text = rewrite.rewritten if rewrite.rewritten else env.text

        # ---- CONCURRENT BLOCK: route + memory + prewarm ----
        stage_start = time.monotonic() * 1000

        async def _do_route():
            cached = self.runtime._check_route_cache_v2(
                routing_text, bg1_busy=self.runtime._bg1_is_saturated()
            )
            if cached is not None:
                return cached, True
            elapsed = (time.monotonic() - turn_started) * 1000
            decision = await asyncio.to_thread(
                self.runtime.dispatcher.route,
                routing_text,
                bg1_busy=self.runtime._bg1_is_saturated(),
                elapsed_ms=elapsed,
                world_state=self.runtime._world_state,
            )
            self.runtime._cache_route_decision_v2(
                routing_text, self.runtime._bg1_is_saturated(), decision
            )
            return decision, False

        async def _do_memory():
            return await asyncio.to_thread(
                self.runtime._retrieve_memory_v2,
                query=routing_text,
                top_k=6,
            )

        (decision, route_cache_hit), memory_hits = await asyncio.gather(
            _do_route(),
            _do_memory(),
        )
        _ts(
            f"After concurrent route+memory (intent={decision.intent}, lane={decision.lane}, mem={len(memory_hits)})"
        )

        # ---- Post-routing bookkeeping (same as sync) ----
        tool_route = self.runtime.tool_router.check_tool_first(routing_text)
        if (
            tool_route.matched
            and tool_route.confidence > 0.8
            and decision.intent == "general_chat"
        ):
            self.runtime._trace_tool_decision(
                tool_name=tool_route.tool_name or "unknown",
                decision="tool_first_override",
                reason=f"confidence={tool_route.confidence:.2f}, overrode general_chat",
            )
        if decision.intent == "general_chat" or decision.reason.startswith(
            "quick_or_general"
        ):
            self.runtime._intent_miss_detector.log_miss(
                turn_id=env.turn_id,
                utterance=env.text,
                normalized_text=decision.normalized_text,
                routed_intent=decision.intent or "unknown",
                match_type=decision.match_type,
                lane=decision.lane,
                miss_reason="fallback_to_general",
                confidence=0.0,
                metadata={"route_reason": decision.reason},
            )
        env = env.replace(
            text=decision.normalized_text,
            metadata={
                **env.metadata,
                "match_type": decision.match_type,
                "route_reason": decision.reason,
                "intent": decision.intent or "",
            },
        )
        artifact.intent = decision.intent or ""
        artifact.chosen_route = decision.lane
        artifact.memory_hits = memory_hits
        memory_items = [f"{h.key}: {h.value}" for h in memory_hits]

        try:
            route_record = RouteDecisionRecord(
                turn_id=env.turn_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                query=text[:200],
                normalized_query=routing_text[:200],
                selected_source=decision.match_type or "classifier",
                selected_intent=decision.intent or "general_chat",
                selected_lane=decision.lane,
                selected_confidence=tool_route.confidence
                if tool_route.matched
                else 0.5,
                cache_hit=route_cache_hit,
                context_rewrite=rewrite.rewritten
                if rewrite.rewritten != env.text
                else None,
                bg1_busy=self.runtime._bg1_is_saturated(),
            )
            if tool_route.matched:
                route_record.candidates.append(
                    RouteCandidateRecord(
                        source="tool_first",
                        intent=tool_route.reason,
                        lane=tool_route.lane,
                        confidence=tool_route.confidence,
                        reason=tool_route.reason,
                        tool_name=tool_route.tool_name,
                    )
                )
            route_record.candidates.append(
                RouteCandidateRecord(
                    source=decision.match_type or "classifier",
                    intent=decision.intent or "general_chat",
                    lane=decision.lane,
                    confidence=0.5,
                    reason=decision.reason,
                )
            )
            self.runtime.route_trace_logger.record(route_record)
        except Exception as e:
            self.runtime.debug_trace.log(
                "route",
                "error",
                {"message": "Async route logging failed", "error": str(e)},
            )
        self.runtime._record_stage_v2(
            "route",
            stage_start,
            time.monotonic() * 1000,
            {"lane": decision.lane, "intent": decision.intent},
        )
        self.runtime._record_stage_v2(
            "memory",
            stage_start,
            time.monotonic() * 1000,
            {"hit_count": len(memory_hits)},
        )
        if self.runtime._current_context:
            self.runtime._current_context.chosen_route = decision.lane
            self.runtime._current_context.intent = decision.intent or ""
        sm.transition("ROUTED")
        sm.transition("RUNNING")

        # ---- Execution (sequential from here — same as sync pipeline) ----
        stage_start = time.monotonic() * 1000
        exec_start = time.perf_counter()
        if decision.lane == "realtime":
            execution = self.runtime._execute_realtime(env, decision)
        else:
            bg1_start = self.runtime._narrate_bg1_start_v2(
                task_subject=artifact.subject, task_type="research"
            )
            if bg1_start:
                self.runtime._append_local_text_log(
                    text=bg1_start, turn_id=env.turn_id, source=env.source
                )
                self.runtime.tts.speak(bg1_start)
            execution = self.runtime._execute_heavy(env, decision)
        exec_elapsed = time.perf_counter() - exec_start
        _ts(f"Lane execution: {exec_elapsed * 1000:.0f}ms (lane={decision.lane})")
        self.runtime._record_stage_v2(
            "tool_exec",
            stage_start,
            time.monotonic() * 1000,
            {"resolved_by": execution.resolved_by},
        )
        artifact.tools_used = (
            execution.tool_summaries if execution.tool_summaries else []
        )
        artifact.tool_summaries = (
            execution.tool_summaries if execution.tool_summaries else []
        )

        # ---- Compile + Render ----
        stage_start = time.monotonic() * 1000
        conversation_items = self.runtime._conversation_context_lines(limit=5)
        brain_items = (
            execution.brain_items or [execution.text] if execution.text else []
        )
        if execution.resolved_by == "tool_plus_renderer":
            evidence_packet = self.runtime._build_evidence_packet_v2(
                user_text=env.text,
                brain_items=brain_items,
                tool_summaries=execution.tool_summaries or [],
                memory_hits=memory_hits,
                job_snapshot=execution.job_snapshot,
                tool_facts=getattr(execution, "tool_facts", []),
            )
            artifact.evidence_summary = str(evidence_packet)
            artifact.evidence_packet = evidence_packet
            compiled = self.runtime.response_compiler.compile(
                evidence_packet=evidence_packet,
                conversation_items=conversation_items,
                constraints=execution.renderer_constraints,
                tone=execution.renderer_tone,
                length_hint=execution.renderer_length_hint,
                deterministic_fallback=execution.text,
            )
            render_result = self.runtime.renderer.render(compiled)
            rendered = render_result["text"]
            artifact.llm_used = render_result["model"]
            if decision.lane != "realtime" and execution.job_snapshot:
                bg1_complete = self.runtime._narrate_bg1_completion_v2(
                    result_summary=execution.text,
                    task_subject=artifact.subject,
                    task_type="research",
                )
                if bg1_complete:
                    rendered = bg1_complete + " " + rendered
        else:
            self.runtime.health_monitor.recent_renderer_fallbacks.append(False)
            rendered = execution.text
            render_result = {"text": rendered, "raw_output": "", "model": "none", "elapsed_ms": 0}
        resolved_by = execution.resolved_by
        artifact.resolved_by = resolved_by
        self.runtime._record_stage_v2(
            "llm",
            stage_start,
            time.monotonic() * 1000,
            {"compiled": rendered[:100] if rendered else ""},
        )

        # ---- Speech format + Delivery ----
        stage_start = time.monotonic() * 1000
        spoken = self.runtime.speech_formatter.format(rendered)
        intent_for_policy = decision.intent or "general_chat"
        spoken = self.runtime.voice_response_policy.truncate_for_voice(
            spoken, intent_for_policy
        )
        artifact.spoken_text = spoken
        artifact.display_text = rendered
        sm.transition("RENDERED")
        delivery = self.runtime.output_coordinator.deliver(
            reply=RenderedReply(
                text=spoken, sink=self.runtime._select_sink(env.source)
            ),
            sink_status=self.runtime._build_sink_status(
                source=env.source, addon_id=env.addon_id, channel_id=env.channel_id
            ),
        )
        if delivery.sink == "local_voice":
            self.runtime._append_local_text_log(
                text=spoken, turn_id=env.turn_id, source=env.source
            )
            self.runtime.tts.speak_reliable(spoken)
        elif delivery.sink == "local_text_log":
            self.runtime._append_local_text_log(
                text=spoken, turn_id=env.turn_id, source=env.source
            )
        sm.transition("DELIVERED")
        self.runtime._record_stage_v2(
            "tts", stage_start, time.monotonic() * 1000, {"sink": delivery.sink}
        )

        # ---- Post-turn bookkeeping ----
        if source == "local_mic" and spoken.strip():
            self.runtime.conversation.activate_follow_up_window()
        total_ms = (time.monotonic() - turn_started) * 1000.0
        self.runtime._last_turn_latency_ms = max(0.0, total_ms)
        self.runtime.health_monitor.recent_turn_latency_ms.append(
            self.runtime._last_turn_latency_ms
        )
        artifact = self.runtime._finalize_turn_v2(
            spoken_text=spoken,
            display_text=rendered,
            resolved_by=resolved_by,
            total_ms=total_ms,
        )
        crsis = self._evaluate_and_persist_crsis(
            source="turn_complete",
            turn_id=env.turn_id,
            lane_decision=execution.lane,
            resolved_by=resolved_by,
        )
        event = EventRecord.build(
            event_type="turn_complete",
            turn_id=env.turn_id,
            lane_decision=execution.lane,
            resolved_by=resolved_by,
            elapsed_ms=1,
            addon_id=env.addon_id,
            channel_id=env.channel_id,
            degraded_mode_active=self.runtime.state.degraded_mode,
            crsis_status=str(crsis.get("status", "")),
            crsis_findings=int(str(crsis.get("findings", 0) or 0)),
            crsis_snapshot_jsonl=str(crsis.get("jsonl_path", "")),
            crsis_snapshot_latest=str(crsis.get("latest_path", "")),
            turn_artifact=asdict(artifact),
        )
        self.runtime.events.emit(event)
        self._emit_state_builder_events(
            turn_id=env.turn_id,
            lane=execution.lane,
            resolved_by=resolved_by,
            tool_summaries=execution.tool_summaries,
            latency_ms=self.runtime._last_turn_latency_ms,
        )
        self.runtime._update_belief_state(
            turn_id=env.turn_id,
            intent=decision.intent or "unknown",
            resolved_by=resolved_by,
            tool_summaries=execution.tool_summaries,
            memory_items=memory_items,
        )
        self.runtime._generate_and_execute_plan(
            turn_id=env.turn_id, intent=decision.intent or "unknown"
        )
        self.runtime._detect_and_log_satisfaction(
            user_message=text,
            turn_id=env.turn_id,
            follow_up_window_active=self.runtime.conversation.expects_follow_up_without_wake_word(),
        )
        self.runtime.conversation_buffer.append(
            TurnSummary(
                user_text=execution.conversation_user_text or env.text,
                intent=decision.intent or "unknown",
                response_summary=self.runtime._summarize_for_context(spoken),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        return {
            "turn_id": env.turn_id,
            "state": sm.state,
            "lane": execution.lane,
            "text": spoken,
            "display_text": rendered,
            "resolved_by": resolved_by,
            "sink": delivery.sink,
            "intent": decision.intent,
            "match_type": decision.match_type,
            "route_reason": decision.reason,
            "sensitive_input": execution.sensitive_input,
            "job_snapshot": execution.job_snapshot,
            "tool_summaries": execution.tool_summaries,
            "memory_items": execution.memory_items,
            "evidence_packet": artifact.evidence_packet,
            "raw_llm_output": render_result["raw_output"],
            "llm_model": render_result["model"],
            "llm_elapsed_ms": render_result["elapsed_ms"],
            "tool_results": getattr(execution, "tool_results", []),
        }

    def run_turn_concurrent(self, text: str, source: str = "local_mic") -> dict:
        """Sync wrapper that runs async_run_turn in a fresh event loop.

        Use this as a drop-in replacement for run_turn() to get concurrent
        routing + memory retrieval + model pre-warming.  Falls back to the
        sync pipeline if asyncio setup fails.
        """
        try:
            return asyncio.run(self.async_run_turn(text, source))
        except RuntimeError:
            # Already inside an event loop — fall back to sync
            return self.run_turn(text, source)
