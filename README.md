# Harold / Jarvis Core

A local-first AI assistant runtime built in Python. Designed for high-integrity, deterministic interaction with integrated memory, tool policy, and self-improvement loops.

## Architecture
- **Cognitive Layer (Mind):** World model, evidence store, belief state, and CRSIS self-improvement engine.
- **Deterministic Pipeline (Spinal Cord):** 5-stage routing cascade, tool policy, and evidence-anchored rendering.
- **Hardware Integration:** 
  - **LLM:** Ollama (Local)
  - **TTS:** Kokoro ONNX
  - **STT:** Faster-Whisper

## Key Features
- **Fact-Anchored Rendering:** Prevents hallucinations by restricting the LLM to verified evidence.
- **5-Stage Routing:** Exact match -> Strict Deterministic -> Soft Deterministic -> Semantic -> Classifier.
- **Asynchronous Voice Pipeline:** Multi-threaded inference for low-latency response.
- **CRSIS Self-Improvement:** Automated pattern detection and AST-safe code modification.

## Quick Start
1. **Setup Environment:**
   ```bash
   ./unify_venv.sh
   source .venv_old/bin/activate
   export PYTHONPATH=$PYTHONPATH:.
   ```
2. **Run Chat:**
   ```bash
   python3 run_chat.py
   ```
3. **Run Voice (requires microphone):**
   ```bash
   python3 run_voice.py
   ```

## Development
- **Tests:** 629 unique test cases.
- **Validation:** Run `pytest tests/ -x` for incremental verification.
- **Documentation:** See `PROJECT_HANDOFF.md` and `CHANGES.md` for recent repair summaries.

## License
Private Property of billybart (James).
