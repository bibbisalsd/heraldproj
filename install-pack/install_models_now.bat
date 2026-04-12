@echo off
setlocal EnableExtensions

set "PACK_ROOT=%~dp0"
for %%I in ("%PACK_ROOT%..") do set "REPO_ROOT=%%~fI"

where pwsh >nul 2>&1
if not errorlevel 1 (
    set "PS_ENGINE=pwsh"
) else (
    set "PS_ENGINE=powershell"
)

set "OLLAMA_EXE="
for /f "delims=" %%I in ('where ollama 2^>nul') do (
    set "OLLAMA_EXE=%%~fI"
    goto have_ollama
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\Ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\Ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\Ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\Ollama.exe"

:have_ollama
if not defined OLLAMA_EXE (
    echo [error] Ollama executable was not found. Run install-pack\bootstrap_host_advanced.bat first.
    exit /b 1
)

echo [info] Using Ollama executable: %OLLAMA_EXE%
"%PS_ENGINE%" -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\install-pack\pull_jarvis_models.ps1" -PullMissingOnly -OllamaBin "%OLLAMA_EXE%"
exit /b %errorlevel%
