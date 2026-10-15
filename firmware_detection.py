# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conservative, user-initiated read-only HHKB firmware identification.

Never use E0/E1/E2/E3, storage or firmware update commands. Existing
legacy telemetry is not a version number. Detection does not authorize flashing.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
import json

RT_OBSERVER_PREFIX = bytes([0x55, 0x55, 0x99, 0x00, 0x0B, 0x52, 0x54, 0x01])
# Distinctive legacy v0.13 Generic HOLD canary response. Verified against
# rc2 patched executable *offline*. Real-hardware detection is experimental.
HOLD_CANARY_PREFIX = bytes([0x55, 0x55, 0x99, 0x00, 0x15, 0x43, 0x4E, 0x59, 0x01])

@dataclass(frozen=True)
class ProbeResult:
    category: str
    detail: str
    device: str = ""
    observer: str = "Unknown"
    exact_version: str = "Unknown — legacy signatures do not encode an exact release"
    reported_revision: str = "Unknown"
    evidence: str = "No recognized response"
    metadata: str = "Not queried — Metadata v1 firmware integration is still under research"
    captured_at: str = ""


def format_details(result):
    return "\n".join((
        f"Device-reported revision: {result.reported_revision} (not the TopreRT version)",
        f"Exact TopreRT version: {result.exact_version}",
        f"Observer: {result.observer} · Evidence: {result.evidence}",
        f"Metadata v1: {result.metadata}", result.detail,
    ))


def shared_report(result):
    return json.dumps({"schema": "toprert-firmware-identification-v1", **asdict(result),
                       "serials_included": False}, ensure_ascii=False, indent=2) + "\n"


def classify_responses(plain: bytes, specific: bytes | None, device: str = "") -> ProbeResult:
    """Pure response classifier; does not perform I/O or assume stock on timeout."""
    if len(plain) < 16 or not plain.startswith(RT_OBSERVER_PREFIX):
        return ProbeResult("Unknown", "No validated TopreRT telemetry response (not proof of stock).", device)
    if specific is not None and 26 <= len(specific) <= 64 and specific.startswith(HOLD_CANARY_PREFIX) and specific[9] == 0x52:
        return ProbeResult("Legacy Dual-Role / HOLD", "HOLD-family signature observed; exact build and SpaceFn configuration are unknown.", device, "Response observed", evidence="RT telemetry + CNY legacy signature")
    return ProbeResult("Legacy TopreRT", "RT telemetry observed; this does not prove RT-only firmware or identify an RT/HOLD release.", device, "Response observed", evidence="RT telemetry signature")


def inspect_hhkb(hhe) -> ProbeResult:
    """A bounded read-only probe, manually initiated while USB is connected."""
    timestamp = datetime.now(timezone.utc).isoformat()
    def finish(result):
        return replace(result, captured_at=timestamp, reported_revision=revision)
    revision = "Unknown"
    hid = hhe.load_hid()
    matches = hhe.enum_vendor(hid)
    if len(matches) != 1:
        return finish(ProbeResult("Unknown", f"Expected exactly one HHKB USB vendor interface, found {len(matches)}."))
    dev = hhe.open_dev(hid, matches[0])
    try:
        # Existing preflight identity requests, not updater mode or device reset.
        info = hhe.identity(dev)
        again = tuple(hhe.query(dev, c) for c in (2, 5, 6))
        if info != again:
            return finish(ProbeResult("Unknown", "Identity changed during query; retry with one connected keyboard."))
        model = hhe.decode_identity(info[0])
        if len(info[0]) >= 24:
            revision = info[0][20:24].split(b"\0", 1)[0].decode("ascii", "replace") or "Unknown"
        if not model.startswith("PD-KB8"):
            return finish(ProbeResult("Unknown", "Unexpected device identity; diagnostic probe not sent."))
        # Already deployed in RT-only and Generic HOLD firmware. In older/stock
        # images this may time out; never classify that result as stock.
        hhe.tx(dev, hhe.packet(0x99))
        try:
            plain = hhe.rx(dev, 750)
        except Exception:
            return finish(ProbeResult("Unknown", "No telemetry response; may be stock, unsupported or unavailable. Not proof of stock.", model))
        if len(plain) < 16 or not plain.startswith(RT_OBSERVER_PREFIX):
            return finish(classify_responses(plain, None, model))
        # C1 A1 initializes live HOLD RAM. Use the existing snapshot path.
        # Unsupported/failed snapshots must never fall back to A1.
        try:
            hhe.tx(dev, hhe.packet(0x99, b"\xC1\x52"))
            specific = hhe.rx(dev, 750)
        except Exception:
            specific = None
        return finish(classify_responses(plain, specific, model))
    finally:
        dev.close()
