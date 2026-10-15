"""Experimental identity-only HHKB probe. Default mode never sends E0.

This module does not import a writer or accept firmware data. Its only HID
write boundary enforces a fixed command/body allowlist and a one-shot E0 gate.
E0 changes device state; a successful query afterwards is NOT a flash test.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

VID = 0x04FE
PIDS = {0x20, 0x21, 0x22}
CONFIRMATION = "ENTER HHKB UPDATE MODE ONCE"


class ProbeFailure(RuntimeError):
    """Only fixed, non-identifying reason codes are exposed in reports."""


def mode_marker_evidence(payload):
    """Report a static-analysis candidate; never use it as update clearance."""
    if len(payload) != 57:
        return {"interpretation": "unavailable_for_this_payload_length",
                "marker": None, "current_hardware_mapping_verified": False}
    marker = payload[56]
    return {"interpretation": {0: "application_candidate", 1: "boot_updater_candidate"}.get(
                marker, "unknown_marker"),
            "marker": marker, "current_hardware_mapping_verified": False}


def parse_identity(payload):
    if len(payload) < 40:
        raise ProbeFailure("incomplete_identity")
    try:
        model = payload[:20].split(b"\0", 1)[0].decode("ascii")
        serial = payload[24:40].split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError:
        raise ProbeFailure("invalid_identity") from None
    # This first harness is deliberately restricted to the user's validated model.
    if model != "PD-KB800W" or not serial.strip():
        raise ProbeFailure("unsupported_model_or_missing_device_serial")
    return model, serial


class GuardedTransport:
    def __init__(self, record):
        self.record = record
        self.e0_armed = False
        self.e0_attempted = False
        self.updater_query_attempted = False
        self.failed = False

    def request(self, dev, command, body=b""):
        allowed = {0x01: b"\0", 0x02: b"", 0x05: b"", 0x06: b"", 0xE0: b""}
        if self.failed or command not in allowed or body != allowed[command]:
            raise ProbeFailure("command_blocked")
        if command == 0xE0:
            if not self.e0_armed or self.e0_attempted:
                raise ProbeFailure("mode_entry_not_armed_or_already_attempted")
            self.e0_attempted = True
        elif self.e0_attempted:
            if command != 0x02 or self.updater_query_attempted:
                raise ProbeFailure("only_one_identity_query_allowed_after_e0")
            self.updater_query_attempted = True
        packet = bytes([0xAA, 0xAA, command, 0, len(body)]) + body
        packet = b"\0" + packet.ljust(64, b"\0")
        # Persist intent before hardware access; failure prevents the write.
        self.record(command, "attempted")
        try:
            if dev.write(packet) != len(packet):
                raise ProbeFailure("hid_write_incomplete")
            response = bytes(dev.read(64, 1500))
            if not response:
                raise ProbeFailure("response_timeout")
            if len(response) < 6 or response[:5] != bytes([0x55, 0x55, command, 0, 0]):
                raise ProbeFailure("unexpected_response")
            length = response[5]
            if length > 58 or len(response) < 6 + length:
                raise ProbeFailure("truncated_response")
            if command in (0x01, 0xE0) and length != 0:
                raise ProbeFailure("unexpected_ack_length")
        except BaseException:
            self.failed = True
            raise
        self.record(command, "response_valid")
        return response[6:6 + length]


def one_device(hid):
    rows = []
    for desc in hid.enumerate(VID, 0):
        path = desc.get("path", b"")
        text = path.decode(errors="ignore") if isinstance(path, bytes) else str(path)
        if desc.get("product_id") in PIDS and (desc.get("interface_number") == 2 or "mi_02" in text.lower()):
            rows.append(desc)
    if len(rows) != 1:
        raise ProbeFailure("expected_exactly_one_supported_interface")
    return rows[0]


def open_device(hid, desc):
    dev = hid.device()
    try:
        dev.open_path(desc["path"])
    except BaseException:
        dev.close()
        raise
    return dev


def run_probe(hid, *, enter_updater=False, confirm=None, checkpoint=lambda report: None,
              sleep=time.sleep, capture_binding=None):
    report = {"schema": "toprert-identity-probe-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "mode": "enter-updater-once" if enter_updater else "normal-only",
        "status": "starting", "normal_identity_stable": False,
        "e0_attempted": False, "e0_acknowledged": False,
        "identity_matches_after_e0": None, "updater_mode_independently_confirmed": False,
        "normal_return_verified": False, "full_update_verified": False,
        "serials_included": False, "commands": []}
    def record(command, result):
        if command == 0xE0 and result == "attempted":
            report["e0_attempted"] = True
        report["commands"].append({"command": f"{command:02X}", "result": result})
        checkpoint(report)
    transport = GuardedTransport(record)
    dev = None
    try:
        checkpoint(report)
        desc = one_device(hid)
        dev = open_device(hid, desc)
        transport.request(dev, 0x01, b"\0")
        first = tuple(transport.request(dev, command) for command in (2, 5, 6))
        second = tuple(transport.request(dev, command) for command in (2, 5, 6))
        if first != second:
            raise ProbeFailure("normal_identity_changed")
        original = parse_identity(first[0])
        report.update(model=original[0], normal_identity_stable=True, status="normal_identity_verified",
                      initial_mode_marker_evidence=mode_marker_evidence(first[0]))
        checkpoint(report)
        if not enter_updater:
            if capture_binding is not None:
                capture_binding(first[0])
            return report
        if confirm is None or not confirm():
            report["status"] = "cancelled_before_e0"
            return report
        # Re-read immediately after the human prompt, before mode entry.
        if tuple(transport.request(dev, c) for c in (2, 5, 6)) != first:
            raise ProbeFailure("identity_changed_before_e0")
        transport.e0_armed = True
        transport.request(dev, 0xE0)
        report["e0_acknowledged"] = True
        checkpoint(report)
        dev.close()
        dev = None
        sleep(10)  # Same initial wait as the legacy writer; no mode-entry retry.
        desc = one_device(hid)
        dev = open_device(hid, desc)
        current_payload = transport.request(dev, 0x02)
        current = parse_identity(current_payload)
        report["after_e0_mode_marker_evidence"] = mode_marker_evidence(current_payload)
        report["identity_matches_after_e0"] = current == original
        if current != original:
            raise ProbeFailure("different_device_identity_after_e0")
        report["status"] = "identity_matched_after_e0_return_not_verified"
        return report
    except ProbeFailure as exc:
        report.update(status="stopped", reason=str(exc))
        return report
    except KeyboardInterrupt:
        report.update(status="interrupted", reason="user_interrupt_no_automatic_recovery")
        return report
    except Exception:
        report.update(status="stopped", reason="device_or_report_io_failed")
        return report
    finally:
        if dev is not None:
            try:
                dev.close()
            except Exception:
                report.update(status="stopped", reason="device_close_failed")
        checkpoint(report)


def load_recovery_plan(path):
    data = Path(path).read_bytes()
    plan = json.loads(data)
    if (plan.get("model") != "PD-KB800W" or plan.get("confirmed_by_user") is not True
            or not isinstance(plan.get("official_source"), str)
            or not plan["official_source"].startswith("https://")
            or not isinstance(plan.get("return_steps"), list)
            or not plan["return_steps"]
            or not all(isinstance(x, str) and x.strip() for x in plan["return_steps"])):
        raise ProbeFailure("recovery_plan_not_confirmed")
    # User acknowledgment, not automatic validation of a recovery procedure.
    return hashlib.sha256(data).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="new JSON output path; existing files are not overwritten")
    parser.add_argument("--enter-updater", action="store_true", help="EXPERIMENTAL: send E0 once after interactive confirmation")
    parser.add_argument("--recovery-plan", type=Path, help="user-confirmed recovery-plan JSON; required for E0")
    args = parser.parse_args(argv)
    try:
        plan_sha = None
        if args.enter_updater:
            if args.recovery_plan is None:
                raise ProbeFailure("recovery_plan_required_before_mode_entry")
            plan_sha = load_recovery_plan(args.recovery_plan)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as out:
            out.write('{"status":"reserved_not_started"}\n')
        def save(report):
            if plan_sha:
                report["user_confirmed_recovery_plan_sha256"] = plan_sha
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.report.parent,
                                                 prefix="probe-", suffix=".tmp", delete=False) as out:
                    temporary = Path(out.name)
                    json.dump(report, out, ensure_ascii=False, indent=2)
                    out.flush()
                    os.fsync(out.fileno())
                temporary.replace(args.report)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        def confirm():
            print("E0 can change persistent boot state before any firmware transfer.")
            print("It may leave the keyboard in update mode; power cycling is not a verified return method.")
            print("This tool cannot restore normal mode. No firmware transfer is implemented.")
            print("The supplied recovery plan is your acknowledgment, not a tool-verified procedure.")
            return input(f'Type exactly "{CONFIRMATION}": ') == CONFIRMATION
        import hid
        report = run_probe(hid, enter_updater=args.enter_updater, confirm=confirm, checkpoint=save)
        print("Result:", report["status"])
        if "initial_mode_marker_evidence" in report:
            print("Identity mode marker:", report["initial_mode_marker_evidence"]["interpretation"],
                  "(experimental static interpretation)")
        print("Report saved:", args.report.name)
        if report["e0_attempted"]:
            print("Device mode may have changed. Normal return and full update are NOT verified.")
        return 0 if report["status"] == "normal_identity_verified" else 2
    except Exception:
        print("Probe could not start/save. Check dependency, recovery plan and a new writable report path.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
