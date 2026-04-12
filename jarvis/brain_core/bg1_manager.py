from __future__ import annotations

import logging
import threading
import time

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.main import JarvisRuntime, TurnExecutionResult
    from jarvis.brain_core.prompt_dispatcher import TaskDecision

from jarvis.models.ollama_client import OllamaClient
from jarvis.tools import job_status_tool
from jarvis.specialists.specialist_code import run as run_specialist_code
from jarvis.specialists.specialist_vision import run as run_specialist_vision
from jarvis.observability.events import EventRecord

logger = logging.getLogger(__name__)


class BG1Manager:
    """Manages Phase 1B heavy background jobs (BG1)."""

    def __init__(self, runtime: JarvisRuntime):
        self.runtime = runtime
        self._bg1_thread: threading.Thread | None = None
        self._bg1_lock = threading.Lock()
        self._last_bg1_result: str | None = None
        self.active_thread_ref: threading.Thread | None = None  # to expose for shutdown
        # Streaming token buffer for real-time terminal display
        self._stream_tokens: list[str] = []
        self._stream_read_pos: int = 0
        self._stream_active: bool = False

    def is_busy(self) -> bool:
        """Check if BG1 is at full capacity (active + queue)."""
        queue_status = self.runtime.bg1_queue.status()
        active_count = 1 if self._is_thread_active() else 0
        queued_count = int(queue_status.get("queue_length", 0))
        
        # If we have an active thread and the queue is full, we are busy.
        total_capacity = self.runtime.admission_control.max_active_jobs + self.runtime.admission_control.max_queue_length
        is_saturated = (active_count + queued_count) >= total_capacity
        return is_saturated

    def _is_thread_active(self) -> bool:
        with self._bg1_lock:
            return self._bg1_thread is not None and self._bg1_thread.is_alive()

    def get_last_result(self) -> str | None:
        return self._last_bg1_result

    def set_last_result(self, val: str | None) -> None:
        self._last_bg1_result = val

    def join(self, timeout: float = 2.0) -> None:
        with self._bg1_lock:
            active_thread = self._bg1_thread
        if active_thread is not None and active_thread.is_alive():
            active_thread.join(timeout=timeout)

    def execute_heavy(self, env, decision: TaskDecision) -> TurnExecutionResult:
        capabilities = self.runtime._capabilities_for_profile(env.profile)
        if not capabilities.get("heavy_tasks", False):
            return self.runtime._deny_capability("heavy_tasks")

        queue_state = self.runtime.bg1_queue.status()
        admission = self.runtime.admission_control.evaluate(
            "bg1",
            queue_state={"queue_length": int(queue_state.get("queue_length", 0))},
            bg1_state={"active_jobs": 1 if self._is_thread_active() else 0},
        )
        if not admission.accepted:
            status_payload = job_status_tool.status(self.runtime.job_status)
            if status_payload.get("state") != "IDLE":
                text = (
                    f"BG1 is currently busy with job {status_payload.get('job_id', 'unknown')}. "
                    "Say 'notify me when free' to subscribe."
                )
                if "notify me when free" in env.text.lower():
                    job_status_tool.subscribe_on_complete(
                        self.runtime.job_status,
                        turn_id=env.turn_id,
                        speaker_id="owner",
                        channel=env.channel_id or "local",
                    )
                    text = "BG1 is busy. I will notify you when it is free."
            else:
                text = "BG1 is busy right now. Please try again in a moment."
            from jarvis.main import TurnExecutionResult

            return TurnExecutionResult(
                lane="realtime",
                text=text,
                resolved_by="fallback_template",
                job_snapshot={"state": str(status_payload.get("state", "RUNNING"))},
            )

        submit = self.runtime.bg1_queue.submit(
            summary=env.text, idempotency_key=decision.idempotency_key
        )
        if submit.get("accepted") != "true":
            from jarvis.main import TurnExecutionResult

            return TurnExecutionResult(
                lane="realtime",
                text="I'm currently busy with a background task. Say 'notify me when free' if you want a callback.",
                resolved_by="fallback_template",
                job_snapshot={"state": "RUNNING"},
            )

        job_id = str(submit.get("job_id"))
        reason = str(submit.get("reason", ""))
        from jarvis.main import TurnExecutionResult

        if reason == "deduped":
            return TurnExecutionResult(
                lane="realtime",
                text="That task is already running. I'll let you know when it's done.",
                resolved_by="tool_only",
                job_snapshot={"state": "RUNNING" if self._is_thread_active() else "QUEUED"},
            )

        if reason == "queued":
            return TurnExecutionResult(
                lane="bg1",
                text=(
                    "I've queued that up. I'll start it after the current background task finishes. "
                    "Ask 'what are you doing' for progress."
                ),
                resolved_by="tool_only",
                job_snapshot={"state": "QUEUED"},
            )

        self.runtime.job_status.create({"job_id": job_id, "stage": "queued"})
        self.start_bg1_job(job_id=job_id, summary=env.text)
        return TurnExecutionResult(
            lane="bg1",
            text=(
                "On it. I'll work on that in the background. "
                "Ask 'what are you doing' for progress, "
                "or say 'cancel current task' to stop it."
            ),
            resolved_by="tool_only",
            job_snapshot={"state": "RUNNING"},
        )

    def start_bg1_job(self, job_id: str, summary: str) -> None:
        worker = threading.Thread(
            target=self._run_bg1_job, args=(job_id, summary), daemon=True
        )
        with self._bg1_lock:
            self._bg1_thread = worker
        worker.start()

    def _run_bg1_job(self, job_id: str, summary: str) -> None:
        try:
            current_job_id = job_id
            current_summary = summary
            while current_job_id is not None:
                result_text: str | None = None
                was_cancelled = False
                next_job = None
                try:
                    self._safe_job_update(
                        current_job_id,
                        {"stage": "Initializing background task...", "percent": 15.0},
                    )

                    # Phase 7: Proactive progress narration at checkpoints
                    progress_msg = self.runtime._narrate_bg1_progress_v2(
                        percent=15.0, task_subject=current_summary[:80]
                    )
                    if progress_msg:
                        self.runtime.speak_reliable(progress_msg)

                    if self._wait_or_cancel(current_job_id, 0.05):
                        was_cancelled = True
                    else:
                        self._safe_job_update(
                            current_job_id,
                            {"stage": "Routing to specialist...", "percent": 60.0},
                        )

                        # Phase 7: Progress checkpoint at 60%
                        progress_msg = self.runtime._narrate_bg1_progress_v2(
                            percent=60.0, task_subject=current_summary[:80]
                        )
                        if progress_msg:
                            self.runtime.speak_reliable(progress_msg)

                        if self._job_should_stop(current_job_id):
                            was_cancelled = True
                        else:
                            result_text = self._execute_bg1_specialist(
                                current_summary, job_id=current_job_id
                            )
                            if self._job_should_stop(current_job_id):
                                was_cancelled = True
                            else:
                                self._safe_job_update(
                                    current_job_id,
                                    {
                                        "stage": "Writing to task_result namespace...",
                                        "percent": 95.0,
                                    },
                                )

                                # Phase 7: Near-complete checkpoint at 95%
                                progress_msg = self.runtime._narrate_bg1_progress_v2(
                                    percent=95.0, task_subject=current_summary[:80]
                                )
                                if progress_msg:
                                    self.runtime.speak_reliable(progress_msg)

                                if self._wait_or_cancel(current_job_id, 0.05):
                                    was_cancelled = True
                                else:
                                    self.runtime.memory.remember(
                                        "last_heavy_task",
                                        current_summary,
                                        confidence=0.8,
                                    )
                                    self.runtime.memory.remember(
                                        "last_heavy_result", result_text, confidence=0.8
                                    )
                                    self._last_bg1_result = result_text

                                    # Phase 7: Persist result to structured task memory
                                    self.runtime._persist_bg1_result_v2(
                                        task_subject=current_summary[:80],
                                        original_request=current_summary,
                                        result_summary=result_text or "",
                                    )
                finally:
                    self.runtime.bg1_queue.complete_active()
                    self.runtime.job_status.complete(current_job_id)
                    self._emit_bg1_notifications(
                        job_id=current_job_id,
                        was_cancelled=was_cancelled,
                        result_text=result_text,
                    )

                    next_job = self.runtime.bg1_queue.active
                    if next_job is not None:
                        self.runtime.job_status.create(
                            {"job_id": next_job.job_id, "stage": "queued"}
                        )

                if next_job is None:
                    current_job_id = None
                else:
                    current_job_id = next_job.job_id
                    current_summary = next_job.summary
        finally:
            with self._bg1_lock:
                if self._bg1_thread is threading.current_thread():
                    self._bg1_thread = None

    def _execute_bg1_specialist(self, summary: str, job_id: str | None = None) -> str:
        try:
            text = summary.lower()
            context_prefix = self._build_bg1_context_prefix()
            task_with_context = (
                f"{context_prefix}{summary}" if context_prefix else summary
            )
            display_job_id = job_id or "unknown"

            # Sequential Relay: Vision -> Code -> Review
            # Triggered if both vision/image and code/script hints are present
            has_vision = any(
                token in text
                for token in ("image", "screen", "vision", "screenshot", "ocr")
            )
            has_code = any(
                token in text
                for token in (
                    "code",
                    "refactor",
                    "debug",
                    "function",
                    "script",
                    "compile",
                    "html",
                    "css",
                )
            )

            if has_vision and has_code:
                logger.debug(
                    f"BG1 routing: Sequential Relay (Vision + Code) for job {display_job_id}"
                )
                # Stage 1: Vision Analysis (Qwen3-VL:8b)
                if job_id:
                    self._safe_job_update(
                        job_id,
                        {
                            "stage": f"Running {self.runtime.config.vision_bg1_model} vision analysis...",
                            "percent": 30.0,
                        },
                    )
                vision_result = run_specialist_vision(
                    task_with_context, model=self.runtime.config.vision_bg1_model
                )
                if not vision_result.get("ok"):
                    error_msg = f"Vision specialist ({self.runtime.config.vision_bg1_model}) failed: {vision_result.get('reason', 'unknown error')}"
                    logger.error(f"{error_msg} for job {display_job_id}")
                    if job_id:
                        self._safe_job_update(
                            job_id, {"stage": "Vision specialist failed"}
                        )
                    return error_msg

                vision_output = str(
                    vision_result.get("result") or "Vision analysis complete."
                )

                # Unload vision model to free VRAM for the code relay
                try:
                    OllamaClient(model=self.runtime.config.vision_bg1_model).run("", keep_alive="0")
                except Exception:
                    pass

                # Stage 2: Code Generation & Review (Deepcoder:14b -> rnj-1:8b)
                # The code specialist's 'analyze' already handles the 14b -> 8b relay.
                if job_id:
                    self._safe_job_update(
                        job_id,
                        {
                            "stage": f"Starting {self.runtime.config.code_bg1_model} generation...",
                            "percent": 70.0,
                        },
                    )
                code_task = f"Based on the following vision analysis, complete the coding task: {summary}\n\nVision Analysis:\n{vision_output}"
                code_result = run_specialist_code(
                    code_task,
                    model=self.runtime.config.code_bg1_model,
                    reviewer_model=self.runtime.config.code_reviewer_model,
                )
                
                # Force unload the reviewer model (Pass 2) which code specialist might leave loaded
                try:
                    OllamaClient(model=self.runtime.config.code_reviewer_model).run("", keep_alive="0")
                except Exception:
                    pass

                if not code_result.get("ok"):
                    error_msg = f"Code specialist ({self.runtime.config.code_bg1_model}) failed: {code_result.get('result', 'unknown error')}"
                    logger.error(f"{error_msg} for job {display_job_id}")
                    if job_id:
                        self._safe_job_update(
                            job_id, {"stage": "Code specialist failed"}
                        )
                    return error_msg

                if job_id:
                    self._safe_job_update(
                        job_id, {"stage": "Writing to task_result namespace..."}
                    )
                res = str(code_result.get("result") or "Code specialist completed")
                if len(res) > 4000:
                    return res[:4000] + " [Truncated]"
                return res

            if has_code:
                logger.debug(f"BG1 routing: Code Specialist for job {display_job_id}")
                if job_id:
                    self._safe_job_update(
                        job_id,
                        {
                            "stage": f"Starting {self.runtime.config.code_bg1_model} generation..."
                        },
                    )
                result = run_specialist_code(
                    task_with_context,
                    model=self.runtime.config.code_bg1_model,
                    reviewer_model=self.runtime.config.code_reviewer_model,
                )
                
                # Unload models to free VRAM
                try:
                    OllamaClient(model=self.runtime.config.code_reviewer_model).run("", keep_alive="0")
                except Exception:
                    pass

                if not result.get("ok"):
                    error_msg = f"Code specialist ({self.runtime.config.code_bg1_model}) failed: {result.get('result', 'unknown error')}"
                    logger.error(f"{error_msg} for job {display_job_id}")
                    if job_id:
                        self._safe_job_update(
                            job_id, {"stage": "Code specialist failed"}
                        )
                    return error_msg

                if job_id:
                    self._safe_job_update(
                        job_id, {"stage": "Writing to task_result namespace..."}
                    )
                res = str(result.get("result") or "Code specialist completed")
                if len(res) > 4000:
                    return res[:4000] + " [Truncated]"
                return res

            if has_vision:
                logger.debug(f"BG1 routing: Vision Specialist for job {display_job_id}")
                if job_id:
                    self._safe_job_update(
                        job_id,
                        {
                            "stage": f"Running {self.runtime.config.vision_bg1_model} vision analysis..."
                        },
                    )
                result = run_specialist_vision(
                    task_with_context, model=self.runtime.config.vision_bg1_model
                )
                
                # Unload vision model to free VRAM
                try:
                    OllamaClient(model=self.runtime.config.vision_bg1_model).run("", keep_alive="0")
                except Exception:
                    pass

                if not result.get("ok"):
                    error_msg = f"Vision specialist ({self.runtime.config.vision_bg1_model}) failed: {result.get('reason', 'unknown error')}"
                    logger.error(f"{error_msg} for job {display_job_id}")
                    if job_id:
                        self._safe_job_update(
                            job_id, {"stage": "Vision specialist failed"}
                        )
                    return error_msg
                if job_id:
                    self._safe_job_update(
                        job_id, {"stage": "Writing to task_result namespace..."}
                    )
                return str(result.get("result") or "Vision specialist completed")[:2000]

            url = self._extract_url_from_text(summary)
            if url:
                logger.debug(f"BG1 routing: Web Fetch for job {display_job_id}")
                if job_id:
                    self._safe_job_update(job_id, {"stage": f"Fetching {url}..."})
                from jarvis.tools.web_fetch_extract import fetch_extract

                fetched = fetch_extract(url)
                if fetched.get("ok") and fetched.get("text"):
                    page_text = fetched["text"][:4000]
                    client = OllamaClient(
                        model=self.runtime.config.renderer_model_fallback,
                        timeout_seconds=60,
                    )
                    system_msg = (
                        "You are Jarvis. Summarize the webpage content below. "
                        "IMPORTANT: Only state facts that are explicitly present in the content. "
                        "Do NOT hallucinate URLs, domain names, colors, layouts, or details not in the text. "
                        "Ignore CSS, JavaScript, and technical markup - focus on the actual content text. "
                        "Extract: title, main heading, description, key sections/topics. "
                        "If the content is unclear or incomplete, say so. "
                        "Be concise and factual."
                    )
                    if context_prefix:
                        system_msg += f"\n\nRecent conversation context:\n{context_prefix.strip()}"
                    llm_result = client.chat(
                        [
                            {"role": "system", "content": system_msg},
                            {
                                "role": "user",
                                "content": f"URL: {url}\n\nPage content:\n{page_text}",
                            },
                        ],
                        keep_alive="0",
                    )
                    if llm_result.ok and llm_result.text.strip():
                        return llm_result.text.strip()[:2000]
                    return f"Fetched {url} but could not summarize. Raw excerpt: {page_text[:500]}"
                return (
                    f"Could not fetch {url}: {fetched.get('reason', 'unknown error')}"
                )

            # General Logic/Research using DeepSeek-R1:8b (Logic Specialist)
            logger.debug(
                f"BG1 routing: Logic Specialist (DeepSeek-R1) for job {display_job_id}"
            )
            if job_id:
                self._safe_job_update(
                    job_id,
                    {
                        "stage": f"Starting research with {self.runtime.config.logic_specialist_model}..."
                    },
                )
            client = OllamaClient(
                model=self.runtime.config.logic_specialist_model,
                timeout_seconds=300,
            )
            system_msg = (
                "You are Jarvis, a senior reasoning specialist. "
                "Analyze the following query with deep logical rigor. "
                "Be factual, direct, and exhaustive but concise in your final reasoning. "
                "If you are unsure or lack data, say so clearly."
            )
            if context_prefix:
                system_msg += (
                    f"\n\nRecent conversation context:\n{context_prefix.strip()}"
                )

            # Stream tokens to terminal for real-time display
            self.reset_stream()
            self._stream_active = True
            if job_id:
                self._safe_job_update(
                    job_id,
                    {
                        "stage": f"Streaming from {self.runtime.config.logic_specialist_model}..."
                    },
                )
            result = client.chat_stream(
                [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": summary},
                ],
                keep_alive="0",
                on_token=self.push_stream_token,
            )
            self._stream_active = False

            if result.ok and result.text.strip():
                if job_id:
                    self._safe_job_update(
                        job_id, {"stage": "Writing to task_result namespace..."}
                    )
                return result.text.strip()[:2000]

            error_msg = f"Logic specialist ({self.runtime.config.logic_specialist_model}) failed: {result.error}"
            if job_id:
                self._safe_job_update(job_id, {"stage": "Logic specialist failed"})
            logger.error(f"{error_msg} for job {display_job_id}")
            return error_msg
        except Exception as e:
            error_msg = f"BG1 specialist execution failed: {str(e)}"
            logger.exception(f"{error_msg} for job {display_job_id}")
            if job_id:
                self._safe_job_update(
                    job_id, {"stage": "Exception in specialist execution"}
                )
            return error_msg

    def _build_bg1_context_prefix(self) -> str:
        context_lines = self.runtime._conversation_context_lines(limit=3)
        if not context_lines:
            return ""
        header = "[Recent conversation for context — use only if relevant to the current task]\n"
        return header + "\n".join(context_lines) + "\n\n[Current task]\n"

    @staticmethod
    def _extract_url_from_text(text: str) -> str | None:
        from jarvis.tools.url_normalize import extract_candidate

        return extract_candidate(text)

    def push_stream_token(self, token: str) -> None:
        """Push a token from the streaming LLM to the shared buffer."""
        self._stream_tokens.append(token)

    def read_new_stream_tokens(self) -> list[str]:
        """Read tokens added since last read (called by progress monitor)."""
        new = self._stream_tokens[self._stream_read_pos :]
        self._stream_read_pos = len(self._stream_tokens)
        return new

    def reset_stream(self) -> None:
        """Reset stream buffer between jobs."""
        self._stream_tokens.clear()
        self._stream_read_pos = 0
        self._stream_active = False

    def _safe_job_update(self, job_id: str, patch: dict) -> None:
        try:
            self.runtime.job_status.update(job_id, patch)
        except ValueError:
            return

    def _job_should_stop(self, job_id: str) -> bool:
        current = self.runtime.job_status.get_current()
        if current is None or current.job_id != job_id:
            return True
        return bool(current.cancel_requested or current.force_kill_requested)

    def _wait_or_cancel(self, job_id: str, duration_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, duration_seconds)
        while True:
            if self._job_should_stop(job_id):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self._job_should_stop(job_id)
            time.sleep(min(0.01, remaining))

    def _emit_bg1_notifications(
        self,
        job_id: str,
        was_cancelled: bool,
        result_text: str | None,
    ) -> None:
        subscriptions = self.runtime.job_status.pop_subscriptions()
        if not subscriptions:
            return

        if was_cancelled:
            message = f"Heavy task {job_id} was cancelled."
        elif result_text:
            message = f"Heavy task {job_id} is complete. {result_text}"
        else:
            message = f"Heavy task {job_id} is complete."

        for subscription in subscriptions:
            if subscription.channel == "local":
                self.runtime.tts.speak(message)

            crsis = self.runtime._evaluate_and_persist_crsis(
                source="job_complete_notification",
                turn_id=subscription.turn_id,
                lane_decision="bg1",
                resolved_by="tool_only",
            )
            self.runtime.events.emit(
                EventRecord.build(
                    event_type="job_complete_notification",
                    turn_id=subscription.turn_id,
                    lane_decision="bg1",
                    resolved_by="tool_only",
                    elapsed_ms=1,
                    channel_id=subscription.channel,
                    degraded_mode_active=self.runtime.state.degraded_mode,
                    crsis_status=crsis["status"],
                    crsis_findings=crsis["findings"],
                    crsis_snapshot_jsonl=crsis["jsonl_path"],
                    crsis_snapshot_latest=crsis["latest_path"],
                )
            )
