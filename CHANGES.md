# CHANGES.md - Jarvis Core Repair Session Summary

## Session Overview
Completed 28 core bug fixes (P1-P3) identified in the codebase audit. Resolved regressions in routing and tool dispatch while maintaining architectural improvements in the Evidence Store and Tool Orchestration.

## Core Fixes (P1 - Runtime Crashes)
- **Quote-Escape Corruption:** Fixed global syntax errors caused by improper string literal escaping in regexes and f-strings.
- **Dynamic Timestamps:** Replaced hardcoded "2026-04-08" strings with dynamic UTC ISO timestamps in `evidence_store.py` and `contracts.py`.
- **Output Gating:** Fixed `AttributeError` in `CLLMRenderer._gate_output` by correctly referencing `tagged_claims`.
- **TTS Protocol:** Added stdin loop to the TTS launcher to support `/ping` coordination for asynchronous reliability.
- **CRSIS Safety:** Implemented atomic temporary-file validation in `CodeModifier` to prevent source corruption during self-improvement cycles.

## Architectural Improvements (P2 - Integrity)
- **Tool Orchestrator:** 
    - Added `LLMDerivedResult` support for inferred provenance.
    - Integrated automatic logging of all tool results to the `EvidenceStore`.
    - Added `Guardrails` check for confirmation-required tools.
- **Asynchronous Voice (P2-10):**
    - Moved inference to daemon threads for non-blocking performance.
    - Added `PYTEST_CURRENT_TEST` detection to switch back to synchronous mode for test stability.
- **SQLite Robustness:** Added `timeout=5` to all SQLite connections to prevent locking during concurrent access.
- **Routing Logic:** 
    - Priority specialist triggers (Code/Vision) now run before deterministic matchers to prevent misrouting of complex queries.
    - Restored original Stage 1-5 ordering in `PromptDispatcher`.
    - Added keyword gates to fuzzy semantic matches (`time_query`, `date_query`) to prevent greedy intercepts.

## Hardening & Refactoring (P3)
- **Legacy Consolidation:** Moved 42-field legacy artifacts to `legacy_contracts.py` to support the new 30-field canonical `TurnArtifact`.
- **Memory Syncing:** Implemented generic `{entity}:{attr}` mirroring rules in `PocketMemory`.
- **Web Timeouts:** Added global timers to Chromium-based tools to prevent hanging on slow network requests.

## Regression Repair
- **Routing Fix:** Resolved issue where "time complexity" requests routed to the clock tool by prioritizing code specialist triggers at the top of the routing cascade.
- **Multi-Intent Restore:** Reverted aggressive interceptor in `handle_codebase_query` that was blocking multi-part tool requests with config file contents.

## Verification
- **Total Tests:** 629 collected.
- **Sanity Check:** `import jarvis` verified OK.
- **Live Test:** Confirmed code requests (BG1) and math/general chat (Realtime) are routing correctly.
