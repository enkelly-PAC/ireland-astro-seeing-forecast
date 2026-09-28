@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Ireland-Forecast.ps1"
if errorlevel 1 (
  echo.
  echo The forecast tool could not start. Review the error above.
  pause
)
