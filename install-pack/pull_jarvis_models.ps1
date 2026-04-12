[CmdletBinding()]
param(
    [switch]$PullMissingOnly = $true,
    [string]$OllamaBin = "ollama",
    [int]$ReadyRetries = 20,
    [int]$ReadyDelaySeconds = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SetupScript = Join-Path $RepoRoot "scripts\setup_models.ps1"

if (-not (Test-Path -LiteralPath $SetupScript)) {
    throw "setup_models.ps1 not found at $SetupScript"
}

function Wait-OllamaReady {
    param(
        [string]$Executable,
        [int]$Retries,
        [int]$DelaySeconds
    )

    for ($attempt = 1; $attempt -le [Math]::Max(1, $Retries); $attempt++) {
        try {
            & $Executable list | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return $true
            }
        }
        catch {
        }
        Start-Sleep -Seconds ([Math]::Max(1, $DelaySeconds))
    }
    return $false
}

if (-not (Wait-OllamaReady -Executable $OllamaBin -Retries $ReadyRetries -DelaySeconds $ReadyDelaySeconds)) {
    throw "Ollama did not become ready before model pull."
}

$setupArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $SetupScript,
    "-OllamaBin", $OllamaBin
)
if ($PullMissingOnly) {
    $setupArgs += "-PullMissingOnly"
}

& powershell @setupArgs
if ($LASTEXITCODE -ne 0) {
    throw "Model pull failed."
}
