# TopreRT v0.3.0-rc5 — HHKB firmware identification

This prerelease adds HHKB build identification and records the recipe behind
generated RT/HOLD firmware. Existing rc3/rc4 releases remain available unchanged.

## Changes

- HHKB generation embeds a deterministic family/build ID and validates saved
  images/manifests before transmission. Inspection connects reported IDs with
  immutable versioned catalogs or local build records.
- Matching RT recipes display release/re-press raw values and estimated mm,
  explicitly as build settings, not device settings readback.
- Detect preserves files/settings when re-detecting the same family, distinguishes
  normal/update modes and discards stale inspection results.
- PC installation history is separate from device identification. RT/HOLD share
  packet counts, elapsed time, transfer ETA and speed presentation.
- Atomic artifact publication preserves conflicting files during concurrent saves;
  malformed custom records stop inspection before device queries.
- The rc4 HOLD snapshot-query correction and updater identity protections remain.

## Installation

Download **TopreRT_v0.3.0-rc5.zip**, extract into a new writable folder, install
Python 3.12 with Python Launcher/Tkinter, run Setup_Demo.bat, then
Start_TopreRT_GUI.bat. Stock firmware is not included: supported model-specific
R3S A0.12 or exact HHKB PD-KB800W A0.48 is required for generation/installation.
R3S creates an .rfb for official REALFORCE software. HHKB RT installs inside the
app; HOLD uses Create HOLD File followed by Install HOLD. Updating the PC app
alone does not require flashing the keyboard.

## Version and validation scope

The app is rc5; generated firmware retains the reviewed **Development** build
IDs and output labels. These IDs are not an assigned firmware release version.
The generator, fixed firmware template and existing catalog snapshots are
unchanged. A separate catalog ZIP is provided for this app release.

One PD-KB800W passed user-operated GUI Golden RT B33E6ADF (R32/P32) and HOLD
A96B4BA0 (Space tap/Fn hold250ms, one slot) installation, reconnect, identification
and functional checks. RT typing/Observer and HOLD typing/SpaceFn were confirmed.
See HARDWARE_IDENTIFICATION_20261018.md. The earlier test suite had153 passing
offline checks; final release-source and packaged-copy results are recorded with
the release preparation. CI does not bundle proprietary stock firmware and skips
the stock-dependent class unless TOPRERT_TEST_STOCK is supplied.

Metadata is a firmware-reported claim, not authentication, full flash readback,
settings readback or physical distance measurement. Other devices/configurations,
default RT81B8EDEB, clean-PC setup and interrupted-update recovery need separate
validation. Fast overlapping typing can place a SpaceFn space after the next
character; this retained behavior limitation is not fixed. R3S identification,
R3S RT overhaul and additional models are not included.

## 한국어 안내

rc5는 HHKB RT/HOLD 빌드 식별, 생성 기록과 카탈로그에 따른 RT 설정 표시,
Detect 개선, PC 설치 이력 분리와 진행률 표시 통합을 포함합니다. 앱은 rc5이며
생성 펌웨어의 Development ID는 검증한 기존 생성 방식을 유지하기 위한 표시입니다.
기기 설정이나 전체 펌웨어를 직접 읽어온 값으로 해석하지 마세요.

기존 폴더에 덮어쓰지 말고 새 폴더에 압축 해제한 뒤 Setup_Demo.bat →
Start_TopreRT_GUI.bat 순서로 실행하세요. 순정 파일은 배포하지 않습니다.
R3S는 생성 .rfb를 공식 프로그램에서 설치하고, HHKB RT는 앱 내 설치,
HOLD는 파일 생성/설치 두 단계를 사용합니다. SpaceFn 공백 순서 지연은 현재 한계로
남겨 두었습니다. 새 펌웨어를 설치하지 않아도 PC 앱을 교체해 사용할 수 있습니다.
