@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import tkinter, hid" >nul 2>nul
  if errorlevel 1 (
    echo Demo dependencies are missing. Run Setup_Demo.bat in this folder.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -B .\toprert_unified_gui.py
  if errorlevel 1 pause
  exit /b
)
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" was not found.
  echo Install Python 3.12 with the Python Launcher, then run Setup_Demo.bat.
  pause
  exit /b 1
)
py -c "import tkinter, hid" >nul 2>nul
if errorlevel 1 (
  echo This Python cannot load the USB library. Run Setup_Demo.bat in this folder.
  pause
  exit /b 1
)
py -B .\toprert_unified_gui.py
if errorlevel 1 pause
