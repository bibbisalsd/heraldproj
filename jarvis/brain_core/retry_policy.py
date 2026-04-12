from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_ms: int
    reason: str


RETRY_LIMITS = {
    "http": 2,
    "chromium_nav": 1,
}


def next_attempt(tool_name: str, attempt: int, error_class: str) -> RetryDecision:
    if error_class not in RETRY_LIMITS:
        return RetryDecision(retry=False, delay_ms=0, reason="non_retryable")
    max_attempts = RETRY_LIMITS[error_class]
    if attempt >= max_attempts:
        return RetryDecision(retry=False, delay_ms=0, reason="attempt_limit_reached")
    delay = min(3000, 400 * (2**attempt))
    return RetryDecision(retry=True, delay_ms=delay, reason=f"retry_{tool_name}")
