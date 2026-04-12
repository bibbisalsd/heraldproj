[CmdletBinding()]
param(
    [switch]$NoStart = $false,
    [switch]$WaitForReady = $false,
    [int]$ReadyRetries = 20,
    [int]$ReadyDelaySeconds = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-OllamaExecutable {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\Ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\Ollama.exe")
    )
    return ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

function Test-Ollama {
    try {
        $exe = Get-OllamaExecutable
        if (-not $exe) {
            return $false
        }
        & $exe --version | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
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

if (Test-Ollama) {
    Write-Host "Ollama already installed."
}
else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "winget is required for automated Ollama installation in this pack."
    }

    & winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install Ollama."
    }
}

$exe = Get-OllamaExecutable
if (-not $exe) {
    throw "Ollama installation finished, but no Ollama executable was found on PATH or in the standard install locations."
}

if (-not $NoStart) {
    if (Test-Path -LiteralPath $exe) {
        Start-Process -FilePath $exe | Out-Null
        Write-Host "Started Ollama: $exe"
    }
    else {
        Write-Warning "Ollama resolved via PATH as '$exe'; startup was not launched directly from disk."
    }
}

if ($WaitForReady) {
    if (Wait-OllamaReady -Executable $exe -Retries $ReadyRetries -DelaySeconds $ReadyDelaySeconds) {
        Write-Host "Ollama is ready."
    }
    else {
        throw "Ollama executable was found, but 'ollama list' did not become ready after waiting."
    }
}

Write-Host "Ollama executable: $exe"
