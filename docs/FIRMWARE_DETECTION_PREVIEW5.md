# Firmware Detection Preview 5 (experimental)

- Inspect installed firmware on HHKB USB (MI_02) with an explicit button.
- Development correction after rc3: HID identity (0x01/0x02/0x05/0x06), legacy 0x99 telemetry, and legacy HOLD snapshot (0x99 with C1 52) only after a valid telemetry signature. The historical C1 A1 request initializes live HOLD RAM and is no longer sent. Failed snapshots never fall back to A1.
- No E0/E1/E2/E3, no firmware writes, no EEPROM/Flash changes.
- Legacy HOLD and RT can share the same 0x99 telemetry response; legacy RT must not be asserted from that response alone.
- A validated HOLD snapshot with operation marker 52 marks legacy Dual-Role/HOLD, not the exact release or slot configuration.
- No response means **Unknown**, never conclusively Stock.
- The legacy snapshot correction was released separately in rc4; public rc3 assets remain unchanged. HOLD users should use rc4 or this Development app rather than rc3 inspection. Earlier snapshot-path hardware results are documented in HOLD_QUERY_FIX.md in the public repository. New metadata generation and GUI trial coverage are described in METADATA_GENERATION_DEVELOPMENT.md and HARDWARE_IDENTIFICATION_20261018.md. Stop Observer before inspection.
- R3S firmware detection not yet implemented; no speculative HID commands are sent to R3S.
- The original preview notes above concern legacy responses. The current Development metadata path reports a family/build ID and catalog channel; a Development ID is not an assigned public release number.
