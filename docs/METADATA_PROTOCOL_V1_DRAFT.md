# Metadata Protocol v1 — historical expanded draft

Current development starts with the smaller [minimal identification proposal](IDENTIFICATION_MVP_DESIGN.md). The fields below remain a historical broader design, not requirements implemented in the app. Neither layout has an approved firmware transport.

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

Existing `0x99` telemetry must remain backwards compatible. The historical
`0x99 / C1 A1` handler initializes live HOLD RAM; development identification
uses `0x99 / C1 52` snapshots instead, without an A1 fallback. Preserving a
historical firmware handler is not a recommendation to send its request.
No new command ID or packet definition is frozen until
we can validate it on real HHKB/R3S hardware.
