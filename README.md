# TopreRT

**Rapid Trigger toolkit for REALFORCE R3S and HHKB Professional Hybrid / Hybrid Type-S**

TopreRT is an unofficial toolkit that adds **Rapid Trigger (RT)** behavior while preserving the stock Topre sensor/state-machine behavior as much as possible. It combines firmware generation, validation, live diagnostics, and recovery guidance in one project.

> [!WARNING]
> Custom firmware always carries a risk of boot failure or recovery work. Keep an exact stock firmware image for your device, use stable USB power, and never disconnect the keyboard or suspend/reboot the PC during an update.

> [!IMPORTANT]
> TopreRT is not affiliated with PFU Limited, REALFORCE, or HHKB. **Stock firmware and pre-patched firmware are not distributed in this repository.**

## Project status

| Device | Firmware | RT core | Observer / writer |
| --- | --- | --- | --- |
| REALFORCE R3SB | A0.12 | **Hardware verified** | **Hardware verified** |
| REALFORCE R3SA / R3SC / R3SD | A0.12 | Binary verified | Observer key map not hardware validated |
| HHKB Professional Hybrid / Hybrid Type-S PD-KB800W | A0.48 | **Hardware verified** | **Hardware verified** |

R3S exact stock SHA-256 values and model-specific validation details are documented in [`backends/r3s/SUPPORTED_FIRMWARE.md`](backends/r3s/SUPPORTED_FIRMWARE.md).

## Highlights

- All-key Rapid Trigger core
- Adjustable release / re-press distance
- Exact-image SHA-256 validation and fail-closed patching
- GUI validation plus independent backend validation
- R / E / W / A / S / D / SPACE live Observer
- R3S read-only C5 telemetry
- HHKB built-in writer with packet ACK and reconnect checks
- Output manifest generation
- Documented R3SB soft-recovery and STM32 ROM DFU recovery path

## Requirements

- Windows 10 / 11
- Python 3.10+
- Windows Python Launcher (`py`)
- `hidapi`
- Tkinter (included with normal Windows Python installations)

Install the Python dependency:

```powershell
py -m pip install -r requirements.txt
```

## Quick start

1. Clone or download this repository.
2. Double-click `Start_TopreRT_GUI.bat`, or run:

```powershell
py .\toprert_unified_gui.py
```

3. Select `REALFORCE R3S` or `HHKB Professional Hybrid`.
4. Select the **exact stock firmware** for your device. TopreRT does not trust the filename; the image must pass SHA-256 and structural validation.
5. Choose a preset or custom Release / Re-press values.
6. Build the validated output.

For REALFORCE R3S, use the **official REALFORCE Software** for normal firmware updating. TopreRT intentionally does not act as the general R3S flash writer.

For supported HHKB firmware, the built-in writer performs candidate revalidation, device-identity preflight, E0/E1/E2/E3 update sequencing, per-packet ACK checking, and reconnect verification.

## Stable profiles

### REALFORCE R3S

Current hardware-tested stable candidate:

```text
Release     = 306 raw (~0.60 mm)
Re-press    = 408 raw (~0.80 mm)
Non-Space   = two-pass DISARM64
Space #60   = NO-DISARM
Scope       = all keys
```

General keys have been hardware-tested for mid-stroke release/re-press and full-release re-entry without runaway input. Development records still contain a **rare Space missed-press candidate**, so this should not be described as completely eliminated.

### HHKB

| Profile | Release | Re-press | Raw |
| --- | ---: | ---: | ---: |
| Stable | ~0.10 mm | ~0.15 mm | 60 / 90 |
| Golden | ~0.053 mm | ~0.053 mm | 32 / 32 |

HHKB millimeter values are **estimated conversions** from the measured raw span; they do not imply a perfectly linear sensor across the entire stroke.

## Safety model

TopreRT rejects unsupported or malformed input rather than guessing. Validation includes exact source hashes, CRC/layout checks, patch whitelists, helper structure checks, and device/update checks where applicable.

The project follows these rules:

1. Preserve stock behavior where possible.
2. Never guess patches for unsupported firmware.
3. Validate again in the backend even if the GUI already passed.
4. Prefer official update paths where available.
5. Separate read-only telemetry from write operations.
6. Distinguish hardware-verified from binary-verified results.
7. Keep dangerous low-level recovery functions out of the normal user flow.
8. **Back up before writing during recovery.**
9. Distinguish observed behavior from reverse-engineering inference.

## Recovery

Do **not** assume that a keyboard missing from REALFORCE Software is hard-bricked. An R3SB soft-failure was recovered while its vendor HID interface was still alive by sending only the E0 `RebootForUpdate` command and then using the official updater.

The included helper defaults to read-only discovery:

```powershell
py .\recovery\r3s\r3sb_e0_probe.py
```

Only after confirming the enumerated target is the expected R3SB31 should `--send` be considered. The helper implements **E0 only**; it does not implement E1/E2/E3, flash erase, or firmware transfer.

If normal USB/HID enumeration is completely absent, see the R3SB-only ROM DFU documentation. **Do not mass-erase first. Read and back up the complete flash before any write.**

See **[R3S Recovery Guide](docs/RECOVERY_R3S.md)** for the full procedure and hardware warning.

## Documentation

- [R3S supported firmware](backends/r3s/SUPPORTED_FIRMWARE.md)
- [R3S Observer key map](backends/r3s/KEYMAP.md)
- [R3S recovery guide](docs/RECOVERY_R3S.md)
- [Technical notes](docs/TECHNICAL_NOTES.md)

## Repository layout

```text
TopreRT/
├─ README.md
├─ LICENSE
├─ requirements.txt
├─ Start_TopreRT_GUI.bat
├─ toprert_unified_gui.py
├─ backends/
│  ├─ r3s/
│  └─ hhkb/
├─ recovery/
│  └─ r3s/
│     └─ r3sb_e0_probe.py
├─ docs/
│  ├─ RECOVERY_R3S.md
│  ├─ TECHNICAL_NOTES.md
│  └─ assets/
│     └─ r3sb_rom_dfu_pins.png
└─ output/
```

## Stock firmware policy

Official stock firmware, generated TopreRT firmware, recovery application binaries, and device flash dumps are intentionally excluded from the repository. Users should supply their own exact stock image locally; TopreRT only proceeds when it matches the supported whitelist and structural checks.

## Known limitations

- R3S support is currently limited to the exact **A0.12 family**.
- R3SB is hardware verified; R3SA/R3SC/R3SD are binary verified only.
- R3SA/R3SC/R3SD Observer physical key maps are not yet hardware validated.
- A rare R3S Space missed-press candidate remains in development records.
- HHKB support is currently limited to **PD-KB800W A0.48**.
- HHKB millimeter values are estimated conversions.
- HHKB Mac DIP mode is not validated.
- The R3SB ROM DFU pin procedure must **not** be assumed valid for other R3S PCB layouts.

## License

TopreRT is released under the [MIT License](LICENSE).

## Disclaimer

TopreRT is unofficial custom-firmware tooling. Firmware modification can cause boot failure, repeated USB re-enumeration, loss of visibility in vendor software, updater-mode entry, or a need for low-level recovery. SHA/CRC/whitelist checks reduce risk but cannot guarantee that every failure mode is impossible.

**If in doubt, do not erase anything. Back up first.**
