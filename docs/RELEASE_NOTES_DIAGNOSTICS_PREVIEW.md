# Diagnostics and update-safety preview

Based on v0.3.0-rc2 and the local Preview5 UI, with no changes to firmware patch payloads. Suggested distribution: a prerelease branch/PR; do not replace the stable release until the revised writer is validated on hardware.

## Changes

- Separate R3S file creation, HHKB RT installation and two-step HOLD installation in the GUI and quick start. Add a Korean user guide and bilingual project introduction. Clarify stock inputs, output files, Observer expectations and Restore Stock.

- Read-only HHKB device diagnostics with masked serials and shared JSON reports omitting identifiers.
- Legacy firmware-family detection distinguishes the device-reported revision, exact patch version (unknown), response evidence and unqueried Metadata v1 research.
- HHKB updates block normal window closing and overlapping operations until the worker/child process exits.
- Reconnect verification uses USB serial when present. Otherwise it queries model/vendor serial before E1, rejecting missing, mismatched or unsupported responses. Final normal-mode identity is compared as well.
- RT and HOLD transports reject incomplete HID writes before reading an ACK; they do not retry automatically.
- Starting any GUI update or restore clears the previous firmware identification and disables report export until a fresh inspection completes, including after failed updates.
- HOLD update logs omit the device serial and raw identity payloads. Unexpected HID responses report the command without dumping device data.
- Public exports are built and checked in a fresh staging folder. Deleted source files cannot linger in the public folder; publication failures roll back the previous artifacts.
- Firmware inspection recovers its controls after rejected work. Observer stop targets the actual running session.
- R3S self-tests select the model-specific reference hash; HOLD validation rejects unknown key indices and out-of-range thresholds.
- Setup selects Python 3.12 explicitly and creates a private virtual environment. It does not depend on any editor runtime or modify system Python.

## Experimental metadata status

Metadata v1 remains a test/research item in this beta. The firmware identification panel displays its status, but the app does not send a new metadata query or install metadata firmware. Exact installed TopreRT release/build identification is unavailable for legacy firmware. Existing RT/HOLD family detection remains usable. Offline metadata research is separate from the public app's regression suite and is not a hardware-tested feature.

## Validation

61 offline tests pass on Windows/Python 3.12, including Tk UI tests, mocked writer sequences, incomplete writes, stale identification invalidation, privacy checks, legacy detection and the identity-only probe. Three separate packaging tests cover removal of obsolete files, rejection of private source content and rollback after publication failure. HHKB stock A0.48 in-memory RT 60/90 and HOLD reference hashes match; RT 32/32 and SpaceFn builds were also checked. Firmware inputs and built images are excluded from this repository.

An experimental identity-only probe and normal-only launcher are included. The E0 path is not cleared for hardware use until a return procedure is verified; see [the probe guide](IDENTITY_PROBE_GUIDE.md). Possession of a matching stock image does not satisfy that prerequisite.

User testing confirmed PD-KB800W diagnostics, RT telemetry identification and Observer operation. On 2026-10-15, a complete exact-stock A0.48 restore passed on one PD-KB800W using the guarded RT engine through a local instrumented harness: updater identity, all 4,960 E2 acknowledgements, finalization and same-device normal reconnect succeeded. The user confirmed typing and official Keymap Tool recognition after restoration. This does not validate other models, the HOLD writer, interrupted-update recovery or the complete GUI button flow. Metadata firmware integration is not shipped. An absent response never proves stock firmware.

On 2026-10-15, the user also confirmed normal typing, diagnostics, firmware inspection and Observer after unplugging and reconnecting the PD-KB800W using the fix3 demo. This validates normal reconnect operation on that device; it does not establish the writer's identity check across an updater-mode transition.

Offline comparison against the historical stock rollback writer found identical E1, all 4,960 E2 packets and E3 for exact stock A0.48. The current writer adds identity checks after reconnect. The complete stock trial establishes updater query compatibility and transfer on the tested PD-KB800W; recovery from a stopped attempt remains unverified on hardware.

## Reproduce offline checks

The subsequent R60/P90 restoration trial on the same PD-KB800W also completed E0/E1/E2/E3 and same-device normal reconnect, using the GUI update worker invoked by a local harness. The full GUI button flow was not exercised. The user confirmed post-restoration typing, Observer and RT identification all work. This result does not expand HOLD or interrupted-recovery coverage. See [the hardware result](HARDWARE_RESULT_20261015.md).

Run `Run_Offline_Tests.bat` after setup, or `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`. Tests do not open a physical HID device. Firmware reference checks require separately obtained user-owned stock and are not part of public CI.
