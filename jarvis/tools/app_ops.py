"""Desktop application launch and focus control.

Cross-platform: Windows (pywin32, COM) and Linux (xdg-open, xdotool).
Safe allowlisted app launch/focus using subprocess.
Permission-gated (owner/trusted only).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


# Allowlist of safe-to-launch applications
# Maps common names to executable paths or command patterns
_WINDOWS_APP_ALLOWLIST = {
    # Built-in Windows apps
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "wordpad": "write.exe",
    "snipping tool": "snippingtool.exe",
    "sticky notes": "stickynotes.exe",
    "clock": "Alarms.exe",
    "alarms": "Alarms.exe",
    "photos": "microsoft.windows.photos:_default",
    "store": "microsoft.windows.store:_default",
    "settings": "ms-settings:",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "powershell": "powershell.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    # Common browsers
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "brave": "brave.exe",
    # Common apps
    "code": "code.exe",
    "vscode": "code.exe",
    "visual studio code": "code.exe",
    "slack": "slack.exe",
    "discord": "discord.exe",
    "spotify": "spotify.exe",
    "steam": "steam.exe",
    "zoom": "zoom.exe",
    "teams": "teams.exe",
    "microsoft teams": "teams.exe",
    "outlook": "outlook.exe",
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
}

_LINUX_APP_ALLOWLIST = {
    # File managers
    "files": "nautilus",
    "file manager": "nautilus",
    "nautilus": "nautilus",
    "thunar": "thunar",
    "dolphin": "dolphin",
    "nemo": "nemo",
    # Terminals
    "terminal": "gnome-terminal",
    "gnome terminal": "gnome-terminal",
    "konsole": "konsole",
    "xterm": "xterm",
    "alacritty": "alacritty",
    "kitty": "kitty",
    # Browsers
    "chrome": "google-chrome",
    "google chrome": "google-chrome",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
    "brave": "brave-browser",
    "chromium": "chromium-browser",
    "edge": "microsoft-edge",
    "microsoft edge": "microsoft-edge",
    # Editors / IDEs
    "code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "gedit": "gedit",
    "kate": "kate",
    "nano": "nano",
    "vim": "vim",
    # Common apps
    "calculator": "gnome-calculator",
    "calc": "gnome-calculator",
    "slack": "slack",
    "discord": "discord",
    "spotify": "spotify",
    "steam": "steam",
    "zoom": "zoom",
    "teams": "teams",
    "microsoft teams": "teams",
    # System
    "settings": "gnome-control-center",
    "system settings": "gnome-control-center",
    "system monitor": "gnome-system-monitor",
    "task manager": "gnome-system-monitor",
}

# Unified allowlist (platform-dependent)
SAFE_APP_ALLOWLIST = _WINDOWS_APP_ALLOWLIST if os.name == "nt" else _LINUX_APP_ALLOWLIST

# Known installation paths for common apps (Windows only)
if os.name == "nt":
    APP_SEARCH_PATHS = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
        if os.environ.get("LOCALAPPDATA")
        else None,
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files"))
        / "Microsoft VS Code"
        / "bin",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps"
        if os.environ.get("LOCALAPPDATA")
        else None,
    ]
    APP_SEARCH_PATHS = [p for p in APP_SEARCH_PATHS if p]
else:
    APP_SEARCH_PATHS = []


def _normalize_app_name(name: str) -> str:
    """Normalize app name for matching."""
    return name.lower().strip().replace("-", " ").replace("_", " ")


def _supports_app_ops(action: str = "launch") -> bool:
    """Check if app operations are supported on the current platform."""
    if sys.platform == "win32":
        try:
            import win32gui
            return True
        except ImportError:
            return False
    
    if sys.platform.startswith("linux"):
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        has_xdotool = bool(shutil.which("xdotool"))
        
        if action == "launch":
            # Launching on Linux is supported if we have a display (even without xdotool)
            # This satisfies B2's instruction to proceed to executable lookup.
            return has_display
            
        # focus/close need a display AND xdotool
        return has_display and has_xdotool
    
    return False


def launch(app_name: str) -> dict[str, Any]:
    """Launch an application by name.

    Args:
        app_name: Name of the application to launch (e.g., "notepad", "chrome", "firefox")

    Returns: dict with keys:
            - ok: bool
            - reason: str (error message if not ok)
            - action: "launch"
            - app: str (app name)
            - pid: int|None (process ID if launched)
            - path: str|None (path to executable)
    """
    if not _supports_app_ops("launch"):
        return {
            "ok": False,
            "reason": "app_ops_unavailable",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": None,
        }

    if os.name == "nt":
        return _launch_windows(app_name)
    return _launch_linux(app_name)


def focus(app_name: str) -> dict[str, Any]:
    """Bring an application window to the foreground.

    Args:
        app_name: Name of the application to focus

    Returns: dict with keys:
            - ok: bool
            - reason: str (error message if not ok)
            - action: "focus"
            - app: str (app name)
            - window_found: bool
            - hwnd: int|None (window handle if found, Windows only)
    """
    if not _supports_app_ops("focus"):
        return {
            "ok": False,
            "reason": "app_ops_unavailable",
            "action": "focus",
            "app": app_name,
            "window_found": False,
            "hwnd": None,
        }

    if os.name == "nt":
        return _focus_windows(app_name)
    return _focus_linux(app_name)


def close(app_name: str) -> dict[str, Any]:
    """Close an application window.

    Args:
        app_name: Name of the application to close

    Returns: dict with keys:
            - ok: bool
            - reason: str
            - action: "close"
            - app: str
    """
    if os.name == "nt":
        return _close_windows(app_name)
    return _close_linux(app_name)


def list_allowed_apps() -> list[str]:
    """List all applications in the allowlist.

    Returns:
        Sorted list of allowed app names
    """
    return sorted(set(SAFE_APP_ALLOWLIST.keys()))


def is_app_allowed(app_name: str) -> bool:
    """Check if an app is in the allowlist.

    Args:
        app_name: Application name to check

    Returns:
        True if app is allowed, False otherwise
    """
    return _normalize_app_name(app_name) in SAFE_APP_ALLOWLIST


def add_to_allowlist(app_name: str, executable: str) -> bool:
    """Add an application to the allowlist (runtime only, not persistent).

    Args:
        app_name: Friendly name for the app
        executable: Executable name or path

    Returns:
        True if added, False if already exists
    """
    normalized = _normalize_app_name(app_name)
    if normalized in SAFE_APP_ALLOWLIST:
        return False

    SAFE_APP_ALLOWLIST[normalized] = executable
    return True


# ---------------------------------------------------------------------------
# Linux implementation
# ---------------------------------------------------------------------------


def _launch_linux(app_name: str) -> dict[str, Any]:
    """Launch an application on Linux."""
    normalized = _normalize_app_name(app_name)

    # Check allowlist
    if normalized not in SAFE_APP_ALLOWLIST:
        return {
            "ok": False,
            "reason": "app_not_in_allowlist",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": None,
        }

    executable = SAFE_APP_ALLOWLIST[normalized]

    # Find executable in PATH
    exe_path = shutil.which(executable)
    if exe_path is None:
        # Try alternative names (e.g., google-chrome-stable for google-chrome)
        alt_names = _linux_executable_alternatives(executable)
        for alt in alt_names:
            exe_path = shutil.which(alt)
            if exe_path:
                break

    if exe_path is None:
        # Last resort: try xdg-open for generic "open" commands
        xdg_open = shutil.which("xdg-open")
        if xdg_open and normalized in {"files", "file manager"}:
            exe_path = xdg_open
            executable = "."  # Open home directory

    if exe_path is None:
        return {
            "ok": False,
            "reason": "app_executable_not_found",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": None,
        }

    # Launch the application
    try:
        if exe_path.endswith("xdg-open"):
            process = subprocess.Popen(
                [exe_path, executable],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            process = subprocess.Popen(
                [exe_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return {
            "ok": True,
            "reason": "",
            "action": "launch",
            "app": app_name,
            "pid": process.pid,
            "path": exe_path,
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "reason": "executable_not_found",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": exe_path,
        }
    except Exception as e:
        return {
            "ok": False,
            "reason": f"launch_failed:{type(e).__name__}:{str(e)}",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": exe_path,
        }


def _focus_linux(app_name: str) -> dict[str, Any]:
    """Bring an application window to the foreground on Linux."""
    normalized = _normalize_app_name(app_name)

    # Check allowlist
    if normalized not in SAFE_APP_ALLOWLIST:
        return {
            "ok": False,
            "reason": "app_not_in_allowlist",
            "action": "focus",
            "app": app_name,
            "window_found": False,
            "hwnd": None,
        }

    xdotool = shutil.which("xdotool")
    if not xdotool:
        return {
            "ok": False,
            "reason": "xdotool_not_installed",
            "action": "focus",
            "app": app_name,
            "window_found": False,
            "hwnd": None,
        }

    # Search for window by name (case-insensitive)
    search_terms = [normalized, app_name]
    # Also try the executable name
    executable = SAFE_APP_ALLOWLIST.get(normalized, "")
    if executable:
        search_terms.append(executable)

    for term in search_terms:
        try:
            result = subprocess.run(
                [xdotool, "search", "--name", term],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                window_ids = result.stdout.strip().splitlines()
                if window_ids:
                    window_id = window_ids[0].strip()
                    # Activate the window
                    activate_result = subprocess.run(
                        [xdotool, "windowactivate", window_id],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    if activate_result.returncode == 0:
                        return {
                            "ok": True,
                            "reason": "",
                            "action": "focus",
                            "app": app_name,
                            "window_found": True,
                            "hwnd": int(window_id) if window_id.isdigit() else None,
                            "backend": "xdotool",
                        }
        except Exception:
            continue

    # Also try wmctrl if xdotool search failed
    wmctrl = shutil.which("wmctrl")
    if wmctrl:
        try:
            result = subprocess.run(
                [wmctrl, "-a", app_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return {
                    "ok": True,
                    "reason": "",
                    "action": "focus",
                    "app": app_name,
                    "window_found": True,
                    "hwnd": None,
                    "backend": "wmctrl",
                }
        except Exception:
            pass

    return {
        "ok": False,
        "reason": "window_not_found",
        "action": "focus",
        "app": app_name,
        "window_found": False,
        "hwnd": None,
        "suggestion": "try_launch",
    }


def _close_linux(app_name: str) -> dict[str, Any]:
    """Close an application window on Linux."""
    normalized = _normalize_app_name(app_name)
    if normalized not in SAFE_APP_ALLOWLIST:
        return {
            "ok": False,
            "reason": "app_not_in_allowlist",
            "action": "close",
            "app": app_name,
        }

    xdotool = shutil.which("xdotool")
    if xdotool:
        search_terms = [normalized, app_name]
        executable = SAFE_APP_ALLOWLIST.get(normalized, "")
        if executable:
            search_terms.append(executable)

        for term in search_terms:
            try:
                result = subprocess.run(
                    [xdotool, "search", "--name", term],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    window_ids = result.stdout.strip().splitlines()
                    for window_id in window_ids:
                        subprocess.run(
                            [xdotool, "windowclose", window_id.strip()], check=False
                        )
                    return {
                        "ok": True,
                        "reason": "",
                        "action": "close",
                        "app": app_name,
                    }
            except Exception:
                pass

    wmctrl = shutil.which("wmctrl")
    if wmctrl:
        try:
            result = subprocess.run(
                [wmctrl, "-c", app_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return {"ok": True, "reason": "", "action": "close", "app": app_name}
        except Exception:
            pass

    # Fallback to killall
    executable = SAFE_APP_ALLOWLIST.get(normalized, app_name)
    if shutil.which("killall"):
        try:
            result = subprocess.run(
                ["killall", executable], capture_output=True, timeout=5, check=False
            )
            if result.returncode == 0:
                return {"ok": True, "reason": "", "action": "close", "app": app_name}
        except Exception:
            pass

    return {
        "ok": False,
        "reason": "close_failed",
        "action": "close",
        "app": app_name,
    }


def _linux_executable_alternatives(executable: str) -> list[str]:
    """Get alternative executable names for common Linux apps."""
    alternatives = {
        "google-chrome": [
            "google-chrome-stable",
            "google-chrome-beta",
            "chromium",
            "chromium-browser",
        ],
        "chromium-browser": ["chromium", "chromium-browser-stable"],
        "brave-browser": ["brave-browser-stable", "brave"],
        "gnome-terminal": ["gnome-terminal.real", "x-terminal-emulator"],
        "nautilus": ["org.gnome.Nautilus", "nautilus"],
        "gnome-calculator": ["org.gnome.Calculator", "galculator", "kcalc"],
        "gnome-control-center": ["gnome-control-center", "org.gnome.Settings"],
        "gnome-system-monitor": ["org.gnome.SystemMonitor", "xfce4-taskmanager"],
        "microsoft-edge": ["microsoft-edge-stable", "microsoft-edge-beta"],
    }
    return alternatives.get(executable, [])


# ---------------------------------------------------------------------------
# Windows implementation (preserved from original)
# ---------------------------------------------------------------------------


def _find_executable_windows(app_name: str) -> Optional[Path]:
    """Find executable path for an app name on Windows."""
    normalized = _normalize_app_name(app_name)

    allowlist_entry = SAFE_APP_ALLOWLIST.get(normalized)
    if allowlist_entry:
        if allowlist_entry.endswith(".exe"):
            found = shutil.which(allowlist_entry)
            if found:
                return Path(found)

            for search_path in APP_SEARCH_PATHS:
                candidate = search_path / allowlist_entry
                if candidate.exists():
                    return candidate
                try:
                    for subdir in search_path.iterdir():
                        if subdir.is_dir():
                            candidate = subdir / allowlist_entry
                            if candidate.exists():
                                return candidate
                except (OSError, PermissionError):
                    pass

    return None


def _get_window_handle_windows(app_name: str) -> Optional[int]:
    """Get window handle for an application on Windows."""
    try:
        import win32gui  # type: ignore
        import win32process  # type: ignore
        import psutil  # type: ignore

        normalized = _normalize_app_name(app_name)

        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    results.append((hwnd, title))
            return True

        windows = []
        win32gui.EnumWindows(enum_callback, windows)

        for hwnd, title in windows:
            title_lower = title.lower()
            if normalized in title_lower:
                return hwnd

            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                proc_name = proc.name().lower()
                if (
                    normalized in proc_name
                    or _normalize_app_name(proc_name) in normalized
                ):
                    return hwnd
            except (psutil.NoSuchProcess, Exception):
                pass

    except ImportError:
        pass
    except Exception:
        pass

    return None


def _launch_windows(app_name: str) -> dict[str, Any]:
    """Launch an application on Windows."""
    normalized = _normalize_app_name(app_name)

    if normalized not in SAFE_APP_ALLOWLIST:
        return {
            "ok": False,
            "reason": "app_not_in_allowlist",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": None,
        }

    exe_path = _find_executable_windows(app_name)
    if exe_path is None:
        return {
            "ok": False,
            "reason": "app_executable_not_found",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": None,
        }

    try:
        process = subprocess.Popen(
            [str(exe_path)],
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            if sys.platform == "win32"
            else 0,
        )
        return {
            "ok": True,
            "reason": "",
            "action": "launch",
            "app": app_name,
            "pid": process.pid,
            "path": str(exe_path),
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "reason": "executable_not_found",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": str(exe_path) if exe_path else None,
        }
    except Exception as e:
        return {
            "ok": False,
            "reason": f"launch_failed:{type(e).__name__}:{str(e)}",
            "action": "launch",
            "app": app_name,
            "pid": None,
            "path": str(exe_path) if exe_path else None,
        }


def _focus_windows(app_name: str) -> dict[str, Any]:
    """Bring an application window to the foreground on Windows."""
    normalized = _normalize_app_name(app_name)

    if normalized not in SAFE_APP_ALLOWLIST:
        return {
            "ok": False,
            "reason": "app_not_in_allowlist",
            "action": "focus",
            "app": app_name,
            "window_found": False,
            "hwnd": None,
        }

    hwnd = _get_window_handle_windows(app_name)
    if hwnd is None:
        return {
            "ok": False,
            "reason": "window_not_found",
            "action": "focus",
            "app": app_name,
            "window_found": False,
            "hwnd": None,
            "suggestion": "try_launch",
        }

    try:
        import win32gui  # type: ignore

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE

        win32gui.SetForegroundWindow(hwnd)

        return {
            "ok": True,
            "reason": "",
            "action": "focus",
            "app": app_name,
            "window_found": True,
            "hwnd": hwnd,
        }
    except Exception as e:
        return {
            "ok": False,
            "reason": f"focus_failed:{type(e).__name__}:{str(e)}",
            "action": "focus",
            "app": app_name,
            "window_found": True,
            "hwnd": hwnd,
        }


def _close_windows(app_name: str) -> dict[str, Any]:
    """Close an application window on Windows."""
    normalized = _normalize_app_name(app_name)
    if normalized not in SAFE_APP_ALLOWLIST:
        return {
            "ok": False,
            "reason": "app_not_in_allowlist",
            "action": "close",
            "app": app_name,
        }

    hwnd = _get_window_handle_windows(app_name)
    if hwnd is not None:
        try:
            import win32gui  # type: ignore

            win32gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            return {"ok": True, "reason": "", "action": "close", "app": app_name}
        except Exception as e:
            return {
                "ok": False,
                "reason": f"close_failed:{type(e).__name__}:{str(e)}",
                "action": "close",
                "app": app_name,
            }

    process_name = SAFE_APP_ALLOWLIST.get(normalized)
    if process_name:
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", process_name],
                capture_output=True,
                check=False,
            )
            return {"ok": True, "reason": "", "action": "close", "app": app_name}
        except Exception:
            pass

    return {"ok": False, "reason": "close_failed", "action": "close", "app": app_name}
