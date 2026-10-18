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
# C1 A1 initializes RAM used by the HOLD state machine. C1 52 snapshots it.
# Never fall back to the initialization query when snapshot is unsupported.
HOLD_READ_QUERY = b"\xC1\x52"

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
    # Additive report fields: legacy category strings remain compatible.
    identification_status: str = "not_identified"
    firmware_family: str = "unknown"
    hold_probe_status: str = "not_attempted"
    rt_only_verified: bool = False
    stock_verified: bool = False
    exact_version_available: bool = False
    build_id: str | None = None
    build_channel: str | None = None
    metadata_status: str = "not_queried"
    catalog_match: bool = False
    build_settings: dict | None = None
    settings_source: str | None = None
    catalog_version: str | None = None


def display_title(result):
    if result.identification_status in {"metadata_registered", "metadata_unregistered"}:
        family = "RT-only" if result.firmware_family == "rt_only" else "HOLD"
        label = {"development": "Development", "prerelease": "Prerelease", "release": "Release"}.get(
            result.build_channel, "Unregistered build")
        return f"{family} · {label} · {result.build_id}"
    if result.identification_status == "metadata_mismatch":
        return "Inconsistent firmware metadata — version not identified"
    if result.identification_status == "metadata_unavailable":
        return "Firmware identification unavailable"
    if result.identification_status == "legacy_common":
        return "TopreRT detected — RT/HOLD not distinguished"
    if result.identification_status == "legacy_hold":
        return "HOLD-family response detected"
    if result.identification_status == "connection_unavailable":
        return "Keyboard query unavailable"
    if result.identification_status == "identity_unstable":
        return "Identity changed — inspection stopped"
    if result.identification_status in {"unexpected_identity", "query_failed"}:
        return "Firmware query failed"
    return "Firmware not identified"


def format_details(result):
    lines = [
        f"Device-reported revision: {result.reported_revision} (not the TopreRT version)",
        f"Exact TopreRT version: {result.exact_version}",
        f"Evidence: {result.evidence}", result.detail,
    ]
    if result.build_id:
        label = f" · {result.catalog_version}" if result.catalog_version else ""
        lines.insert(2, f"Build ID: {result.build_id} · Catalog: {'matched' if result.catalog_match else 'unregistered'}{label}")
    if result.build_settings and result.firmware_family == 'rt_only':
        values = result.build_settings
        lines.append(f"Build recipe settings (not read back): Release R{values['release_raw']} (~{values['release_mm_estimated']:.3f} mm) / "
                     f"Re-press P{values['repress_raw']} (~{values['repress_mm_estimated']:.3f} mm)")
    return "\n".join(lines)


def shared_report(result):
    return json.dumps({"schema": "toprert-firmware-identification-v1", **asdict(result),
                       "serials_included": False}, ensure_ascii=False, indent=2) + "\n"


def _legacy_response(data, prefix, minimum):
    return isinstance(data, bytes) and minimum <= len(data) <= 64 and data.startswith(prefix)


def classify_responses(plain: bytes, specific: bytes | None, device: str = "",
                       *, hold_probe_status=None, expected_hold_operation=None) -> ProbeResult:
    """Pure response classifier; does not perform I/O or assume stock on timeout."""
    if not _legacy_response(plain, RT_OBSERVER_PREFIX, 16):
        return ProbeResult("Unknown", "No validated TopreRT telemetry response (not proof of stock).", device)
    if (_legacy_response(specific, HOLD_CANARY_PREFIX, 26)
            and specific[9] in (0x52, 0xA1)
            and (expected_hold_operation is None or specific[9] == expected_hold_operation)):
        return ProbeResult("Legacy Dual-Role / HOLD", "HOLD-family signature observed; exact build and SpaceFn configuration are unknown.", device, "Response observed", evidence="RT telemetry + CNY legacy signature",
                           identification_status="legacy_hold", firmware_family="hold",
                           hold_probe_status="signature_observed")
    state = hold_probe_status or ("no_matching_signature" if specific is not None else "not_observed")
    return ProbeResult("Legacy TopreRT", "RT telemetry observed; this does not prove RT-only firmware or identify an RT/HOLD release.", device, "Response observed", evidence="RT telemetry signature",
                       identification_status="legacy_common", firmware_family="toprert_unspecified",
                       hold_probe_status=state)


def inspect_hhkb(hhe) -> ProbeResult:
    """A bounded read-only probe, manually initiated while USB is connected."""
    timestamp = datetime.now(timezone.utc).isoformat()
    def finish(result):
        return replace(result, captured_at=timestamp, reported_revision=revision)
    revision = "Unknown"
    try:
        hid = hhe.load_hid()
        matches = hhe.enum_vendor(hid)
    except Exception:
        return finish(ProbeResult("Unknown", "USB query unavailable. Check setup and close other keyboard tools.",
                                  identification_status="connection_unavailable"))
    if len(matches) != 1:
        return finish(ProbeResult("Unknown", f"Expected exactly one HHKB USB vendor interface, found {len(matches)}.",
                                  identification_status="connection_unavailable"))
    try:
        dev = hhe.open_dev(hid, matches[0])
    except Exception:
        return finish(ProbeResult("Unknown", "Cannot open the keyboard. Close other keyboard tools and retry.",
                                  identification_status="connection_unavailable"))
    try:
        # Existing preflight identity requests, not updater mode or device reset.
        info = hhe.identity(dev)
        again = tuple(hhe.query(dev, c) for c in (2, 5, 6))
        if info != again:
            return finish(ProbeResult("Unknown", "Identity changed during query; retry with one connected keyboard.",
                                      identification_status="identity_unstable"))
        model = hhe.decode_identity(info[0])
        if len(info[0]) >= 24:
            revision = info[0][20:24].split(b"\0", 1)[0].decode("ascii", "replace") or "Unknown"
        if not model.startswith("PD-KB8"):
            return finish(ProbeResult("Unknown", "Unexpected device identity; diagnostic probe not sent.",
                                      identification_status="unexpected_identity"))
        # Already deployed in RT-only and Generic HOLD firmware. In older/stock
        # images this may time out; never classify that result as stock.
        hhe.tx(dev, hhe.packet(0x99))
        try:
            plain = hhe.rx(dev, 750)
        except Exception:
            return finish(ProbeResult("Unknown", "No telemetry response; may be stock, unsupported or unavailable. Not proof of stock.", model,
                                      identification_status="no_telemetry_response"))
        if not _legacy_response(plain, RT_OBSERVER_PREFIX, 16):
            return finish(classify_responses(plain, None, model))
        # Read the HOLD snapshot only. The historical C1 A1 canary query writes
        # active HOLD RAM and must never be used for ordinary identification.
        try:
            hhe.tx(dev, hhe.packet(0x99, HOLD_READ_QUERY))
            specific = hhe.rx(dev, 750)
        except Exception:
            return finish(classify_responses(plain, None, model, hold_probe_status="query_unavailable"))
        return finish(classify_responses(plain, specific, model, expected_hold_operation=0x52))
    except Exception:
        return finish(ProbeResult("Unknown", "Firmware query failed; retry after closing other keyboard tools.",
                                  identification_status="query_failed"))
    finally:
        try:
            dev.close()
        except Exception:
            # A closing error must not leak identifiers or leave a successful result.
            raise RuntimeError("Could not close firmware query cleanly; reconnect before retrying.") from None
