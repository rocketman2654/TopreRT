# Technical Notes

In the REALFORCE R3S research, key-related data—including `base`, `cur`, `delta`, and calibration values—alongside stock state thresholds were directly observed. Testing confirmed that `delta` updates continuously in response to physical key movement.

Rather than completely replacing the stock state machine, the Rapid Trigger (RT) implementation uses a runtime anchor to measure relative movement from the extreme point corresponding to the most recent movement direction.

Following the initial implementation of RT on the R3S, sensitivity thresholds and stale-anchor edge cases were iteratively refined.

The current stable release candidate settings are:

* **Release:** `0.60 mm`
* **Re-press:** `0.80 mm`
* **Non-Space Keys:** Two-pass `DISARM64`
* **Spacebar:** `NO-DISARM`

On the HHKB, mid-stroke RT functionality was likewise confirmed on physical hardware using separate telemetry and runtime state mechanics.

---

## Development Philosophy

1. **Preserve stock behavior** as much as possible.
2. **Do not speculate** or patch firmware revisions that are not officially supported.
3. **Fail-closed validation:** Even if the GUI passes an input, the backend must independently enforce safety blocks.
4. **Prefer official vendor tools:** When an official update path is available, prioritize it over custom flasher tools.
5. **Decoupled execution:** Avoid designs where patched firmware requires a specific GUI version to function.
6. **Isolate telemetry:** Strictly separate read-only telemetry operations from flash write mechanisms.
7. **Transparent verification:** Explicitly distinguish between *hardware-verified* and *binary-verified* states.
8. **Protected recovery:** Document recovery paths, but do not expose low-level flashing/recovery tools in general user flows.
9. **Mandatory backup:** During recovery procedures, reading and backing up flash precedes writing.
10. **Objective reporting:** Clearly distinguish observed empirical facts from reverse-engineering assumptions in all documentation.

------------------------------------------------------------------------
