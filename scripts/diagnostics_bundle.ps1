[CmdletBinding()]
param(
    [string]$OutputDir = "./logs",
    [switch]$NoVoiceSmoke,
    [switch]$NoGpuCheck,
    [switch]$Quiet,
    [int]$KeepBackups = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-JarvisPython {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        return $pythonCommand.Source
    }

    return "python"
}

function Write-Status {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Host $Message
    }
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outputPath = Join-Path $OutputDir "diagnostics_bundle_$timestamp.json"
    $latestPath = Join-Path $OutputDir "diagnostics_bundle_latest.json"

    # Ensure output directory exists
    if (-not (Test-Path -LiteralPath $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    }

    $pythonBin = Get-JarvisPython

    # Set up Kokoro pack environment
    $defaultPackDir = Join-Path (Split-Path -Parent $PSScriptRoot) "jarvis\\voice\\kokoro_pack"
    if (Test-Path (Join-Path $defaultPackDir "jarvis_launcher.py")) {
        $env:JARVIS_USE_KOKORO_PACK = "true"
        $env:JARVIS_KOKORO_PACK_DIR = $defaultPackDir
        $defaultPackPython = Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\\Scripts\\python.exe"
        if (Test-Path $defaultPackPython) {
            $env:JARVIS_KOKORO_PYTHON = $defaultPackPython
        }
    }

    Write-Status "Collecting diagnostics bundle..."
    Write-Status "  Timestamp: $timestamp"

    # Run comprehensive diagnostics
    $diagnosticsScript = @"
import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

def run_command(cmd, timeout=30):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip()[:2000] if result.stdout else "",
            "stderr": result.stderr.strip()[:500] if result.stderr else "",
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

def get_pytest_status():
    """Get pytest status."""
    result = run_command("pytest -q --collect-only", timeout=60)
    if result["ok"]:
        # Count tests
        lines = result["stdout"].split("\n")
        test_count = 0
        for line in lines:
            if "test" in line.lower() and ("passed" in line or "collected" in line):
                test_count = line
        return {
            "ok": True,
            "tests_collected": result["stdout"],
            "last_run_summary": test_count
        }
    return {"ok": False, "error": result.get("error", "pytest failed")}

def get_model_readiness():
    """Get model readiness status."""
    result = run_command(
        "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/model_readiness.ps1 -OutputFormat json",
        timeout=60
    )
    if result["ok"]:
        try:
            # Try to parse JSON from stdout
            json_start = result["stdout"].find("{")
            json_end = result["stdout"].rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(result["stdout"][json_start:json_end])
        except:
            pass
    return {"ok": False, "raw_output": result["stdout"][:500], "error": result.get("error")}

def get_compile_status():
    """Get compile/pytest status."""
    result = run_command("pytest -q", timeout=120)
    if result["ok"]:
        # Parse pytest output
        output = result["stdout"]
        passed = 0
        failed = 0
        for line in output.split("\n"):
            if "passed" in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        passed = int(p)
            if "failed" in line:
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        failed = int(p)
        return {
            "ok": failed == 0,
            "tests_passed": passed,
            "tests_failed": failed,
            "output_summary": output.split("\n")[-5:]
        }
    return {"ok": False, "error": result.get("error", "pytest failed")}

def get_voice_quick_status():
    """Get voice subsystem quick status."""
    try:
        from jarvis.voice.diagnostics import VoiceDiagnostics
        diag = VoiceDiagnostics()
        return diag.get_quick_status()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

def get_addon_health():
    """Get addon health status."""
    try:
        from jarvis.brain_core.addon_manager import AddonManager
        from jarvis.brain_core.addon_registry import AddonRegistry

        registry = AddonRegistry()
        manager = AddonManager(registry)

        # Scan for addons
        addons_dir = repo_root / "addons"
        addons_found = []
        if addons_dir.exists():
            for subdir in addons_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("_"):
                    manifest_py = subdir / "manifest.py"
                    if manifest_py.exists():
                        addons_found.append(subdir.name)

        return {
            "ok": True,
            "addons_found": addons_found,
            "addon_count": len(addons_found)
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

def get_gpu_status():
    """Get GPU status."""
    # Check NVIDIA
    nvidia = run_command("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader", timeout=10)
    if nvidia["ok"]:
        return {
            "gpu_type": "nvidia",
            "gpus": nvidia["stdout"].split("\n"),
            "ollama_ps": run_command("ollama ps", timeout=10)
        }

    # Check AMD
    amd = run_command("rocm-smi", timeout=10)
    if amd["ok"]:
        return {
            "gpu_type": "amd",
            "rocm_output": amd["stdout"][:500],
            "ollama_ps": run_command("ollama ps", timeout=10)
        }

    return {
        "gpu_type": "unknown",
        "nvidia": "not detected",
        "amd": "not detected"
    }

def get_memory_status():
    """Get memory service status."""
    try:
        from jarvis.brain_core.memory_service import MemoryService

        db_path = repo_root / ".data" / "jarvis_memory.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        memory = MemoryService(str(db_path))

        # Get quick stats
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM memory_facts")
        fact_count = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM memory_embeddings")
        embedding_count = cursor.fetchone()[0]
        conn.close()

        return {
            "ok": True,
            "fact_count": fact_count,
            "embedding_count": embedding_count,
            "backups": memory.list_backups()[:5]
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

def get_event_log_summary():
    """Get recent event log summary."""
    try:
        logs_dir = repo_root / "logs"
        if not logs_dir.exists():
            return {"ok": True, "events": [], "note": "no logs directory"}

        # Find latest event log
        event_logs = sorted(logs_dir.glob("events_*.jsonl"), reverse=True)[:1]
        if not event_logs:
            return {"ok": True, "events": [], "note": "no event logs found"}

        # Read last 20 events
        events = []
        with open(event_logs[0], "r", encoding="utf-8") as f:
            lines = f.readlines()[-20:]
            for line in lines:
                try:
                    events.append(json.loads(line.strip()))
                except:
                    pass

        return {
            "ok": True,
            "source_file": str(event_logs[0]),
            "recent_events": events
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

# Build diagnostics bundle
bundle = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "version": "1.0",
    "system": {
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "repo_root": str(repo_root)
    },
    "pytest": get_pytest_status(),
    "model_readiness": get_model_readiness(),
    "compile": get_compile_status(),
    "voice": get_voice_quick_status(),
    "addons": get_addon_health(),
    "gpu": get_gpu_status(),
    "memory": get_memory_status(),
    "events": get_event_log_summary()
}

# Calculate overall status
issues = []
if not bundle["compile"]["ok"]:
    issues.append("compile_failed")
if bundle["voice"].get("status") == "degraded":
    issues.append("voice_degraded")
if bundle["gpu"]["gpu_type"] == "unknown":
    issues.append("gpu_not_detected")

bundle["overall"] = {
    "status": "degraded" if len(issues) > 1 else "partial" if issues else "ok",
    "issues": issues
}

print(json.dumps(bundle, indent=2, default=str))
"@

    Write-Status "  Running diagnostics collection..."
    $output = & $pythonBin -c $diagnosticsScript

    # Save output
    $output | Out-File -FilePath $outputPath -Encoding utf8
    $output | Out-File -FilePath $latestPath -Encoding utf8

    Write-Status "  Saved to: $outputPath"
    Write-Status "  Latest: $latestPath"

    # Clean up old backups
    if ($KeepBackups -gt 0) {
        $oldFiles = Get-ChildItem -Path $OutputDir -Filter "diagnostics_bundle_*.json" |
            Where-Object { $_.Name -notlike "*_latest.json" } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -Skip $KeepBackups

        foreach ($file in $oldFiles) {
            Remove-Item -LiteralPath $file.FullName -Force
        }
    }

    # Output summary
    if (-not $Quiet) {
        $json = $output | ConvertFrom-Json
        Write-Host "`n=== Diagnostics Summary ===" -ForegroundColor Cyan
        Write-Host "Timestamp: $($json.timestamp)"
        Write-Host "Overall Status: $($json.overall.status)" -ForegroundColor $(
            if ($json.overall.status -eq "ok") { "Green" }
            elseif ($json.overall.status -eq "partial") { "Yellow" }
            else { "Red" }
        )

        if ($json.overall.issues) {
            Write-Host "Issues:" -ForegroundColor Yellow
            foreach ($issue in $json.overall.issues) {
                Write-Host "  - $issue"
            }
        }

        Write-Host "`nComponent Status:"
        Write-Host "  Pytest: $(if ($json.pytest.ok) { 'OK' } else { 'FAILED' })"
        Write-Host "  Compile: $(if ($json.compile.ok) { 'OK' } else { 'FAILED' })"
        Write-Host "  Voice: $($json.voice.status)"
        Write-Host "  Addons: $($json.addons.addon_count) found"
        Write-Host "  GPU: $($json.gpu.gpu_type)"
        Write-Host "  Memory: $(if ($json.memory.ok) { "$($json.memory.fact_count) facts" } else { 'ERROR' })"
    }

    # Return exit code based on status
    if ($json.overall.status -eq "degraded") {
        exit 1
    }

} finally {
    Remove-Item Env:JARVIS_USE_KOKORO_PACK -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PACK_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PYTHON -ErrorAction SilentlyContinue
    Pop-Location
}
