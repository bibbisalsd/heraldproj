from __future__ import annotations
from jarvis.main import JarvisRuntime


def test_end_to_end_realtime_turn():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    result = rt.run_turn("status")
    assert result["state"] == "DELIVERED"
    assert result["lane"] == "realtime"


def test_end_to_end_heavy_turn():
    rt = JarvisRuntime()
    rt.startup(model_ready=True)
    result = rt.run_turn("please research this deeply")
    assert result["state"] == "DELIVERED"
    assert result["lane"] == "bg1"
