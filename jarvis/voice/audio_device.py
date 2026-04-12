"""Audio device enumeration, selection, and persistence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def _get_config_dir() -> Path:
    """Get the config directory for device persistence."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    config_dir = repo_root / ".config" / "jarvis"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _get_device_config_path() -> Path:
    """Get the path to the device config file."""
    return _get_config_dir() / "audio_devices.json"


def load_saved_device_config() -> dict[str, Any]:
    """Load saved device configuration from disk.

    Returns dict with keys:
        - input_device: str|int|None
        - output_device: str|int|None
        - input_device_name: str|None
        - output_device_name: str|None
    """
    config_path = _get_device_config_path()
    if not config_path.exists():
        return {
            "input_device": None,
            "output_device": None,
            "input_device_name": None,
            "output_device_name": None,
        }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {
            "input_device": None,
            "output_device": None,
            "input_device_name": None,
            "output_device_name": None,
        }


def save_device_config(
    input_device: str | int | None = None,
    output_device: str | int | None = None,
    input_device_name: str | None = None,
    output_device_name: str | None = None,
) -> bool:
    """Save device configuration to disk.

    Returns True if saved successfully, False on error.
    """
    config_path = _get_device_config_path()
    config = {
        "input_device": input_device,
        "output_device": output_device,
        "input_device_name": input_device_name,
        "output_device_name": output_device_name,
    }

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def list_audio_devices() -> list[dict[str, Any]]:
    """List all available audio devices.

    Returns list of dicts with keys:
        - index: int
        - name: str
        - max_input_channels: int
        - max_output_channels: int
        - default_samplerate: float
        - is_default_input: bool
        - is_default_output: bool
        - supports_input: bool
        - supports_output: bool
    """
    if importlib.util.find_spec("sounddevice") is None:
        return []

    try:
        import sounddevice as sd

        # Get default device indices
        default_input = sd.query_devices(kind="input")
        default_output = sd.query_devices(kind="output")
        default_input_index = None
        default_output_index = None

        # Find indices by iterating
        for i, dev in enumerate(sd.query_devices()):
            if dev is default_input:
                default_input_index = i
            if dev is default_output:
                default_output_index = i

        devices = []
        for index, raw_device in enumerate(sd.query_devices()):
            device = dict(raw_device)
            max_in = int(device.get("max_input_channels", 0) or 0)
            max_out = int(device.get("max_output_channels", 0) or 0)

            devices.append(
                {
                    "index": index,
                    "name": str(device.get("name", "")).strip(),
                    "max_input_channels": max_in,
                    "max_output_channels": max_out,
                    "default_samplerate": float(
                        device.get("default_samplerate", 48000)
                    ),
                    "is_default_input": index == default_input_index,
                    "is_default_output": index == default_output_index,
                    "supports_input": max_in > 0,
                    "supports_output": max_out > 0,
                }
            )

        return devices
    except Exception:
        return []


def get_input_devices() -> list[dict[str, Any]]:
    """Get list of devices that support audio input (microphones)."""
    all_devices = list_audio_devices()
    return [d for d in all_devices if d["supports_input"]]


def get_output_devices() -> list[dict[str, Any]]:
    """Get list of devices that support audio output (speakers)."""
    all_devices = list_audio_devices()
    return [d for d in all_devices if d["supports_output"]]


def resolve_device(
    requested: str | int | None,
    *,
    kind: str,
    devices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a device request to a specific device.

    Args:
        requested: Device index (int) or name (str) or None for default
        kind: "input" or "output"
        devices: Optional pre-fetched device list

    Returns dict with keys:
        - ok: bool
        - reason: str (error message if not ok)
        - selected_device: dict|None
        - requested_device: str|int|None
    """
    if devices is None:
        devices = list_audio_devices()

    # Filter by kind
    if kind == "input":
        devices = [d for d in devices if d["supports_input"]]
    else:
        devices = [d for d in devices if d["supports_output"]]

    if not devices:
        return {
            "ok": False,
            "reason": f"no_{kind}_devices_found",
            "requested_device": requested,
            "selected_device": None,
        }

    # None or empty string -> use default
    if requested is None or (isinstance(requested, str) and not requested.strip()):
        # Find default device
        for d in devices:
            if kind == "input" and d["is_default_input"]:
                return {
                    "ok": True,
                    "reason": "",
                    "selected_device": d,
                    "requested_device": requested,
                }
            if kind == "output" and d["is_default_output"]:
                return {
                    "ok": True,
                    "reason": "",
                    "selected_device": d,
                    "requested_device": requested,
                }
        # No default marked, use first available
        return {
            "ok": True,
            "reason": "",
            "selected_device": devices[0],
            "requested_device": requested,
        }

    # Integer index
    if isinstance(requested, int):
        for d in devices:
            if d["index"] == requested:
                return {
                    "ok": True,
                    "reason": "",
                    "selected_device": d,
                    "requested_device": requested,
                }
        return {
            "ok": False,
            "reason": f"{kind}_device_index_not_found",
            "requested_device": requested,
            "selected_device": None,
        }

    # String - try parsing as int first
    requested_str = str(requested).strip()
    if requested_str.isdigit():
        idx = int(requested_str)
        for d in devices:
            if d["index"] == idx:
                return {
                    "ok": True,
                    "reason": "",
                    "selected_device": d,
                    "requested_device": requested,
                }
        return {
            "ok": False,
            "reason": f"{kind}_device_index_not_found",
            "requested_device": requested,
            "selected_device": None,
        }

    # String - match by name (case-insensitive, partial match)
    requested_lower = requested_str.lower()
    matches = [d for d in devices if requested_lower in d["name"].lower()]

    if len(matches) == 1:
        return {
            "ok": True,
            "reason": "",
            "selected_device": matches[0],
            "requested_device": requested,
        }
    if len(matches) > 1:
        # Multiple matches - prefer exact or default
        for m in matches:
            if m["name"].lower() == requested_lower:
                return {
                    "ok": True,
                    "reason": "",
                    "selected_device": m,
                    "requested_device": requested,
                }
            if kind == "input" and m["is_default_input"]:
                return {
                    "ok": True,
                    "reason": "",
                    "selected_device": m,
                    "requested_device": requested,
                }
            if kind == "output" and m["is_default_output"]:
                return {
                    "ok": True,
                    "reason": "",
                    "selected_device": m,
                    "requested_device": requested,
                }
        # Return first match with note
        return {
            "ok": True,
            "reason": "multiple_matches_first_selected",
            "selected_device": matches[0],
            "requested_device": requested,
        }

    # No matches
    return {
        "ok": False,
        "reason": f"{kind}_device_name_not_found",
        "requested_device": requested,
        "selected_device": None,
    }


def get_device_summary() -> dict[str, Any]:
    """Get a summary of available devices and current configuration.

    Returns dict with:
        - input_devices: list of input device names
        - output_devices: list of output device names
        - default_input: str|None
        - default_output: str|None
        - saved_config: dict (from load_saved_device_config)
    """
    devices = list_audio_devices()
    input_devs = [d for d in devices if d["supports_input"]]
    output_devs = [d for d in devices if d["supports_output"]]

    default_input = None
    default_output = None
    for d in input_devs:
        if d["is_default_input"]:
            default_input = d["name"]
            break
    for d in output_devs:
        if d["is_default_output"]:
            default_output = d["name"]
            break

    return {
        "input_devices": [d["name"] for d in input_devs],
        "output_devices": [d["name"] for d in output_devs],
        "default_input": default_input,
        "default_output": default_output,
        "saved_config": load_saved_device_config(),
    }
