[CmdletBinding()]
param(
    [switch]$SkipModelPull = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $venvPython = Join-Path (Get-Location) ".venv\\Scripts\\python.exe"
    $pythonBin = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

    if (-not $SkipModelPull) {
        & (Join-Path $PSScriptRoot "setup_models.ps1") -PullMissingOnly
        if ($LASTEXITCODE -ne 0) { throw "setup_models failed" }
    }

    & (Join-Path $PSScriptRoot "smoke_test.ps1")
    if ($LASTEXITCODE -ne 0) { throw "smoke_test failed" }

    & (Join-Path $PSScriptRoot "run_tests.ps1")
    if ($LASTEXITCODE -ne 0) { throw "run_tests failed" }

    $defaultPackDir = Join-Path (Split-Path -Parent $PSScriptRoot) "jarvis\\voice\\kokoro_pack"
    if (Test-Path (Join-Path $defaultPackDir "jarvis_launcher.py")) {
        $env:JARVIS_USE_KOKORO_PACK = "true"
        $env:JARVIS_KOKORO_PACK_DIR = $defaultPackDir
        $defaultPackPython = $venvPython
        if (Test-Path $defaultPackPython) {
            $env:JARVIS_KOKORO_PYTHON = $defaultPackPython
        }
    }
    $env:JARVIS_TTS_BACKEND = "kokoro"

    $probe = @"
from jarvis.main import JarvisRuntime
rt = JarvisRuntime()
rt.startup(model_ready=True)
turns = [
    "jarvis whats the time",
    "status",
    "please research this code task deeply",
    "what are you doing",
]
for t in turns:
    r = rt.run_turn(t)
    print({"input": t, "lane": r["lane"], "text": r["text"]})
rt.shutdown()
"@
    $probe | & $pythonBin -
    if ($LASTEXITCODE -ne 0) { throw "runtime_probe failed" }

    $artifact = Join-Path (Get-Location) "artifacts\\v1_operating_report.md"
    @"
# V1 Operating Report

- checked_at_utc: $((Get-Date).ToUniversalTime().ToString("o"))
- status: pass
- local_only: true
- models_targeted:
  - llama3.2:1b
  - llama3.2:3b
  - qwen2.5vl:3b
  - qwen3-vl:8b
  - deepcoder:14b
  - nomic-embed-text-v2-moe
- tts_target: Kokoro-82M
- stt_target: small.en
"@ | Set-Content -LiteralPath $artifact -Encoding UTF8

    Write-Host "compile_v1 completed."
}
finally {
    Remove-Item Env:JARVIS_USE_KOKORO_PACK -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PACK_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_KOKORO_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:JARVIS_TTS_BACKEND -ErrorAction SilentlyContinue
    Pop-Location
}
