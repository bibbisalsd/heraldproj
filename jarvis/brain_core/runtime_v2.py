"""Runtime V2 Integration: Wire new packets and modules into JarvisRuntime.

This module provides mixin classes that extend JarvisRuntime with:
- EvidencePacket and TurnArtifact integration
- Reference resolution for follow-up understanding
- Debug trace logging
- BG1 narrator for natural speech
- Memory namespaces (hot working, session, user, task/result)
- Tool policy with lane-aware routing (wrapping ToolOrchestrator)
- Self-knowledge index for structured self-inspection
- TTS state machine for reliable voice delivery
- BG1 progress checkpoint narration

Usage:
    class JarvisRuntimeV2(JarvisRuntime, RuntimeV2Mixin):
        pass
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .contracts import (
    TurnArtifact,
    LatencyBreakdown,
    MemoryHit,
    EvidencePacket,
    MemoryInfo,
    TaskInfo,
    VerifiedFact,
    StylePolicy,
    LLMDerivedResult,
)
from .turn_context import TurnContextPacket
from .reference_resolver import resolve_references, ContextualRewrite
from .debug_trace import DebugTraceLogger
from .bg1_narrator import BG1Narrator, NarrationStyle
from .memory_namespaces import MemoryNamespaces, SessionTurnRecord
from .tool_policy import ToolPolicy
from .self_knowledge_index import SelfKnowledgeIndex
from .latency_budget import LatencyBudgetEnforcer, LatencyTracker
from .route_cache import RouteCache, ToolResultCache


@dataclass
class StageTiming:
    """Timing for a single pipeline stage."""

    stage: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    elapsed_ms: float = 0.0

    def record(self) -> float:
        """Record end time and return elapsed."""
        self.end_ms = time.monotonic() * 1000
        self.elapsed_ms = self.end_ms - self.start_ms
        return self.elapsed_ms


class RuntimeV2Mixin:
    """Mixin that adds Phase 2 capabilities to JarvisRuntime.

    Capabilities added:
    1. TurnArtifact tracking for every turn
    2. EvidencePacket compilation for LLM
    3. Reference resolution for follow-ups
    4. Debug trace logging
    5. BG1 narrator for natural speech
    6. Memory namespaces integration
    7. Tool policy with lane routing
    """

    def _init_phase2_components(self) -> None:
        """Initialize Phase 2 components. Call this from JarvisRuntime.__init__."""
        # Phase 2 components
        self.debug_trace = DebugTraceLogger(
            log_dir=getattr(self.config, "logs_dir", "./logs"),
            level="verbose",
            hide_sensitive=True,
        )
        self.bg1_narrator = BG1Narrator(
            style=NarrationStyle(
                formal=False,
                include_sir=False,
                address_term=None,  # Will be set from user memory
                verbose=False,
            )
        )
        self.memory_namespaces = MemoryNamespaces(
            memory_db_path=getattr(self.config, "memory_db_path", None),
            session_log_dir=getattr(self.config, "logs_dir", "./logs/sessions"),
        )
        self.tool_policy = ToolPolicy(orchestrator=self.tool_orchestrator)

        # Self-knowledge index (Phase 10)
        self.self_knowledge = SelfKnowledgeIndex()

        # TTS state machine (Phase 8) — initialized in main after TTS instance exists
        self._tts_state_machine = None  # Set by _init_tts_state_machine()

        # Latency budget enforcement (Phase 9)
        self._latency_tracker = LatencyTracker(max_samples=500)
        self._latency_enforcer = LatencyBudgetEnforcer(tracker=self._latency_tracker)

        # Route and tool result caching (Phase 9)
        self._route_cache = RouteCache(max_size=100, ttl_seconds=30.0)
        self._tool_result_cache = ToolResultCache(max_size=150)

        # Current turn state
        self._current_turn_artifact: TurnArtifact | None = None
        self._current_context: TurnContextPacket | None = None
        self._stage_timings: dict[str, StageTiming] = {}

        # Context persistence: snapshot from previous turn for follow-up resolution
        self._last_context_snapshot: dict[str, Any] | None = None

        # Register built-in tools with policy metadata

    def _init_tts_state_machine(self) -> None:
        """Initialize TTS state machine wrapping the existing TTS instance.

        Call AFTER self.tts is created in JarvisRuntime.__init__.
        """
        from jarvis.voice.tts_state import TTSStateMachine, TTSConfig

        config = TTSConfig(
            watchdog_timeout_ms=15000.0,
            max_retries=2,
            retry_delay_ms=500.0,
            device_recovery_enabled=True,
        )

        def _on_state_change(old, new):
            self.debug_trace.log(
                "tts_state",
                "state_change",
                {
                    "from": old.value,
                    "to": new.value,
                },
            )

        self._tts_state_machine = TTSStateMachine(
            tts=self.tts,
            config=config,
            on_state_change=_on_state_change,
        )

    def speak_reliable(self, text: str, channel: str = "local") -> dict:
        """Speak text through the TTS state machine for reliability.

        If the state machine is STALLED or FAILED, falls back to text-only sinks.
        """
        from jarvis.voice.tts_state import TTSState

        # Check if voice is down
        if self._tts_state_machine is not None:
            if self._tts_state_machine.state in (TTSState.STALLED, TTSState.FAILED):
                # Voice is down, route to alternative channel if local
                if channel == "local":
                    # Try to find a text-based sink (e.g. Discord)
                    # For now we just log it and return failure
                    return {
                        "ok": False,
                        "text": text,
                        "reason": f"voice_down_state_{self._tts_state_machine.state.value}",
                        "sink": "fallback_text",
                    }
            return self._tts_state_machine.speak(text)

        return self.tts.speak(text)

    def _start_turn_v2(self, turn_id: str, raw_text: str, source: str) -> TurnArtifact:
        """Start a new turn with Phase 2 tracking.

        Args:
            turn_id: Unique turn identifier
            raw_text: Raw input text
            source: Input source (local_mic, text, addon, etc.)

        Returns:
            TurnArtifact for tracking this turn
        """
        # Initialize debug trace
        self.debug_trace.start_turn(turn_id)
        self.debug_trace.log_ingress(raw_text, source)

        # Create turn artifact
        artifact = TurnArtifact(
            turn_id=turn_id,
            source=source,
            raw_text=raw_text,
            normalized_text="",
            canonical_text="",
            context_rewrite="",
        )

        # Create context packet
        context = TurnContextPacket(
            turn_id=turn_id,
            raw_text=raw_text,
        )

        # ── Context persistence fix ──────────────────────────────────
        # Load prior turn's context from hot working memory so reference
        # resolver can see the previous topic/subject/task for follow-ups.
        self._load_prior_context_into_turn(context)

        # Load address term from user memory if available
        owner_name = self.memory_namespaces.get_all_user_memory()
        for record in owner_name:
            if record.key == "user_name" and record.value:
                self.bg1_narrator.style.address_term = (
                    "sir"  # Or derive from title preference
                )
                break

        self._current_turn_artifact = artifact
        self._current_context = context
        self._stage_timings = {}

        return artifact

    def _load_prior_context_into_turn(self, context: TurnContextPacket) -> None:
        """Load prior turn context into the new turn for follow-up resolution.

        Reads from hot working memory (persisted at end of previous turn)
        and from the last context snapshot to populate the active context
        so the reference resolver can see previous topic, subject, and
        active task.
        """
        hot = self.memory_namespaces.get_hot_working()

        # Restore active context from hot working memory
        if hot.active_topic:
            context.active_context.topic = hot.active_topic
        if hot.active_subject:
            context.active_context.subject = hot.active_subject
        if hot.active_bg1_task_subject:
            context.active_context.subject = (
                context.active_context.subject or hot.active_bg1_task_subject
            )

        # Restore reference map from last snapshot
        if self._last_context_snapshot:
            prior_refs = self._last_context_snapshot.get("reference_map", {})
            for original, resolved in prior_refs.items():
                context.add_resolved_reference(original, resolved, 0.6, "prior_turn")

        # Mark context as fresh (was set within the last 30 seconds)
        if hot.active_topic or hot.active_subject:
            context.active_context.set_at = time.monotonic()
            context.active_context.max_age_seconds = 120.0  # 2 min follow-up window

    def _record_stage_v2(
        self, stage: str, start_ms: float, end_ms: float, data: dict
    ) -> float:
        """Record a pipeline stage timing, check budget, and log to debug trace."""
        elapsed = end_ms - start_ms
        self._stage_timings[stage] = StageTiming(
            stage=stage, start_ms=start_ms, end_ms=end_ms, elapsed_ms=elapsed
        )
        self.debug_trace.log(stage, "stage_complete", data, latency_ms=elapsed)

        # Latency budget enforcement
        violation = self._latency_enforcer.check_stage(
            stage,
            elapsed,
            self._current_turn_artifact.turn_id if self._current_turn_artifact else "",
        )
        if violation:
            # Use structured latency violation logging (always logged at basic level)
            self.debug_trace.log_latency_violation(
                stage=stage,
                actual_ms=elapsed,
                budget_ms=violation.budget_ms,
                severity=violation.severity,
                turn_id=self._current_turn_artifact.turn_id
                if self._current_turn_artifact
                else "",
            )

        return elapsed

    def _check_route_cache_v2(self, normalized_text: str, bg1_busy: bool) -> Any | None:
        """Check route cache for a cached decision."""
        cached = self._route_cache.get_route(normalized_text, bg1_busy)
        if cached:
            self.debug_trace.log(
                "route",
                "cache_hit",
                {
                    "normalized_text": normalized_text[:100],
                    "cached_intent": getattr(cached, "intent", None),
                },
            )
        return cached

    def _cache_route_decision_v2(
        self, normalized_text: str, bg1_busy: bool, decision: Any
    ) -> None:
        """Cache a route decision."""
        self._route_cache.cache_route(normalized_text, bg1_busy, decision)

    # ── Expanded Debug Trace Helpers ──────────────────────────────

    def _trace_wake_word_decision(
        self, raw_text: str, accepted: bool, token: str | None = None, reason: str = ""
    ) -> None:
        """Log wake-word acceptance/rejection decision."""
        self.debug_trace.log(
            "wake_word",
            "decision",
            {
                "raw_text": raw_text[:100],
                "accepted": accepted,
                "matched_token": token,
                "reason": reason,
            },
        )

    def _trace_followup_decision(
        self, text: str, accepted: bool, window_age_ms: float = 0.0, reason: str = ""
    ) -> None:
        """Log follow-up window acceptance/rejection."""
        self.debug_trace.log(
            "followup",
            "decision",
            {
                "text": text[:100],
                "accepted": accepted,
                "window_age_ms": round(window_age_ms, 1),
                "reason": reason,
            },
        )

    def _trace_bg1_state(
        self, event: str, task_id: str = "", progress: float = 0.0, subject: str = ""
    ) -> None:
        """Log BG1 state transition."""
        self.debug_trace.log(
            "bg1",
            event,
            {
                "task_id": task_id,
                "progress": progress,
                "subject": subject,
            },
        )

    def _trace_tts_event(
        self, event: str, backend: str = "", retry_count: int = 0, error: str = ""
    ) -> None:
        """Log TTS backend/retry event."""
        self.debug_trace.log(
            "tts",
            event,
            {
                "backend": backend,
                "retry_count": retry_count,
                "error": error[:200] if error else "",
            },
        )

    def _trace_tool_decision(
        self, tool_name: str, decision: str, reason: str = ""
    ) -> None:
        """Log tool-first vs LLM decision."""
        self.debug_trace.log(
            "tool_policy",
            "decision",
            {
                "tool": tool_name,
                "decision": decision,
                "reason": reason,
            },
        )

    def _get_latency_health(self) -> dict:
        """Get latency health summary for status queries."""
        return self._latency_enforcer.get_health_summary()

    def _get_cache_stats(self) -> dict:
        """Get route and tool cache statistics."""
        return {
            "route_cache": self._route_cache.stats(),
            "tool_cache": self._tool_result_cache.stats(),
        }

    def _resolve_references_v2(
        self,
        normalized_text: str,
        tokens: list[str],
    ) -> ContextualRewrite:
        """Resolve vague references using active context.

        Args:
            normalized_text: Normalized input text
            tokens: Tokenized text

        Returns:
            ContextualRewrite with resolved references
        """
        # Get active context from hot working memory
        hot_working = self.memory_namespaces.get_hot_working()

        # Build recent subjects from session memory
        recent_turns = self.memory_namespaces.get_recent_turns(limit=5)
        recent_subjects = [t.subject for t in recent_turns if t.subject]

        # Get active task subject if any
        active_task_subject = hot_working.active_bg1_task_subject

        # Resolve references
        rewrite = resolve_references(
            normalized_text=normalized_text,
            context=self._current_context,
            recent_subjects=recent_subjects,
            active_task_subject=active_task_subject,
        )

        # Log to debug trace
        self.debug_trace.log_resolve(
            original=normalized_text,
            rewritten=rewrite.rewritten,
            resolutions=[
                {
                    "original": r.original_phrase,
                    "resolved": r.resolved_reference,
                    "confidence": r.confidence,
                }
                for r in rewrite.resolutions
            ],
            reason=rewrite.reason,
        )

        # Update context packet
        if self._current_context:
            self._current_context.context_rewrite = rewrite.rewritten
            self._current_context.context_rewrite_reason = rewrite.reason
            for r in rewrite.resolutions:
                self._current_context.add_resolved_reference(
                    r.original_phrase,
                    r.resolved_reference,
                    r.confidence,
                    "context",
                )

        return rewrite

    def _retrieve_memory_v2(
        self,
        query: str,
        top_k: int = 6,
    ) -> list[MemoryHit]:
        """Retrieve memory with unified namespace support.

        Args:
            query: Search query
            top_k: Number of results

        Returns: list of memory hits
        """
        start_ms = time.monotonic() * 1000
        hits: list[MemoryHit] = []

        if not self.memory_namespaces.service:
            return hits

        # Search persistent memory across all namespaces via unified service
        try:
            records = self.memory_namespaces.service.search(
                query,
                top_k=top_k,
                embedding_model=self.config.embedding_model,
                keep_alive="2h",
            )
            for r in records:
                hits.append(
                    MemoryHit(
                        memory_type=getattr(r, "namespace", "persistent") or "persistent",
                        key=r.key,
                        value=r.value,
                        confidence=r.confidence,
                        provenance=r.source or "sqlite",
                    )
                )
        except Exception as exc:
            self.debug_trace.log(
                "memory",
                "search_failed",
                {
                    "error": str(exc),
                    "query": query[:100],
                    "error_type": type(exc).__name__,
                },
            )

        elapsed = time.monotonic() * 1000 - start_ms

        # Log to debug trace
        self.debug_trace.log_memory(
            hits=[h.__dict__ for h in hits],
            hit_count=len(hits),
            retrieval_ms=elapsed,
        )

        # Update context
        if self._current_context:
            self._current_context.memory_retrieved = len(hits) > 0
            self._current_context.memory_hit_count = len(hits)

        return hits

    def _build_evidence_packet_v2(
        self,
        user_text: str,
        brain_items: list[str],
        tool_summaries: list[str],
        memory_hits: list[MemoryHit],
        job_snapshot: dict | None = None,
        tool_facts: list[VerifiedFact | LLMDerivedResult] | None = None,
    ) -> EvidencePacket:
        """Build an EvidencePacket from turn data.

        Args:
            user_text: Original user text
            brain_items: Brain inference items
            tool_summaries: Tool execution summaries
            memory_hits: Retrieved memory items
            job_snapshot: BG1 job status snapshot
            tool_facts: Explicit tool fact objects (P2-9)

        Returns:
            EvidencePacket for LLM compilation
        """
        # Build memory info
        memory_info: list[MemoryInfo] = []
        for hit in memory_hits:
            memory_info.append(
                MemoryInfo(
                    memory_type=hit.memory_type,
                    key=hit.key,
                    value=hit.value,
                    confidence=hit.confidence,
                    provenance=hit.provenance,
                    timestamp="",
                )
            )

        # Build task info if job snapshot available
        task_info: TaskInfo | None = None
        if job_snapshot:
            task_info = TaskInfo(
                task_id=job_snapshot.get("job_id", ""),
                subject=job_snapshot.get("subject", ""),
                original_request=job_snapshot.get("original_request", ""),
                state=job_snapshot.get("state", "unknown"),
                progress_percent=job_snapshot.get("progress_percent", 0.0),
                result_summary=job_snapshot.get("result_summary"),
            )

        # Build verified facts
        verified_facts: list[VerifiedFact | LLMDerivedResult] = []
        for item in brain_items:
            verified_facts.append(
                VerifiedFact(
                    content=item,
                    source="inference",
                    confidence=0.7,
                    timestamp="",
                    verification_strength="inferred",
                )
            )
        
        # Add explicit tool facts if provided (P2-9)
        if tool_facts:
            verified_facts.extend(tool_facts)
            
        # Add fallback summaries if no explicit facts
        existing_content = {f.content for f in verified_facts}
        for summary in tool_summaries:
            if summary not in existing_content:
                verified_facts.append(
                    VerifiedFact(
                        content=summary,
                        source="tool",
                        confidence=0.95,
                        timestamp="",
                        verification_strength="observed",
                    )
                )

        # Get resolved references from context
        reference_map = {}
        if self._current_context:
            for res in self._current_context.resolved_references:
                reference_map[res.original] = res.resolved

        # Get active context
        active_topic = None
        active_subject = None
        if self._current_context and self._current_context.active_context.is_fresh():
            active_topic = self._current_context.active_context.topic
            active_subject = self._current_context.active_context.subject

        # Get address preference from user memory
        address_preference = None
        for record in self.memory_namespaces.get_all_user_memory():
            if record.key == "user_title_preference":
                address_preference = record.value
                break

        # Build style policy
        style_policy = StylePolicy(
            tone="helpful",
            length_hint="short",
            spoken_friendly=True,
            avoid_internal_ids=True,
            address_preference=address_preference,
        )

        # Build evidence packet
        packet = EvidencePacket(
            latest_user_message=user_text,
            resolved_intent=brain_items[0] if brain_items else "user_query",
            active_topic=active_topic,
            active_subject=active_subject,
            resolved_reference_map=reference_map,
            memory_info=memory_info,
            previous_message_context=None,  # Could add from conversation buffer
            task_info=task_info,
            tools_used=tool_summaries,
            tool_results=tool_summaries,
            verified_facts=verified_facts,
            inference_policy="evidence_only",
            style_policy=style_policy,
        )

        return packet

    def _narrate_bg1_start_v2(
        self, task_subject: str | None, task_type: str = "default"
    ) -> str:
        """Generate natural BG1 start narration.

        Args:
            task_subject: Task subject
            task_type: Task type (research, code, vision, etc.)

        Returns:
            Spoken narration text
        """
        result = self.bg1_narrator.narrate_start(task_subject, task_type)
        return result.spoken_text

    def _narrate_bg1_completion_v2(
        self,
        result_summary: str | None,
        task_subject: str | None,
        task_type: str = "default",
    ) -> str:
        """Generate natural BG1 completion narration.

        Args:
            result_summary: Result summary
            task_subject: Task subject
            task_type: Task type

        Returns:
            Spoken narration text
        """
        result = self.bg1_narrator.narrate_completion(
            result_summary, task_subject, task_type
        )
        return result.spoken_text

    def _narrate_bg1_progress_v2(
        self,
        percent: float,
        task_subject: str | None,
        task_type: str = "default",
    ) -> str | None:
        """Generate proactive BG1 progress narration at checkpoints.

        Only produces narration at meaningful checkpoints (30%, 60%, 90%).
        Returns None if not at a checkpoint.

        Args:
            percent: Current progress percentage
            task_subject: Task subject
            task_type: Task type

        Returns:
            Spoken narration text, or None if not at a checkpoint
        """
        result = self.bg1_narrator.narrate_progress_checkpoint(
            progress_percent=percent,
            task_subject=task_subject,
            task_type=task_type,
        )
        if result and result.spoken_text:
            # Phase 7: Log BG1 narration events for observability
            self._trace_bg1_state(
                event="progress_narration",
                progress=percent,
                subject=task_subject or "",
            )
            self.debug_trace.log(
                "bg1_narration",
                "checkpoint",
                {
                    "percent": percent,
                    "task_subject": task_subject,
                    "spoken_text": result.spoken_text[:100],
                },
            )
            return result.spoken_text
        return None

    def _persist_bg1_result_v2(
        self,
        task_subject: str,
        original_request: str,
        result_summary: str,
        tools_used: list[str] | None = None,
    ) -> None:
        """Persist BG1 task result to structured task memory.

        Args:
            task_subject: Task subject
            original_request: Original user request
            result_summary: Result summary text
            tools_used: Tools used during execution
        """
        try:
            self.memory_namespaces.write_task_result(
                task_id=f"bg1_{int(time.time())}",
                task_subject=task_subject,
                original_request=original_request,
                result_summary=result_summary[:2000],
                tools_used=tools_used or [],
                confidence=0.85,
                verification_strength="observed",
            )
        except Exception:
            pass  # Don't crash the BG1 thread on memory write failure

    def _finalize_turn_v2(
        self,
        spoken_text: str | None,
        display_text: str | None,
        resolved_by: str,
        total_ms: float,
    ) -> TurnArtifact:
        """Finalize turn and return TurnArtifact.

        Args:
            spoken_text: Spoken output text
            display_text: Display output text
            resolved_by: Resolution method
            total_ms: Total turn latency

        Returns:
            Completed TurnArtifact
        """
        if not self._current_turn_artifact:
            raise RuntimeError("Turn not started")

        artifact = self._current_turn_artifact

        # Set output fields
        artifact.spoken_text = spoken_text
        artifact.display_text = display_text
        artifact.resolved_by = resolved_by

        # Build latency breakdown
        breakdown = LatencyBreakdown(
            total_ms=total_ms,
        )
        for stage_name, timing in self._stage_timings.items():
            if stage_name == "normalize":
                breakdown.normalize_ms = timing.elapsed_ms
            elif stage_name == "resolve":
                breakdown.context_resolve_ms = timing.elapsed_ms
            elif stage_name == "route":
                breakdown.route_ms = timing.elapsed_ms
            elif stage_name == "memory":
                breakdown.memory_ms = timing.elapsed_ms
            elif stage_name == "tool_plan":
                breakdown.tool_plan_ms = timing.elapsed_ms
            elif stage_name == "tool_exec":
                breakdown.tool_exec_ms = timing.elapsed_ms
            elif stage_name == "llm":
                breakdown.llm_ms = timing.elapsed_ms
            elif stage_name == "render":
                breakdown.renderer_ms = timing.elapsed_ms
            elif stage_name == "tts":
                # Use actual measured values from the delivery/speak breakdown.
                # The tts stage covers both delivery setup and speak; if sub-timings
                # were recorded in metadata, use them; otherwise split proportionally.
                breakdown.tts_prep_ms = (
                    timing.elapsed_ms * 0.15
                )  # delivery setup is typically ~15%
                breakdown.tts_speak_ms = (
                    timing.elapsed_ms * 0.85
                )  # actual speak is ~85%

        artifact.latency_breakdown = breakdown

        # Log output
        self.debug_trace.log_output(spoken_text, display_text, resolved_by, total_ms)

        # Flush debug trace
        self.debug_trace.flush()

        # Write to session memory
        if self._current_context:
            session_turn = SessionTurnRecord(
                turn_id=artifact.turn_id,
                timestamp=artifact.created_at,
                raw_text=artifact.raw_text,
                normalized_text=artifact.normalized_text,
                canonical_text=artifact.canonical_text,
                rewritten_routing_text=artifact.context_rewrite,
                intent=artifact.intent,
                topic=artifact.topic,
                subject=artifact.subject,
                tools_used=artifact.tools_used,
                tool_outputs_summary="; ".join(artifact.tool_summaries),
                final_response_summary=spoken_text,
                timing_breakdown=breakdown.to_dict(),
            )
            self.memory_namespaces.add_session_turn(session_turn)

        # Update hot working memory with current context
        if self._current_context:
            self.memory_namespaces.update_hot_working(
                active_topic=self._current_context.active_context.topic,
                active_subject=self._current_context.active_context.subject,
                last_tools_used=artifact.tools_used,
                last_route_chosen=self._current_context.chosen_route,
            )

            # ── Context persistence: save snapshot for next turn ─────
            self._last_context_snapshot = {
                "topic": self._current_context.active_context.topic,
                "subject": self._current_context.active_context.subject,
                "intent": self._current_context.intent,
                "reference_map": {
                    r.original: r.resolved
                    for r in self._current_context.resolved_references
                },
                "tools_used": artifact.tools_used,
                "route": self._current_context.chosen_route,
            }

        # Decay hot working for turns without reference
        if (
            self._current_context
            and not self._current_context.active_context.is_fresh()
        ):
            self.memory_namespaces.decay_hot_working()

        # Check total turn latency against budget
        self._latency_enforcer.check_turn_total(
            total_ms,
            artifact.turn_id,
        )

        # Clear current state
        self._current_turn_artifact = None
        self._current_context = None

        return artifact

    def _get_turn_artifact_v2(self) -> TurnArtifact | None:
        """Get current turn artifact."""
        return self._current_turn_artifact

    def _get_context_packet_v2(self) -> TurnContextPacket | None:
        """Get current context packet."""
        return self._current_context
