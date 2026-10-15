# Firmware Detection Preview 5 (experimental)

- Inspect installed firmware on HHKB USB (MI_02) with an explicit button.
- Read-only HID identity (0x01/0x02/0x05/0x06), legacy 0x99 telemetry, and legacy HOLD canary (0x99 with C1 A1) only after a valid telemetry signature.
- No E0/E1/E2/E3, no firmware writes, no EEPROM/Flash changes.
- Legacy HOLD and RT can share the same 0x99 telemetry response; legacy RT must not be asserted from that response alone.
- A verified HOLD canary marks legacy Dual-Role/HOLD, not the exact release or slot configuration.
- No response means **Unknown**, never conclusively Stock.
- Special canary path is identified in the RC2 binary, but has NOT BEEN TESTED ON REAL HARDWARE in this preview. Perform only under USB and with Observer stopped.
- R3S firmware detection not yet implemented; no speculative HID commands are sent to R3S.
- Future v1 metadata support needs a new independently validated firmware responder before exact version numbers are reported.
