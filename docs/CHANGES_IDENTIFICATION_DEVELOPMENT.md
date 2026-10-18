# Firmware identification checkpoint — Development

Unreleased changes after rc3/rc4; existing public tags/assets remain unchanged.

- HHKB RT/HOLD generation embeds deterministic family/build metadata. Exact stock,
  generated image, recipe and saved manifest are checked before transmission.
- Inspection matches the device-reported metadata with versioned catalogs and
  custom local records. Matching RT records show release/re-press recipe settings,
  clearly distinguished from settings readback. Legacy/unknown paths remain.
- Detect searches in the background, separates normal/update modes and preserves
  selected files/settings when the keyboard family stays the same. Pending old
  inspection results are discarded after device/platform/update changes.
- Installation history remains a separate PC record. HHKB RT/HOLD progress uses
  the shared Development presentation; update and Observer operation guards remain.
- Versioned catalog snapshots are immutable. Custom records stay under output;
  public source snapshots exclude firmware, local records and environments.
- PR review follow-up: saved artifacts use atomic publication that cannot replace
  another writer's file. Identical concurrent content is accepted; different
  content is preserved and reported as a conflict. Malformed non-object custom
  records stop inspection before any device query instead of raising an uncaught
  attribute error. Firmware generation sources and build IDs are unchanged.

[User-confirmed GUI RT and SpaceFn results](HARDWARE_IDENTIFICATION_20261018.md)
cover one PD-KB800W and the named settings. SpaceFn input-order delay is retained
as a behavior limitation. R3S firmware identification and the planned R3S RT
overhaul are not part of this checkpoint.
