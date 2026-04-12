[CmdletBinding()]
param(
    [string]$TaskName = "JarvisDailyOps",
    [switch]$IgnoreMissing,
    [switch]$PreviewOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-SchtasksSafe {
    param([string[]]$Args)

    $nativePref = $null
    $hasNativePref = Test-Path Variable:PSNativeCommandUseErrorActionPreference
    if ($hasNativePref) {
        $nativePref = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        & schtasks @Args | Out-Null
        return [int]$LASTEXITCODE
    }
    finally {
        if ($hasNativePref) {
            $PSNativeCommandUseErrorActionPreference = $nativePref
        }
    }
}

$exists = $false
$queryExit = Invoke-SchtasksSafe @("/Query", "/TN", $TaskName)
if ($queryExit -eq 0) {
    $exists = $true
}

$deleteArgs = @("/Delete", "/TN", $TaskName, "/F")

if ($PreviewOnly) {
    @{
        preview_only = $true
        task_name = $TaskName
        exists = $exists
        delete_args = $deleteArgs
    } | ConvertTo-Json -Depth 4
    exit 0
}

if (-not $exists) {
    if ($IgnoreMissing) {
        @{
            deleted = $false
            task_name = $TaskName
            reason = "missing"
        } | ConvertTo-Json -Depth 4
        exit 0
    }
    throw "Task '$TaskName' does not exist."
}

$deleteExitCode = Invoke-SchtasksSafe $deleteArgs
if ($deleteExitCode -ne 0) {
    throw "Failed to remove scheduled task '$TaskName'."
}

@{
    deleted = $true
    task_name = $TaskName
} | ConvertTo-Json -Depth 4
