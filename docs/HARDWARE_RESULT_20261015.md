# PD-KB800W stock and RT restoration result

Date: 2026-10-15 KST. Coverage: one HHKB Professional Hybrid / Type-S PD-KB800W with no USB serial and a usable vendor identity response.

| Trial | Image SHA-256 | Result |
|---|---|---|
| Stock A0.48 restore | `635b995eb5a15aa50c2cedc60da7d8998fcca8285a09d41d984c07fffcaf9d43` | Complete transfer and normal reconnect passed; user confirmed HHKB typing and official Keymap Tool recognition |
| RT R60/P90 reinstall | `e67d7a75583f86f0d6185087cdaf323daba62748fc6c6d7eb189cb66301661d5` | Complete transfer and normal reconnect passed; user confirmed typing, Observer and RT identification |

Both trials acknowledged E0, E1, all 4,960 E2 packets and E3. Vendor model/serial identity matched the private normal-mode binding before E0, before E1 and after normal reconnect. The observed query 02 marker transition was 0 → 1 → 0; this is evidence for this tested device and these images, not a general firmware authenticity rule.

Stock restoration used the guarded RT engine through an instrumented local harness. RT reinstallation invoked the actual GUI update worker through that harness; it did not exercise the full window/button flow. The harness added exact-image and identity checks and a persistent journal. No automatic retry or interrupted-update recovery was performed.

RT R60/P90 corresponds to estimated release 0.10 mm and re-press 0.15 mm. Legacy telemetry does not encode the exact installed TopreRT release; an unknown exact version remains expected.

Unverified coverage: other HHKB models/units, other profiles, the revised HOLD writer, full GUI button flow, recovery after an interrupted write, and a clean-PC installation. Metadata firmware integration is not included. Firmware, private identity bindings, serials and USB paths are excluded from the public package.
