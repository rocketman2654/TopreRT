@echo off
cd /d "%~dp0"
echo Normal identity check only. This launcher does NOT enter update mode.
echo Close TopreRT Observer and other keyboard tools before continuing.
pause
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup_Demo.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B hhkb_identity_probe.py --report "output\identity_probe_%RANDOM%_%RANDOM%.json"
pause
