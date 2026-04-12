[CmdletBinding()]
param()

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
    @"
from jarvis.main import JarvisRuntime

rt = JarvisRuntime()
rt.startup(model_ready=True)
print("Jarvis started. Type 'exit' to quit.")

while True:
    try:
        user = input("You> ").strip()
    except EOFError:
        break
    if not user:
        continue
    if user.lower() in {"exit", "quit"}:
        break
    result = rt.run_turn(user)
    print(f"Jarvis> {result['text']}")

rt.shutdown()
"@ | python -
}
finally {
    Remove-Item Env:JARVIS_USE_KOKORO_PACK -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PACK_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_TTS_BACKEND -ErrorAction SilentlyContinue
    Pop-Location
}
