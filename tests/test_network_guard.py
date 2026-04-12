from __future__ import annotations
from jarvis.brain_core.network_guard import NetworkGuard


def test_network_guard_rejects_disallowed_scheme():
    ok, reason = NetworkGuard().validate_url("file:///tmp/test.txt")
    assert ok is False
    assert reason == "DISALLOWED_SCHEME"


def test_network_guard_rejects_private_targets():
    ok, reason = NetworkGuard().validate_url("http://127.0.0.1")
    assert ok is False
    assert reason == "DISALLOWED_TARGET"


def test_network_guard_accepts_public_https():
    ok, reason = NetworkGuard().validate_url("https://example.com")
    assert ok is True
    assert reason == "OK"
