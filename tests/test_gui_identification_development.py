"""Real Tk button/queue tests with mocked enumeration and metadata; no device I/O."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import device_discovery as discovery
import firmware_detection as legacy
import firmware_inspection as inspection
from firmware_identity import codec, identity_catalog as catalog
import toprert_unified_gui as gui


def row(vid=0x04FE, pid=0x21, interface=2, path=b'private-mi_02'):
    return {'vendor_id': vid, 'product_id': pid, 'interface_number': interface, 'path': path}


def metadata(family='rt_only', identifier=0xBA90567B):
    text = catalog.envelope.encode_identity(codec.Identity(1, 1, family, identifier))[2:].decode('utf-16-le')
    resolved = catalog.resolve_text(text, expected_product=1, catalog_document=catalog.load_catalog())
    return {'status': resolved['status'], 'resolution': resolved,
            'timestamp_utc': '2026-10-17T00:00:00+00:00', 'worker_cleanup': 'reaped'}


class DiscoveryTests(unittest.TestCase):
    def scan(self, r3=(), hh=()):
        hid = Mock()
        hid.enumerate.side_effect = [r3, hh]
        result = discovery.scan(hid)
        self.assertEqual(hid.method_calls, [unittest.mock.call.enumerate(0x0853, 0x0311),
                                          unittest.mock.call.enumerate(0x04FE, 0)])
        return result

    def test_single_both_none_and_multiple_are_distinct(self):
        r3 = row(0x0853, 0x0311)
        self.assertEqual(self.scan([r3]).selected, 'r3s')
        self.assertEqual(self.scan(hh=[row()]).selected, 'hhkb')
        for r3s, hhs, word in (([r3], [row()], 'Both'), ([], [], 'No supported'),
                               ([r3, r3], [], 'Multiple'), ([], [row(), row()], 'Multiple')):
            result = self.scan(r3s, hhs)
            self.assertIsNone(result.selected)
            self.assertIn(word, result.message)

    def test_update_mode_never_selects_normal_keyboard(self):
        for rows in ([row(pid=0x20)], [row(pid=0x20), row()]):
            result = self.scan(hh=rows)
            self.assertIsNone(result.selected)
            self.assertEqual(result.hhkb_updater, 1)
            self.assertIn('update-mode', result.message)

    def test_conflicting_interfaces_and_wrong_vendor_are_rejected(self):
        for item in (row(interface=3), row(interface=2, path=b'mi_01'), row(vid=1),
                     row(pid=1), row(interface=True), row(interface='2')):
            self.assertEqual(self.scan(hh=[item]).hhkb, 0)

    def test_missing_interface_uses_windows_marker_only(self):
        for interface in (None, -1):
            self.assertEqual(self.scan(hh=[row(interface=interface)]).hhkb, 1)
            self.assertEqual(self.scan(hh=[row(interface=interface, path=b'no-marker')]).hhkb, 0)

    def test_dependency_and_enumeration_failure_hide_private_text(self):
        hid = Mock()
        hid.enumerate.side_effect = RuntimeError('PRIVATE-SERIAL-AND-PATH')
        result = discovery.scan(hid)
        self.assertFalse(result.available)
        self.assertNotIn('PRIVATE', result.message)
        self.assertIsNone(result.selected)


class InspectionTests(unittest.TestCase):
    def inspect(self, response):
        hhe = Mock()
        with tempfile.TemporaryDirectory(prefix='.inspection-test-', dir=Path(__file__).resolve().parents[2]) as folder, \
                patch.object(inspection.registry, 'DEFAULT_ROOT', Path(folder) / 'identity'), \
                patch.object(inspection.reader, 'probe_metadata', return_value=response) as read, \
                patch.object(inspection.legacy, 'inspect_hhkb') as old:
            result = inspection.inspect_hhkb(hhe)
            read.assert_called_once_with()
            return result, old

    def test_registered_rt_and_hold_show_development_id_without_release_or_settings_claim(self):
        for family, identifier in (('rt_only', 0xBA90567B), ('hold', 0xECC9B8A2)):
            result, old = self.inspect(metadata(family, identifier))
            old.assert_not_called()
            self.assertEqual(result.firmware_family, family)
            self.assertEqual(result.build_id, f'{identifier:08X}')
            self.assertEqual(result.build_channel, 'development')
            self.assertTrue(result.catalog_match)
            self.assertFalse(result.exact_version_available)
            self.assertFalse(result.stock_verified)
            self.assertFalse(result.rt_only_verified)
            self.assertIn('Development', legacy.display_title(result))
            report = json.loads(legacy.shared_report(result))
            self.assertEqual(report['metadata_status'], 'registered_build_claim')
            self.assertNotIn('PRIVATE', json.dumps(report))

    def test_unregistered_id_preserves_claim_but_never_borrows_version(self):
        result, old = self.inspect(metadata(identifier=0xDEADBEEF))
        self.assertEqual(result.identification_status, 'metadata_unregistered')
        self.assertIn('Unregistered', legacy.display_title(result))
        self.assertIsNone(result.build_channel)
        self.assertFalse(result.catalog_match)
        self.assertFalse(result.exact_version_available)
        old.assert_not_called()

    def test_catalog_mismatch_does_not_fall_back_or_reuse_registered_family(self):
        result, old = self.inspect(metadata('hold', 0xBA90567B))
        self.assertEqual(result.identification_status, 'metadata_mismatch')
        self.assertIsNone(result.build_id)
        self.assertEqual(result.firmware_family, 'unknown')
        old.assert_not_called()

    def test_legacy_fallback_only_after_worker_reaped_with_no_retry(self):
        old_result = legacy.ProbeResult('Legacy TopreRT', 'RT/HOLD not distinguished')
        for status in ('metadata_unavailable', 'platform_unavailable'):
            response = {'status': status, 'worker_cleanup': 'reaped', 'timestamp_utc': 'test'}
            with patch.object(inspection.reader, 'probe_metadata', return_value=response) as read, \
                    patch.object(inspection.legacy, 'inspect_hhkb', return_value=old_result) as old:
                result = inspection.inspect_hhkb(Mock())
                old.assert_called_once()
                read.assert_called_once()
                self.assertEqual(result.metadata_status, status)
                self.assertIsNone(result.build_id)

    def test_timeout_invalid_connection_change_and_missing_catalog_never_open_legacy(self):
        for status, cleanup in (('parent_timeout', 'terminated'), ('metadata_unavailable', 'termination_unconfirmed'),
                                ('invalid_metadata_response', 'reaped'), ('connection_changed', 'reaped'),
                                ('catalog_unavailable', 'not_started')):
            result, old = self.inspect({'status': status, 'worker_cleanup': cleanup, 'timestamp_utc': 'test'})
            old.assert_not_called()
            self.assertEqual(result.identification_status, 'metadata_unavailable')
            self.assertIsNone(result.build_id)


class TkIntegrationTests(unittest.TestCase):
    @contextmanager
    def app(self):
        original_init = gui.tk.Tk.__init__
        def hidden(root, *args, **kwargs):
            original_init(root, *args, **kwargs)
            root.withdraw()
        with patch.object(gui.tk.Tk, '__init__', hidden), \
                patch.object(gui.UnifiedGUI, 'after', return_value='test-timer'), \
                patch.object(gui.UnifiedGUI, '_auto_find_hhkb_stock'), \
                patch.object(gui.HHE, 'load_hid', side_effect=AssertionError('No physical HID allowed')), \
                patch.object(gui.messagebox, 'showinfo'):
            app = gui.UnifiedGUI()
            try:
                yield app
            finally:
                if app.worker and app.worker.is_alive():
                    app.worker.join(3)
                app.destroy()

    def detect(self, app, result):
        with patch.object(gui.DEVICE_DISCOVERY, 'scan', return_value=result) as scan:
            app.detect_btn.invoke()
            app.worker.join(2)
            app._poll()
            scan.assert_called_once_with()

    def test_actual_detect_button_selects_one_keyboard_and_is_not_firmware_inspection(self):
        with self.app() as app, patch.object(gui.FW_INSPECT, 'inspect_hhkb') as inspect:
            self.detect(app, discovery.Discovery(hhkb=1))
            self.assertEqual(app.platform.get(), gui.PLAT_HHKB)
            self.assertIn('Detected HHKB', app.status_line.get())
            self.assertIsNone(app.firmware_identification)
            inspect.assert_not_called()
            self.assertEqual(str(app.detect_btn.cget('state')), 'normal')

    def test_repeated_same_platform_detection_preserves_selected_file_profile_and_hold_slots(self):
        with self.app() as app:
            app.platform.set(gui.PLAT_HHKB)
            app.source_path = Path('selected-stock.hfb')
            app.release.set('0.12')
            app.repress.set('0.18')
            app.hh_slot_threshold[0].set('321')
            app.firmware_identification = legacy.ProbeResult('old', 'old')
            self.detect(app, discovery.Discovery(hhkb=1))
            self.assertEqual(app.source_path, Path('selected-stock.hfb'))
            self.assertEqual(app.release.get(), '0.12')
            self.assertEqual(app.repress.get(), '0.18')
            self.assertEqual(app.hh_slot_threshold[0].get(), '321')
            self.assertIsNone(app.firmware_identification)
            self.assertEqual(str(app.firmware_report_btn.cget('state')), 'disabled')

    def test_both_none_multiple_and_updater_preserve_manual_selection(self):
        with self.app() as app:
            for result in (discovery.Discovery(1, 1), discovery.Discovery(), discovery.Discovery(hhkb=2),
                           discovery.Discovery(hhkb_updater=1), discovery.Discovery(available=False)):
                before = app.platform.get()
                self.detect(app, result)
                self.assertEqual(app.platform.get(), before)
                self.assertEqual(app.status_line.get(), result.message)

    def test_detect_blocks_during_flash_observer_and_other_worker(self):
        with self.app() as app, patch.object(gui.DEVICE_DISCOVERY, 'scan') as scan:
            app.flash_active = True
            app.detect_btn.invoke()
            app.flash_active = False
            app.r3_observer_proc = Mock()
            app.r3_observer_proc.poll.return_value = None
            app.detect_btn.invoke()
            app.r3_observer_proc = None
            app.worker = Mock()
            app.worker.is_alive.return_value = True
            app.detect_btn.invoke()
            scan.assert_not_called()
            app.worker = None

    def test_detect_is_background_and_late_result_cannot_override_manual_platform_change(self):
        entered, release = threading.Event(), threading.Event()
        def delayed():
            entered.set()
            release.wait(3)
            return discovery.Discovery(hhkb=1)
        with self.app() as app, patch.object(gui.DEVICE_DISCOVERY, 'scan', side_effect=delayed):
            started = time.monotonic()
            app.detect_btn.invoke()
            try:
                self.assertLess(time.monotonic() - started, .5)
                self.assertTrue(entered.wait(1))
                app.platform.set(gui.PLAT_HHKB)
                app.platform.set(gui.PLAT_R3S)
            finally:
                release.set()
                app.worker.join(2)
            app._poll()
            self.assertEqual(app.platform.get(), gui.PLAT_R3S)

    def test_inspect_button_renders_build_and_saved_report_then_discards_stale_results(self):
        with self.app() as app:
            app.platform.set(gui.PLAT_HHKB)
            result, _ = InspectionTests().inspect(metadata())
            with patch.object(gui.FW_INSPECT, 'inspect_hhkb', return_value=result):
                app.inspect_btn.invoke()
                app.worker.join(2)
                app._poll()
            self.assertIn('RT-only · Development · BA90567B', app.installed_firmware.get())
            self.assertIn('Build ID: BA90567B', app.detect_detail.get())
            self.assertIn('Not assigned', app.detect_detail.get())
            self.assertEqual(app.firmware_identification, result)
            epoch = app._inspection_epoch
            app.platform.set(gui.PLAT_R3S)
            before = app.installed_firmware.get()
            app.q.put(('fw_inspection_result', (epoch, result)))
            app.q.put(('fw_inspection_error', (epoch, 'old error')))
            app._poll()
            self.assertIsNone(app.firmware_identification)
            self.assertEqual(app.installed_firmware.get(), before)


if __name__ == '__main__':
    unittest.main()
