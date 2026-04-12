[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    pytest -q tests/test_guardrails.py tests/test_network_guard.py
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
