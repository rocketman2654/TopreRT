# Firmware identification development after rc3

Current follow-up: [GUI metadata generation and versioned catalogs](METADATA_GENERATION_DEVELOPMENT.md)
now adds deterministic IDs to Development RT/HOLD output and displays matching RT recipe
settings. The reader-integration notes below describe the earlier stage.

## GUI metadata integration and Detect correction — 2026-10-17

The Development GUI now reads the hardware-tried metadata path from a standalone
app/firmware_identity package. It has no runtime dependency on workspace research
or firmware input files. Original research/source snapshots and candidate IDs are
preserved. This does not change public rc3/rc4 assets or the D-drive repository.

- Detect enumerates USB interfaces only, in the background. It selects a keyboard
  family only when exactly one normal-mode device is present. Both families,
  multiple devices, no devices and HHKB update mode are reported separately.
- Detect cannot run during an update, Observer or another worker. Re-detecting the
  same family preserves the selected stock file, profile and HOLD settings.
  It invalidates the earlier inspection/report until Inspect firmware is used.
- Inspect firmware first performs one bounded metadata read. A registered
  Development result shows family, build ID and Development, not a published
  release number. Unregistered claims and catalog mismatches remain distinct.
- Missing metadata may use the existing C1 52 legacy snapshot after the metadata
  worker is reaped. Invalid metadata, changed connection and worker timeouts do
  not trigger legacy fallback or automatic metadata retries.
- Platform changes and update attempts invalidate pending inspection results, so
  late results/errors cannot replace the newly selected platform's information.
- Export keeps serials/USB paths out and includes build/channel/catalog status.
  Metadata is a firmware claim, not whole-image authentication or settings readback.

Validation: **135 app tests passed**, including25 bundled reader tests and16 new
discovery/adapter/actual Tk widget tests. No physical devices were opened by these
tests. Separately, the actual hidden Development GUI's Detect callback enumerated
one R3S and one normal HHKB; it preserved the manual selection and showed both.
One Inspect button invocation displayed RT-only/Development/BA90567B, enabled
report export and used one metadata read with no legacy probe. No firmware was
written or mode switched. Visual layout and HOLD on the new GUI were not separately
hardware-tested. Detailed evidence is in the workspace docs/validation folder.

Current limitation: the existing Create RT/Create HOLD builders are unchanged.
They do not yet embed new metadata. Such files still receive conservative legacy
identification. GUI metadata display is Development-only and is not a new release.

Below are earlier investigation records, retained as historical context.

## Current development update — 2026-10-16

The Development app now shows [PC operation history](LOCAL_INSTALL_HISTORY_DEVELOPMENT.md)
in its own panel. It records successful HHKB installations after reconnect and
R3S file generation only. It never supplies the connected device's firmware
version or converts an unknown inspection result to RT/stock/HOLD. App build and
intended settings are PC records, not values read from firmware. The full app
suite passes 94 offline tests, including mocked operation and actual Tk widget
integration; no new hardware trial was performed.

A separate exact-image investigation traced standard USB string requests through
EP0. All existing string indices 0..6 are occupied; 7..255 reject. Adding identity
requires a reviewed dispatcher change, descriptor source/lifetime/reset analysis
and Windows access validation. No new index is assigned, host query enabled or
firmware produced. The full workspace research suite passes 284 offline tests.
These results do not establish firmware integration safety. See workspace
`research/firmware_identity_mvp/USB_DESCRIPTOR_FINDINGS.md`.

The sections below retain earlier development-stage details. The HOLD query
correction was subsequently published separately as rc4; immutable rc3 assets
remain preserved. This current history/string work is absent from both releases.

Date: 2026-10-15. Local development only; the public rc3 tag/ZIP and PR have not been changed by this work.

## Legacy host improvements

- The screen explicitly distinguishes a HOLD-family response, common TopreRT telemetry with RT/HOLD ambiguity, and firmware not identified.
- Report v1 remains backward-compatible with existing category fields and adds structured identification/family/probe-status fields. Legacy probes never claim stock, RT-only or an exact version as verified.
- Missing or failed HOLD-specific replies preserve common telemetry evidence without converting it to RT-only.
- Truncated and oversized legacy packets are rejected. Identity changes and access/query failures have distinct statuses and sanitized messages.
- Internal metadata research text stays in exported reports; the basic screen focuses on the result and its limits.
- Normal identity and common telemetry queries remain. Development HOLD inspection now uses the existing C1 52 snapshot handler rather than rc3's C1 A1 initialization handler. No metadata command or update-mode command was added to inspection.

## HOLD query correction and transport audit

Exact-image static analysis found that C1 A1 stores 16 initialization bytes at 0x20004FF0, which the HOLD state machine also reads. This is a RAM side effect, not a flash write; no typing failure was reproduced on hardware. C1 52 skips those stores and returns a snapshot. Development inspection requires its operation marker and never retries with A1. A stale A1 reply, unknown marker or failed snapshot cannot establish HOLD or RT-only.

The public rc3 inspector still contains the historical query. Its immutable release assets were not replaced. Until a separately reviewed fix is released, HOLD users should avoid rc3's Inspect firmware operation. This finding does not establish a firmware-writing failure.

The default command hook is shared by unknown commands, rather than exclusive to 0x99. A future identity handler must check the complete request. The sender can return zero without queuing when USB is not configured; shared TX RAM is also used by telemetry. An immutable response source is a candidate to investigate, not a completed ownership solution. Detailed addresses and reproducible checks are in the workspace research/firmware_identity_mvp/TRANSPORT_FINDINGS.md; research tools are excluded from the app package.

## Minimum future identity

See [proposal 0.1](IDENTIFICATION_MVP_DESIGN.md). A separate offline prototype parses a proposed 24-byte payload with family, product/stock pairing, patch build ID and CRC. It is not imported by the app and no wire command has been allocated. Exact release labels require a separately reviewed build catalog; legacy firmware cannot gain information it never stored.

Stage22 still leaves endpoint quiescence, pending traffic, reset generation/ownership and complete receive/transmit exit behavior unresolved. The smaller payload does not remove these blockers. No firmware patch or device trial was performed.

## Validation

- App suite: 71 tests passed, including the actual Tk result/report integration with mocked hardware, snapshot failure without A1 fallback, stale A1 rejection and unknown operation rejection.
- Offline payload proposal: 6 tests passed, including every single-byte mutation of the fixture, valid-CRC unsupported layouts, wrong products, unsupported combinations and unknown builds.
- Exact-image transport audit: 4 tests passed using the supplied stock/RT inputs and an in-memory HOLD derivation. These check instruction contracts, bounded dispatch, shared RAM references and mutation rejection; they do not emulate the MCU or USB controller.
- Public export tool: 3 existing tests passed.

An initial full app run hit the previously observed intermittent mock-probe report I/O failure under the sandbox. A diagnostic rerun and the final uninstrumented full run passed; this is recorded separately from physical device behavior. No test in this step opened a physical HID device.

Next: review an explicitly guarded handler with an immutable response source, including source lifetime, pending traffic, reset/cancel and receive cleanup. Catalog/firmware integration follows only after those gates are addressed. This development does not add a real-device HOLD detection trial or produce an installable firmware candidate.
