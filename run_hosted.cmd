@echo off
setlocal
cd /d "%~dp0"
python -m agent_privacy.hosted %*
set "hosted_exit_code=%errorlevel%"
echo.
pause
exit /b %hosted_exit_code%
