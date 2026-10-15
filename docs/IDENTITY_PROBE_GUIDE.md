# HHKB identity probe — 2026-10-14

This is an experimental compatibility tool for PD-KB800W. It does not import a firmware writer, accept a firmware image, or transmit E1/E2/E3. E0 still changes device state. Full update compatibility is not established by this probe.

## Start with the normal-only check

1. Close Observer, the TopreRT GUI and other keyboard tools.
2. Connect one supported HHKB over USB.
3. Double-click `Check_HHKB_Normal_Identity.bat`.
4. Look for `normal_identity_verified`. The new JSON report is in `output/identity_probe_*.json`.

The launcher sends only 01/02/05/06 and compares two reads. It never passes `--enter-updater`. Reports contain command IDs and verification results, but no serials, USB paths, raw responses, firmware data or original exception text. Existing report files are never overwritten.

An experimental marker is also reported from existing query 02 when its payload is exactly 57 bytes. Static analysis found byte 56 initialized to 0 in exact stock/checked RT application code and 1 in the historical boot backup. The report labels these as application_candidate/boot_updater_candidate and keeps other layouts/values unavailable/unknown. This adds no USB commands and does not independently verify updater entry, return, current firmware provenance or recovery compatibility.

## Experimental E0 path — not yet cleared for hardware use

Static analysis on 2026-10-14 found that exact A0.48 E0 handling requests stores to persistent-state addresses before resetting. The supplied RT R60/P90 candidate has identical code in the checked E0/helper/reset windows. A historical boot backup checks one of those locations before jumping to the application. Its match to the current device is unverified, but this is concrete evidence against treating E0 as a harmless temporary mode switch. No E1/E2/E3 transmission does not mean no persistent state change. Power cycling is not a verified return method. The E0-only experiment remains on hold.

The official [PFU download page](https://happyhackingkb.com/download/) lists HHKB Professional Keymap Tool 2.0.1 for Windows and HYBRID A0.48 as checked on 2026-10-14. It describes normal firmware updating. It does **not** establish a return procedure for stopping our sequence immediately after E0. Do not treat downloading the tool or possessing stock firmware as proof of that return path.

The CLI has `--enter-updater`, requires a `--recovery-plan` JSON and an interactive confirmation before E0. The unconfirmed template in this directory fails the gate. The plan must document a separately verified official source and return steps for the actual device; `confirmed_by_user` is a user acknowledgment, not automatic validation by this program. Do not change it to true merely to get past the check.

Once the return procedure is independently verified and the experiment is explicitly agreed:

- The tool checks normal identity twice and rechecks after the confirmation prompt.
- It records intent on disk before sending each command.
- E0 may be attempted once. Failed/ambiguous acknowledgment stops the attempt without retry.
- After a 10-second wait, exactly one supported interface must be present.
- It sends exactly one query 02 and compares model/vendor serial against the original.
- It closes the handle without sending any finalize, recovery or firmware-transfer commands.

Matching after E0 is reported as `identity_matched_after_e0_return_not_verified`. It does not independently prove that the device entered updater mode, returned to normal, or can accept a firmware update. A missing/bad/different response stops the experiment; automatic retries, reconnection resets and firmware writing are deliberately absent.

The official return method remains an open prerequisite. No real E0 command was sent while developing this tool. Before that prerequisite is satisfied, use only the normal-only launcher.

## Verification

The Windows offline suite has 58 tests, including 17 probe tests: disallowed command/body rejection, one-shot E0, one query after E0, default/cancel behavior, identity mismatch/missing identity/timeout, changed identity during confirmation, command checkpoint failures, report privacy, no overwrite, recovery-plan requirements and mode-marker reporting without new commands. All device operations in these tests are mocked.
