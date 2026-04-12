@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PACK_ROOT=%~dp0"
for %%I in ("%PACK_ROOT%..") do set "REPO_ROOT=%%~fI"

set "VOICE_MODE=Pack"
set "SKIP_OLLAMA=0"
set "SKIP_MODEL_PULL=0"
set "SKIP_COMPILE=0"
set "SKIP_ACCEPTANCE=0"
set "RUN_VOICE_MIC=1"
set "MIC_DURATION=3"
set "DRY_RUN=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help
if /I "%~1"=="--dry-run" set "DRY_RUN=1" & shift & goto parse_args
if /I "%~1"=="--skip-ollama" set "SKIP_OLLAMA=1" & shift & goto parse_args
if /I "%~1"=="--skip-model-pull" set "SKIP_MODEL_PULL=1" & shift & goto parse_args
if /I "%~1"=="--skip-compile" set "SKIP_COMPILE=1" & shift & goto parse_args
if /I "%~1"=="--skip-acceptance" set "SKIP_ACCEPTANCE=1" & shift & goto parse_args
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

if not exist "%REPO_ROOT%\install-pack\install_python_env.ps1" (
    echo [error] Repo root was not resolved correctly: "%REPO_ROOT%"
    goto fail
)

echo [info] Repo root: %REPO_ROOT%
echo [info] PowerShell engine: %PS_ENGINE%
echo [info] Voice mode: %VOICE_MODE%
echo [info] Voice mic acceptance: %RUN_VOICE_MIC%
echo [info] Skip compile: %SKIP_COMPILE%
echo [info] Skip acceptance: %SKIP_ACCEPTANCE%
echo [info] Dry run: %DRY_RUN%

call :run_ps "%REPO_ROOT%\install-pack\install_python_env.ps1" -VoiceMode %VOICE_MODE%
if errorlevel 1 goto fail

if "%SKIP_OLLAMA%"=="0" (
    call :ensure_ollama
    if errorlevel 1 goto fail
)

if "%SKIP_MODEL_PULL%"=="0" (
    call :pull_models
    if errorlevel 1 goto fail
)

if "%SKIP_ACCEPTANCE%"=="0" (
    call :run_acceptance
    if errorlevel 1 goto fail
) else (
    echo [info] Acceptance skipped by request.
)

echo [ok] Advanced bootstrap completed successfully.
exit /b 0

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

:locate_ollama
set "OLLAMA_EXE="
for /f "delims=" %%I in ('where ollama 2^>nul') do (
    set "OLLAMA_EXE=%%~fI"
    goto ollama_found
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\Ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\Ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\Ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\Ollama.exe"
:ollama_found
if defined OLLAMA_EXE (
    for %%I in ("%OLLAMA_EXE%") do set "OLLAMA_DIR=%%~dpI"
    exit /b 0
)
exit /b 1

:ensure_ollama
if "%DRY_RUN%"=="1" (
    call :locate_ollama >nul 2>&1
    if not errorlevel 1 (
        echo [info] Ollama detected at: %OLLAMA_EXE%
    ) else (
        echo [info] Ollama not found. Installer fallback would run here.
    )
    exit /b 0
)

call :locate_ollama
if not errorlevel 1 (
    echo [info] Ollama detected at: %OLLAMA_EXE%
    call :prepend_ollama_path
    call :wait_ollama
    if not errorlevel 1 exit /b 0
    echo [warn] Ollama executable exists but is not ready yet. Attempting startup.
    if "%DRY_RUN%"=="0" start "" "%OLLAMA_EXE%" >nul 2>&1
    call :wait_ollama
    exit /b %errorlevel%
)

echo [info] Ollama not found. Running installer fallback.
call :run_ps "%REPO_ROOT%\install-pack\install_ollama_runtime.ps1" -WaitForReady -ReadyRetries 20 -ReadyDelaySeconds 3
if errorlevel 1 exit /b 1

call :locate_ollama
if errorlevel 1 (
    echo [error] Ollama install completed but the executable still could not be located.
    exit /b 1
)

call :prepend_ollama_path
call :wait_ollama
exit /b %errorlevel%

:prepend_ollama_path
if defined OLLAMA_DIR (
    echo %PATH% | find /I "%OLLAMA_DIR%" >nul
    if errorlevel 1 set "PATH=%OLLAMA_DIR%;%PATH%"
)
exit /b 0

:wait_ollama
if "%DRY_RUN%"=="1" exit /b 0
if not defined OLLAMA_EXE (
    echo [error] wait_ollama called without a resolved OLLAMA_EXE.
    exit /b 1
)

for /L %%N in (1,1,20) do (
    "%OLLAMA_EXE%" list >nul 2>&1
    if not errorlevel 1 (
        echo [ok] Ollama responded to 'list'.
        exit /b 0
    )
    if %%N==1 start "" "%OLLAMA_EXE%" >nul 2>&1
    echo [wait] Waiting for Ollama readiness (attempt %%N/20)...
    timeout /t 3 /nobreak >nul
)
echo [error] Ollama did not become ready after repeated checks.
exit /b 1

:pull_models
echo [info] Pulling Jarvis model set...
if defined OLLAMA_EXE (
    call :run_ps "%REPO_ROOT%\install-pack\pull_jarvis_models.ps1" -PullMissingOnly -OllamaBin "%OLLAMA_EXE%"
) else (
    call :run_ps "%REPO_ROOT%\install-pack\pull_jarvis_models.ps1" -PullMissingOnly
)
if not errorlevel 1 exit /b 0

echo [warn] Model pull failed on first attempt. Re-checking Ollama and retrying once.
call :ensure_ollama
if errorlevel 1 exit /b 1
if defined OLLAMA_EXE (
    call :run_ps "%REPO_ROOT%\install-pack\pull_jarvis_models.ps1" -PullMissingOnly -OllamaBin "%OLLAMA_EXE%"
) else (
    call :run_ps "%REPO_ROOT%\install-pack\pull_jarvis_models.ps1" -PullMissingOnly
)
exit /b %errorlevel%

:run_acceptance
echo [info] Running target-stack acceptance...
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

:help
echo.
echo Jarvis Advanced Bootstrap
echo -------------------------
echo Runs Python env setup, Ollama detection/install, model pulls, and acceptance.
echo Voice mic acceptance is ON by default.
echo.
echo Usage:
echo   bootstrap_host_advanced.bat [options]
echo.
echo Options:
echo   --voice-mode Pack^|Package^|None   Select Python voice dependency mode. Default: Pack
echo   --mic-duration SECONDS            Microphone acceptance duration. Default: 3
echo   --skip-voice-mic                  Disable microphone validation in acceptance
echo   --skip-compile                    Skip compile inside acceptance
echo   --skip-acceptance                 Skip the acceptance phase entirely
echo   --skip-model-pull                 Skip model pull step
echo   --skip-ollama                     Skip Ollama install/detect step
echo   --dry-run                         Print steps without executing them
echo   --help                            Show this help
echo.
exit /b 0

:invalid_args
echo.
echo Use --help for usage.
exit /b 2

:fail
echo [error] Advanced bootstrap failed.
exit /b 1
