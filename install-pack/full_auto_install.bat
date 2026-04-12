@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PACK_ROOT=%~dp0"
for %%I in ("%PACK_ROOT%..") do set "REPO_ROOT=%%~fI"

set "VOICE_MODE=Pack"
set "SKIP_COMPILE=0"
set "RUN_VOICE_MIC=1"
set "MIC_DURATION=3"
set "DRY_RUN=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help
if /I "%~1"=="--dry-run" set "DRY_RUN=1" & shift & goto parse_args
if /I "%~1"=="--skip-compile" set "SKIP_COMPILE=1" & shift & goto parse_args
if /I "%~1"=="--skip-voice-mic" set "RUN_VOICE_MIC=0" & shift & goto parse_args
if /I "%~1"=="--voice-mode" (
    if "%~2"=="" goto invalid_args
    set "VOICE_MODE=%~2"
    shift
    shift
    goto parse_args
)
if /I "%~1"=="--mic-duration" (
    if "%~2"=="" goto invalid_args
    set "MIC_DURATION=%~2"
    shift
    shift
    goto parse_args
)
echo [error] Unknown argument: %~1
goto invalid_args

:args_done
call :locate_powershell || goto fail

echo [info] Repo root: %REPO_ROOT%
echo [info] PowerShell engine: %PS_ENGINE%
echo [info] Voice mode: %VOICE_MODE%
echo [info] Voice mic acceptance: %RUN_VOICE_MIC%
echo [info] Skip compile: %SKIP_COMPILE%
echo [info] Dry run: %DRY_RUN%

set "ADV_ARGS=--voice-mode %VOICE_MODE% --skip-model-pull --skip-acceptance"
if "%DRY_RUN%"=="1" set "ADV_ARGS=%ADV_ARGS% --dry-run"

call :run_bat "%REPO_ROOT%\install-pack\bootstrap_host_advanced.bat" %ADV_ARGS%
if errorlevel 1 goto fail

call :run_bat "%REPO_ROOT%\install-pack\install_models_now.bat"
if errorlevel 1 goto fail

call :run_acceptance
if errorlevel 1 goto fail

echo [ok] Full auto install completed successfully.
exit /b 0

:run_bat
set "TARGET_BAT=%~1"
shift
set "BAT_ARGS="
:run_bat_collect
if "%~1"=="" goto run_bat_ready
set "BAT_ARGS=!BAT_ARGS! %~1"
shift
goto run_bat_collect
:run_bat_ready
echo [run] "%TARGET_BAT%"!BAT_ARGS!
if "%DRY_RUN%"=="1" exit /b 0
call "%TARGET_BAT%"!BAT_ARGS!
exit /b %errorlevel%

:run_ps
set "TARGET_SCRIPT=%~1"
shift
set "SCRIPT_ARGS="
:run_ps_collect
if "%~1"=="" goto run_ps_ready
set "SCRIPT_ARGS=!SCRIPT_ARGS! "%~1""
shift
goto run_ps_collect
:run_ps_ready
echo [run] "%TARGET_SCRIPT%"!SCRIPT_ARGS!
if "%DRY_RUN%"=="1" exit /b 0
"%PS_ENGINE%" -NoProfile -ExecutionPolicy Bypass -File "%TARGET_SCRIPT%"!SCRIPT_ARGS!
exit /b %errorlevel%

:run_acceptance
if "%RUN_VOICE_MIC%"=="1" (
    if "%SKIP_COMPILE%"=="1" (
        call :run_ps "%REPO_ROOT%\scripts\accept_target_stack.ps1" -SkipCompile -SkipVoiceMic:$false -MicDurationSeconds %MIC_DURATION%
    ) else (
        call :run_ps "%REPO_ROOT%\scripts\accept_target_stack.ps1" -SkipVoiceMic:$false -MicDurationSeconds %MIC_DURATION%
    )
) else (
    if "%SKIP_COMPILE%"=="1" (
        call :run_ps "%REPO_ROOT%\scripts\accept_target_stack.ps1" -SkipCompile -SkipVoiceMic
    ) else (
        call :run_ps "%REPO_ROOT%\scripts\accept_target_stack.ps1" -SkipVoiceMic
    )
)
exit /b %errorlevel%

:locate_powershell
where pwsh >nul 2>&1
if not errorlevel 1 (
    set "PS_ENGINE=pwsh"
    exit /b 0
)
where powershell >nul 2>&1
if not errorlevel 1 (
    set "PS_ENGINE=powershell"
    exit /b 0
)
echo [error] Neither 'pwsh' nor 'powershell' was found on PATH.
exit /b 1

:help
echo.
echo Jarvis Full Auto Install
echo ------------------------
echo Combines advanced bootstrap, direct model install, and acceptance in one BAT.
echo Voice mic acceptance is ON by default.
echo.
echo Usage:
echo   full_auto_install.bat [options]
echo.
echo Options:
echo   --voice-mode Pack^|Package^|None   Select Python voice dependency mode. Default: Pack
echo   --mic-duration SECONDS            Microphone acceptance duration. Default: 3
echo   --skip-voice-mic                  Disable microphone validation in acceptance
echo   --skip-compile                    Skip compile inside acceptance
echo   --dry-run                         Print steps without executing them
echo   --help                            Show this help
echo.
exit /b 0

:invalid_args
echo.
echo Use --help for usage.
exit /b 2

:fail
echo [error] Full auto install failed.
exit /b 1
