from __future__ import annotations
from jarvis.tools.active_window_info import current
from jarvis.tools.app_ops import focus, launch
from jarvis.tools.research_brief import build


def test_active_window_info_reports_unavailable_when_platform_unsupported(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.tools.active_window_info._supports_active_window", lambda: False)

    result = current()

    assert result["ok"] is False
    assert result["reason"] == "active_window_info_unavailable"
    assert result["window_title"] is None
    assert result["process_name"] is None


def test_active_window_info_reports_window_details_when_available(monkeypatch) -> None:
    monkeypatch.setattr("jarvis.tools.active_window_info._supports_active_window", lambda: True)
    monkeypatch.setattr(
        "jarvis.tools.active_window_info._read_windows_active_window",
        lambda: {
            "ok": True,
            "window_title": "Visual Studio Code",
            "process_name": "Code.exe",
            "pid": 4242,
            "backend": "win32_user32",
        },
    )

    result = current()

    assert result["ok"] is True
    assert result["window_title"] == "Visual Studio Code"
    assert result["process_name"] == "Code.exe"
    assert result["pid"] == 4242


def test_app_ops_report_unavailable() -> None:
    launched = launch("calculator")
    focused = focus("calculator")

    assert launched["ok"] is False
    assert launched["reason"] == "app_ops_unavailable"
    assert launched["action"] == "launch"
    assert focused["ok"] is False
    assert focused["reason"] == "app_ops_unavailable"
    assert focused["action"] == "focus"


def test_research_brief_marks_empty_findings_as_input_derived() -> None:
    result = build(topic="Jarvis", findings=[], urls=["https://example.com"])

    assert result["ok"] is True
    assert result["summary"] == ""
    assert result["summary_source"] == "input_findings"
    assert result["finding_count"] == 0


def test_research_brief_marks_summary_as_input_derived() -> None:
    result = build(topic="Jarvis", findings=["finding one", "finding two"], urls=["https://example.com"])

    assert result["ok"] is True
    assert result["summary"] == "finding one finding two"
    assert result["summary_source"] == "input_findings"
    assert result["finding_count"] == 2
