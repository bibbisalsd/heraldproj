"""Hardware discovery tool using psutil and pynvml."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def get_hardware_info() -> dict:
    """Detect CPU, RAM, and GPU specs."""
    info = {
        "cpu_cores": None,
        "cpu_cores_logical": None,
        "ram_total_gb": None,
        "gpus": []
    }
    
    try:
        import psutil
        info["cpu_cores"] = psutil.cpu_count(logical=False)
        info["cpu_cores_logical"] = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        info["ram_total_gb"] = round(mem.total / (1024**3), 1)
    except ImportError:
        logger.warning("psutil not installed, hardware info will be limited.")
    except Exception as e:
        logger.error(f"Error gathering CPU/RAM info: {e}")

    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            # pynvml returns bytes in some versions, string in others
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(h)
            info["gpus"].append({
                "name": name,
                "vram_total_gb": round(mem_info.total / (1024**3), 1),
            })
        pynvml.nvmlShutdown()
    except ImportError:
        # Expected if no NVIDIA drivers/pynvml installed
        pass
    except Exception as e:
        logger.debug(f"NVIDIA GPU discovery skipped or failed: {e}")

    return info
