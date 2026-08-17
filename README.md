# TopreRT
**Rapid Trigger toolkit for REALFORCE R3S and HHKB Professional Hybrid / Hybrid Type-S**

TopreRT is an unofficial toolkit that adds **Rapid Trigger (RT)** behavior to Topre keyboards while preserving the stock sensor and state-machine behavior as closely as possible. It combines firmware generation, validation, live diagnostics, and recovery guidance into a single project.

> **Warning:** Custom firmware always carries a risk of boot failure or bricking. Keep an exact stock firmware image for your device, use a stable USB connection, and **never disconnect the keyboard or suspend/reboot your PC** during an update.

> **Important:** TopreRT is not affiliated with PFU Limited, REALFORCE, or HHKB. Stock firmware and pre-patched firmware binaries are **not** distributed in this repository.

---

## Project Status

| Device | Firmware | RT Core | Observer / Writer |
|---|---|---|---|
| **REALFORCE R3S** (R3SB) | A0.12 | Hardware verified | Hardware verified |
| **REALFORCE R3S** (R3SA / R3SC / R3SD) | A0.12 | Binary verified | Observer key map not hardware validated |
| **HHKB Professional Hybrid / Hybrid Type-S** (PD-KB800W) | A0.48 | Hardware verified | Hardware verified |

*Exact stock SHA-256 values and model-specific validation details for the R3S are documented in [`backends/r3s/SUPPORTED_FIRMWARE.md`](backends/r3s/SUPPORTED_FIRMWARE.md).*

---

## Highlights

* **All-key Rapid Trigger core** with adjustable release and re-press distances.
* **Exact-image SHA-256 validation** and fail-closed patching logic.
* **Dual-layer validation:** GUI-level checks backed by independent backend validation.
* **Live Observer interface** for real-time key testing (`WASD`, `Space`, `R`, `E`).
* **Read-only C5 telemetry** for REALFORCE R3S.
* **Built-in HHKB flash writer** with packet ACK verification and reconnect checks.
* **Automated output manifest generation.**
* **Documented recovery paths:** Soft-recovery guidance and STM32 ROM DFU hardware recovery for R3SB.

---

## Requirements

* **OS:** Windows 10 / 11
* **Python:** 3.10+ (with Windows Python Launcher `py`)
* **Libraries:** `hidapi`, `Tkinter` (included with standard Windows Python installers)

Install dependencies using:

```powershell
py -m pip install -r requirements.txt
```
## Quick start

1. Clone or download this repository.
2. Launch the application by double-clicking `Start_TopreRT_GUI.bat`, or running:

```powershell
py .\toprert_unified_gui.py
```

3. Select your device model `REALFORCE R3S` or `HHKB Professional Hybrid`.
4. Select your **exact stock firmware file**. (TopreRT verifies the file using SHA-256 and structural analysis rather than relying on the filename).
5. Select a preset or set custom Release / Re-press threshold values.
6. Build the validated output firmware.
7. Flashing your device:

    REALFORCE R3S: Use the **official REALFORCE Software** to flash the built image. TopreRT does not act as a flasher for R3S devices.

    HHKB: Use the built-in TopreRT writer, which performs candidate revalidation, device-identity preflight, `E0/E1/E2/E3` update sequencing, per-packet ACK checking, and reconnect verification.

## Stable Profiles

### REALFORCE R3S

Current hardware-tested stable candidate:

```text
Release     = 306 raw (~0.60 mm)
Re-press    = 408 raw (~0.80 mm)
Non-Space   = two-pass DISARM64
Space #60   = NO-DISARM
Scope       = all keys
```

General keys have been hardware-tested for mid-stroke release/re-press and full-release re-entry without runaway input. A rare Space bar missed-press candidate remains in development logs and is not yet completely eliminated.

### HHKB

| Profile | Release | Re-press | Raw |
| --- | ---: | ---: | ---: |
| Stable | ~0.10 mm | ~0.15 mm | 60 / 90 |
| Golden | ~0.053 mm | ~0.053 mm | 32 / 32 |

*Millimeter values are **estimated conversions** based on the measured raw span; they do not imply a perfectly linear sensor response across the entire key stroke.*

## Safety Model

TopreRT rejects unsupported or malformed inputs rather than attempting to guess patches. Safety mechanics include:

- Preserve stock behavior wherever possible.
- Never guess patches for unsupported firmware revisions.
- Re-validate in the backend even if the GUI check passed.
- Prefer official vendor update utility paths where available.
- Isolate telemetry: Keep read-only telemetry separate from flash writing operations.
- Strict verification states: Explicitly distinguish hardware-verified from binary-verified states.
- Protect recovery tools: Keep low-level recovery features out of standard user workflows.
- Mandatory backup: Read and back up existing flash memory before recovery writes.
- Factual reporting: Distinguish observed hardware behavior from reverse-engineering inferences.

## Recovery

If your keyboard is no longer recognized by vendor software (e.g., REALFORCE Software), it is not necessarily hard-bricked. An R3SB soft-failure state was successfully recovered while its vendor HID interface was still responsive by sending an `E0 RebootForUpdate` command and using the official vendor updater.

Run the read-only discovery tool first:

```powershell
py .\recovery\r3s\r3sb_e0_probe.py
```

  Caution: Only append the `--send` flag after confirming that the enumerated target matches your target `R3SB31`. This helper only issues the `E0` command—it does not implement `E1/E2/E3` flashing sequence steps or mass erase functions.

If USB/HID enumeration is completely absent, refer to the R3SB-only ROM DFU documentation from **[R3S Recovery Guide](docs/RECOVERY_R3S.md)** for STM32 ROM DFU pin recovery. **Do not perform a mass erase.** Always read and back up the full flash contents before writing.

## Documentation

- [R3S Supported Firmware Details](backends/r3s/SUPPORTED_FIRMWARE.md)
- [R3S Observer Key Map](backends/r3s/KEYMAP.md)
- [R3S Recovery Guide](docs/RECOVERY_R3S.md)
- [Technical Notes](docs/TECHNICAL_NOTES.md)

## Repository Layout

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

## Stock Firmware Policy

To comply with licensing and intellectual property standards: official stock firmware binaries, generated TopreRT firmware images, recovery binaries, and raw flash dumps are **strictly excluded** from this repository.

Users must supply their own stock firmware images locally. TopreRT will only process images that pass exact SHA-256 hash whitelisting and structural checks.

## Known Limitations

- R3S support: Currently limited strictly to the **A0.12** family.
- R3S Hardware verification: R3SB is fully hardware-verified. R3SA, R3SC, and R3SD variants are binary-verified only.
- R3S Observer maps: Physical key mapping for R3SA / R3SC / R3SD Observer modes is not yet hardware-validated.
- R3S Spacebar: A rare missed-press edge-case remains under investigation.
- HHKB support: Currently limited strictly to **PD-KB800W A0.48**.
- HHKB Measurement precision: Millimeter values are estimated approximations.
- HHKB macOS DIP switch mode: Not yet validated.
- R3SB ROM DFU: Pin placement procedures are specific to the R3SB PCB and must **not** be assumed valid for other R3S revisions.

## License

TopreRT is released under the [MIT License](LICENSE).

## Disclaimer

TopreRT is an open-source, unofficial firmware modification tool. Modifying keyboard firmware involves inherent risks, including boot loops, endless USB re-enumeration, loss of software detection, or bricking requiring hardware recovery. While SHA/CRC whitelisting and safety checks minimize these risks, they cannot guarantee immunity from failures.

**If you are uncertain about a step, do not erase your device and make a full backup first.**
