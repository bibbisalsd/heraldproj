[CmdletBinding()]
param()

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

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $pythonBin = Get-JarvisPython
    $baseTemp = Join-Path (Get-Location) ".pytest-safe\run_tests"
    $baseTempParent = Split-Path -Parent $baseTemp
    if (-not (Test-Path -LiteralPath $baseTempParent)) {
        New-Item -ItemType Directory -Path $baseTempParent -Force | Out-Null
    }
    @"
import os
import pytest
import _pytest.tmpdir
import _pytest.pathlib

orig_mkdir = os.mkdir

def safe_mkdir(path, mode=0o777, *, dir_fd=None):
    if dir_fd is None:
        return orig_mkdir(path)
    return orig_mkdir(path, dir_fd=dir_fd)

os.mkdir = safe_mkdir
_pytest.tmpdir.cleanup_dead_symlinks = lambda path: None
_pytest.pathlib.cleanup_dead_symlinks = lambda path: None

raise SystemExit(pytest.main([
    "-q",
    "tests",
    "--basetemp",
    r"$baseTemp",
]))
"@ | & $pythonBin -
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
