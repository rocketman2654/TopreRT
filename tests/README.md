# HHKB hold release regression

These tests execute the A0.48 Cortex-M0 per-key scanner, including the RT and
hold hooks, native keymap lookup, debouncing, and HID report-buffer updates.
They do not open a keyboard or flash anything. Firmware images are not included.

Install `tests/requirements.txt`, then run from the repository root:

```sh
HHKB_STOCK_HFB=/path/to/HHKB800_FW_A048.hfb python -m unittest discover -s tests -v
```

PowerShell:

```powershell
$env:HHKB_STOCK_HFB = "C:\path\to\HHKB800_FW_A048.hfb"
py -m unittest discover -s tests -v
```

The builder requires the exact official A0.48 SHA-256:
`635b995eb5a15aa50c2cedc60da7d8998fcca8285a09d41d984c07fffcaf9d43`.
Missing or wrong input fails rather than silently skipping emulation.

## Regression and correction

With `SPACE>SPACE>FN:250`, hold Space, press Ctrl, release Ctrl, release Space,
then press A. The original core leaves report byte 0 at 1: A becomes Ctrl+A.
The test restoring the original instruction verifies this reproduction; the
stock physical-Fn control clears Ctrl correctly.

The wrapper at runtime 0x0801F1E4 already suppresses a physical key release when
that key is the active synthetic hold target. Its fallback for physical Ctrl
enters the legacy path at 0x0801F104, which additionally suppresses release for
*any* active hold. The correction replaces only that redundant conditional branch
at runtime 0x0801F10E (HFB offset 0xF112), `17 d0`, with Thumb NOP `00 bf`.
The generic target-ownership check remains intact, including synthetic Ctrl.

The reference image is now SHA-256
`327fd161b61a90095e6cdcb38adfa877ce5f9a79e4f59fc07a29aef50fd93f1a`
for `A>A>LALT:250`. A test reverses the instruction change and recomputes CRCs
to reproduce the original reference SHA, constraining the image difference to
that instruction and the CRC header. The GUI self-test uses the new reference
and does not claim hardware validation of the correction.

Coverage includes:

- Ctrl before/after a hold, both release orders, with Fn, Ctrl, LAlt, V, Space targets.
- Physical modifier and Fn overlap in both press/release orders.
- All six valid Space/Ctrl event orders at five event spacings.
- 50 repeated SpaceFN/Ctrl cycles with clean report and Fn state afterwards.
- Space tap, native Fn+A mapping, exact 250 ms threshold and 32-bit tick wrap.
- Stock control, original-bug reproduction, image scope, CRCs and reference hash.

## Limits

The fixture uses synthetic base/Fn maps, identical in all three mode banks; it
does not contain a personal keyboard dump. Capacitive readings are 1000 when
pressed and 0 when released, calibration is 500, and time is supplied by tests.
Sensor-selection and busy-delay routines are stubbed, GPIO has inert memory
backing, and RAM is initialized by the fixture rather than the MCU boot path.
Each pass runs all 128 candidate indices; two passes allow release debouncing.

Startup, interrupts, transport (USB/Bluetooth), and the outer main loop are not
emulated. These tests check native report buffers, not host-received packets.
They do not validate analog RT behavior, every remapping/mode, or simultaneous
multiple dual-role sources. Hardware validation of the correction remains pending.
