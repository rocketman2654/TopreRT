# REALFORCE R3S Recovery Guide


이 절은 **정상적인 stock rollback부터 soft failure, hard brick까지**의
복구 경로를 한곳에 정리합니다.

가장 중요한 원칙:

> **REALFORCE Software에서 키보드가 사라졌다는 이유만으로 즉시 hard
> brick으로 판정하지 마세요.**

실제로 확인된 soft failure에서는 REALFORCE Software가 장치를 찾지
못했지만 Windows HID vendor interface는 살아 있었고, E0 명령을 직접
전송한 뒤에야 B0.01 updater firmware로 재열거되어 공식 앱에서 다시
인식되었습니다.

------------------------------------------------------------------------

## 12.1 Recovery Level 0 - 정상 rollback

REALFORCE Software가 키보드를 정상 인식한다면 가장 먼저 공식 updater로
exact stock A0.12를 다시 설치합니다.

하드웨어 분해는 필요하지 않습니다.

------------------------------------------------------------------------

## 12.2 Recovery Level 1 - REALFORCE Software에서는 사라졌지만 USB/HID는 살아 있음

이 상태는 **hard brick이라고 단정할 수 없습니다.**

R3SB에서 실제로 확인된 recovery helper:

``` text
recovery\r3s\r3sb_e0_probe.py
```

필요 패키지:

``` powershell
py -m pip install hidapi
```

먼저 **read-only discovery**만 실행합니다.

``` powershell
py .\r3sb_e0_probe.py
```

이 모드에서는 USB 명령을 보내지 않습니다.

실험한 R3SB31의 normal application에서 관찰된 descriptor는:

``` text
VID              0853
PID              0311
vendor interface 2
```

였습니다.

> \[!IMPORTANT\] `0853:0311`, interface `2`는 **Windows가 임의로 이
> PC에만 부여한 장치 경로가 아닙니다.** VID/PID와 USB
> `bInterfaceNumber`는 장치 firmware/USB descriptor에서 제공되는
> 값이므로 같은 firmware/configuration의 같은 장치 계열에서는 일반적으로
> 동일해야 합니다.
>
> 반대로 HID `path` 문자열, 장치 인스턴스 경로, 포트 위치 등은 PC/USB
> 포트/열거 시점에 따라 달라질 수 있으므로 문서나 코드에서 고정값으로
> 사용하면 안 됩니다.
>
> 또한 다른 R3S 모델, 다른 firmware mode, B0.01 updater mode까지 동일
> PID/interface를 사용한다고 **추정해서는 안 됩니다.** Recovery helper는
> 실제 enumerate 결과를 먼저 보여주고, 예상 interface가 정확히 하나일
> 때만 E0 전송을 허용하는 fail-closed 방식으로 사용해야 합니다.

실제 R3SB31 capture에서 vendor updater command를 운반한 interface는
`interface 2`였으며, 당시 endpoint는 OUT `0x04`, IN `0x83`으로
관찰되었습니다. 현재 helper는 HIDAPI의 enumerated path를 사용하므로
Windows의 물리 USB 포트 번호를 하드코딩하지 않습니다.

### E0 강제 진입

read-only discovery에서 자신의 R3SB31임을 확인한 경우에만:

``` powershell
py .\r3sb_e0_probe.py --send
```

를 사용합니다.

helper가 보내는 것은 **E0 RebootForUpdate 한 개뿐**입니다.

``` text
Request prefix:
AA AA E0 00 00 ...

Expected ACK prefix:
55 55 E0 00 00 ...
```

이 helper에는 다음이 구현되어 있지 않습니다.

-   E1 StartUpdate
-   E2 firmware chunks
-   E3 EndUpdate
-   flash erase
-   flash write
-   custom RFB transfer

즉 E0 helper 자체가 A0.12를 덮어쓰는 프로그램은 아닙니다.

정상적인 E0 ACK가 오면 키보드는 disconnect 후 updater mode로
re-enumerate되어야 합니다.

실제 soft-failure 복구에서는 이 과정을 거친 뒤 REALFORCE Software에서:

``` text
FW Version B0.01
```

로 다시 장치가 나타났습니다.

그 상태에서 공식 REALFORCE Software를 이용해 exact stock **A0.12**를
다시 설치하고 정상 복귀를 확인했습니다.

``` text
A0.12 application failure
        ↓
REALFORCE Software: device missing
        ↓
USB/HID vendor interface still alive
        ↓
E0 RebootForUpdate
        ↓
matching E0 ACK
        ↓
disconnect / re-enumerate
        ↓
B0.01 updater firmware
        ↓
REALFORCE Software sees keyboard again
        ↓
install exact stock A0.12
        ↓
normal operation
```

------------------------------------------------------------------------

## 12.3 언제 Hard Brick으로 의심할 것인가

다음은 더 심각한 상태입니다.

-   REALFORCE Software에서 장치가 없음
-   Windows에서 정상 R3S USB/HID enumeration 자체가 없음
-   E0 helper가 명령을 보낼 vendor HID target을 찾지 못함
-   케이블/포트/전원 재확인 후에도 동일

이 경우 application-level recovery 명령을 보낼 USB endpoint 자체가
없으므로 **STM32 ROM DFU recovery가 필요한 hard-brick 후보**입니다.

> \[!WARNING\] 아래 절차는 R3SB 실기에서 사용한 최후 수단입니다.
> R3SA/R3SC/R3SD의 PCB layout 및 동일 접점은 아직 검증되지 않았습니다.
> 다른 모델에서 위치를 추정해 쇼트하지 마세요.

------------------------------------------------------------------------

## 12.4 Recovery Level 2 - STM32 ROM DFU

실기 대상 MCU:

``` text
STM32L072RBT6
LQFP64
```

R3SB 보드에서 ROM DFU 진입에 사용한 위치는 **사진 기준 MCU 왼쪽 변의
아래쪽에서 세었을 때 1번째 핀과 4번째 핀**입니다.

Repository에 recovery 사진을 넣는 경우:

``` markdown
![R3SB STM32 ROM DFU recovery pins](docs/assets/r3sb_rom_dfu_pins.png)
```

![R3SB STM32 ROM DFU recovery pins](docs/assets/r3sb_rom_dfu_pins.png)

사진의 빨간 표시 영역은 **정확한 두 핀에 접근하기 어려웠던 실제 작업
영역을 표시하기 위한 것**입니다.

> \[!CAUTION\] 주변 핀 전체를 무작정 단락하는 것은 권장 절차가 아닙니다.
> 실제 복구에서는 좁은 pitch 때문에 드라이버로 주변 접점까지 함께
> 접촉하는 시행착오가 있었지만, 공개 절차의 목표는 가능한 한 **왼쪽 아래
> 1번/4번 대상 핀만 정확히 접촉**하는 것입니다. 잘못된 핀을 단락하면
> MCU나 보드에 추가 손상을 줄 수 있습니다.

과거 기록에서는 이 hardware intervention 과정에서 Windows USB
disconnect/reconnect 변화가 관찰되었고, 이후 STM32 ROM DFU에 접근할 수
있었습니다.

------------------------------------------------------------------------

## 12.5 ROM DFU 진입 후 가장 먼저 할 일: 전체 flash 백업

**바로 erase/write하지 마세요.**

실제 복구에서는 먼저 STM32L072RBT6의 전체 128 KiB flash를 읽어 백업했고,
반복 dump SHA-256이 동일한지 확인했습니다.

기록된 동일 dump SHA-256:

``` text
588CD32B79CAC0D318A3CD9182B71F7C0C6778C2193F030F80515874B49AD020
```

이 값은 당시 해당 실기에서 얻은 dump 식별값이지, 모든 R3S에서 반드시
같아야 하는 universal stock hash라는 의미는 아닙니다.

복구 기본 원칙:

``` text
1. DFU 진입 확인
2. 전체 flash READ
3. 백업 파일 보존
4. 가능하면 반복 dump
5. dump hash 비교
6. 그 다음에만 application recovery 검토
```

------------------------------------------------------------------------

## 12.6 A0.12 application recovery

실제 복구에서는 순정 RFB에서 64 KiB application payload를 추출했습니다.

기록된 파일:

``` text
R3SB_A012_RECOVERY_08010000.bin
```

기록된 application load address:

``` text
0x08010000
```

기록된 recovery payload SHA-256:

``` text
58b52fe0e63a2d0c1e724dc21b9304d4eee6c6298fb8e4cce8bad3f704124291
```

당시 준비한 STM32CubeProgrammer CLI write 형태:

``` powershell
STM32_Programmer_CLI.exe -c port=USB1 -w ".\R3SB_A012_RECOVERY_08010000.bin" 0x08010000 -v
```

> \[!DANGER\] **Mass erase를 기본 복구 절차로 사용하지 마세요.** 실제
> 복구는 전체 flash를 먼저 보존한 뒤, 확인된 application 영역
> `0x08010000`에 필요한 application image만 기록하는 방향으로
> 진행했습니다. boot/recovery 영역을 불필요하게 지우지 않는 것이
> 핵심입니다.

당시 보존 기록에서 확실하게 확인되는 것은:

-   ROM DFU 진입
-   128 KiB 전체 flash backup
-   반복 dump hash 확인
-   64 KiB recovery application 추출
-   `0x08010000` load address 확인
-   recovery image hash 확인
-   이후 동일 키보드가 다시 stock rollback과 TopreRT 실기 테스트를
    수행할 수 있는 상태로 복귀

입니다.

당시 STM32CubeProgrammer의 최종 verify 콘솔 문구 자체는 보존되어 있지
않으므로 문서에서 임의로 재현하지 않습니다.

### Recovery golden rule

``` text
READ & BACK UP FIRST
        ↓
VERIFY SOURCE / TARGET HASHES
        ↓
WRITE ONLY THE CONFIRMED APPLICATION REGION
        ↓
VERIFY
        ↓
CHECK NORMAL USB/HID ENUMERATION
```

------------------------------------------------------------------------

## USB identification notes USB 식별값에 대한 주의

Recovery code에서 가장 혼동하기 쉬운 부분입니다.

### 일반적으로 장치 쪽에서 정해지는 값

-   USB VID
-   USB PID
-   USB interface descriptor의 `bInterfaceNumber`
-   usage page / usage
-   endpoint descriptor

따라서 R3SB31 A0.12에서 관찰한:

``` text
VID 0853
PID 0311
interface 2
```

는 단순히 "이 PC가 우연히 준 번호"로 보기는 어렵습니다.

### PC마다 달라질 수 있는 값

-   HID device path
-   Windows device instance path
-   USB hub/port topology
-   열거 순서
-   HIDAPI가 반환하는 배열 순서

따라서 recovery tool은 `[0]`, `[1]` 같은 enumerate 순서나 특정 `path`
문자열을 영구적으로 하드코딩해서는 안 됩니다.

현재 E0 probe는 VID/PID로 enumerate한 뒤 `interface_number`를 확인하고,
해당 interface가 **정확히 하나**일 때만 `--send`를 허용합니다.

향후 공개판에서는 가능하면 추가로 다음을 함께 검증하는 것이 좋습니다.

-   manufacturer = `Topre`
-   product/model signature
-   read-only DeviceInfo response가 가능한 경우 model field
-   normal app / updater mode를 서로 구분할 수 있는 signature

------------------------------------------------------------------------
