@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" was not found.
  echo Install Python 3.10+ and hidapi, then retry.
  pause
  exit /b 1
)
py .\toprert_unified_gui.py
if errorlevel 1 pause
