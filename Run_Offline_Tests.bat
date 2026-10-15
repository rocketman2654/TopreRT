@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup_Demo.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -B -m unittest discover -s tests -v
pause
