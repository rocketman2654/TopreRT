import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hhkb_identity_probe as probe


def info(serial="PRIVATE-DEVICE", model="PD-KB800W"):
    return model.encode().ljust(20, b"\0") + b"A3\0\0" + serial.encode().ljust(16, b"\0")


class Device:
    def __init__(self, serial="PRIVATE-DEVICE", *, timeout=None, unstable=False):
        self.serial = serial
        self.timeout = timeout
        self.unstable = unstable
        self.closed = False
        self.commands = []
        self.reads = 0

    def open_path(self, path):
        pass

    def write(self, data):
        assert len(data) == 65 and data[:3] == b"\0\xaa\xaa"
        self.commands.append(data[3])
        return len(data)

    def read(self, size, timeout):
        command = self.commands[-1]
        if command == self.timeout:
            return b""
        payload = b""
        if command == 2:
            self.reads += 1
            payload = info("OTHER" if self.unstable and self.reads > 1 else self.serial)
        return bytes([0x55, 0x55, command, 0, 0, len(payload)]) + payload

    def close(self):
        self.closed = True


class Hid:
    def __init__(self, before=None, after=None, count=1):
        self.before = before or Device()
        self.after = after or Device()
        self.opens = 0
        self.count = count

    def enumerate(self, vid, pid):
        return [{"path": b"PRIVATE-PATH", "product_id": 0x21, "interface_number": 2}] * self.count

    def device(self):
        self.opens += 1
        return self.before if self.opens == 1 else self.after


class IdentityProbeTests(unittest.TestCase):
    def test_mode_marker_requires_exact_layout_and_never_claims_hardware_verification(self):
        for marker, expected in ((0, "application_candidate"), (1, "boot_updater_candidate"),
                                 (255, "unknown_marker")):
            evidence = probe.mode_marker_evidence(info().ljust(56, b"\0") + bytes([marker]))
            self.assertEqual(evidence["interpretation"], expected)
            self.assertEqual(evidence["marker"], marker)
            self.assertFalse(evidence["current_hardware_mapping_verified"])
        for size in (0, 40, 56, 58):
            evidence = probe.mode_marker_evidence(b"\0" * size)
            self.assertIsNone(evidence["marker"])
            self.assertEqual(evidence["interpretation"], "unavailable_for_this_payload_length")

    def test_marker_reporting_keeps_normal_probe_command_sequence_and_privacy(self):
        class FullIdentityDevice(Device):
            def read(self, size, timeout):
                result = super().read(size, timeout)
                if self.commands[-1] == 2:
                    return result[:5] + bytes([57]) + result[6:].ljust(57, b"\0")
                return result
        device = FullIdentityDevice()
        report = probe.run_probe(Hid(before=device))
        self.assertEqual(device.commands, [1, 2, 5, 6, 2, 5, 6])
        self.assertEqual(report["status"], "normal_identity_verified")
        self.assertEqual(report["initial_mode_marker_evidence"]["interpretation"], "application_candidate")
        self.assertFalse(report["updater_mode_independently_confirmed"])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_default_is_normal_only_and_report_omits_identifiers(self):
        hid = Hid()
        report = probe.run_probe(hid)
        self.assertEqual(report["status"], "normal_identity_verified")
        self.assertEqual(hid.before.commands, [1, 2, 5, 6, 2, 5, 6])
        self.assertEqual(hid.opens, 1)
        self.assertTrue(hid.before.closed)
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_all_unlisted_commands_and_wrong_bodies_are_blocked(self):
        for command in range(256):
            if command in (1, 2, 5, 6, 0xE0):
                continue
            dev = Device()
            with self.subTest(command=command), self.assertRaises(probe.ProbeFailure):
                probe.GuardedTransport(Mock()).request(dev, command)
            self.assertEqual(dev.commands, [])
        for command in (1, 2, 5, 6, 0xE0):
            dev = Device()
            with self.assertRaises(probe.ProbeFailure):
                probe.GuardedTransport(Mock()).request(dev, command, b"arbitrary payload")
            self.assertEqual(dev.commands, [])

    def test_e0_unarmed_and_second_attempt_are_blocked(self):
        transport = probe.GuardedTransport(Mock())
        dev = Device()
        with self.assertRaises(probe.ProbeFailure):
            transport.request(dev, 0xE0)
        transport.e0_armed = True
        transport.request(dev, 0xE0)
        with self.assertRaises(probe.ProbeFailure):
            transport.request(dev, 0xE0)
        self.assertEqual(dev.commands, [0xE0])

    def test_only_one_query02_after_e0(self):
        transport = probe.GuardedTransport(Mock())
        transport.e0_armed = True
        dev = Device()
        transport.request(dev, 0xE0)
        with self.assertRaises(probe.ProbeFailure):
            transport.request(dev, 1, b"\0")
        transport.request(dev, 2)
        with self.assertRaises(probe.ProbeFailure):
            transport.request(dev, 2)
        self.assertEqual(dev.commands, [0xE0, 2])

    def test_cancel_never_sends_e0(self):
        hid = Hid()
        report = probe.run_probe(hid, enter_updater=True, confirm=lambda: False)
        self.assertEqual(report["status"], "cancelled_before_e0")
        self.assertNotIn(0xE0, hid.before.commands)

    def test_match_is_not_reported_as_verified_update_or_normal_return(self):
        hid = Hid()
        report = probe.run_probe(hid, enter_updater=True, confirm=lambda: True, sleep=lambda _: None)
        self.assertTrue(report["identity_matches_after_e0"])
        self.assertFalse(report["normal_return_verified"])
        self.assertFalse(report["full_update_verified"])
        self.assertFalse(report["updater_mode_independently_confirmed"])
        self.assertEqual(hid.after.commands, [2])
        self.assertEqual(hid.before.commands.count(0xE0), 1)
        self.assertTrue(hid.before.closed and hid.after.closed)

    def test_mismatch_timeout_and_empty_serial_stop_after_single_query(self):
        for after in (Device("OTHER"), Device(timeout=2), Device("")):
            hid = Hid(after=after)
            report = probe.run_probe(hid, enter_updater=True, confirm=lambda: True, sleep=lambda _: None)
            self.assertEqual(report["status"], "stopped")
            self.assertEqual(after.commands, [2])
            self.assertTrue(after.closed)

    def test_e0_timeout_does_not_retry_or_open_updater(self):
        hid = Hid(before=Device(timeout=0xE0))
        report = probe.run_probe(hid, enter_updater=True, confirm=lambda: True, sleep=lambda _: None)
        self.assertTrue(report["e0_attempted"])
        self.assertFalse(report["e0_acknowledged"])
        self.assertEqual(hid.opens, 1)
        self.assertEqual(hid.before.commands.count(0xE0), 1)

    def test_multiple_devices_or_unstable_identity_stop_before_e0(self):
        for hid in (Hid(count=2), Hid(before=Device(unstable=True))):
            report = probe.run_probe(hid, enter_updater=True, confirm=lambda: True)
            self.assertEqual(report["status"], "stopped")
            self.assertNotIn(0xE0, hid.before.commands)

    def test_identity_changed_while_confirmation_open_stops_before_e0(self):
        hid = Hid()
        def confirm():
            hid.before.serial = "OTHER"
            return True
        report = probe.run_probe(hid, enter_updater=True, confirm=confirm)
        self.assertEqual(report["reason"], "identity_changed_before_e0")
        self.assertNotIn(0xE0, hid.before.commands)

    def test_report_failure_before_write_prevents_command(self):
        transport = probe.GuardedTransport(Mock(side_effect=OSError("PRIVATE-PATH")))
        transport.e0_armed = True
        dev = Device()
        with self.assertRaises(OSError):
            transport.request(dev, 0xE0)
        self.assertEqual(dev.commands, [])

    def test_device_errors_are_sanitized_and_closed(self):
        hid = Hid()
        hid.before.read = Mock(side_effect=OSError("PRIVATE-SERIAL PRIVATE-PATH"))
        report = probe.run_probe(hid)
        self.assertEqual(report["reason"], "device_or_report_io_failed")
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertTrue(hid.before.closed)

    def test_plan_is_required_and_no_report_is_overwritten(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            dest = Path(folder) / "report.json"
            self.assertEqual(probe.main(["--enter-updater", "--report", str(dest)]), 2)
            self.assertFalse(dest.exists())
            dest.write_text("existing", encoding="utf-8")
            self.assertEqual(probe.main(["--report", str(dest)]), 2)
            self.assertEqual(dest.read_text(), "existing")

    def test_unconfirmed_plan_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "plan.json"
            path.write_text(json.dumps({"model": "PD-KB800W", "confirmed_by_user": False,
                "official_source": "https://example.invalid", "return_steps": []}))
            with self.assertRaises(probe.ProbeFailure):
                probe.load_recovery_plan(path)

    def test_cli_default_with_mock_hid_saves_private_data_free_report(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            dest = Path(folder) / "report.json"
            hid = Hid()
            with patch.dict(sys.modules, {"hid": hid}):
                self.assertEqual(probe.main(["--report", str(dest)]), 0)
            report = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "normal_identity_verified")
            self.assertNotIn("PRIVATE", dest.read_text())
            self.assertNotIn(0xE0, hid.before.commands)


if __name__ == "__main__":
    unittest.main()
