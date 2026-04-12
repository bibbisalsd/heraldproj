@echo off
setlocal

cd /d "%~dp0"

set "_mode=%~1"

if /i "%_mode%"=="chat" (
    shift
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_chat.ps1" %*
    exit /b %errorlevel%
)

if /i "%_mode%"=="voice" shift

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_jarvis_voice_loop.ps1" %*
exit /b %errorlevel%
