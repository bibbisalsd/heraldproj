from __future__ import annotations
from jarvis.brain_core.retry_policy import next_attempt


def test_retry_policy_allows_http_retry_with_backoff():
    decision = next_attempt("web_fetch_http", attempt=0, error_class="http")
    assert decision.retry is True
    assert decision.delay_ms >= 400


def test_retry_policy_blocks_unknown_error_class():
    decision = next_attempt("unknown", attempt=0, error_class="non_idempotent")
    assert decision.retry is False
