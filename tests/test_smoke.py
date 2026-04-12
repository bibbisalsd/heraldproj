from __future__ import annotations
from jarvis.config import build_default_config


def test_smoke_config_instantiates():
    cfg = build_default_config()
    assert cfg.wake_word_phrase == "jarvis"
