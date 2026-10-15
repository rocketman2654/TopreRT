# TopreRT v0.3.0-rc4 — HOLD inspection correction

This prerelease corrects the PC application's HHKB firmware inspection. Updating the app does not require reinstalling keyboard firmware. Firmware patch payloads, writers, thresholds and supported devices are unchanged from rc3.

## Fixed

- Replace the historical C1 A1 HOLD identification request, which initializes live HOLD state RAM, with the existing C1 52 snapshot request.
- Require the snapshot's operation marker and reject oversized replies. A failed transmit/receive or unsupported snapshot never falls back to initialization and never proves RT-only or stock.
- Add the HOLD inspection advisory and regression coverage.

## Evidence and limits

64 offline app tests passed on Windows/Python 3.12. The RT regression check was user-confirmed on one PD-KB800W. The same user then installed the SHA-verified SpaceFn candidate (SPACE -> tap SPACE / hold FN, 250ms, one slot), confirmed long-press Fn behavior, ran inspection and supplied a screenshot of Legacy Dual-Role / HOLD with common telemetry plus CNY signature. The user reported it appeared to work after inspection. The screenshot also shows finalization and normal reconnect completion.

This is one device and one configuration. It does not validate all HOLD targets, threshold timings, USB conditions or interrupted-update recovery. No physical failure from the old query was deliberately reproduced. Static analysis establishes RAM initialization, not flash damage or bricking.

## Known SpaceFn behavior

The user reports occasional delayed spaces appearing after the next character during fast typing. The exact execution cause and query-related change were not measured. This remains an input-order/tap-hold policy issue separate from the inspection correction. This release does not claim to fix it; lowering the threshold is not a guaranteed remedy.

## Upgrade

Extract rc4 into a separate folder, run Setup_Demo.bat and then Start_TopreRT_GUI.bat. Do not overwrite an existing output folder or virtual environment. No firmware flashing is needed for the inspection correction. Exact legacy TopreRT build versions remain unknown. RT/HOLD detection evidence does not authorize flashing.

rc3 tags/assets remain intact. Until upgrading the app, rc3 HOLD/SpaceFn users should avoid Inspect firmware. Progress-meter redesign and metadata firmware integration are not included.

## 한국어

HOLD 조회 시 동작 RAM을 초기화하던 명령을 snapshot 조회로 교체한 수정판입니다. PC 앱만 새 폴더에 받아 실행하면 되며, 이 수정을 적용하기 위해 키보드 펌웨어를 다시 설치할 필요는 없습니다. PD-KB800W 한 대의 RT 조회와 SpaceFn 250ms 설치·조회 후 동작을 사용자 확인으로 기록했습니다. 빠른 입력에서 공백이 다음 글자 뒤로 밀리는 현상은 별도 제한사항이며 이번 수정 대상이 아닙니다. 모든 기기·HOLD 설정의 검증이나 무고장 보장을 뜻하지 않습니다.
