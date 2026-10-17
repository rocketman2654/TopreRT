# Minimal firmware identification — proposal 0.1

Latest workspace follow-up (2026-10-17): separate Development recipes now reserve
string index7/language0409 and bind distinct RT/HOLD identity descriptors to
source/tool fingerprints and local build IDs. The end-to-end check is offline
and uses our native wrapper with mock providers, not USB metadata or original
ARM execution. The Development review package contains JSON/source, no HFB/BIN.
The GUI does not query index7. Public rc3/rc4 and legacy installed firmware do
not acquire these IDs. See workspace `DEVELOPMENT_IDENTITY_RECIPES.md` under
`research/firmware_identity_mvp/`; earlier notes below describe prior stages.

Workspace follow-up (2026-10-17): research now includes a strict offline USB
string-envelope parser and build-catalog resolver. The checked-in catalog has
no assigned IDs. Registered Development labels cannot become release versions;
unknown/mismatched IDs and metadata-free rc3/rc4 cannot acquire guessed versions.
See `research/firmware_identity_mvp/BUILD_CATALOG_DESIGN.md` and
`USB_IDENTITY_HOST_CONTRACT.md` in the workspace. These research modules are not
imported by the GUI or shipped as a firmware responder. The historical proposal
and implementation status below describe the initial stage.

Status: **offline design and synthetic payload parser only**. No request command is assigned, no new request is sent by the app, and no metadata firmware image has been built or installed. This proposal does not clear the earlier Metadata firmware integration for hardware use.

## A. Legacy identification in the host app

Development inspection uses normal identity 01/02/05/06, repeated 02/05/06, 99 telemetry, and 99 C1 52 only after a valid common telemetry response. No E0/E1/E2/E3 or new metadata request is used. Static analysis of the exact HOLD core found that the historical C1 A1 query initializes RAM also consumed by the HOLD state machine. C1 52 branches past that initialization and returns a snapshot. Unsupported/failed snapshots never fall back to A1; the result remains RT/HOLD ambiguous. This revised HOLD query has offline evidence only, not a real-device trial.

| Evidence | App interpretation | What remains unknown |
|---|---|---|
| Valid common telemetry + valid HOLD-specific response | HOLD-family response detected | Exact build, SpaceFn slots/settings, other capabilities |
| Valid common telemetry only | TopreRT detected — RT/HOLD not distinguished | Whether it is RT-only or HOLD; exact build |
| Missing/truncated/unrecognized common response | Firmware not identified | Stock, modified, unsupported or unavailable |
| Identity changes, access errors | Inspection stopped/unavailable | Firmware family |

The report retains the existing v1 schema/category names and adds identification_status, firmware_family, hold_probe_status, rt_only_verified, stock_verified and exact_version_available. Legacy probes never set the last three booleans true. Failed HOLD probing preserves valid common evidence but never proves RT-only. No raw device payload or serial is added to the report. Internal Metadata research status stays in the report; the basic screen focuses on the detected result and its limits.

## B. New firmware: smallest useful payload

First scope: identify a claimed firmware family and a registered patch build, with an exact supported product/stock pairing. Settings, slot configuration, initial-press configuration, serials and firmware-image hashes are out of scope.

The following is a **candidate payload**, not a frozen USB command or an extension of the deployed legacy telemetry response. It deliberately uses TRID rather than the historical TRT! research layout. All multibyte values are little-endian.

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 4 | TRID candidate magic |
| 4 | 1 | Layout major = 1 |
| 5 | 1 | Layout minor = 0 |
| 6 | 1 | Payload length = 24 |
| 7 | 1 | Proposed product: 1 = HHKB PD-KB800W, 2 = R3SB |
| 8 | 1 | Proposed family: 1 = RT-only, 2 = HOLD |
| 9 | 1 | Reserved, must be zero |
| 10 | 2 | Proposed stock ID: 1 = exact HHKB A0.48, 2 = exact R3SB A0.12 |
| 12 | 4 | Nonzero patch build ID, assigned by a versioned catalog |
| 16 | 4 | Reserved, must be zero |
| 20 | 4 | CRC-32/ISO-HDLC of bytes 0..19 (Python zlib.crc32 convention) |

Allowed pairs in this proposal: HHKB/RT, HHKB/HOLD, R3SB/RT. R3SB/HOLD, combined-family flags, other products and reserved fields are rejected. IDs are local design values until an actual protocol is reviewed. This does not announce additional device support.

A build ID maps to a specific patch recipe/core release. Configurable distances may share that build ID; it is not the hash of the exact generated image and does not recover settings. The catalog must record product, stock hash, patch source revision, family and readable patch version. IDs must not be reused for a different recipe. Unknown nonzero IDs may be displayed as an unknown build, never guessed from A3, a GUI title or the newest release. Synthetic fixture IDs are not production assignments.

A CRC checks accidental payload damage. It does not authenticate firmware, prove the rest of the image is intact, identify a physical keyboard or authorize flashing. A mismatched product is rejected even when its checksum is valid. Legacy replies and the older TRT! draft are not parsed as this layout. A future transport must validate its response envelope and extract the exact 24-byte payload before calling the parser; that adapter does not exist yet.

## C. Firmware integration gates

Prior Stage20/21/22 work remains relevant even though the payload is smaller:

- Fixed REQ readers and the timing of re-registration/wipe must preserve ordinary commands.
- Stage22 observed a single-buffer EP4 initialization and software completion without automatic re-arm for the normal 64-byte request. That does not prove endpoint NAK or absence of pending traffic.
- busy, EVENT, device state or a reused context pointer alone do not establish request ownership or distinguish reset generations.
- Source and destination lifetime through PMA copy, TX completion, reset/cancel and failed registration must be established. Shrinking the payload or giving it another magic does not resolve those issues.
- Request encoding/collision checks, RAM/code ownership, all exit paths, read-only behavior, legacy telemetry compatibility and updater exclusion must be reviewed before assigning a command.

The next engineering task is a transport ownership/exit-path audit using the existing exact-image evidence. Only after those gates are addressed should an immutable identification block and read-only firmware handler be prototyped. Hardware entry needs a separate, concrete trial plan. No automatic metadata probing is added to legacy devices.

## Completion criteria

1. Legacy states are unambiguous in screen/report and malformed/failure paths cannot claim stock or RT-only.
2. Payload and catalog semantics are reviewed offline, including unknown builds, wrong products and corrupt responses.
3. A firmware read-only transport implementation is justified by source/assembly evidence and legacy regression checks.
4. A controlled normal-operation trial reads the installed build/family and confirms existing keyboard behavior.

Only items 1 and the initial parser/design portion of 2 are implemented in this development step. Items 3 and 4 remain open. R3S RT overhaul and additional device support follow this identification work.

Workspace research follow-up (2026-10-15): an independent request predicate, symbolic 64-byte storage object and unlinked 34-byte Thumb compare now have offline tests. They are not imported by this app and do not constitute a firmware responder or assigned wire format. They assume owned immutable request memory and an allowed context supplied by a caller; establishing those facts in the real hook remains an open integration obligation. See research/firmware_identity_mvp/GUARD_FRAME_PROTOTYPE.md in the workspace (research tools are not shipped in the app package).
