# Jarvis Core (Esoteric v0.2) - Project Handoff Document

## What This Is

Jarvis is a local-first voice assistant runtime built in Python. It runs entirely on the user's machine using Ollama for LLM inference, Kokoro ONNX for TTS, and faster-whisper for STT. No cloud APIs. The project was originally built for Windows and has been partially ported to Linux (Pop!_OS).

**Owner**: billybart (goes by James to Jarvis)
**Location**: `/home/billybart/Downloads/Harold/esotericv0.2CURRENT/Harold/Jarvis/Jarviscore/`
**Test Suite**: 627 tests (all mocked — no real TTS/Ollama in tests)
**main.py**: ~960 lines (down from ~2306 after Phase 2 decomposition)

### Completed Plan Phases
| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Observability Hygiene | ✅ Done |
| 1 | Dependency & Configuration Hygiene | ✅ Done |
| 2 | main.py God Class Decomposition | ✅ Done |
| 3 | Tool Registration Unification | ✅ Done |
| 4 | Latency Optimization | ✅ Done |
| 5A | Wire WorldState into routing | ✅ Done |
| 5B | Judge for response claim tagging | ✅ Done |
| 5C | Planner actions executable | ✅ Done |
| 6 | Follow-up Pattern Modernization | ✅ Done |
| 7 | Platform & Security Cleanup | ✅ Done |
| 8 | Documentation Site Updates | ✅ Done |
| 9A | OllamaClient async-capable | ✅ Done |
| 9B | Async pipeline (concurrent route+memory+prewarm) | ✅ Done |

---

## Architecture Overview

### Execution Flow
```
User Speech/Text
  -> VoiceRuntime (mic capture + STT via faster-whisper)
  -> JarvisRuntime.run_turn()
    -> IngressHub -> IngressNormalizer (clean text, assign profile)
    -> PromptDispatcher.route() (5-stage intent classification)
    -> _execute_realtime() OR _execute_heavy()
      -> IntentHandlerRegistry (deterministic handlers)
      -> OR _generate_general_chat_reply() (Ollama LLM)
      -> OR BG1 specialist (code/vision/web/research)
    -> ResponseCompiler + CLLMRenderer (format response)
    -> OutputCoordinator (route to voice/text/discord)
    -> TTS.speak() (Kokoro ONNX pack mode)
  -> Audio playback via sounddevice
```

### Two Execution Lanes
- **Realtime**: Fast path (<100ms target). Greetings, time, status, simple chat. Uses deterministic handlers or gemma4:e2b/e4b.
- **BG1 (Background)**: Heavy tasks run in a separate thread. Single active + single queued. Code generation (deepcoder:14b -> rnj-1:8b review relay), vision (qwen3-vl:8b), web fetch, general research/reasoning (deepseek-r1:8b, 300s timeout).

### 5-Stage Routing (prompt_dispatcher.py)
1. **Exact match** - Hardcoded phrases ("what time is it", "status", etc.)
2. **Strict deterministic** - Signal-based (asks_time, asks_date, asks_cancel, etc.)
3. **Soft deterministic** - Greetings, wellbeing, capabilities, identity, codebase, screen queries
4. **Semantic match** - Ollama embedding model (nomic-embed-text-v2-moe) for fuzzy intent matching. **This is slow (~seconds) and runs on every turn that isn't caught above.**
5. **Classifier fallback** - Keywords route to bg1; everything else becomes `general_chat`

### Key Subsystems
- **Memory**: SQLite-backed key-value facts + pocket entities (relationships). Semantic search via embeddings with lexical fallback.
- **World Model**: Frozen WorldState snapshots, BeliefState tracking, confidence ledger, evidence store.
- **CRSIS**: Self-improvement engine. Analyzes decision logs for misrouting/quality issues, generates repair proposals.
- **Addons**: Plugin framework (Discord reference addon exists). Manifests define tools, bridges, sinks, permissions.
- **Observability**: Event persistence (JSONL), voice path metrics, health reports.

---

## Required Models (Ollama)

| Model | Seat | Purpose | Size |
|-------|------|---------|------|
| gemma4:e2b | renderer_preferred + vision_lite | Primary realtime reasoner, quick vision (multimodal) | ~3 GB |
| gemma4:e4b | renderer_fallback | Fallback reasoner (multimodal, 128K context) | ~4 GB |
| qwen3-vl:8b | vision_bg1 | Heavy vision analysis (BG1) — beats 300B models on vision benchmarks | ~5 GB |
| deepcoder:14b | code_bg1 | Code generation (BG1) — Pass 1 of sequential relay | ~9 GB |
| rnj-1:8b | code_reviewer | Code review/profiling (BG1) — Pass 2, reviews deepcoder output | ~5 GB |
| deepseek-r1:8b | logic_specialist | Deep reasoning, math, research (BG1, 300s timeout) | ~5 GB |
| nomic-embed-text-v2-moe | embedding | Semantic intent matching + memory search (~100 languages) | ~1 GB |

All models run locally via Ollama HTTP API on `127.0.0.1:11434`.

### Model Architecture: Sequential Code Relay
```
Code request -> deepcoder:14b (generate) -> rnj-1:8b (review/profile) -> output
```
If the reviewer model fails, the system gracefully falls back to the initial generation.

---

## Configuration (jarvis/config.py)

```python
@dataclass(frozen=True)
class JarvisConfig:
    renderer_model_preferred: str = "gemma4:e2b"
    renderer_model_fallback: str = "gemma4:e4b"
    vision_lite_model: str = "gemma4:e2b"
    vision_bg1_model: str = "qwen3-vl:8b"
    code_bg1_model: str = "deepcoder:14b"
    code_reviewer_model: str = "rnj-1:8b"
    logic_specialist_model: str = "deepseek-r1:8b"
    embedding_model: str = "nomic-embed-text-v2-moe"
    wake_word_enabled: bool = True
    wake_word_phrase: str = "jarvis"
    stt_model: str = "small.en"  # faster-whisper model
    tts_model: str = "Kokoro-82M"
    conversation_buffer_max_turns: int = 8
    bg1_max_active_jobs: int = 1
    bg1_max_queue_length: int = 1
    core_output_default: str = "local_voice"
    permission_profiles: Tuple = ("owner", "trusted", "guest")
```

---

## Directory Structure

```
Jarviscore/
  jarvis/
    main.py               # JarvisRuntime (~1900 lines) - the core
    config.py             # JarvisConfig frozen dataclass
    memory.py             # SQLite memory interface
    pocket_memory.py      # Entity-keyed memories
    name_profile.py       # Owner name/title management
    brain_core/
      contracts.py        # All data contracts (RawEvent, IngressEnvelope, etc.)
      prompt_dispatcher.py  # 5-stage intent routing
      intent_handlers.py  # 50+ deterministic intent handlers (~1400 lines)
      deterministic_understanding.py  # Signal extraction (is_greeting, asks_time, etc.)
      semantic_command_match.py  # Embedding-based intent matching
      task_classifier.py  # Heavy vs realtime classification
      conversation_buffer.py  # Turn history
      ingress_hub.py / ingress_normalizer.py  # Input pipeline
      lane_coordinator.py  # Realtime vs BG1 dispatch
      output_coordinator.py  # Sink selection (voice/text/discord)
      bg1_queue.py / bg1_worker.py  # Background job execution
      turn_state_machine.py  # Turn lifecycle states
      admission_control.py  # Rate limiting
      fallback_policy.py  # Degraded mode handling
      addon_*.py          # Addon management (registry, channels, audio, health, permissions)
    models/
      ollama_client.py    # Ollama HTTP+CLI wrapper
      cllm_renderer.py    # Response rendering via LLM
      embedding.py        # Semantic embeddings
      workspace_inputs.py # File context for specialists
    voice/
      runtime.py          # VoiceRuntime (~1100 lines) - mic capture + orchestration
      stt.py              # faster-whisper STT
      tts.py              # Kokoro/SAPI TTS dispatcher
      kokoro_pack/        # Bundled Kokoro ONNX voice pack
        jarvis_launcher.py  # Standalone TTS engine
        kokoro/             # Model files (kokoro-v1.0.onnx, voices-v1.0.bin)
    tools/                # 35+ tool implementations
      web_fetch_http.py   # HTTP fetcher (urllib, respects robots.txt)
      web_fetch_extract.py  # Fetch + extract main text
      web_extract_main_text.py  # HTML -> readable text
      calculator.py       # Deterministic math
      code_runner.py      # Python exec (owner-only, confirmation-gated)
      file_write.py       # File operations
      memory_tool.py      # Memory search/save
      job_status_tool.py  # BG1 job monitoring
      app_ops.py          # App launch/focus (Windows-only currently)
      screen_capture.py   # Screenshots (Windows-only currently)
      ocr_read.py         # OCR (Windows OCR / Tesseract / sidecar)
    specialists/
      specialist_code.py  # Code analysis via deepcoder:14b -> rnj-1:8b review relay
      specialist_vision.py  # Vision analysis via qwen3-vl:8b
    world_model/          # Unified state tracking
    crsis/                # Self-improvement engine
    observability/        # Events, metrics, health reports
    maintenance/          # Daily ops, retention, readiness
  addons/
    discord_addon/        # Reference addon implementation
  tests/                  # Extensive test suite
  scripts/                # PowerShell automation (Windows-only)
  run_chat.py             # Linux text chat entry point (we created this)
  run_voice.py            # Linux voice loop entry point (we created this)
  mic_test.py             # Mic diagnostic tool (we created this)
```

---

## Linux Port Status (Changes We Made)

### Files Modified

**jarvis/voice/kokoro_pack/jarvis_launcher.py**
- `import winsound` changed to conditional import (None on Linux)
- `winsound.PlaySound()` falls back to `sounddevice.play()` + `sd.wait()` on Linux
- Lines affected: top imports + line ~1128

**jarvis/voice/runtime.py**
- `reuse_stream=True` changed to `reuse_stream=False` in `process_microphone_passive()` continuous mode (line ~253). Persistent PortAudio streams hang on Linux PipeWire/PulseAudio.
- Speech detection thresholds lowered for Linux mic levels:
  - `speech_threshold`: 520 -> 150
  - `silence_threshold`: 220 -> 60
  - `soft_speech_threshold`: 260 -> 80
- Dynamic threshold multipliers reduced: `noise_floor * 2.4` -> `1.8`, `1.55` -> `1.4`
- Debug amplitude prints added (every 15 chunks): `[mic] amp=X noise=Y soft=Z hard=W`

**jarvis/voice/stt.py**
- STT runs on CPU: `WhisperModel(model, device="cpu", compute_type="int8")`
- We tried CUDA but it broke transcription (needs nvidia-cublas/cudnn packages). Reverted.

**jarvis/brain_core/prompt_dispatcher.py**
- Moved `_match_soft_deterministic()` call BEFORE `semantic_matcher.match()` in `route()`. This skips the slow Ollama embedding call for greetings, identity queries, etc.
- Added `is_greeting` check to `_match_soft_deterministic()` so "hello" routes instantly without hitting the LLM.

**jarvis/main.py**
- `_generate_general_chat_reply()`: Added conversation history (last 5 turns as user/assistant pairs) so the LLM has context for follow-up questions.
- `_execute_bg1_specialist()`: 
  - Added web URL detection + actual page fetching via `web_fetch_extract` tool
  - Added general research fallback using llama3.2:3b (was previously a dead-end "Heavy task completed." string)
  - Increased result truncation from 400/800 chars to 2000
  - Added `_extract_url_from_text()` static method for URL/domain detection

### Files Created (Linux-specific)

**run_chat.py** - Text-only chat loop (no voice)
```python
from jarvis.main import JarvisRuntime
rt = JarvisRuntime()
rt.startup(model_ready=True)
# ... input loop calling rt.run_turn(user) ...
rt.shutdown()
```

**run_voice.py** - Full voice loop with mic input + TTS output
- Sets JARVIS_USE_KOKORO_PACK, JARVIS_KOKORO_PACK_DIR, JARVIS_TTS_BACKEND env vars
- Supports JARVIS_VOICE_INPUT_DEVICE / JARVIS_VOICE_OUTPUT_DEVICE env vars for device selection
- Uses `process_microphone_passive()` with wake word detection
- Equivalent of Windows `start_jarvis_voice_loop.ps1`

**mic_test.py** - Quick mic diagnostic (records 3s, shows amplitude stats)

---

## Known Issues / Incomplete Items

### Voice / Audio
- **Mic amplitude is low on Linux**: Most chunks read amp=1-5 via InputStream callback, but sd.rec() shows normal levels (mean ~938). Likely a PipeWire streaming issue. Speech still gets detected on loud chunks but quiet speech is missed. The user may need to boost input gain in PulseAudio/PipeWire settings.
- **STT is CPU-only**: CUDA for faster-whisper needs nvidia-cublas and nvidia-cudnn packages installed separately. Without them, model loads but inference fails silently.
- **TTS latency**: First Kokoro synthesis is slow (~5s) due to ONNX model cold-start. Subsequent calls are faster.
- **No voice output device selection**: TTS always plays to system default. The `output_device` parameter is audit-only.

### Platform-Specific (Windows-only, not ported)
- `app_ops.py` (launch/focus apps) - uses Windows COM
- `screen_capture.py` - uses Windows screen grab APIs
- OCR via `Windows.Media.Ocr` - Tesseract works as alternative on Linux
- SAPI TTS fallback - not available on Linux (Kokoro is the only backend)
- All PowerShell scripts in `scripts/` - Linux equivalents are `run_chat.py` and `run_voice.py`

### Functional Gaps
- **Web fetch works but routing is keyword-based**: Only triggers if URL is detected in the task text. Requests like "look up weather" or "search for X" don't trigger web fetch.
- **general_chat has no web access**: The LLM can only answer from training knowledge. No search/scraping for realtime-routed questions.
- **Conversation history only in general_chat**: The 5-turn history injection was added to `_generate_general_chat_reply()` but not to the renderer or BG1 paths.
- **Planner execution is single-action only (Phase 5C)**: The planner can now execute single-action, realtime-lane tool_call plans deterministically. Multi-action plans and BG1-only plans are still log-only. Tasks need `tool_name` (and optionally `tool_kwargs`) in their metadata to trigger tool_call plan generation.
- **Code review relay adds latency**: The deepcoder:14b -> rnj-1:8b sequential relay requires VRAM swap on 6GB GPU (~10-15s per swap). The reviewer pass is gracefully optional (falls back to Pass 1 output on failure).
- **9 duplicate class definitions (merger artifact)**: TurnArtifact, EvidencePacket, JobStatus, TaskDecision, and 5 others exist in two files with diverged fields. Canonical locations are documented with docstring markers. See GEMINI.md for the full table.

### Recently Fixed (2026-04-08)
- PromptDispatcher now routes natural coding phrases ("write a Python class") to BG1 code specialist
- PromptDispatcher now routes stories/poems/jokes to general_chat renderer
- tool_policy.py safe getattr checks prevent crashes on ToolDescriptor/ToolMetadata mismatch
- DeepSeek-R1:8b logic specialist timeout increased from 120s to 300s
- code_reviewer_model config field now properly wired through bg1_manager -> specialist_code -> models/code
- TYPE_CHECKING imports in bg1_manager corrected (was importing from wrong module)
- brain_core/__init__.py now exports the canonical contracts.py TurnArtifact (was exporting the diverged turn_artifact.py version)

### Hardware (User's Setup)
- **GPU**: NVIDIA GeForce RTX 4050 Laptop (6GB VRAM) - Ollama uses it (~1750MB)
- **CPU**: Gets hot during STT (faster-whisper on CPU) and Kokoro TTS
- **OS**: Pop!_OS (Linux, kernel 6.18.7), PipeWire audio
- **Python**: 3.12.3

---

## How to Run on Linux

### Prerequisites
```bash
sudo apt install portaudio19-dev libportaudio2  # Required for sounddevice
```

### Setup
```bash
cd ~/Downloads/Harold/esotericv0.2CURRENT/Harold/Jarvis/Jarviscore
python3 -m venv .venv
source .venv/bin/activate
pip install numpy soundfile kokoro_onnx sounddevice faster-whisper
```

### Pull Ollama Models
```bash
ollama pull gemma4:e2b && ollama pull gemma4:e4b
ollama pull qwen3-vl:8b && ollama pull deepcoder:14b
ollama pull rnj-1:8b && ollama pull deepseek-r1:8b
ollama pull nomic-embed-text-v2-moe
```

### Run
```bash
# Text chat only
python3 run_chat.py

# Voice loop (mic + TTS)
export JARVIS_VOICE_INPUT_DEVICE=4   # optional: pick specific mic
python3 run_voice.py

# Mic diagnostic
python3 mic_test.py
```

### Environment Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| JARVIS_TTS_BACKEND | kokoro | TTS engine (kokoro/auto/sapi) |
| JARVIS_USE_KOKORO_PACK | true | Use bundled ONNX voice pack |
| JARVIS_KOKORO_PACK_DIR | jarvis/voice/kokoro_pack | Pack location |
| JARVIS_VOICE_INPUT_DEVICE | (none) | Mic device index |
| JARVIS_VOICE_OUTPUT_DEVICE | (none) | Speaker device index |
| JARVIS_VOICE_DURATION | 6.0 | Capture window seconds |
| JARVIS_VOICE_SAMPLE_RATE | 16000 | Audio sample rate |
| JARVIS_VOICE_PAUSE_SECONDS | 0.9 | Silence detection threshold |
| JARVIS_VOICE_MAX_UTTERANCE_SECONDS | 18.0 | Max speech duration |
| JARVIS_ENABLE_EMBEDDING_MATCH | true | Semantic intent matching |
| JARVIS_ENABLE_SEMANTIC_MEMORY_RETRIEVAL | true | Semantic memory search |

---

## Key Code Patterns

### Adding a new deterministic intent
1. Add signal detection in `brain_core/deterministic_understanding.py`
2. Add routing in `prompt_dispatcher.py` (_match_strict_deterministic or _match_soft_deterministic)
3. Add handler in `intent_handlers.py`
4. Register in `build_default_registry()`

### Adding a new tool
1. Create tool function in `jarvis/tools/`
2. Register in `JarvisRuntime._register_default_tools()`
3. Optionally gate with capability + confirmation

### Adding a new BG1 specialist
1. Add keyword detection in `_execute_bg1_specialist()` in `main.py`
2. Create specialist function in `jarvis/specialists/`
3. The specialist gets the task summary and returns a result dict

### Data contracts
All message types are frozen dataclasses in `brain_core/contracts.py`. Key types:
- `RawEvent` -> `IngressEnvelope` -> `TaskDecision` -> `TurnExecutionResult` -> `RenderedReply`
