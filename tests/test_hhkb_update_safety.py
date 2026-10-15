"""Offline regression tests. HID loading is replaced before any writer runs."""
import contextlib
import io
from pathlib import Path
import queue
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import toprert_unified_gui as gui
import hhkb_toprert_engine_v0_6 as engine
import hhkb_v013_validated_flasher_v0_1 as hold
from hhkb_update_identity import DeviceBinding, IdentityMismatch


def info(serial="FW-A", revision=b"A048", model="PD-KB800"):
    return model.encode().ljust(20, b"\0") + revision + serial.encode().ljust(16, b"\0")


class Device:
    def __init__(self, serial):
        self.serial = serial
        self.closed = False

    def get_serial_number_string(self):
        return self.serial

    def close(self):
        self.closed = True


class BindingTests(unittest.TestCase):
    def test_descriptor_handle_disagreement(self):
        with self.assertRaises(IdentityMismatch):
            DeviceBinding.capture({"serial_number": "B"}, Device("A"), info())

    def test_incomplete_and_empty_identity(self):
        for payload in (b"short", info(""), info(model="OTHER")):
            with self.subTest(payload=payload), self.assertRaises(IdentityMismatch):
                DeviceBinding.capture({}, Device("A"), payload)

    def test_missing_serial_api(self):
        binding = DeviceBinding.capture({}, object(), info())
        self.assertIsNone(binding.usb_serial)
        with self.assertRaises(IdentityMismatch):
            binding.verify_usb({}, object(), "Updater")

    def test_revision_can_change_but_model_cannot(self):
        binding = DeviceBinding.capture({}, Device("A"), info())
        binding.verify_firmware(info(revision=b"A049"))
        with self.assertRaises(IdentityMismatch):
            binding.verify_firmware(info(model="PD-KB801"))


class WriterTests(unittest.TestCase):
    def test_unexpected_ack_error_omits_raw_device_response(self):
        private = b"PRIVATE-SERIAL-1234"
        for request, packet in ((engine.req, engine.packet), (hold.request, hold.make_packet)):
            with self.subTest(writer=request.__module__):
                dev = Mock()
                dev.write.return_value = 65
                dev.read.return_value = private
                with self.assertRaises(Exception) as caught:
                    request(dev, packet(2), b"\x55\x55\x02\0\0")
                message = str(caught.exception)
                self.assertIn("02", message)
                self.assertNotIn(private.decode(), message)
                self.assertNotIn(private.hex(" "), message)

    def test_incomplete_write_stops_before_reading_ack_without_retry(self):
        for request, packet in ((engine.req, engine.packet), (hold.request, hold.make_packet)):
            for count in (-1, 0, 1, 64, 66, None):
                with self.subTest(writer=request.__module__, count=count):
                    dev = Mock()
                    dev.write.return_value = count
                    dev.read.return_value = bytes([0x55, 0x55, 0xE1, 0, 0, 0])
                    with self.assertRaisesRegex(Exception, "HID write incomplete"):
                        request(dev, packet(0xE1), bytes([0x55, 0x55, 0xE1, 0, 0, 0]))
                    dev.write.assert_called_once()
                    dev.read.assert_not_called()

    def test_complete_write_keeps_existing_ack_validation(self):
        for request, packet in ((engine.req, engine.packet), (hold.request, hold.make_packet)):
            with self.subTest(writer=request.__module__):
                dev = Mock()
                dev.write.return_value = 65
                ack = bytes([0x55, 0x55, 0xE1, 0, 0, 0])
                dev.read.return_value = ack
                self.assertEqual(request(dev, packet(0xE1), ack), ack)
                dev.write.assert_called_once_with(b"\0" + packet(0xE1))
                dev.read.return_value = b"invalid ACK"
                with self.assertRaises(Exception):
                    request(dev, packet(0xE1), ack)

    def test_multiple_devices_are_rejected_without_opening_any(self):
        hid = Mock()
        hid.enumerate.return_value = [
            {"path": b"A", "product_id": 0x21, "interface_number": 2},
            {"path": b"B", "product_id": 0x21, "interface_number": 2},
        ]
        for wait in (engine.wait_one, hold.wait_for_one_vendor):
            with self.subTest(wait=wait.__name__), self.assertRaisesRegex(Exception, "[Mm]ultiple"):
                wait(hid, 1)
        hid.device.assert_not_called()

    def test_truncated_identity_query_is_rejected(self):
        for response in (b"\x55\x55\x02\0\0", b"\x55\x55\x02\0\0\x28short"):
            with patch.object(engine, "req", return_value=response), self.assertRaises(engine.Reject):
                engine.query(None, 2)

    def run_writer(self, kind, serials=("A", "A", "A"), final_serial="FW-A", bad_ack=False,
                   updater_serial="FW-A", updater_query_fails=False):
        devices = [Device(s) for s in serials]
        descriptors = iter({"path": i, "vendor_id": 0x04FE, "product_id": 0x20 + i,
                            "serial_number": s} for i, s in enumerate(serials))
        trace = []
        opened = []
        output = io.StringIO()
        instance = types.SimpleNamespace(q=queue.Queue(), flash_t0=None, flash_rate=None)

        def open_device(hid, desc):
            device = devices[desc["path"]]
            opened.append(device)
            return device

        def payload(device):
            if device is devices[1]:
                if updater_query_fails:
                    raise RuntimeError("unsupported identity query")
                return info(updater_serial)
            return info(final_serial if device is devices[2] else "FW-A",
                        b"A049" if device is devices[2] else b"A048")

        def request(device, packet, prefix):
            trace.append((devices.index(device), packet[2]))
            return prefix + (b"\xff\xff" if bad_ack else b"\0\0")

        packets = (engine.packet(0xE1), [engine.packet(0xE2)], engine.packet(0xE3))
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(patch("builtins.input", return_value="YES"))
            stack.enter_context(patch.object(engine.time, "sleep", return_value=None))
            if kind == "hold":
                query_info = lambda d: {"payload": payload(d), "type": "PD-KB800",
                                       "revision": "A048", "serial": "FW-A", "tail": b""}
                empty = lambda d: {"payload": b""}
                replacements = dict(load_hid=lambda: None,
                    wait_for_one_vendor=lambda *a: next(descriptors), open_device=open_device,
                    capture_identity=lambda d: (query_info(d), empty(d), empty(d)),
                    query_info=query_info, query_dips=empty, query_mode=empty, request=request)
                stack.enter_context(patch.multiple(hold, **replacements))
                call = lambda: hold.do_flash({}, *packets)
            else:
                replacements = dict(load_hid=lambda: None, wait_one=lambda *a: next(descriptors),
                    open_dev=open_device, identity=lambda d: (payload(d), b"", b""),
                    query=lambda d, c: payload(d) if c == 2 else b"", req=request,
                    build_packets=lambda image: packets)
                stack.enter_context(patch.multiple(engine, **replacements))
                call = (lambda: engine.flash_image(b"", "YES", "test")) if kind == "cli" else (
                    lambda: gui.UnifiedGUI._hhkb_flash(instance, b""))
            error = None
            try:
                call()
            except Exception as exc:
                error = exc
        self.assertTrue(all(d.closed for d in opened))
        events = list(instance.q.queue)
        if kind == "hold":
            self.assertNotIn("FW-A", output.getvalue())
            self.assertNotIn("Info tail", output.getvalue())
        success = "FLASH SEQUENCE COMPLETED." in output.getvalue() or (
            "log", "Reconnect: PASS") in events
        return trace, error, success

    def test_same_device_different_paths_pids_and_revision_succeeds(self):
        for kind in ("gui", "cli", "hold"):
            with self.subTest(kind=kind):
                trace, error, success = self.run_writer(kind)
                self.assertIsNone(error)
                self.assertTrue(success)
                self.assertEqual([cmd for _, cmd in trace if cmd >= 0xE0], [0xE0, 0xE1, 0xE2, 0xE3])

    def test_no_usb_serial_uses_vendor_identity_across_all_writers(self):
        for kind in ("gui", "cli", "hold"):
            with self.subTest(kind=kind):
                trace, error, success = self.run_writer(kind, serials=("", "", ""))
                self.assertIsNone(error)
                self.assertTrue(success)
                self.assertIn((1, 0xE3), trace)

    def test_vendor_fallback_rejects_replacement_missing_and_unsupported_query_before_e1(self):
        for kind in ("gui", "cli", "hold"):
            for serial, fails in (("OTHER", False), ("", False), ("FW-A", True)):
                with self.subTest(kind=kind, serial=serial, fails=fails):
                    trace, error, success = self.run_writer(kind, serials=("", "", ""),
                        updater_serial=serial, updater_query_fails=fails)
                    self.assertIsInstance(error, IdentityMismatch)
                    self.assertEqual(trace, [(0, 0xE0)])
                    self.assertFalse(success)

    def test_vendor_fallback_rejects_final_replacement(self):
        for kind in ("gui", "cli", "hold"):
            with self.subTest(kind=kind):
                _, error, success = self.run_writer(kind, serials=("", "", ""), final_serial="OTHER")
                self.assertIsInstance(error, IdentityMismatch)
                self.assertFalse(success)

    def test_replaced_or_unidentifiable_updater_never_receives_e1(self):
        for kind in ("gui", "cli", "hold"):
            for updater in ("B", ""):
                with self.subTest(kind=kind, updater=updater):
                    trace, error, success = self.run_writer(kind, serials=("A", updater, "A"))
                    self.assertIsInstance(error, IdentityMismatch)
                    self.assertEqual(trace, [(0, 0xE0)])
                    self.assertFalse(success)

    def test_final_usb_or_firmware_mismatch_never_reports_success(self):
        for kind in ("gui", "cli", "hold"):
            for serials, fwserial in ((("A", "A", "B"), "FW-A"), (("A", "A", "A"), "FW-B")):
                with self.subTest(kind=kind, serials=serials, fwserial=fwserial):
                    _, error, success = self.run_writer(kind, serials, fwserial)
                    self.assertIsInstance(error, IdentityMismatch)
                    self.assertFalse(success)

    def test_bad_ack_never_sends_finalize(self):
        for kind in ("gui", "cli", "hold"):
            with self.subTest(kind=kind):
                trace, error, success = self.run_writer(kind, bad_ack=True)
                self.assertIsNotNone(error)
                self.assertNotIn(0xE3, [cmd for _, cmd in trace])
                self.assertFalse(success)


class LifecycleTests(unittest.TestCase):
    def make_gui(self):
        instance = types.SimpleNamespace(flash_active=False, _closing=False, worker=None,
            r3_observer_proc=None, q=queue.Queue(), stop_event=threading.Event(),
            _flash_widget_states=[], after=Mock(), destroy=Mock(), _lock_flash_controls=Mock(),
            firmware_identification=object(), firmware_report_btn=Mock(),
            installed_firmware=Mock(), detect_detail=Mock(),
            _hh_slots_changed=Mock(), _live_validate=Mock())
        for name in ("_operation_available", "_worker", "_worker_wrap", "_finish_flash",
                     "_on_close", "_close_when_idle"):
            setattr(instance, name, types.MethodType(getattr(gui.UnifiedGUI, name), instance))
        return instance

    def test_close_and_duplicate_start_blocked_until_worker_exits(self):
        instance = self.make_gui()
        entered, release = threading.Event(), threading.Event()
        def work():
            entered.set()
            release.wait(5)
        with patch.object(gui.messagebox, "showinfo"):
            try:
                self.assertTrue(instance._worker(work, flash=True))
                self.assertTrue(entered.wait(2))
                self.assertFalse(instance.worker.daemon)
                instance._on_close()
                instance.destroy.assert_not_called()
                self.assertFalse(instance._worker(lambda: None, flash=True))
                instance._finish_flash()
                self.assertTrue(instance.flash_active)
            finally:
                release.set()
                instance.worker.join(2)
        instance._finish_flash()
        self.assertFalse(instance.flash_active)
        self.assertIsNone(instance.firmware_identification)
        instance.firmware_report_btn.configure.assert_called_with(state="disabled")
        instance._hh_slots_changed.assert_called_once()
        instance._on_close()
        instance.destroy.assert_called_once()

    def test_failure_always_signals_finish_and_allows_unlock(self):
        instance = self.make_gui()
        def fail():
            raise RuntimeError("transfer failed")
        instance._worker(fail, flash=True)
        instance.worker.join(2)
        self.assertEqual(list(instance.q.queue), [("error", "transfer failed"), ("flash_finished", None)])
        instance._finish_flash()
        self.assertFalse(instance.flash_active)
        self.assertIsNone(instance.firmware_identification)
        instance.firmware_report_btn.configure.assert_called_with(state="disabled")

    def test_thread_start_failure_releases_protection(self):
        instance = self.make_gui()
        with patch.object(gui.threading.Thread, "start", side_effect=RuntimeError("cannot start")):
            with self.assertRaisesRegex(RuntimeError, "cannot start"):
                instance._worker(lambda: None, flash=True)
        self.assertFalse(instance.flash_active)
        instance._hh_slots_changed.assert_called_once()

    def test_stop_targets_running_observer_without_platform_selection(self):
        instance = self.make_gui()
        instance.r3_observer_proc = Mock()
        instance.r3_observer_proc.poll.return_value = None
        instance.r3_stop_file = Mock()
        instance.observer_state = Mock()
        gui.UnifiedGUI.stop_observer(instance)
        self.assertTrue(instance.stop_event.is_set())
        instance.r3_stop_file.write_text.assert_called_once_with("stop", encoding="ascii")
        instance.r3_observer_proc.terminate.assert_not_called()

    def test_live_observer_prevents_flash(self):
        instance = self.make_gui()
        instance.r3_observer_proc = Mock()
        instance.r3_observer_proc.poll.return_value = None
        with patch.object(gui.messagebox, "showinfo"):
            self.assertFalse(instance._worker(lambda: None, flash=True))
        self.assertFalse(instance.flash_active)

    def test_close_waits_for_nonflash_worker_and_blocks_new_work(self):
        instance = self.make_gui()
        instance.worker = Mock()
        instance.worker.is_alive.return_value = True
        instance._on_close()
        self.assertTrue(instance.stop_event.is_set())
        instance.destroy.assert_not_called()
        with patch.object(gui.messagebox, "showinfo"):
            self.assertFalse(instance._worker(lambda: None, flash=True))
        instance.worker.is_alive.return_value = False
        instance._close_when_idle()
        instance.destroy.assert_called_once()

    def test_hold_child_is_waited_for_even_if_output_read_fails(self):
        instance = self.make_gui()
        process = Mock()
        process.poll.return_value = None
        process.stdout = Mock()
        def broken_output():
            yield "E1: start..."
            raise OSError("output pipe failure")
        process.stdout.__iter__ = Mock(return_value=broken_output())
        baseline = Mock()
        baseline.exists.return_value = True
        with patch.object(gui.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(OSError, "output pipe failure"):
                gui.UnifiedGUI._hh_slots_flash_worker(instance, "candidate", "sha", "token", baseline)
        process.communicate.assert_called_once()
        process.wait.assert_called_once()
        process.terminate.assert_not_called()
        process.stdout.close.assert_called_once()
        self.assertNotIn(("hh_flash_done", None), list(instance.q.queue))

    def test_real_widgets_lock_and_restore_without_hid(self):
        original_init = gui.tk.Tk.__init__
        def hidden_init(root, *args, **kwargs):
            original_init(root, *args, **kwargs)
            root.withdraw()
        release = threading.Event()
        with patch.object(gui.tk.Tk, "__init__", hidden_init), \
             patch.object(gui.UnifiedGUI, "_detect_platform"), \
             patch.object(engine, "load_hid", side_effect=AssertionError("No HID in GUI test")):
            root = gui.UnifiedGUI()
            try:
                root.firmware_identification = gui.FW_DETECT.ProbeResult("Legacy TopreRT", "old result")
                root.installed_firmware.set("Legacy TopreRT")
                root.firmware_report_btn.configure(state="normal")
                root._worker(lambda: release.wait(5), flash=True)
                self.assertIsNone(root.firmware_identification)
                states = list(root._flash_widget_states)
                self.assertGreater(len(states), 10)
                self.assertTrue(all(str(w.cget("state")) == "disabled" for w, _ in states))
                root._live_validate()
                self.assertEqual(str(root.apply_btn.cget("state")), "disabled")
                release.set()
                root.worker.join(2)
                root._poll()
                self.assertFalse(root.flash_active)
                self.assertEqual(str(root.inspect_btn.cget("state")), "normal")
                self.assertEqual(str(root.hh_slots_flash_btn.cget("state")), "disabled")
                self.assertEqual(str(root.firmware_report_btn.cget("state")), "disabled")
                self.assertIn("Not verified", root.installed_firmware.get())
                self.assertIn("Inspect firmware", root.detect_detail.get())
                with patch.object(gui.filedialog, "asksaveasfilename") as save:
                    root.save_firmware_identification()
                    save.assert_not_called()
                fresh = gui.FW_DETECT.ProbeResult("Unknown", "fresh query")
                root.q.put(("fw_detect_result", fresh))
                root._poll()
                self.assertIs(root.firmware_identification, fresh)
                self.assertEqual(str(root.firmware_report_btn.cget("state")), "normal")
                self.assertEqual(root._flash_widget_states, [])
            finally:
                release.set()
                if root.worker:
                    root.worker.join(2)
                for timer in root.tk.call("after", "info"):
                    root.after_cancel(timer)
                root.destroy()


if __name__ == "__main__":
    unittest.main()
