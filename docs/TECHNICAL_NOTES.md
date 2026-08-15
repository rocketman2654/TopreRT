# Technical Notes


R3S 연구에서는 key별 `base`, `cur`, `delta`, calibration 관련 값과 여러
stock threshold가 관찰되었고, `delta`가 키 이동에 따라 연속적으로
변화하는 것을 확인했습니다.

RT 구현은 stock state machine을 통째로 교체하지 않고 runtime anchor를
이용해 최근 이동 방향의 극점으로부터 상대 이동량을 판정하는 방식으로
구성했습니다.

R3S에서 최초 RT 성공 후 민감도와 stale-anchor 문제를 단계적으로
다듬었고, 현재 안정판 후보는:

``` text
Release 0.60 mm / Re-press 0.80 mm
Non-Space two-pass DISARM64
Space NO-DISARM
```

입니다.

HHKB에서도 별도의 telemetry와 runtime state를 이용해 mid-stroke RT가
성립함을 실제 하드웨어에서 확인했습니다.

------------------------------------------------------------------------

## 20. 개발 철학

1.  **Stock behavior를 가능한 한 보존한다.**
2.  지원하지 않는 firmware는 추측해서 패치하지 않는다.
3.  GUI가 실수해도 backend가 다시 차단한다.
4.  공식 update 경로를 사용할 수 있으면 공식 경로를 우선한다.
5.  특정 GUI 버전이 없으면 firmware를 사용할 수 없는 구조를 피한다.
6.  Read-only telemetry와 실제 write 동작을 명확히 분리한다.
7.  Hardware-verified와 binary-verified를 구분한다.
8.  Recovery path는 준비하되 위험한 low-level 기능을 일반 사용자 UI에
    무분별하게 노출하지 않는다.
9.  복구에서는 **write보다 backup이 먼저**다.
10. 관찰한 사실과 내부 구조에 대한 추정을 문서에서 구분한다.

------------------------------------------------------------------------
