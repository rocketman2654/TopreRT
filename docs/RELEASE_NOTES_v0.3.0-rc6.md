# TopreRT v0.3.0-rc6 — Python setup hotfix

This prerelease fixes PC app installation when Python 3.12 is absent and when
an explicit Python path is passed to Setup_Demo.bat. Updating the PC app does
not require reinstalling keyboard firmware.

## Fixed

- Prefer Python 3.12, then try the launcher's default Python 3, PATH python,
  and PATH python3. Automatic candidates must provide Python 3.10+ and Tkinter.
- Forward -PythonPath from the BAT wrapper to the PowerShell script, including
  quoted paths with spaces. An explicit path takes priority over discovery.
- Preserve the setup failure exit code after the BAT pause. Show the selected
  interpreter and distinguish dependency errors from discovery errors.
- Avoid nested quotes in Python checks: Windows PowerShell can strip them and
  cause a SyntaxError in the final readiness check even after dependencies install.

## Installation

Extract TopreRT_v0.3.0-rc6.zip into a new writable folder. Python 3.12 with
Tcl/Tk (Tkinter) remains recommended. Run Setup_Demo.bat, then Start_TopreRT_GUI.bat.
Alternatively, from PowerShell in the extracted folder:

```powershell
.\Setup_Demo.bat -PythonPath "C:\path\to\python.exe"
```

Replace the example path with the actual Python executable. The launcher is
optional when a usable interpreter is on PATH or supplied explicitly.

## Scope and validation

The baseline is rc5 commit 9cd731d839760910f7375a599384d4a83aab9b61.
Firmware generators, templates, USB writers, supported models, thresholds,
firmware IDs and existing catalog snapshots are unchanged. R3S RT overhaul
development is excluded. App version labels and the release catalog mapping
identify rc6; generated firmware retains its reviewed Development IDs.

Setup discovery and BAT forwarding regressions are tested without hardware.
Windows CI runs the actual setup script, dependency installation, offline tests
and hidden GUI widget tests on Python 3.12 and 3.14. Consult the associated CI
results for the completed validation, rather than treating configuration as a
passing result. Detection of other Python 3.10+ versions is not a claim that all
Python versions or devices have been tested. No new keyboard hardware trial is
part of this setup fix. Existing SpaceFn ordering and recovery limits remain.

## 한국어

Python 3.14만 설치된 PC에서도 다른 Python을 탐색할 수 있도록 3.12 고정 탐색을
수정했습니다. BAT에 전달한 -PythonPath가 무시되던 문제와 종료 코드도 수정했습니다.
새 폴더에 압축을 풀고 Setup_Demo.bat → Start_TopreRT_GUI.bat 순서로 실행하세요.
키보드 펌웨어 재설치는 필요하지 않습니다. 기존 rc3/rc4/rc5 자산은 보존합니다.
이 수정은 PC 설치 절차에 한정하며 R3S RT 오버홀은 포함하지 않습니다.
