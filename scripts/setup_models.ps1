[CmdletBinding()]
param(
    [switch]$PullMissingOnly = $true,
    [string]$OllamaBin = "ollama"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-OllamaBin {
    param(
        [string]$Requested = "ollama"
    )

    $candidate = $Requested
    if ($null -eq $candidate) {
        $candidate = ""
    }
    $candidate = $candidate.Trim()
    if ([string]::IsNullOrWhiteSpace($candidate)) { $candidate = "ollama" }
    if ($candidate -ne "ollama") {
        return $candidate
    }

    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }

    $fallbacks = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\Ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles "Ollama\Ollama.exe")
    )
    $resolved = $fallbacks | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($resolved) {
        return $resolved
    }
    return $candidate
}

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $ResolvedOllamaBin = Resolve-OllamaBin -Requested $OllamaBin
    $models = @(
        "llama3.2:1b",
        "llama3.2:3b",
        "qwen2.5vl:3b",
        "qwen3-vl:8b",
        "deepcoder:14b",
        "nomic-embed-text-v2-moe"
    )

    try {
        $listOutput = & $ResolvedOllamaBin list 2>&1
        $listExitCode = $LASTEXITCODE
    }
    catch {
        throw "ollama list failed. Ensure Ollama is installed and running locally."
    }
    $joinedOutput = (($listOutput | ForEach-Object { "$_" }) -join "`n").Trim()
    if ($listExitCode -ne 0) {
        if ($joinedOutput -match "failed to create server log" -and $joinedOutput -match "Access is denied") {
            throw (
                "ollama list failed due log-file permissions under %LOCALAPPDATA%\Ollama. " +
                "Fix permissions or run Ollama under the current user context."
            )
        }
        throw "ollama list failed. Ensure Ollama is installed and running locally."
    }

    $installed = @{}
    $installedBases = @{}
    foreach ($line in ($listOutput -split "`r?`n")) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed -like "NAME*") { continue }
        if ($trimmed -like "*WARN*") { continue }
        if ($trimmed -like "*ERROR*") { continue }
        $parts = $trimmed -split "\s+"
        if ($parts.Count -gt 0 -and $parts[0] -match "^[A-Za-z0-9._-]+:[A-Za-z0-9._-]+$") {
            $installed[$parts[0]] = $true
            $installedBases[($parts[0] -split ":", 2)[0]] = $true
        }
    }

    foreach ($model in $models) {
        $modelBase = ($model -split ":", 2)[0]
        $modelInstalled = $installed.ContainsKey($model) -or (-not ($model -like "*:*") -and $installedBases.ContainsKey($modelBase))
        if ($PullMissingOnly -and $modelInstalled) {
            Write-Host "[skip] $model already installed"
            continue
        }
        Write-Host "[pull] $model"
        & $ResolvedOllamaBin pull $model
        if ($LASTEXITCODE -ne 0) {
            throw "Failed pulling model: $model"
        }
    }

    Write-Host "Model setup complete."
}
finally {
    Pop-Location
}
