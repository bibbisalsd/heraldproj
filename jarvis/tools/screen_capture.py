from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

from jarvis.brain_core.guardrails import Guardrails
from jarvis.models.workspace_inputs import resolve_workspace_target, workspace_root

_ALLOWED_CAPTURE_TARGETS = {"screen", "foreground_window"}


def capture(
    output_path: str, *, target: str = "screen", smart_crop: bool = False
) -> dict:
    """Capture screen or active window with optional smart cropping.

    Phase 2C: Vision Depth
    - Active-window crop capture: Smart crop to window content (exclude title bar, borders)

    Args:
        output_path: Path to save screenshot
        target: "screen" or "foreground_window"
        smart_crop: If True and target is foreground_window, crop to content area

    Returns: dict with ok, path, mode, target, and optionally crop_info
    """
    normalized_target = target.strip().lower() or "screen"
    if normalized_target not in _ALLOWED_CAPTURE_TARGETS:
        return {
            "ok": False,
            "reason": "unsupported_capture_target",
            "path": output_path,
            "mode": "unavailable",
            "target": normalized_target,
        }

    use_smart_crop = smart_crop and normalized_target == "foreground_window"

    target = resolve_workspace_target(output_path)
    if target is None:
        return {
            "ok": False,
            "reason": "path_outside_workspace",
            "target": normalized_target,
        }

    root = workspace_root(target.parent)
    decision = Guardrails().check_path_safety(str(target), str(root))
    if not decision.allowed:
        return {"ok": False, "reason": decision.reason, "target": normalized_target}

    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Platform dispatch
    if os.name == "nt":
        return _capture_windows(path, normalized_target, use_smart_crop)
    else:
        return _capture_linux(path, normalized_target, use_smart_crop)


# ---------------------------------------------------------------------------
# Linux implementation
# ---------------------------------------------------------------------------


def _capture_linux(path: Path, target: str, use_smart_crop: bool) -> dict:
    """Capture screen on Linux using available backends."""

    if use_smart_crop:
        result = _try_linux_smart_crop(path)
        if result:
            return result

    if target == "foreground_window":
        result = _try_linux_window_capture(path)
        if result:
            return result

    # Full screen capture — try backends in order
    for backend_fn in (
        _try_mss_capture,
        _try_gnome_screenshot,
        _try_scrot_capture,
        _try_import_screenshot,
    ):
        result = backend_fn(path, target)
        if result:
            return result

    return {
        "ok": False,
        "path": str(path),
        "mode": "unavailable",
        "reason": "native_capture_unavailable (install python-mss, gnome-screenshot, or scrot)",
        "target": target,
    }


def _try_mss_capture(path: Path, target: str = "screen") -> dict | None:
    """Capture using python-mss (cross-platform, pip-installable)."""
    if importlib.util.find_spec("mss") is None:
        return None

    try:
        import mss

        with mss.mss() as sct:
            if target == "foreground_window":
                # mss doesn't support window capture directly, capture full screen
                monitor = sct.monitors[1]  # Primary monitor
            else:
                monitor = sct.monitors[1]  # Primary monitor

            screenshot = sct.grab(monitor)

            # Convert to PNG via mss tools
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(path))

        if path.exists() and path.stat().st_size > 0:
            return {
                "ok": True,
                "path": str(path),
                "mode": "native",
                "target": target,
                "backend": "mss",
            }
    except Exception:
        pass
    return None


def _try_gnome_screenshot(path: Path, target: str = "screen") -> dict | None:
    """Capture using gnome-screenshot CLI."""
    gnome_screenshot = shutil.which("gnome-screenshot")
    if not gnome_screenshot:
        return None

    cmd = [gnome_screenshot, "-f", str(path)]
    if target == "foreground_window":
        cmd.append("-w")  # Capture active window

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode == 0 and path.exists() and path.stat().st_size > 0:
            return {
                "ok": True,
                "path": str(path),
                "mode": "native",
                "target": target,
                "backend": "gnome-screenshot",
            }
    except Exception:
        pass
    return None


def _try_scrot_capture(path: Path, target: str = "screen") -> dict | None:
    """Capture using scrot CLI (X11)."""
    scrot = shutil.which("scrot")
    if not scrot:
        return None

    cmd = [scrot, str(path)]
    if target == "foreground_window":
        cmd = [scrot, "-u", str(path)]  # -u = focused window

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode == 0 and path.exists() and path.stat().st_size > 0:
            return {
                "ok": True,
                "path": str(path),
                "mode": "native",
                "target": target,
                "backend": "scrot",
            }
    except Exception:
        pass
    return None


def _try_import_screenshot(path: Path, target: str = "screen") -> dict | None:
    """Capture using ImageMagick import command (X11)."""
    import_bin = shutil.which("import")
    if not import_bin:
        return None

    cmd = [import_bin, "-window", "root", str(path)]
    if target == "foreground_window":
        # Use xdotool to get active window ID
        xdotool = shutil.which("xdotool")
        if xdotool:
            try:
                wid_result = subprocess.run(
                    [xdotool, "getactivewindow"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if wid_result.returncode == 0 and wid_result.stdout.strip():
                    cmd = [import_bin, "-window", wid_result.stdout.strip(), str(path)]
            except Exception:
                pass

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode == 0 and path.exists() and path.stat().st_size > 0:
            return {
                "ok": True,
                "path": str(path),
                "mode": "native",
                "target": target,
                "backend": "imagemagick",
            }
    except Exception:
        pass
    return None


def _try_linux_window_capture(path: Path) -> dict | None:
    """Capture active window on Linux using best available method."""
    # gnome-screenshot -w is the cleanest for GNOME
    result = _try_gnome_screenshot(path, "foreground_window")
    if result:
        return result

    # scrot -u for X11
    result = _try_scrot_capture(path, "foreground_window")
    if result:
        return result

    # imagemagick import with xdotool window ID
    result = _try_import_screenshot(path, "foreground_window")
    if result:
        return result

    return None


def _try_linux_smart_crop(path: Path) -> dict | None:
    """Capture foreground window with smart cropping on Linux.

    Uses xdotool to get window geometry, then captures full screen
    and crops to the window content area using Pillow.
    """
    xdotool = shutil.which("xdotool")
    if not xdotool:
        return None

    if (
        importlib.util.find_spec("PIL") is None
        and importlib.util.find_spec("Pillow") is None
    ):
        # Without Pillow, fall back to window capture without smart crop
        return None

    try:
        # Get active window geometry
        wid_result = subprocess.run(
            [xdotool, "getactivewindow"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if wid_result.returncode != 0 or not wid_result.stdout.strip():
            return None

        window_id = wid_result.stdout.strip()

        geo_result = subprocess.run(
            [xdotool, "getwindowgeometry", "--shell", window_id],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if geo_result.returncode != 0:
            return None

        # Parse geometry: X=100\nY=200\nWIDTH=800\nHEIGHT=600\nSCREEN=0
        geo = {}
        for line in geo_result.stdout.splitlines():
            if "=" in line:
                key, _, val = line.partition("=")
                try:
                    geo[key.strip()] = int(val.strip())
                except ValueError:
                    pass

        x = geo.get("X", 0)
        y = geo.get("Y", 0)
        width = geo.get("WIDTH", 0)
        height = geo.get("HEIGHT", 0)

        if width < 2 or height < 2:
            return None

        # Apply smart crop offset (skip title bar ~32px, borders ~2px)
        title_bar_height = 32
        border_width = 2
        crop_x = x + border_width
        crop_y = y + title_bar_height
        crop_width = max(1, width - 2 * border_width)
        crop_height = max(1, height - title_bar_height - border_width)

        # Capture full screen first
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        full_result = None
        for backend_fn in (_try_mss_capture, _try_gnome_screenshot, _try_scrot_capture):
            full_result = backend_fn(tmp_path, "screen")
            if full_result:
                break

        if not full_result:
            tmp_path.unlink(missing_ok=True)
            return None

        # Crop using Pillow
        try:
            from PIL import Image

            img = Image.open(tmp_path)
            cropped = img.crop(
                (crop_x, crop_y, crop_x + crop_width, crop_y + crop_height)
            )
            cropped.save(str(path), "PNG")
            img.close()
            cropped.close()
        finally:
            tmp_path.unlink(missing_ok=True)

        if path.exists() and path.stat().st_size > 0:
            return {
                "ok": True,
                "path": str(path),
                "mode": "smart_crop",
                "target": "foreground_window",
                "backend": "xdotool+pillow",
                "crop_info": {
                    "content_only": True,
                    "title_bar_excluded": True,
                    "crop_rect": {
                        "x": crop_x,
                        "y": crop_y,
                        "w": crop_width,
                        "h": crop_height,
                    },
                },
            }
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Windows implementation (unchanged from original)
# ---------------------------------------------------------------------------


def _capture_windows(path: Path, target: str, use_smart_crop: bool) -> dict:
    """Capture screen on Windows using PowerShell/.NET."""
    if use_smart_crop:
        result = _try_windows_smart_crop(path)
        if result:
            return result

    if _try_windows_capture(path, target=target):
        return {"ok": True, "path": str(path), "mode": "native", "target": target}

    return {
        "ok": False,
        "path": str(path),
        "mode": "unavailable",
        "reason": (
            "foreground_window_capture_unavailable"
            if target == "foreground_window"
            else "native_capture_unavailable"
        ),
        "target": target,
    }


def _try_windows_capture(path: Path, *, target: str = "screen") -> bool:
    escaped = str(path).replace("'", "''")
    script = _build_capture_script(escaped, target=target)
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except Exception:
        return False
    return completed.returncode == 0 and path.exists() and path.stat().st_size > 0


def _try_windows_smart_crop(path: Path) -> dict | None:
    """Capture foreground window with smart cropping.

    Phase 2C: Vision Depth - Active-window crop capture
    Excludes title bar, borders, and non-client areas.
    """
    escaped = str(path).replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Capture {{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {{
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }}

    [StructLayout(LayoutKind.Sequential)]
    public struct DWM_BLURBEHIND {{
        public uint dwFlags;
        public bool fEnable;
        public IntPtr hRgnBlur;
        public bool fTransitionOnMaximized;
    }}

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

    [DllImport("dwmapi.dll")]
    public static extern int DwmGetWindowAttribute(IntPtr hwnd, uint dwAttribute, out RECT pvAttribute, uint cbAttribute);

    public const int DWMWA_EXTENDED_FRAME_BOUNDS = 9;
}}
"@

$hwnd = [Win32Capture]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) {{ exit 2 }}

# Get full window rect (including non-client area)
$fullRect = New-Object Win32Capture+RECT
if (-not [Win32Capture]::GetWindowRect($hwnd, [ref]$fullRect)) {{ exit 3 }}

# Get extended frame bounds (content area)
$contentRect = New-Object Win32Capture+RECT
$result = [Win32Capture]::DwmGetWindowAttribute($hwnd, 9, [ref]$contentRect, [System.Runtime.InteropServices.Marshal]::SizeOf([Win32Capture+RECT]))

if ($result -eq 0) {{
    # Use content area (excludes title bar and borders)
    $left = $contentRect.Left
    $top = $contentRect.Top
    $width = [Math]::Max(0, $contentRect.Right - $contentRect.Left)
    $height = [Math]::Max(0, $contentRect.Bottom - $contentRect.Top)
    $cropInfo = @{{ content_only = $true; title_bar_excluded = $true }}
}} else {{
    # Fall back to full window
    $left = $fullRect.Left
    $top = $fullRect.Top
    $width = [Math]::Max(0, $fullRect.Right - $fullRect.Left)
    $height = [Math]::Max(0, $fullRect.Bottom - $fullRect.Top)
    $cropInfo = @{{ content_only = $false; title_bar_excluded = $false }}
}}

if ($width -lt 2 -or $height -lt 2) {{ exit 4 }}

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($left, $top, 0, 0, $bitmap.Size)
$bitmap.Save('{escaped}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()

# Output crop info as JSON
$cropInfo | ConvertTo-Json -Compress
"""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except Exception:
        return None

    if completed.returncode == 0 and path.exists() and path.stat().st_size > 0:
        result = {
            "ok": True,
            "path": str(path),
            "mode": "smart_crop",
            "target": "foreground_window",
        }
        # Try to parse crop info from last line
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if lines:
            try:
                result["crop_info"] = json.loads(lines[-1])
            except json.JSONDecodeError:
                pass
        return result

    return None


def _build_capture_script(escaped_path: str, *, target: str) -> str:
    if target == "foreground_window":
        return f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Capture {{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {{
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }}

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
}}
"@
$hwnd = [Win32Capture]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) {{ exit 2 }}
$rect = New-Object Win32Capture+RECT
if (-not [Win32Capture]::GetWindowRect($hwnd, [ref]$rect)) {{ exit 3 }}
$width = [Math]::Max(0, $rect.Right - $rect.Left)
$height = [Math]::Max(0, $rect.Bottom - $rect.Top)
if ($width -lt 2 -or $height -lt 2) {{ exit 4 }}
$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
$bitmap.Save('{escaped_path}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
"""

    return f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save('{escaped_path}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
"""
