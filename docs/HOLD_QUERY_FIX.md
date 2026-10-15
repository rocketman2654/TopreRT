# HOLD inspection correction — unreleased

The rc3 Inspect firmware operation sends C1 A1 after common telemetry. Static analysis of the exact HHKB A0.48 Generic HOLD core shows that this request initializes 16 bytes at 0x20004FF0 also used by its HOLD state machine. This is a RAM side effect, not a flash write. No typing failure or flash corruption has been reproduced on hardware.

Until a reviewed correction is released, HOLD/SpaceFn users should avoid Inspect firmware in rc3. Device diagnostics is a separate identity operation. Updating the PC app for this correction does not require reflashing the keyboard.

This branch sends the existing C1 52 snapshot request instead, checks its operation marker and maximum length, and never falls back to A1 on transmit/receive failure. Firmware writers and patchers are unchanged. No metadata firmware implementation is included.

Static evidence: in the audited HOLD derivation, the wrapper at 0x0801EAD0 routes A1 through initialization stores at 0x0801EAEE..0x0801EAFE. Selector 52 enters at 0x0801EB04, skipping those stores. Core references at 0x0801EF08 and 0x0801EF28 use the same state RAM. This evidence is specific to that implementation, not every possible historical HOLD build.

Validation: 64 offline app tests passed locally on Windows/Python 3.12. Added cases cover transmit/receive failure without initialization fallback, stale A1/unknown markers and oversized snapshot replies. On 2026-10-15 the user confirmed the isolated candidate works with RT installed; a screenshot shows PD-KB800W, revision A3 and common RT telemetry. The earlier screenshot with zero HHKB interfaces was not a successful device test. No new firmware was installed for this RT check.

HOLD snapshot hardware validation remains pending. A same-device RT check is not HOLD verification. A future controlled trial should compare existing tap/hold behavior before and after inspection with Observer/official tools closed. Firmware installation requires a separate concrete plan. Keep rc3 tags/assets intact and publish any approved correction under a new version.

## 한국어 안내

rc3에서 HOLD/SpaceFn을 사용하는 분은 수정판 검토 전까지 Inspect firmware를 피해주세요. 기존 조회가 HOLD 동작에 사용하는 RAM을 초기화하는 경로를 확인했습니다. 플래시 손상이나 실제 입력 장애를 재현했다는 뜻은 아닙니다. 수정판은 초기화를 건너뛰는 snapshot 조회를 사용하고 실패 시 초기화 명령으로 재시도하지 않습니다. PC 앱 수정이며 펌웨어 재설치는 필요하지 않습니다. RT 상태의 조회는 사용자 확인을 받았고, HOLD 실기 검증은 아직 남아 있습니다.
