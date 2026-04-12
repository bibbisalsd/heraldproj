from __future__ import annotations

import os
import sys
from pathlib import Path


def get_thermal_status() -> dict:
    """Get system thermal status (CPU/GPU temperature)."""
    status = {"ok": True, "sensors": {}}
    
    try:
        if sys.platform == "linux":
            # Check /sys/class/thermal
            thermal_dir = Path("/sys/class/thermal")
            if thermal_dir.exists():
                for zone in thermal_dir.glob("thermal_zone*"):
                    try:
                        temp = int((zone / "temp").read_text().strip()) / 1000.0
                        type_name = (zone / "type").read_text().strip()
                        status["sensors"][type_name] = temp
                    except Exception:
                        continue
            
            # Try nvidia-smi for GPU if available
            try:
                import subprocess
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True
                )
                if res.returncode == 0:
                    status["sensors"]["gpu_nvidia"] = float(res.stdout.strip())
            except Exception:
                pass

        elif sys.platform == "win32":
            # Windows requires WMI or specialized tools, hard to do with stdlib
            status["sensors"]["platform_note"] = "Thermal monitoring limited on Windows without psutil"

        # Basic health assessment
        high_temp = False
        for name, temp in status["sensors"].items():
            if isinstance(temp, (int, float)) and temp > 85:
                high_temp = True
                break
        
        status["throttling_recommended"] = high_temp
        return status
        
    except Exception as e:
        return {"ok": False, "reason": str(e)}
