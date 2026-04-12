from __future__ import annotations
from jarvis.main import JarvisRuntime


def test_runtime_startup_and_shutdown_are_clean():
    runtime = JarvisRuntime()
    state = runtime.startup(model_ready=True)
    assert state.started is True
    assert state.degraded_mode is False
    state = runtime.shutdown()
    assert state.shutdown is True


def test_runtime_enters_degraded_mode_when_model_not_ready():
    runtime = JarvisRuntime()
    state = runtime.startup(model_ready=False)
    assert state.degraded_mode is True
