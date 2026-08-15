# Supported firmware / recommended profiles

## REALFORCE R3S A0.12

현재 v0.4는 정확히 아래 원본 이미지만 지원합니다.

- Size: 65,568 bytes
- SHA-256: `7f475139d6585afa6c3079f0139ceb76f880b9718885bfd1e180d81ee08f531d`
- Inner CRC: `AC5E`
- Outer CRC: `970F`

SHA가 다르면 같은 A0.12처럼 보여도 패치하지 않습니다.

## Verified RT profiles

| Release | Re-press | Raw | Status |
|---|---|---:|---|
| 0.60 mm | 0.80 mm | 306 / 408 | Hardware verified, all-key stable candidate |
| 0.60 mm | 0.70 mm | 306 / 358 | Hardware verified, R-key transition |
| 0.50 mm | 0.70 mm | 256 / 358 | Hardware verified, R-key transition |

다른 허용 범위 설정은 구조적으로 생성할 수 있지만 `EXPERIMENTAL`로 표시합니다.


## v0.4.1 friendly preset names

- `stable` = 0.60 / 0.80 mm (306 / 408 raw) — Recommended
- `responsive` = 0.60 / 0.70 mm (306 / 358 raw)
- `fast-release` = 0.50 / 0.70 mm (256 / 358 raw)

Friendly names do not alter the RT implementation; they select existing hardware-tested values.


## Observer key mapping status

Toolkit v0.7 includes a partial, hardware-observed R3S key map:
W, E, R, A, S, D, and Space.

This is not a full inferred layout. Only directly measured mappings are exposed in the GUI.
