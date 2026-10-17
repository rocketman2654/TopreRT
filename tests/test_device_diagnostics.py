import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import device_diagnostics as diag
import toprert_unified_gui as gui


class FakeDevice:
    def __init__(self, usb="PRIVATE-USB-123456", serial="PRIVATE-FW-12345"):
        self.usb = usb
        self.serial = serial
        self.commands = []
        self.closed = False
        self.broken = False
        self.changed = False

    def write(self, data):
        self.commands.append(data[3])  # HID report ID then protocol header.
        return len(data)

    def read(self, size, timeout):
        if self.broken:
            raise OSError("PRIVATE-PATH PRIVATE-USB-123456")
        command = self.commands[-1]
        payload = b""
        if command == 2:
            model = b"PD-KB800" if not (self.changed and len(self.commands) > 4) else b"PD-KB801"
            payload = model.ljust(20, b"\0") + b"A048" + self.serial.encode().ljust(16, b"\0")
        return bytes([0x55, 0x55, command, 0, 0, len(payload)]) + payload

    def get_serial_number_string(self):
        return self.usb

    def close(self):
        self.closed = True


class DiagnosticsTests(unittest.TestCase):
    def test_library_failure_is_distinct_from_enumeration_failure(self):
        with patch.object(gui.HHE, "load_hid", side_effect=ImportError("PRIVATE-PATH")):
            snapshot = diag.collect_hhkb(gui.HHE)
        self.assertIn("Setup_Demo.bat", snapshot["report"]["detail"])
        self.assertNotIn("PRIVATE", diag.shared_report(snapshot))
        with patch.object(gui.HHE, "load_hid", return_value=object()), \
             patch.object(gui.HHE, "enum_vendor", side_effect=OSError("PRIVATE-PATH")):
            snapshot = diag.collect_hhkb(gui.HHE)
        self.assertIn("enumeration failed", snapshot["report"]["detail"])
        self.assertNotIn("PRIVATE", diag.shared_report(snapshot))

    def collect(self, device, count=1, advertised=None):
        descriptor = {"path": "PRIVATE-PATH", "serial_number": advertised or device.usb}
        with patch.object(gui.HHE, "load_hid", return_value=object()), \
             patch.object(gui.HHE, "enum_vendor", return_value=[descriptor] * count), \
             patch.object(gui.HHE, "open_dev", return_value=device) as opening:
            result = diag.collect_hhkb(gui.HHE)
            if count != 1:
                opening.assert_not_called()
        return result

    def test_read_only_protocol_and_private_export(self):
        device = FakeDevice()
        snapshot = self.collect(device)
        self.assertEqual(device.commands, [1, 2, 5, 6, 2, 5, 6])
        self.assertTrue(device.closed)
        self.assertEqual(snapshot["report"]["status"], "checked")
        self.assertEqual(snapshot["report"]["reported_revision"], "A048")
        self.assertEqual(snapshot["display"]["usb_serial"], "••••56")
        text = diag.shared_report(snapshot)
        for secret in (device.usb, device.serial, "PRIVATE-PATH", "••••56", "••••45"):
            self.assertNotIn(secret, text)
        report = json.loads(text)
        self.assertFalse(report["serials_included"])
        self.assertIn("Not tested", report["updater_identity_check"])

    def test_zero_and_multiple_devices_never_open(self):
        for count in (0, 2):
            device = FakeDevice()
            self.assertEqual(self.collect(device, count)["report"]["status"], "unavailable")
            self.assertEqual(device.commands, [])

    def test_missing_and_mismatched_serial_do_not_claim_ready(self):
        for device, advertised in ((FakeDevice(serial=""), None),
                                   (FakeDevice(), "OTHER")):
            snapshot = self.collect(device, advertised=advertised)
            self.assertEqual(snapshot["report"]["status"], "limited")
            self.assertTrue(device.closed)

    def test_device_serial_available_without_usb_serial(self):
        snapshot = self.collect(FakeDevice(usb=""))
        self.assertEqual(snapshot["report"]["status"], "checked")
        self.assertIn("via device serial", snapshot["report"]["normal_identity_check"])
        self.assertIn("untested", snapshot["report"]["detail"])

    def test_inspect_rejection_preserves_button_and_can_retry(self):
        import types
        app = types.SimpleNamespace(platform=Mock(), worker=None, installed_firmware=Mock(),
            detect_detail=Mock(), inspect_btn=Mock(), firmware_report_btn=Mock(), _operation_available=Mock(return_value=False),
            _worker=Mock(return_value=False))
        app.platform.get.return_value = gui.PLAT_HHKB
        gui.UnifiedGUI.inspect_installed_firmware(app)
        app.inspect_btn.configure.assert_not_called()
        app.installed_firmware.set.assert_not_called()
        app._operation_available.return_value = True
        gui.UnifiedGUI.inspect_installed_firmware(app)
        self.assertEqual(app.inspect_btn.configure.call_args.kwargs, {"state": "normal"})
        app._worker.side_effect = RuntimeError("thread failed")
        with self.assertRaises(RuntimeError):
            gui.UnifiedGUI.inspect_installed_firmware(app)
        self.assertEqual(app.inspect_btn.configure.call_args.kwargs, {"state": "normal"})

    def test_query_error_hides_raw_exception_and_closes(self):
        device = FakeDevice()
        device.broken = True
        snapshot = self.collect(device)
        self.assertEqual(snapshot["report"]["status"], "unavailable")
        self.assertNotIn("PRIVATE", diag.shared_report(snapshot))
        self.assertTrue(device.closed)

    def test_identity_changes_are_reported(self):
        device = FakeDevice()
        device.changed = True
        self.assertEqual(self.collect(device)["report"]["status"], "unstable")

    def test_close_error_is_sanitized(self):
        device = FakeDevice()
        device.close = Mock(side_effect=OSError("PRIVATE-PATH"))
        snapshot = self.collect(device)
        self.assertEqual(snapshot["report"]["status"], "unavailable")
        self.assertNotIn("PRIVATE", diag.shared_report(snapshot))

    def test_real_diagnostic_window_and_save(self):
        snapshot = self.collect(FakeDevice())
        original_init = gui.tk.Tk.__init__
        def hidden_init(root, *args, **kwargs):
            original_init(root, *args, **kwargs)
            root.withdraw()
        with patch.object(gui.tk.Tk, "__init__", hidden_init), \
             patch.object(gui.UnifiedGUI, "_detect_platform"), \
             patch.object(gui.DEVICE_DIAG, "collect_hhkb", return_value=snapshot) as collect:
            root = gui.UnifiedGUI()
            try:
                root.platform.set(gui.PLAT_HHKB)
                root.r3_observer_proc = Mock()
                root.r3_observer_proc.poll.return_value = None
                previous_label = root.installed_firmware.get()
                with patch.object(gui.messagebox, "showinfo"):
                    root.inspect_installed_firmware()
                self.assertEqual(str(root.inspect_btn.cget("state")), "normal")
                self.assertEqual(root.installed_firmware.get(), previous_label)
                root.r3_observer_proc = None
                from dataclasses import replace
                identification = replace(gui.FW_DETECT.classify_responses(
                    gui.FW_DETECT.RT_OBSERVER_PREFIX.ljust(16, b"\0"), None, "PD-KB800W"),
                    reported_revision="A3")
                root.q.put(("fw_detect_result", identification))
                root._poll()
                self.assertIn("Exact TopreRT version: Unknown", root.detect_detail.get())
                self.assertIn("RT/HOLD not distinguished", root.installed_firmware.get())
                self.assertEqual(str(root.firmware_report_btn.cget("state")), "normal")
                with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
                    report_path = Path(folder) / "identification.json"
                    with patch.object(gui.filedialog, "asksaveasfilename", return_value=str(report_path)):
                        root.save_firmware_identification()
                    self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["reported_revision"], "A3")
                    self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["firmware_family"], "toprert_unspecified")
                root.platform.set(gui.PLAT_R3S)
                self.assertIsNone(root.firmware_identification)
                self.assertEqual(str(root.firmware_report_btn.cget("state")), "disabled")
                root.platform.set(gui.PLAT_HHKB)
                root.inspect_device_diagnostics()
                root.worker.join(2)
                root._poll()
                collect.assert_called_once_with(gui.HHE)
                window = next(w for w in root.winfo_children() if isinstance(w, gui.tk.Toplevel))
                window.withdraw()
                body = window.winfo_children()[0]
                text = next(w for w in body.winfo_children() if isinstance(w, gui.tk.Text))
                self.assertIn("PD-KB800", text.get("1.0", "end"))
                self.assertNotIn("PRIVATE", text.get("1.0", "end"))
                buttons = body.winfo_children()[-1].winfo_children()
                with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
                    path = Path(directory) / "report.json"
                    with patch.object(gui.filedialog, "asksaveasfilename", return_value=str(path)), \
                         patch.object(gui.messagebox, "showinfo"):
                        buttons[0].invoke()
                    self.assertEqual(json.loads(path.read_text(encoding="utf-8")), snapshot["report"])
                root._lock_flash_controls()
                window.destroy()
                # Closing a diagnostic window cannot invalidate the update lock's widgets.
                for widget, state in root._flash_widget_states:
                    widget.configure(state=state)
            finally:
                for timer in root.tk.call("after", "info"):
                    root.after_cancel(timer)
                root.destroy()


if __name__ == "__main__":
    unittest.main()
