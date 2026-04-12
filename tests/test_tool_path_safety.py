from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.tools.artifact_store import store_text
from jarvis.tools.download_file import download


def _make_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("# workspace root\n", encoding="utf-8")
    monkeypatch.chdir(workspace)
    return workspace


def test_artifact_store_writes_inside_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _make_workspace(tmp_path, monkeypatch)

    result = store_text("artifacts", "note.txt", "hello")

    assert result["ok"] is True
    written = Path(result["path"])
    assert written == workspace / "artifacts" / "note.txt"
    assert written.read_text(encoding="utf-8") == "hello"


def test_artifact_store_rejects_outside_workspace_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_workspace(tmp_path, monkeypatch)
    outside_dir = tmp_path / "outside"

    result = store_text(str(outside_dir), "note.txt", "hello")

    assert result == {"ok": False, "reason": "path_outside_workspace"}


def test_artifact_store_rejects_name_traversal_outside_artifact_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_workspace(tmp_path, monkeypatch)

    result = store_text("artifacts", "..\\escape.txt", "hello")

    assert result == {"ok": False, "reason": "path_outside_artifact_dir"}


def test_download_writes_inside_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _make_workspace(tmp_path, monkeypatch)

    result = download("https://example.com/file.txt", "downloads/file.txt")

    assert result["ok"] is True
    written = Path(result["path"])
    assert written == workspace / "downloads" / "file.txt"
    assert written.read_text(encoding="utf-8") == "downloaded-from:https://example.com/file.txt"


def test_download_rejects_outside_workspace_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_workspace(tmp_path, monkeypatch)
    outside_destination = tmp_path / "outside" / "file.txt"

    result = download("https://example.com/file.txt", str(outside_destination))

    assert result == {"ok": False, "reason": "path_outside_workspace"}


def test_download_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _make_workspace(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "escaped.txt"
    target.write_text("original", encoding="utf-8")

    link_path = workspace / "downloads" / "link.txt"
    link_path.parent.mkdir(parents=True)
    try:
        link_path.symlink_to(target)
    except (NotImplementedError, OSError) as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = download("https://example.com/file.txt", str(link_path))

    assert result == {"ok": False, "reason": "path_outside_workspace"}
    assert target.read_text(encoding="utf-8") == "original"
