# TopreRT

**TopreRT v0.3.0-rc6 — prerelease.** Previous rc3/rc4/rc5 tags and assets remain unchanged.
**Rapid Trigger toolkit for REALFORCE R3S and HHKB Professional Hybrid / Hybrid Type-S**

TopreRT is an unofficial Windows toolkit for creating Rapid Trigger firmware for supported REALFORCE R3S and HHKB keyboards. It validates user-supplied stock firmware, provides an interface for configuring RT or HHKB HOLD/SpaceFn, and includes a live sensor Observer. **R3S files are installed through official REALFORCE software; HHKB firmware is installed by the updater inside TopreRT.**

[한국어 사용 설명서](docs/USER_GUIDE_KO.md) · [Project introduction / 소개 문구](docs/PROJECT_INTRO.md)

> **Warning:** Custom firmware always carries a risk of boot failure or bricking. Keep an exact stock firmware image for your device, use a stable USB connection, and **never disconnect the keyboard or suspend/reboot your PC** during an update.

> **Important:** TopreRT is not affiliated with PFU Limited, REALFORCE, or HHKB. Stock firmware and pre-patched firmware binaries are **not** distributed in this repository.

---

## Project Status

Release notes: [v0.3.0-rc6](docs/RELEASE_NOTES_v0.3.0-rc6.md). Identification investigation notes retain their Development history.

Development displays [local operation history](docs/LOCAL_INSTALL_HISTORY_DEVELOPMENT.md) separately from device inspection. History never establishes the connected device's current firmware or exact version. Inspect firmware reads HHKB metadata when present, displaying family, build ID, channel and catalog version. [Development generation](docs/METADATA_GENERATION_DEVELOPMENT.md) embeds deterministic metadata in RT/HOLD output and stores portable recipes; matching RT recipes show release/re-press settings explicitly as recipe information, not settings readback. Versioned catalogs are bundled separately from custom local records. GUI-generated Golden RT B33E6ADF (R32/P32) and SpaceFn HOLD A96B4BA0 (250 ms, one slot) passed user-confirmed installation, reconnect, identification and functional checks on one PD-KB800W. See [hardware coverage and limits](docs/HARDWARE_IDENTIFICATION_20261018.md). Default RT 81B8EDEB has not been hardware-tested. Detect searches USB devices and preserves the manual selection when both families are connected.

**Current app version: v0.3.0-rc6.** This is a prerelease source distribution for Windows. The earlier stock A0.48 restore/RT R60/P90 cycle and the latest GUI-generated RT/SpaceFn checks cover one PD-KB800W. Other models, other HOLD configurations, interrupted-update recovery and clean-PC setup need separate validation. Published rc3/rc4/rc5 assets are preserved.

| Device | Firmware | RT Core | Observer / Writer |
|---|---|---|---|
| **REALFORCE R3S** (R3SB) | A0.12 | Hardware verified | Hardware verified |
| **REALFORCE R3S** (R3SA / R3SC / R3SD) | A0.12 | Binary verified | Observer key map not hardware validated |
| **HHKB Professional Hybrid / Hybrid Type-S** (PD-KB800W) | A0.48 | Prior core hardware results retained | Legacy Observer: user-tested; stock/RT cycle passed on one device (see validation plan) |

*Exact stock SHA-256 values and model-specific validation details for the R3S are documented in [`backends/r3s/SUPPORTED_FIRMWARE.md`](backends/r3s/SUPPORTED_FIRMWARE.md).*

---

## Highlights

* **All-key Rapid Trigger core** with adjustable release and re-press distances.
* **HHKB Dual-Role / Generic HOLD** with up to eight configurable slots.
* **Hardware-validated HHKB SpaceFn:** tap Space for Space, hold Space for the native Fn layer.
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
* **Python:** Python 3.12 recommended, with Tkinter. Setup also detects Python 3.10+ through `py`, `python`, or `python3`. See the rc6 release notes for tested versions.
* **Libraries:** `hidapi`, `Tkinter` (included with standard Windows Python installers)

Install dependencies using:

```powershell
.\Setup_Demo.bat
```
## Quick start

1. Extract the complete package to a writable folder. Install **Python 3.12 with the Python Launcher and Tkinter**.
2. Run `Setup_Demo.bat` in that folder once. It installs USB dependencies into the app's private environment. Start the app with `Start_TopreRT_GUI.bat`.

Setup prefers Python 3.12, then tries `py -3`, `python` and `python3`. To select an interpreter, run `.\Setup_Demo.bat -PythonPath "C:\path\to\python.exe"` with your actual path. Python 3.10+ and Tkinter are required. Dependency installation errors are reported separately from Python discovery failures.
3. Connect the keyboard by USB and select its family. Supply your supported **original stock firmware**: model-specific R3S A0.12 `.rfb`, or HHKB PD-KB800W A0.48 `.hfb`. Do not select an earlier TopreRT output as the stock input. Firmware files are not included.
4. Choose the installation path below. Changing a profile or pressing **Check Settings** does not change the keyboard.

| Path | In TopreRT | Next step |
|---|---|---|
| R3S Rapid Trigger | Set distances → **Create Firmware File** | **Open Output Folder** → select the newly generated `.rfb` in official REALFORCE software and install it there |
| HHKB Rapid Trigger | Set distances → **Create & Install RT** → confirm | TopreRT generates the image and installs it using its built-in updater; wait for normal reconnect |
| HHKB HOLD / SpaceFn | Select **SPACEFN / GENERIC HOLD**, configure slots → **1. Create HOLD File** → **2. Install HOLD** → enter the confirmation phrase | Wait for normal reconnect, then check the configured tap/hold behavior |

For R3S, file creation is not installation. Choose the newly generated `.rfb`, not the original stock image or `.manifest.json`. Do not assume the official updater accepts every version combination; if it rejects the file, record the message and app/model version before proceeding.

For HHKB, close Observer and other keyboard tools before installing. Keep USB connected and the PC awake until completion. No separate updater launch or second installation in the official HHKB app is required. The stock/RT cycle and GUI-generated Golden RT/SpaceFn checks cover one PD-KB800W; see [current hardware coverage](docs/HARDWARE_IDENTIFICATION_20261018.md). Interrupted-update recovery remains unverified.

`output` is inside the folder of the app you are running. Use **Open Output Folder** to avoid picking files from an older copy. HHKB output files are retained as artifacts; RT installation already happens in the same operation.

### Settings, inspection and completion

- **Release / Re-press:** RT movement thresholds, with estimated mm conversions. These are not an independent initial-actuation-point control. Applying changed values requires creating/installing firmware again.
- **Check Settings / Validate Stock File / Software Self-test:** inspect settings, validate the input file or check software. They do not install firmware or prove that the connected keyboard passes every hardware test.
- **Detect:** find connected keyboard families. **Device diagnostics:** inspect HHKB identity. **Inspect firmware:** query the HHKB firmware family. These are read-only operations; firmware inspection is not yet supported for R3S.
- **Observer:** watch sensor responses using the profile selected in the GUI as expected values. Use the same profile you installed; thresholds are not automatically read back from the keyboard. Stop Observer before inspection or installation.
- **Installed firmware:** the last inspection result. Legacy TopreRT can be recognized while its exact release remains unknown. A3 is a device-reported revision, not a TopreRT version; no response is not proof of stock firmware.
- **Restore Stock (HHKB):** writes original firmware and removes RT/HOLD. It is not a settings reset or a universal repair for an unresponsive keyboard. **Recovery Instructions (R3S)** opens guidance only.
- **After installation:** confirm normal typing. For RT, check Observer responses; for HOLD, check the configured short-press/long-press behavior. A reconnect message alone is not a complete functional test.

RT-only and HOLD/SpaceFn are alternative builds. Selecting a mode chooses what to install next; it does not report or switch the currently installed firmware. Metadata identification is integrated in rc5; independent initial-press adjustment remains a research feature.

SpaceFn currently defers the Space tap decision. Fast overlapping typing can put the space after the following character. This is a documented behavior limitation and is not changed by the identification work.

### Developer tests

Run `python -B -m unittest discover -s tests -v` for offline checks. The real-stock generation test class requires the exact supported A0.48 file via `TOPRERT_TEST_STOCK`; without it that class is explicitly skipped. A configured missing or invalid file fails validation. Firmware is never bundled for CI. Tests use mocked transport and do not flash devices.

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
- R3S Hardware verification: R3SB has recorded hardware results for the documented profiles. R3SA, R3SC, and R3SD variants are binary-verified only.
- R3S Observer maps: Physical key mapping for R3SA / R3SC / R3SD Observer modes is not yet hardware-validated.
- R3S Spacebar: A rare missed-press edge-case remains under investigation.
- HHKB support: Currently limited strictly to **PD-KB800W A0.48**.
- HHKB Measurement precision: Millimeter values are estimated approximations.
- HHKB macOS DIP switch mode: Not yet validated.
- R3SB ROM DFU: Pin placement procedures are specific to the R3SB PCB and must **not** be assumed valid for other R3S revisions.

## HHKB v0.3.0-rc2 — Dual-Role / Generic HOLD + SpaceFn

HHKB Professional Hybrid / Hybrid Type-S (PD-KB800W, A0.48) can use up to
eight descriptor-driven dual-role slots. Each enabled slot has its own
**Source**, **Tap**, **Hold**, and **hold threshold**.

The GUI requires the user's own exact stock A0.48 HFB. TopreRT verifies the
input by SHA-256, reconstructs the hardware-tested generic-HOLD core locally
from audited byte substitutions, writes the 64-byte descriptor table,
recomputes both CRCs, and revalidates the candidate before flashing is enabled.

Exact supported stock image:

```text
SHA-256 635b995eb5a15aa50c2cedc60da7d8998fcca8285a09d41d984c07fffcaf9d43
```

Hardware-validated generic HOLD targets currently include **CTRL, LALT, V, and SPACE**.

### SpaceFn

v0.3.0-rc2 adds a hardware-validated SpaceFn special case:

```text
Source: SPACE
Tap:    SPACE
Hold:   FN
```

A short press behaves as a normal Space key. Holding Space activates the native
HHKB Fn layer, and the hold threshold is user-configurable.

SpaceFn was hardware-tested with physical and synthetic Fn overlap, both Fn
press/release orders, rapid reactivation, repeated threshold-edge use, multiple
Fn-layer functions, and reversed Space / layer-key release order. No stuck-Fn
behavior was observed during these tests.

`FN` is **not** an unrestricted generic HOLD target. Only the validated
`SPACE -> SPACE / FN` combination is currently accepted. Other Source -> Fn
combinations remain unsupported. `LSHIFT` and `RSHIFT` HOLD targets remain
blocked. Other selectable HOLD targets should be treated as limited-tested.

v0.3.0-rc2 also fixes an rc1 GUI regression where **Build & Validate** could
succeed while **Flash validated build** remained disabled.

No stock firmware or pre-patched HHKB firmware binary is distributed by this
workflow.

## License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Disclaimer

TopreRT is an open-source, unofficial firmware modification tool. Modifying keyboard firmware involves inherent risks, including boot loops, endless USB re-enumeration, loss of software detection, or bricking requiring hardware recovery. While SHA/CRC whitelisting and safety checks minimize these risks, they cannot guarantee immunity from failures.

**If you are uncertain about a step, do not erase your device and make a full backup first.**

## App version versus firmware build

The app is v0.3.0-rc6. Generated firmware still carries the reviewed Development family/build IDs; the existing generator, template and catalogs are unchanged. Development output filenames/inspection labels are intentional, not a failed app update. The app release number is not assigned retrospectively to earlier firmware. Inspect firmware reads metadata only when that firmware includes it. Existing firmware does not need reinstalling just to update the PC app.
