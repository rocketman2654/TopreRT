# Metadata Protocol v1 — design draft only

Do **not** deploy this draft to keyboards; implementation, CRC discipline,
command collision checks, and real-hardware tests are still required.

Recommended fields in an **explicit future read-only** metadata response:

- signature (4 bytes, e.g. `TRT!`)
- protocol_major and protocol_minor
- product_id and stock_firmware_id
- patch_build_id (unique across release builds)
- rapid_trigger_core_revision
- dual_role_core_revision
- feature_flags: `0x01` RT, `0x02` Generic HOLD, `0x04` SpaceFn,
  `0x08` Observer, `0x10` future First-press configuration
- response length, schema version, checksum

A firmware may support RT, Dual-Role, or both. Feature flags describe
**verified** built-in features, not GUI settings. Legacy HOLD's `CNY`
response is a historical implementation identifier, **not** v1 metadata.
Never claim that a missing firmware response establishes a stock firmware.

Existing `0x99` telemetry and `0x99 / C1 A1` legacy query must remain
backwards compatible. No new command ID or packet definition is frozen until
we can validate it on real HHKB/R3S hardware.
