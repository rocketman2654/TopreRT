# TopreRT v0.3.0-rc2 — GUI workflow preview 1 (unreleased)

This is a **UI-only preview**, not an official v0.3.1 firmware release.
The RT-only, HOLD/SpaceFn, recovery and observer firmware engines are the
**unaltered** v0.3.0-rc2 files. No firmware images are bundled.

## Changes

- HHKB workflow is separated into `Rapid Trigger (RT-only)` and
  `SpaceFn / Generic HOLD` tabs. These are **alternative firmware builds**;
  they are **not combined**. Switching tabs never writes to a keyboard.
- The stock firmware picker is shared between the HHKB RT and HOLD builders.
  Both still validate the exact original A0.48 image through their respective
  existing backend validators.
- `Apply TopreRT`, `Build & Validate HOLD`, `Flash validated HOLD`, and
  `Restore Stock` remain in a persistent bottom action bar. The content
  scrolls vertically and horizontally when needed.
- On R3S, the HOLD tab is hidden; the existing R3S build-only workflow remains.
- The HOLD route preserves its separate Build & Validate phase, output SHA
  lock, confirmation token, and disarm-on-edit safety behavior.

## Use on Windows (recommended preview procedure)

1. Keep a backup of the original `TopreRT_GitHub_v0.2` directory and do not
   overwrite the working RC2 installation at first.
2. Extract the supplied full preview ZIP into a **new directory**.
3. Run `Start_TopreRT_GUI.bat` from the new directory.
4. Inspect the two HHKB tabs, resize the window and check stock validation.
5. **Do not flash a firmware for GUI testing.** Hardware updating was not
   exercised by these preview tests. Only perform flashing after separately
   reviewing and confirming the image and recovery procedure.

For code review, a separate unified diff (`.patch`) is also provided; it
only changes `toprert_unified_gui.py` from the v0.3.0-rc2 snapshot.

## Checks performed

- Python syntax compilation: passed
- GUI smoke testing under virtual X display at 960 x 580: passed
- R3S settings and apply button visible: passed
- HHKB RT apply and HOLD build/flash actions visible in matching modes: passed
- Exact stock A0.48 picker shared by RT and HOLD: passed
- RT-only firmware binary reproduced exactly from original RC2 backend: passed
- HOLD/SpaceFn builder audit and SHA-locked output: passed
- HOLD flash disabled after subsequent slot change: passed
- **Real Windows desktop and physical keyboard flashing: not tested**

No Bluetooth changes or firmware-detection logic are included in this preview.
