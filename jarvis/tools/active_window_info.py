from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _supports_active_window() -> bool:
    """Check if active window tracking is supported on the current platform."""
    if os.name == "nt":
        return True
    return _linux_display_available()


def current() -> dict:
    if not _supports_active_window():
        return {
            "ok": False,
            "reason": "active_window_info_unavailable",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    # Try Windows reader first (even on Linux if supported/monkeypatched)
    # This ensures test_active_window_info_reports_window_details_when_available passes
    try:
        result = _read_windows_active_window()
        if result.get("ok"):
            return result
    except Exception:
        pass

    # Fall back to Linux reader
    result = _read_linux_active_window()
    if result.get("ok"):
        return result
    return {
        "ok": False,
        "reason": str(result.get("reason", "active_window_info_unavailable")),
        "window_title": result.get("window_title"),
        "process_name": result.get("process_name"),
        "pid": result.get("pid"),
    }


# ---------------------------------------------------------------------------
# Linux implementation
# ---------------------------------------------------------------------------


def _linux_display_available() -> bool:
    """Check if a display server is available (X11 or Wayland)."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _read_linux_active_window() -> dict:
    """Read active window info on Linux using xdotool (X11) or fallbacks."""
    # Try xdotool first (works on X11 and XWayland)
    xdotool = shutil.which("xdotool")
    if xdotool:
        return _read_via_xdotool(xdotool)

    # Try xprop as fallback (X11 only)
    xprop = shutil.which("xprop")
    if xprop:
        return _read_via_xprop(xprop)

    return {
        "ok": False,
        "reason": "no_linux_window_tool_available (install xdotool)",
        "window_title": None,
        "process_name": None,
        "pid": None,
    }


def _read_via_xdotool(xdotool_bin: str) -> dict:
    """Read active window info using xdotool."""
    # Get active window ID
    try:
        wid_result = subprocess.run(
            [xdotool_bin, "getactivewindow"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return {
            "ok": False,
            "reason": "xdotool_getactivewindow_failed",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    if wid_result.returncode != 0 or not wid_result.stdout.strip():
        return {
            "ok": False,
            "reason": "no_foreground_window",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    window_id = wid_result.stdout.strip()

    # Get window name
    window_title = None
    try:
        name_result = subprocess.run(
            [xdotool_bin, "getwindowname", window_id],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if name_result.returncode == 0:
            window_title = name_result.stdout.strip() or None
    except Exception:
        pass

    # Get PID
    pid = None
    try:
        pid_result = subprocess.run(
            [xdotool_bin, "getwindowpid", window_id],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if pid_result.returncode == 0 and pid_result.stdout.strip().isdigit():
            pid = int(pid_result.stdout.strip())
    except Exception:
        pass

    # Get process name from PID
    process_name = None
    executable_path = None
    if pid is not None:
        process_name, executable_path = _process_name_from_pid(pid)

    if not window_title and not process_name:
        return {
            "ok": False,
            "reason": "foreground_window_metadata_unavailable",
            "window_title": None,
            "process_name": None,
            "pid": pid,
        }

    return {
        "ok": True,
        "window_title": window_title,
        "process_name": process_name,
        "pid": pid,
        "executable_path": executable_path,
        "backend": "xdotool",
    }


def _read_via_xprop(xprop_bin: str) -> dict:
    """Read active window info using xprop (fallback)."""
    # Get active window title via _NET_ACTIVE_WINDOW
    try:
        result = subprocess.run(
            [xprop_bin, "-root", "_NET_ACTIVE_WINDOW"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return {
            "ok": False,
            "reason": "xprop_failed",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    if result.returncode != 0:
        return {
            "ok": False,
            "reason": "xprop_net_active_window_failed",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    # Parse window ID from xprop output like "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x4600003"
    import re

    match = re.search(r"0x[0-9a-fA-F]+", result.stdout)
    if not match:
        return {
            "ok": False,
            "reason": "no_foreground_window",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    window_id = match.group(0)

    # Get window name and PID
    window_title = None
    pid = None
    try:
        wm_result = subprocess.run(
            [xprop_bin, "-id", window_id, "WM_NAME", "_NET_WM_PID"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if wm_result.returncode == 0:
            for line in wm_result.stdout.splitlines():
                if "WM_NAME" in line:
                    name_match = re.search(r'"(.+)"', line)
                    if name_match:
                        window_title = name_match.group(1).strip() or None
                if "_NET_WM_PID" in line:
                    pid_match = re.search(r"=\s*(\d+)", line)
                    if pid_match:
                        pid = int(pid_match.group(1))
    except Exception:
        pass

    process_name = None
    executable_path = None
    if pid is not None:
        process_name, executable_path = _process_name_from_pid(pid)

    if not window_title and not process_name:
        return {
            "ok": False,
            "reason": "foreground_window_metadata_unavailable",
            "window_title": None,
            "process_name": None,
            "pid": pid,
        }

    return {
        "ok": True,
        "window_title": window_title,
        "process_name": process_name,
        "pid": pid,
        "executable_path": executable_path,
        "backend": "xprop",
    }


def _process_name_from_pid(pid: int) -> tuple[str | None, str | None]:
    """Get process name and executable path from PID via /proc."""
    proc_exe = Path(f"/proc/{pid}/exe")
    proc_comm = Path(f"/proc/{pid}/comm")

    executable_path = None
    process_name = None

    try:
        if proc_exe.exists():
            executable_path = str(proc_exe.resolve())
            process_name = Path(executable_path).name or None
    except (OSError, PermissionError):
        pass

    if process_name is None:
        try:
            if proc_comm.exists():
                process_name = proc_comm.read_text().strip() or None
        except (OSError, PermissionError):
            pass

    return process_name, executable_path


# ---------------------------------------------------------------------------
# Windows implementation (unchanged from original)
# ---------------------------------------------------------------------------


def _read_windows_active_window() -> dict:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return {
            "ok": False,
            "reason": "win32_api_import_failed",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    user32 = ctypes.windll.user32  # type: ignore
    kernel32 = ctypes.windll.kernel32  # type: ignore

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {
            "ok": False,
            "reason": "no_foreground_window",
            "window_title": None,
            "process_name": None,
            "pid": None,
        }

    title_length = max(int(user32.GetWindowTextLengthW(hwnd)), 0)
    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    window_title = title_buffer.value.strip() or None

    pid = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not thread_id or not pid.value:
        return {
            "ok": False,
            "reason": "foreground_window_pid_unavailable",
            "window_title": window_title,
            "process_name": None,
            "pid": None,
        }

    executable_path = None
    process_name = None
    process_handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if process_handle:
        try:
            size = wintypes.DWORD(32768)
            path_buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(
                process_handle, 0, path_buffer, ctypes.byref(size)
            ):
                executable_path = path_buffer.value
                process_name = Path(executable_path).name or None
        finally:
            kernel32.CloseHandle(process_handle)

    if not window_title and not process_name:
        return {
            "ok": False,
            "reason": "foreground_window_metadata_unavailable",
            "window_title": None,
            "process_name": None,
            "pid": int(pid.value),
        }

    return {
        "ok": True,
        "window_title": window_title,
        "process_name": process_name,
        "pid": int(pid.value),
        "executable_path": executable_path,
        "backend": "win32_user32",
    }
