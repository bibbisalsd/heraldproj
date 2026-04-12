[CmdletBinding()]
param(
    [string]$Text = "status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $defaultPackDir = Join-Path (Split-Path -Parent $PSScriptRoot) "jarvis\\voice\\kokoro_pack"
    if (Test-Path (Join-Path $defaultPackDir "jarvis_launcher.py")) {
        $env:JARVIS_USE_KOKORO_PACK = "true"
        $env:JARVIS_KOKORO_PACK_DIR = $defaultPackDir
        $defaultPackPython = Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\\Scripts\\python.exe"
        if (Test-Path $defaultPackPython) {
            $env:JARVIS_KOKORO_PYTHON = $defaultPackPython
        }
    }
    $env:JARVIS_TTS_BACKEND = "kokoro"
    $env:JARVIS_CLI_TEXT = $Text
    @"
import os
from jarvis.main import JarvisRuntime
rt = JarvisRuntime()
rt.startup(model_ready=True)
print(rt.run_turn(os.environ.get("JARVIS_CLI_TEXT", "status")))
"@ | python -
}
finally {
    Remove-Item Env:JARVIS_USE_KOKORO_PACK -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PACK_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_TTS_BACKEND -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_CLI_TEXT -ErrorAction SilentlyContinue
    Pop-Location
}
