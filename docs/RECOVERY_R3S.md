# REALFORCE R3S Recovery Guide

This section consolidates the recovery paths for the REALFORCE R3S, covering everything from a normal stock rollback to soft failure and hard brick.

> **Core Principle:** Do not immediately assume a hard brick just because the keyboard has disappeared from REALFORCE Software.

In an actual confirmed soft-failure case, REALFORCE Software could not detect the device, but the Windows HID vendor interface was still alive. Only after directly sending the `E0` command did the keyboard re-enumerate with the `B0.01` updater firmware, allowing the official software to recognize it again.

---

## 12.1 Recovery Level 0 - Normal Rollback

If REALFORCE Software recognizes the keyboard normally, the first step is to reinstall the exact stock `A0.12` firmware using the official updater. No hardware disassembly is required.

---

## 12.2 Recovery Level 1 - Missing from REALFORCE Software but USB/HID Still Alive

This state **should not automatically be considered a hard brick**.

The recovery helper path confirmed on an R3SB is:
```text
recovery\r3s\r3sb_e0_probe.py
```

## Requirements

Install the required dependency:

``` powershell
py -m pip install hidapi
```

## Read-Only Discovery

First, **run read-only discovery**:

``` powershell
py .\r3sb_e0_probe.py
```

*This mode does not send any USB commands.*

The descriptor observed on an `R3SB31` running the normal application was:

- VID: `0853`
- PID: `0311`
- Vendor Interface: `2`


> IMPORTANT: `0853:0311` and interface `2` re provided directly by the device firmware/USB descriptor. They generally remain identical across the same device family running the same firmware configuration.
> 
> Conversely, the HID `path` string, device instance path, and physical port location depend on the host PC and must not be hard-coded.
>
> Do not assume that other R3S models, different firmware modes, or `B0.01` updater mode use the same PID/interface. Following a fail-closed design, the recovery helper displays the actual enumeration results and only permits `E0` transmission when exactly one matching interface is found.

In the captured `R3SB31` session, the vendor updater command was carried over `interface 2` (OUT endpoint `0x04`, IN endpoint `0x83`). The helper uses the HIDAPI-enumerated path to avoid hard-coding Windows physical port paths.

### Forced E0 Entry

Only after confirming that the enumerated device matches your target `R3SB31`, run:

``` powershell
py .\r3sb_e0_probe.py --send
```

The helper sends a single `E0 RebootForUpdate` command:

``` text
Request prefix:
AA AA E0 00 00 ...

Expected ACK prefix:
55 55 E0 00 00 ...
```

The helper intentionally does not implement:

-   E1 StartUpdate
-   E2 firmware chunks
-   E3 EndUpdate
-   Flash erase / write operations
-   Custom RFB transfers

*(The E0 helper itself does not overwrite A0.12.)*

If a valid `E0` ACK is received, the keyboard will disconnect and re-enumerate in updater mode.

In the soft-failure test case, the keyboard subsequently appeared in REALFORCE Software as:

``` text
FW Version B0.01
```

At that point, the official REALFORCE Software was used to reinstall the exact stock `A0.12` firmware, restoring normal operation.

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

A hard brick should only be suspected if:

-   The device is missing from REALFORCE Software.
-   Normal R3S USB/HID enumeration does not occur in Windows.
-   The `E0` helper cannot locate a vendor HID target.
-   The issue persists after checking cables, ports, and power.

In this state, no application-level USB endpoints are available, requiring **STM32 ROM DFU hardware recovery**.

> **WARNING!**: The procedure below was used as a last resort on an **R3SB** unit. PCB layouts and contact points for R3SA / R3SC / R3SD have not been verified. Do not short pins based on assumed locations on other models.

------------------------------------------------------------------------

## 12.4 Recovery Level 2 - STM32 ROM DFU

Hardware Specs

- MCU: `STM32L072RBT6`
- Package: `LQFP64`

In the R3SB board, ROM DFU was entered by shorting the **1st and 4th pins** counted from the bottom on the left side of the MCU (as viewed in the photograph below):

``` markdown
![R3SB STM32 ROM DFU recovery pins](assets/r3sb_rom_dfu_pins.png)
```

![R3SB STM32 ROM DFU recovery pins](assets/r3sb_rom_dfu_pins.png)

*(The red highlighted area highlights the narrow working zone where targeting the exact two pins requires precision.)*

> **CAUTION!**: Randomly shorting surrounding pins is extremely risky and can damage the MCU or PCB. Target only pins 1 and 4 on the lower-left side.

Once successfully shorted during USB insertion, Windows enumeration will change, exposing the STM32 ROM DFU interface.

------------------------------------------------------------------------

## 12.5 First Step in DFU Mode: Back Up Flash

**Do not immediately erase or flash the board.**

1. Read and back up the full 128 KiB flash from the `STM32L072RBT6`.
2. Perform repeated dumps and compare their SHA-256 hashes to verify image integrity.

The expected identification SHA-256 hash for the matching hardware dump in this test was:

``` text
588CD32B79CAC0D318A3CD9182B71F7C0C6778C2193F030F80515874B49AD020
```

*(Note: This hash is specific to the test device dump and is not a universal stock value).*

### General Protocol

``` text
1. Confirm DFU mode
2. READ entire flash
3. Preserve backup file
4. Repeat dump
5. Compare dump hashes
6. Proceed to application recovery
```

------------------------------------------------------------------------

## 12.6 A0.12 Application Recovery

During hardware recovery, a 64 KiB application payload was extracted from the stock RFB file:

- Payload file: `R3SB_A012_RECOVERY_08010000.bin`
- Target Load Address: `0x08010000`
- Recovery Payload SHA-256: `58b52fe0e63a2d0c1e724dc21b9304d4eee6c6298fb8e4cce8bad3f704124291`

The CLI write command used via STM32CubeProgrammer:

``` powershell
STM32_Programmer_CLI.exe -c port=USB1 -w ".\R3SB_A012_RECOVERY_08010000.bin" 0x08010000 -v
```

> **DANGER!**: **8Do not use Mass Erase**. Always preserve the boot/recovery region and write exclusively to the confirmed application region at `0x08010000`.

The following were definitively confirmed in the preserved recovery records:

-   ROM DFU entry
-   Full 128 KiB flash backup
-   Verification of repeated dump hashes
-   Extraction of the 64 KiB recovery application
-   Confirmation of the `0x08010000` load address
-   Verification of the recovery image hash
-   The same keyboard subsequently returned to a state where stock rollback and TopreRT hardware testing could be performed

The exact final verification message from STM32CubeProgrammer was not preserved, so the documentation does not fabricate or reconstruct it.

### Recovery Summary

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

### Fixed Device Attributes

These parameters are defined by device firmware and descriptors:

-   USB VID (`0853`)
-   USB PID (`0311`)
-   USB interface descriptor `bInterfaceNumber`(`2`)
-   Usage Page / Usage
-   Endpoint Descriptors

### Host-Dependent Attributes

These parameters vary per host system and configuration:

-   HID device path
-   Windows device instance path
-   USB hub/port topology
-   Enumeration order & HIDAPI array order

The recovery tool avoids hard-coding index positions (e.g., `[0]`) or fixed OS paths. It filters dynamically by VID/PID and interface number before executing commands.

For a future public release, it would be preferable to additionally verify:

-   manufacturer = `Topre`
-   product/model signature
-   a model field from a read-only DeviceInfo response, if available
-   a signature that can distinguish normal application mode from updater mode

------------------------------------------------------------------------
