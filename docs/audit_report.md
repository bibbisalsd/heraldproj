## Ruff Audit & Cleanup
- Automatically fixed 34 linting issues (imports, unused variables).
- Manually resolved 10 'unsafe' unused variable and missing import issues.
- Standardized formatting across 138 files using Ruff format.
## Vulture Dead Code Audit
- Removed 3 unused files: jarvis/brain.py, jarvis/brain_core/bg1_lane.py, jarvis/brain_core/task_router.py.
- Cleaned up unreachable code in intent_handlers.py.
- Removed multiple unused constants in deterministic_understanding.py and intent_handlers.py.
- Preserved all 9 legacy duplicate classes as per project instructions.
## Pyright Type Safety Audit
- Fixed critical type mismatch in WorldState ('recent_turn_confidences' was typed as tuple[float, ...] instead of tuple[TurnConfidence, ...]).
- Resolved 15+ missing import warnings by fully restoring .venv with required packages.
- **Remaining Errors (252):** The vast majority of the remaining Pyright errors relate to dynamic dictionary access (e.g., dict[str, object] passed to dict[str, str]), Windows-only module imports failing on Linux (ctypes.windll, win32gui), and missing TypedDict structures. Resolving these autonomously requires invasive architectural changes, so they have been left for manual review.
