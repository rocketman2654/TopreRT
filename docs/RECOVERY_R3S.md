# REALFORCE R3S Recovery Guide


This section consolidates the recovery paths for the REALFORCE R3S, covering everything from **a normal stock rollback to soft failure and hard brick**.

The most important principle is:

> **Do not immediately assume a hard brick just because the keyboard has disappeared from REALFORCE Software.**

In an actually confirmed soft-failure case, REALFORCE Software could not detect the device, but the Windows HID vendor interface was still alive. Only after directly sending the E0 command did the keyboard re-enumerate with the B0.01 updater firmware, allowing the official software to recognize it again.

------------------------------------------------------------------------

## 12.1 Recovery Level 0 - Normal Rollback

If REALFORCE Software recognizes the keyboard normally, the first step is to reinstall the **exact stock A0.12** firmware using the official updater.

No hardware disassembly is required.

------------------------------------------------------------------------

## 12.2 Recovery Level 1 - Missing from REALFORCE Software but USB/HID Still Alive

This state ***should not automatically be considered a hard brick**.

The recovery helper actually confirmed on an R3SB was:

``` text
recovery\r3s\r3sb_e0_probe.py
```

Required package:

``` powershell
py -m pip install hidapi
```

First, **run read-only discovery**:

``` powershell
py .\r3sb_e0_probe.py
```

This mode does not send any USB commands.

The descriptor observed on an R3SB31 running the normal application was:

``` text
VID              0853
PID              0311
vendor interface 2
```

> IMPORTANT: `0853:0311` and interface `2` are not values arbitrarily assigned by Windows to this particular PC. The VID/PID and USB `bInterfaceNumber` are provided by the device firmware/USB descriptor, so they should generally remain the same for the same device family running the same firmware/configuration.
>
> In contrast, the HID `path` string, device instance path, physical port location, and similar values may vary depending on the PC, USB port, and enumeration state. These must therefore not be hard-coded in documentation or code.
>
> Also, you should not assume that other R3S models, different firmware modes, or B0.01 updater mode use the same PID/interface. The recovery helper should first display the actual enumeration results and should only permit E0 transmission when exactly one matching interface is found, following a fail-closed design.

In the actual R3SB31 capture, the vendor updater command was carried over `interface 2`, with OUT endpoint `0x04` and IN endpoint `0x83` observed at the time. The current helper uses the HIDAPI-enumerated path, so it does not hard-code the physical USB port number used by Windows.

### Forced E0 Entry

Only if the read-only discovery confirms that the device is your R3SB31, run:

``` powershell
py .\r3sb_e0_probe.py --send
```

The helper sends only one E0 RebootForUpdate command.

``` text
Request prefix:
AA AA E0 00 00 ...

Expected ACK prefix:
55 55 E0 00 00 ...
```

The helper does not implement any of the following:

-   E1 StartUpdate
-   E2 firmware chunks
-   E3 EndUpdate
-   flash erase
-   flash write
-   custom RFB transfer

In other words, the E0 helper itself is not a program that overwrites A0.12.

If a valid E0 ACK is received, the keyboard should disconnect and re-enumerate in updater mode.

In the actual soft-failure recovery, after this process the keyboard appeared in REALFORCE Software as:

``` text
FW Version B0.01
```

At that point, the official REALFORCE Software was used to reinstall the exact stock A0.12 firmware and normal operation was restored.

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

## 12.3 When to Suspect a Hard Brick

The following indicates a more serious condition:

-   The device is missing from REALFORCE Software
-   Normal R3S USB/HID enumeration does not occur in Windows
-   The E0 helper cannot find a vendor HID target to send the command to
-   The same behavior persists after rechecking the cable, USB port, and power

In this case, there is no USB endpoint available for application-level recovery commands, making it **a hard-brick candidate requiring STM32 ROM DFU recovery**.

> **WARNING!**: The procedure below was used as a last resort on an R3SB unit. The PCB layout and corresponding contact points for R3SA/R3SC/R3SD have not been verified. Do not short pins based on assumed locations on other models.

------------------------------------------------------------------------

## 12.4 Recovery Level 2 - STM32 ROM DFU

The MCU on the actual device was:

``` text
STM32L072RBT6
LQFP64
```
On the R3SB board, the location used to enter ROM DFU was **the 1st and 4th pins counted from the bottom on the left side of the MCU, as viewed in the photograph**.

If recovery photos are included in the repository:

``` markdown
![R3SB STM32 ROM DFU recovery pins](assets/r3sb_rom_dfu_pins.png)
```

![R3SB STM32 ROM DFU recovery pins](assets/r3sb_rom_dfu_pins.png)

The red highlighted area in the photograph is intended to show **the actual working area where accessing the exact two pins was difficult**.

> **CAUTION!**: Randomly shorting an entire group of nearby pins is not a recommended procedure. During the actual recovery, there was some trial and error due to the narrow pitch, including accidental contact with surrounding pads. However, the goal of the documented procedure is to contact only the exact pins 1 and 4 on the lower-left side as precisely as possible. Shorting the wrong pins may cause additional damage to the MCU or board.

Historical records show that Windows USB disconnect/reconnect changes were observed during the hardware intervention, after which STM32 ROM DFU became accessible.

------------------------------------------------------------------------

## 12.5 First Step After Entering ROM DFU: Back Up the Entire Flash

**Do not immediately erase or write anything.**

During the actual recovery, the entire **128 KiB flash** of the STM32L072RBT6 was first read and backed up.
Repeated dumps were then compared to confirm that their SHA-256 hashes matched.

The SHA-256 of the matching dumps was:

``` text
588CD32B79CAC0D318A3CD9182B71F7C0C6778C2193F030F80515874B49AD020
```

This value is an identification hash for the dump obtained from that particular physical device. It does **not** mean that every R3S must have this universal stock hash.

Basic recovery principle:

``` text
1. Confirm DFU mode
2. READ the entire flash
3. Preserve the backup file
4. Repeat the dump if possible
5. Compare the dump hashes
6. Only then consider application recovery
```

------------------------------------------------------------------------

## 12.6 A0.12 application recovery

During the actual recovery, a 64 KiB application payload was extracted from the stock RFB.

Recorded file:

``` text
R3SB_A012_RECOVERY_08010000.bin
```

Recorded application load address:

``` text
0x08010000
```

Recorded recovery payload SHA-256:

``` text
58b52fe0e63a2d0c1e724dc21b9304d4eee6c6298fb8e4cce8bad3f704124291
```

The STM32CubeProgrammer CLI write command prepared at the time was:

``` powershell
STM32_Programmer_CLI.exe -c port=USB1 -w ".\R3SB_A012_RECOVERY_08010000.bin" 0x08010000 -v
```

> **DANGER!**: **Do not use Mass Erase as the default recovery procedure.** The actual recovery preserved the entire flash first and then wrote only the necessary application image to the confirmed application region at `0x08010000`. Avoiding unnecessary erasure of the boot/recovery region is critical.

The following were definitively confirmed in the preserved recovery records:

-   ROM DFU entry
-   Full 128 KiB flash backup
-   Verification of repeated dump hashes
-   Extraction of the 64 KiB recovery application
-   Confirmation of the `0x08010000` load address
-   Verification of the recovery image hash
-   The same keyboard subsequently returned to a state where stock rollback and TopreRT hardware testing could be performed

The exact final verification message from STM32CubeProgrammer was not preserved, so the documentation does not fabricate or reconstruct it.

### Recovery Golden Rule

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

## USB Identification Notes

This is one of the easiest parts of the recovery process to misunderstand.

### Values Generally Defined by the Device

-   USB VID
-   USB PID
-   USB interface descriptor `bInterfaceNumber`
-   Usage Page / Usage
-   Endpoint Descriptor

Therefore, the following values observed on an R3SB31 running A0.12:

``` text
VID 0853
PID 0311
interface 2
```

should not be treated simply as numbers that were randomly assigned by the PC.

### Values That May Vary Between PCs

-   HID device path
-   Windows device instance path
-   USB hub/port topology
-   Enumeration Order
-   HIDAPI array ordering

Therefore, the recovery tool should not permanently hard-code `[0]`, `[1]`, or a specific `path` string based on enumeration order.

The current E0 probe enumerates devices by VID/PID, checks the `interface_number`, and only permits `--send` when exactly one matching interface is found.

For a future public release, it would be preferable to additionally verify:

-   manufacturer = `Topre`
-   product/model signature
-   a model field from a read-only DeviceInfo response, if available
-   a signature that can distinguish normal application mode from updater mode

------------------------------------------------------------------------
