@echo off
setlocal

cd /d "%~dp0"

call "%~dp0start_jarvis.bat" %*
exit /b %errorlevel%