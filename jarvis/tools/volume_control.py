from __future__ import annotations

import subprocess
import sys


def set_volume(level: int) -> dict:
    """Set system volume (0-100)."""
    level = max(0, min(100, level))
    
    try:
        if sys.platform == "linux":
            # Try pactl (PulseAudio/Pipewire) first
            try:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True)
                return {"ok": True, "volume": level, "engine": "pactl"}
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback to amixer (ALSA)
                subprocess.run(["amixer", "sset", "Master", f"{level}%"], check=True)
                return {"ok": True, "volume": level, "engine": "amixer"}
        
        elif sys.platform == "win32":
            # Requires nircmd.exe in path
            subprocess.run(["nircmd.exe", "setsysvolume", str(int(level * 655.35))], check=True)
            return {"ok": True, "volume": level, "engine": "nircmd"}
            
        return {"ok": False, "reason": "unsupported_platform"}
    except (subprocess.CalledProcessError, OSError) as e:
        reason = str(e)
        if isinstance(e, subprocess.CalledProcessError):
            reason = f"Command failed with exit code {e.returncode}: {e.stderr or str(e)}"
        return {"ok": False, "reason": reason}


def get_volume() -> dict:
    """Get current system volume (Linux only for now)."""
    try:
        if sys.platform == "linux":
            res = subprocess.run(["amixer", "sget", "Master"], capture_output=True, text=True)
            # Brittle parsing but works for common ALSA output
            import re
            match = re.search(r"\\b(\\d+)%\\b", res.stdout)
            if match:
                return {"ok": True, "volume": int(match.group(1))}
        return {"ok": False, "reason": "unsupported_or_failed"}
    except (subprocess.CalledProcessError, OSError) as e:
        reason = str(e)
        if isinstance(e, subprocess.CalledProcessError):
            reason = f"Command failed with exit code {e.returncode}: {e.stderr or str(e)}"
        return {"ok": False, "reason": reason}
