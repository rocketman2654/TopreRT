# HHKB revised-writer validation plan

Latest evidence: the subsequent user-operated stock/RT GUI cycle passed on the same PD-KB800W; see HARDWARE_RESULT_20261015.md. The older entries below preserve the sequence of evidence. Distance precision remains unverified by the coarse Observer samples.

Status (2026-10-15 KST): one PD-KB800W passed a complete exact-stock A0.48 restore using the guarded RT engine through a local instrumented harness. E0, updater identity, E1, all 4,960 E2 acknowledgements, E3 and same-device normal reconnect passed. The user confirmed HHKB typing and official Keymap Tool recognition. HOLD writer, interrupted-update recovery and the complete GUI button flow remain separate validation items. The earlier observations below describe evidence available before this trial. Keep raw serials and USB paths out of public logs.

Subsequent RT trial (2026-10-15 KST): the previously validated R60/P90 image, SHA-256 `e67d7a75583f86f0d6185087cdaf323daba62748fc6c6d7eb189cb66301661d5`, was transferred using the actual GUI update worker invoked by a local harness. E0, matched updater identity, E1, all 4,960 E2 acknowledgements, E3 and matched normal-mode identity passed. This exercises the GUI worker, not the full window/button flow. The user confirmed post-RT typing, Observer and RT identification all work. This stock-to-RT trial passed on the tested device.

User functional check (2026-10-15 KST): after launching the current fix3 demo, the user confirmed Device diagnostics, Inspect firmware and Observer work. This is a user-reported normal-mode functional result. No new report payload was supplied; physical USB reconnection, ordinary typing and identity consistency across that reconnection were not explicitly confirmed in this message. No update-mode transition or transfer is established by this result.

Subsequent user confirmation (2026-10-15 KST): the user followed the normal reconnect procedure (stop Observer/close tools, unplug USB, reconnect, check typing, launch fix3, check diagnostics/firmware inspection/Observer) and reported it works. Normal USB reconnect functional validation is therefore recorded as passed for this device, by user report. No before/after identity report pair was supplied, so automated identity matching across reconnects and updater-mode identity remain unverified.

Normal marker observation (2026-10-15 01:52:27 KST): a saved normal-only report was read directly. PD-KB800W repeated identity was stable, the query 02 marker was 0 (`application_candidate`), and E0 was not attempted. This agrees with the application-side static interpretation for this device. The boot-side value 1 and updater identity/return remain unobserved. This observation does not establish firmware provenance or a recovery procedure.

## 1. Normal-mode baseline — no update commands

Connect exactly one supported HHKB over a reliable USB cable. Stop Observer and other keyboard tools. Save Device diagnostics and Inspect firmware reports. The current PD-KB800W case provides a vendor serial but no USB serial. Confirm two normal identity reads agree. Do not infer TopreRT build version from A3 or other device-reported revision strings.

Observed result: the user's normal-only probe recorded `normal_identity_verified`, `normal_identity_stable: true`, valid responses to 01/02/05/06 and repeated 02/05/06, and `e0_attempted: false`. This establishes repeated identity consistency within that session, not identity across reconnects or the installed firmware hash. Next, check normal-mode recognition in the official Professional Keymap Tool without starting an update; this does not establish updater recovery.

## 2. Preconditions for a mode-transition experiment

Additional baseline evidence: the user supplied a screenshot of the official Keymap Tool showing HYBRID US Layout and the keymap, and reported normal input operation. This completes the requested normal-mode baseline only. Static inspection of the installed official tool (file version 1.3.1.3) found E3 on the successful transfer path, not an established E0-only cancellation path. Do not use E3 as an unverified abort command. That tool's observed update path checks identity before E0; it does not establish query 02 support after E0.

Obtain and hash the exact supported stock image and the official updater appropriate for the actual model. Verify the manufacturer's documented recovery/return procedure for a device already in update mode. Record that procedure and its source; no assumed unplug/replug or power-cycle recovery is specified here. If return/recovery is uncertain, stop at stage 1 and inspect the protocol/official updater further.

Use a spare device if available, a stable power supply and direct USB connection. Do not unplug a device or force-close an updater to test protections on hardware. Explicitly agree to the mode-changing experiment before running it.

## 3. Identity-only updater experiment — harness implemented, hardware prerequisites pending

Planning update (2026-10-15): do not make the E0-only experiment a required stepping stone to a full update. Static analysis found persistent-state changes outside the application backup range, and no standalone return procedure is established. The historical stock rollback writer always starts with preflight and E0; it has no proven resume-from-updater path. Its complete E1/E2/E3 packet output matches the current RT engine for exact stock A0.48. Prefer designing a complete controlled stock-update test with a verified failure-recovery route; neither that test nor the identity-only experiment is cleared by this offline comparison. The following describes the existing harness, not an instruction to run it now.

The regular Apply/Restore buttons are NOT this test: they can continue into firmware writes. A separate harness must enforce that only normal identity reads, E0, and the bounded updater identity query 02 are possible. It must contain no E1, E2 or E3 transmission path and no automatic retry/reboot loop.

Capture normal identity, send E0 once, wait for re-enumeration, require one supported interface, send query 02 once and compare the model/vendor serial. Log command IDs, response validity and match result without publishing identifiers. If unsupported, timed out, malformed, multiple devices or mismatch: send no further commands and follow only the independently verified return procedure. E0 itself changes device state and may leave the keyboard in updater mode. Such a result is a compatibility failure, not permission to skip identity checking.

Success requires both identity comparison and verified return to normal typing. This stage does not establish firmware-transfer reliability. The experimental harness is now `hhkb_identity_probe.py`; see [the guide](IDENTITY_PROBE_GUIDE.md). It has passed mocked tests, but the verified return procedure remains missing. No mode transition was performed while preparing it.

## 4. Full transfer — separately authorized with verified failure recovery

With a validated return path and compatible updater identity response, perform one controlled exact-stock restore using the guarded writer. Check ACK ordering/counters, finalize response, same normal-mode device, ordinary typing and the vendor tool's recognition. Then consider a previously validated RT image and verify Observer/input behavior. Do not start with an experimental Metadata/Initial Press image.

The boot-side marker and identity response can be observed within this complete test rather than requiring an E0-only stop first. A protocol response failure must still stop before E1; the failure-recovery prerequisite applies to that branch. Starting a real transfer requires a separate explicit agreement because it changes the installed firmware and stock restore removes RT/HOLD behavior until a validated image is reinstalled.

## Release gate

Publish the device/firmware coverage and failures, not just a global PASS. Keep this branch a prerelease until E0 identity, full stock restore and post-update behavior have real-device evidence. Unverified models remain explicitly unverified. A USB-port match alone is not device identity.
