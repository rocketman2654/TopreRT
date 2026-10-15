# Supported R3S stock firmware

The current app accepts these exact original A0.12 images (65,568 bytes each). Version labels alone are insufficient; the application checks the hash and model tag.

| Model | Original SHA-256 | Validation scope |
|---|---|---|
| R3SA | `45be872b38e66f1974dcc0018e654c6c828936a807e819a988e898f2d853a64d` | BINARY VERIFIED; Observer: NOT HARDWARE VALIDATED |
| R3SB | `7f475139d6585afa6c3079f0139ceb76f880b9718885bfd1e180d81ee08f531d` | HARDWARE VERIFIED; Observer: HARDWARE VERIFIED |
| R3SC | `90e0ec8edd3eba758ff0785ddeee52fafa4fb95bb7466cce22ebc40a848b07e3` | BINARY VERIFIED; Observer: NOT HARDWARE VALIDATED |
| R3SD | `5025fceec277fc001721cee9a7ed8891d9a7f4e4797d2412b4382be2be76da40` | BINARY VERIFIED; Observer: NOT HARDWARE VALIDATED |

TopreRT creates an output `.rfb`; install that generated file through official REALFORCE software. Historical toolkit version numbers below describe backend history, not the current GUI release.

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
