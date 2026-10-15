"""Read-only HHKB identity snapshot. Reports intentionally omit identifiers."""
from datetime import datetime, timezone
import json


def _field(payload, start, end):
    return payload[start:end].split(b"\0", 1)[0].decode("ascii", "strict")


def collect_hhkb(hhe):
    report = {
        "schema": "toprert-device-diagnostics-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "platform": "HHKB", "status": "unavailable",
        "model": "Unknown", "reported_revision": "Unknown",
        "firmware_variant": "Not determined by identity query",
        "identity_stable": False, "usb_serial_available": False,
        "firmware_serial_available": False, "normal_identity_check": "Not verified",
        "updater_identity_check": "Not tested — no mode switch performed",
        "serials_included": False,
    }
    display = {"usb_serial": "Unavailable", "firmware_serial": "Unavailable"}
    def result(status, detail):
        report.update(status=status, detail=detail)
        return {"report": report, "display": display}
    try:
        hid = hhe.load_hid()
    except Exception:
        return result("unavailable", "USB library could not load in this Python environment. Close this app, run Setup_Demo.bat in the same folder, then Start_TopreRT_GUI.bat.")
    try:
        matches = hhe.enum_vendor(hid)
    except Exception:
        return result("unavailable", "USB library loaded, but device enumeration failed. Check Windows device access and reconnect USB.")
    report["interface_count"] = len(matches)
    if len(matches) != 1:
        return result("unavailable", "Connect exactly one supported HHKB USB device, then retry.")
    desc = matches[0]
    try:
        dev = hhe.open_dev(hid, desc)
    except Exception:
        return result("unavailable", "Cannot open the keyboard; close other keyboard tools and retry.")
    try:
        first = hhe.identity(dev)
        second = tuple(hhe.query(dev, c) for c in (2, 5, 6))
        if first != second:
            return result("unstable", "Identity changed between reads; reconnect and retry.")
        payload = first[0]
        if len(payload) < 40:
            return result("unavailable", "Keyboard returned an incomplete identity.")
        model = _field(payload, 0, 20)
        revision = _field(payload, 20, 24)
        serial = _field(payload, 24, 40)
        if not model.startswith("PD-KB8"):
            return result("unsupported", "The connected device is not a supported HHKB 800-series identity.")
        report.update(model=model, reported_revision=revision or "Unknown", identity_stable=True,
                      firmware_serial_available=bool(serial.strip()))
        def masked(value):
            return "••••" + value[-2:] if len(value) > 4 else "••••"
        if serial.strip():
            display["firmware_serial"] = masked(serial)
        try:
            usb = dev.get_serial_number_string()
        except Exception:
            usb = None
        if isinstance(usb, str) and usb.strip():
            report["usb_serial_available"] = True
            display["usb_serial"] = masked(usb)
        advertised = desc.get("serial_number")
        matched = bool(report["usb_serial_available"] and (not advertised or advertised == usb))
        if matched and report["firmware_serial_available"]:
            report["normal_identity_check"] = "Available in normal mode"
            return result("checked", "Normal-mode identity available. Update-mode compatibility remains unverified.")
        if not report["usb_serial_available"] and not advertised and report["firmware_serial_available"]:
            report["normal_identity_check"] = "Available via device serial (USB serial absent)"
            return result("checked", "Device serial available. Updater must answer the identity query before transfer; support is untested and failure will stop the update after mode entry.")
        report["normal_identity_check"] = "Unavailable or inconsistent"
        return result("limited", "Required serial information is missing or inconsistent; protected updating may be blocked.")
    except Exception:
        # Exception messages may contain device paths, serials or raw responses.
        return result("unavailable", "Identity query failed; no update command was sent. Reconnect and retry.")
    finally:
        try:
            dev.close()
        except Exception:
            report.update(status="unavailable", detail="Could not close the diagnostic session cleanly; reconnect before retrying.")


def shared_report(snapshot):
    """Export only our defined fields; never display masks, paths or raw responses."""
    allowed = ("schema", "captured_at", "platform", "status", "model", "reported_revision",
               "firmware_variant", "identity_stable", "usb_serial_available",
               "firmware_serial_available", "normal_identity_check", "updater_identity_check",
               "serials_included", "interface_count", "detail")
    return json.dumps({k: snapshot["report"][k] for k in allowed if k in snapshot["report"]},
                      ensure_ascii=False, indent=2) + "\n"
