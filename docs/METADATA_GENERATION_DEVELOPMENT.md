# HHKB 식별 정보 자동 생성과 버전별 카탈로그 — Development

2026-10-17. 개발 GUI의 RT/HOLD 생성 경로에 식별 정보를 연결했다. 실제 키보드에는
추가로 쓰지 않았다. 공개 rc3/rc4·D 저장소와 앞서 실기 확인한 후보는 그대로다.

## 생성과 검증

- 정확한 순정 A0.48에서 기존 RT 또는 HOLD 생성기로 기본 이미지를 만든다.
- 검증된 metadata hook/text/unwind를 같은 위치에 넣고 불변 descriptor만 새 ID로
  구성한다. metadata 영역196바이트, 추가 고정 RAM0바이트다.
- 같은 소스 바이트와 설정이면 같은 recipe/ID/이미지가 나온다. RT raw 값이나 HOLD
  슬롯/임계값, 생성 소스가 바뀌면 ID가 달라진다. 실행 중 소스가 바뀌면 재시작을 요구한다.
- metadata 섹션과 CRC 외 변경을 거부하고 파일·manifest를 저장한 뒤 새로 재빌드한다.
  HOLD 설치용 별도 helper도 정확한 SHA/token·manifest·원본에서 재생성한 결과를
  검사한 다음 기존 guarded HOLD 전송 함수를 호출한다. 기존 flasher validator를
  느슨하게 만들지 않았다. RT도 전송 직전에 새 validator를 다시 호출한다.
- RT는 생성 파일과 ID를 먼저 준비하고 확인 뒤 설치한다. 취소해도 생성 파일/기록은
  남지만 설치 이력은 생기지 않는다. HOLD는 기존 두 단계 생성/설치 방식을 유지한다.

## 카탈로그 배포 정책

`firmware_identity/catalogs/<catalog-version>/`에 build catalog, 설정 기록과 체크섬
manifest를 함께 보존한다. 현재 선택한 개발 스냅샷은 **development-20261017-3**다.
앞선1/2 스냅샷과 ZIP은 덮어쓰지 않았다. 앞으로 공개 릴리즈는 검토한 소스/버전의
카탈로그 스냅샷을 ZIP에 함께 넣고 버전/체크섬을 고정해야 한다. 현재 스냅샷은
Development이며 공개 릴리즈 번호가 아니다.

사용자 커스텀 생성 기록은 `output/identity/builds/<recipe SHA>.json`에 따로 저장한다.
공식/개발 기본 카탈로그를 수정하지 않고 조회 시 합친 snapshot을 사용한다. ID가
충돌하거나 기록이 손상되면 이전 항목을 덮어쓰거나 추측하지 않는다. 생성 HFB의
`.manifest.json`은 설정과 recipe를 포함하므로 파일과 함께 보관한다. 다른 PC에서는
해당 카탈로그 또는 생성 기록이 필요하다. 기록이 없으면 미등록 ID로 표시한다.

## RT 설정 표시

예: `Build recipe settings (not read back): Release R60 (~0.100 mm) /
Re-press P90 (~0.150 mm)`.

기기가 보고한 ID를 카탈로그/생성 recipe와 연결한 설정이다. 키보드의 설정 메모리나
실제 작동 거리를 직접 읽어온 값은 아니며 mm는 기존 추정 환산값이다. 최초 입력
지점을 따로 조절/조회하는 기능은 추가하지 않았다. 편집 중인 GUI 프로필을 설치
상태라고 사용하지 않고, 빌드 기록을 찾지 못하면 설정을 표시하지 않는다.

## 확인된 범위

2026-10-18 추가 실기: GUI 생성 SpaceFn **A96B4BA0**(Space tap/Fn hold250ms,
1슬롯)도 사용자가 설치했다. 화면에서 FLASH PASS·일반 재연결·HOLD 계열/ID·catalog
일치를 확인했고 사용자가 일반 입력과 SpaceFn 정상 동작을 확인했다. 로컬 HFB SHA는
생성 manifest와 일치한다. 별도 `docs/validation/gui_generated_hold_spacefn_user_validation_20261018.json`에
기록했다. 다른 HOLD 설정/공식 앱 확인이나 기존 공백 순서 문제 해결을 뜻하지 않는다.

2026-10-18 후속 실기: 사용자가 GUI 생성 Golden RT **B33E6ADF**(R32/P32)를 설치했다.
화면에서 전송 완료·Reconnect PASS·카탈로그/로컬 기록 일치·설정 표시를 확인했고,
사용자가 일반 입력과 Observer도 정상이라고 확인했다. 로컬 HFB SHA는 생성 manifest와
일치한다. 이는 해당 기기/빌드의 사용자 실기 결과이며 새 기본 RT/HOLD 파일 전체의
검증으로 확대하지 않는다. 원 생성 manifest와 catalog snapshot은 바꾸지 않고 별도
`docs/validation/gui_generated_rt_golden_user_validation_20261018.json`에 기록했다.
이번 빌드의 공식 앱 인식이나 실제 작동 거리 측정은 보고되지 않았다.

앱147개 검사 통과(최종47.176초). 실제 입력 파일에서 RT/HOLD 생성·재현, 독립 CRC,
CRC를 다시 맞춘 코드/descriptor/정렬/tail/설정 변조 거절, ID 충돌/기록 손상,
버전 snapshot checksum, standalone helper dry run, 실제 Tk 생성 callback과 취소,
정확한 token/--flash 조건 뒤의 모의 전송 연결을 포함한다. 실제 USB는 열지 않았다.

현재 기본 생성 ID는 RT R60/P90 **81B8EDEB**, SpaceFn250ms **A96B4BA0**다.
이 중 HOLD A96B4BA0는 위 사용자 실기 범위가 확인됐고 RT 81B8EDEB는 아직 실기하지 않았다.
앞선 BA90567B/ECC9B8A2와 같은 기본 설정에서
차이가 CRC와 metadata descriptor뿐인지 별도로 대조했으며 실행 코드는 같다.
이 코드 대조 자체는 실기 성공·전체 이미지 readback/진위·중단 복구 증명이 아니다.
