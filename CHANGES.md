# CHANGES.md - Harold / Jarvis Core Repair Session Summary

## Session Overview
Successfully implemented 28 core bug fixes (P1-P3) and resolved critical regressions in routing and multi-intent tool dispatch. Established a GitHub-compliant repository baseline with optimized history.

## Repository Setup
- **Initialized Git:** Created a new clean repository in `esotericv0.2CURRENT/Harold/Jarvis/Jarviscore`.
- **Optimization:** Added comprehensive `.gitignore` to exclude large voice models (*.onnx, *.bin) and local artifacts, keeping the push size under GitHub limits.
- **Remote:** Pushed to `https://github.com/bibbisalsd/heraldproj.git` (main branch).

## Core Fixes (P1 - Runtime Crashes)
- **Quote-Escape Corruption:** Restored thousands of string literals and regex patterns damaged by global `sed` operations.
- **Dynamic Timestamps:** Switched from hardcoded "2026-04-08" to dynamic UTC ISO timestamps in `evidence_store.py` and `contracts.py`.
- **Output Gating:** Fixed `AttributeError` in `CLLMRenderer._gate_output` by correcting `tagged_claims` references.
- **TTS Reliability:** Implemented standard input loop in TTS launcher to support async `/ping` coordination.
- **CRSIS Safety:** Added atomic file validation in `CodeModifier` to prevent source corruption.

## Architectural Improvements (P2 - Integrity)
- **Tool Orchestrator (P2-9):** 
    - Added `LLMDerivedResult` for better handling of inferred facts.
    - Integrated automatic evidence logging for every tool execution.
    - Added guardrails for high-risk tools.
- **Asynchronous Voice (P2-10):**
    - Moved inference to background threads for non-blocking response.
    - Added logic to detect `pytest` and switch to synchronous mode for test stability.
- **SQLite Robustness:** Added 5-second timeouts to all database connections.
- **Routing Precision:**
    - Moved Code/Vision specialist triggers to the absolute top of the cascade.
    - Restored original 5-stage deterministic order.
    - Added keyword gates to fuzzy matches (`time_query`, `date_query`) to fix misrouting of "time complexity" requests.

## Hardening (P3)
- **Artifact Consolidation:** Partitioned 42-field legacy artifacts into `legacy_contracts.py`.
- **Memory Syncing:** Implemented `{entity}:{attr}` mirroring rules in `PocketMemory`.
- **Browser Tools:** Added global crawl timeouts to prevent hanging on slow web requests.

## Final Verification
- **Total Tests:** 629.
- **Sanity Check:** `import jarvis` verified OK.
- **Live Test (BST):** Confirmed "Write a binary search tree" routes correctly to Code Specialist (BG1).
- **Live Test (Multi-Intent):** Confirmed "sqrt and date" query no longer dumps config files and returns a structured codebase summary.
