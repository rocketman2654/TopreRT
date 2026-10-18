"""History integration tests. No HID access or real firmware operation."""
import contextlib
import hashlib
import json
from pathlib import Path
import queue
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch,PropertyMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import toprert_unified_gui as gui


class HistoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='.history-gui-',dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name); self.path=self.folder/'install_history.json'
        self.stack=self.enterContext(contextlib.ExitStack())
        self.stack.enter_context(patch.object(gui.HHE,'load_hid',side_effect=AssertionError('No HID allowed')))
        self.stack.enter_context(patch.object(gui.HHE,'validate_stock'))
        self.stack.enter_context(patch.object(gui.HHE,'validate_candidate'))
        self.stack.enter_context(patch.object(gui.HHE,'build',return_value=b'exact-RT-bytes'))
        self.stack.enter_context(patch.object(gui.HH_ID,'build_rt',return_value=(b'exact-RT-bytes',{'identity':{'build_id':1}})))
        self.stack.enter_context(patch.object(gui.HH_ID,'validate'))
        self.stack.enter_context(patch.object(gui.BUILD_REGISTRY,'write_build'))
        self.stack.enter_context(patch.object(gui.HHE,'write_manifest'))
        self.stack.enter_context(patch.object(gui.messagebox,'askyesno',return_value=True))
        self.stack.enter_context(patch.object(gui.messagebox,'showinfo'))
        self.stack.enter_context(patch.object(gui.messagebox,'showerror'))

    def fake(self):
        app=types.SimpleNamespace(source_path=Mock(),source_valid=True,output_dir=self.folder,
            q=queue.Queue(),progress={},progress_text=Mock(),_busy=Mock(),_worker=Mock(),
            _profile_values=Mock(return_value=(.1,.15,60,90)),_hhkb_flash=Mock(return_value='PD-KB800W'),
            history_path=self.path,platform=Mock(),_operation_available=Mock(return_value=True),
            status_line=Mock(),_append=Mock())
        app.platform.get.return_value=gui.PLAT_HHKB
        app.source_path.read_bytes.return_value=b'exact-stock-bytes'
        app.source_path.stem='stock'
        app._record_operation_history=lambda **kw: gui.UnifiedGUI._record_operation_history(app,**kw)
        return app

    def test_rt_history_is_written_after_success_with_exact_used_bytes(self):
        app=self.fake(); gui.UnifiedGUI._apply_hhkb(app)
        self.assertFalse(self.path.exists())
        app._worker.call_args.args[0]()
        app._hhkb_flash.assert_called_once_with(b'exact-RT-bytes')
        row=gui.INSTALL_HISTORY.load_history(self.path)[0]
        self.assertEqual((row['event'],row['intended_mode'],row['model']),('installed','rt','PD-KB800W'))
        self.assertEqual(row['firmware_sha256'],hashlib.sha256(b'exact-RT-bytes').hexdigest())
        self.assertEqual(row['settings']['release_raw'],60)
        self.assertEqual(row['application_build'],gui.APP_BUILD)
        self.assertEqual(row['application_channel'],'release')
        self.assertFalse(row['device_firmware_verified'])

    def test_failed_or_cancelled_rt_install_does_not_claim_success_in_history(self):
        app=self.fake(); app._hhkb_flash.side_effect=RuntimeError('update failed')
        gui.UnifiedGUI._apply_hhkb(app)
        with self.assertRaises(RuntimeError): app._worker.call_args.args[0]()
        self.assertFalse(self.path.exists())
        with patch.object(gui.messagebox,'askyesno',return_value=False):
            app=self.fake(); gui.UnifiedGUI._apply_hhkb(app)
        app._worker.assert_not_called(); self.assertFalse(self.path.exists())

    def test_history_write_failure_does_not_retry_or_fail_completed_rt_install(self):
        app=self.fake(); gui.UnifiedGUI._apply_hhkb(app)
        with patch.object(gui.INSTALL_HISTORY,'record_event',side_effect=PermissionError('private/path')):
            app._worker.call_args.args[0]()
        app._hhkb_flash.assert_called_once()
        items=list(app.q.queue)
        self.assertTrue(any(k=='status' and 'applied' in v for k,v in items))
        self.assertFalse(any(k=='error' for k,v in items))
        self.assertNotIn('private/path',str(items))

    def test_stock_history_uses_completed_stock_bytes_not_rt_settings(self):
        app=self.fake(); gui.UnifiedGUI.recovery_action(app)
        self.assertFalse(self.path.exists()); app._worker.call_args.args[0]()
        row=gui.INSTALL_HISTORY.load_history(self.path)[0]
        self.assertEqual(row['intended_mode'],'stock'); self.assertEqual(row['settings'],{})
        self.assertEqual(row['firmware_sha256'],hashlib.sha256(b'exact-stock-bytes').hexdigest())

    def test_hold_history_uses_sha_lock_and_captured_settings_only_after_child_success(self):
        for code in (1,0):
            app=self.fake(); app._record_operation_history=Mock()
            child=Mock(); child.stdout=[]; child.wait.return_value=code; child.poll.return_value=code
            baseline=Mock(); baseline.exists.return_value=True
            captured={'slots':[{'source_name':'SPACE','tap_name':'SPACE','hold_name':'FN','threshold_ms':250}]}
            with patch.object(gui.subprocess,'Popen',return_value=child):
                if code:
                    with self.assertRaises(RuntimeError):
                        gui.UnifiedGUI._hh_slots_flash_worker(app,'candidate','a'*64,'token',baseline,captured)
                    app._record_operation_history.assert_not_called()
                else:
                    gui.UnifiedGUI._hh_slots_flash_worker(app,'candidate','a'*64,'token',baseline,captured)
                    app._record_operation_history.assert_called_once_with(event='installed',model='PD-KB800W',
                        mode='hold',sha='a'*64,settings=captured)

    def test_r3s_file_creation_is_never_recorded_as_an_install(self):
        app=self.fake(); app.platform.get.return_value=gui.PLAT_R3S
        with patch.object(gui.R3P,'validate_source'),patch.object(gui.R3P,'build',return_value=(
            b'exact-R3S-bytes',{'source_model':'R3SB','output_sha256':hashlib.sha256(b'exact-R3S-bytes').hexdigest()})):
            gui.UnifiedGUI._build_r3s(app)
        row=gui.INSTALL_HISTORY.load_history(self.path)[0]
        self.assertEqual((row['event'],row['model'],row['reconnect_status']),('generated','R3SB','not_applicable'))
        self.assertIn('installation with official REALFORCE software is not recorded',
            gui.local_history_summary([row],gui.PLAT_R3S))
        app._hhkb_flash.assert_not_called()

    def test_hold_settings_exclude_raw_responses_paths_and_build_policy(self):
        slot={'source_name':'SPACE','tap_name':'SPACE','hold_name':'FN','threshold_ms':250,
              'descriptor_hex':'private-data','serial':'private-serial'}
        self.assertEqual(gui.hold_history_settings({'slots':[slot],'path':'private-path'}),
            {'slots':[{k:slot[k] for k in ('source_name','tap_name','hold_name','threshold_ms')}]})
        self.assertEqual(gui.hold_history_settings(None),{})

    def test_summary_does_not_relabel_history_as_current_version_or_device_match(self):
        app=self.fake(); app._record_operation_history(event='installed',model='PD-KB800W',mode='hold',sha='a'*64)
        rows=gui.INSTALL_HISTORY.load_history(self.path)
        text=gui.local_history_summary(rows,gui.PLAT_HHKB)
        self.assertIn('Last completed installation',text)
        self.assertIn('device not matched and firmware not read back',text)
        self.assertIn('App build:',text)
        self.assertIn('No local record',gui.local_history_summary(rows,gui.PLAT_HHKB,model='PD-KB800B'))
        self.assertIn('No local record',gui.local_history_summary(rows,gui.PLAT_R3S))

    def test_real_release_widgets_keep_history_separate_from_inspection(self):
        app=self.fake(); app._record_operation_history(event='installed',model='PD-KB800W',mode='rt',sha='a'*64)
        original_init=gui.tk.Tk.__init__
        def hidden(root,*a,**kw):
            original_init(root,*a,**kw); root.withdraw()
        with patch.object(gui.tk.Tk,'__init__',hidden),patch.object(gui.UnifiedGUI,'_detect_platform'), \
             patch.object(gui.UnifiedGUI,'_auto_find_hhkb_stock'), \
             patch.object(gui.UnifiedGUI,'history_path',new_callable=PropertyMock,return_value=self.path):
            root=gui.UnifiedGUI()
            try:
                root.platform.set(gui.PLAT_HHKB)
                before=root.installed_firmware.get()
                self.assertIn('Last completed installation',root.local_history.get())
                root.q.put(('history_changed',None)); root._poll()
                self.assertEqual(root.installed_firmware.get(),before)
                self.assertIsNone(root.firmware_identification)
                result=gui.FW_DETECT.ProbeResult('Unknown','No validated response.',device='PD-KB800W')
                root.q.put(('fw_detect_result',result)); root._poll()
                self.assertIn('not identified',root.installed_firmware.get())
                self.assertIn('firmware not read back',root.local_history.get())
                self.assertIn('Unknown',root.detect_detail.get())
                self.assertEqual(root.firmware_identification.exact_version_available,False)
                root.platform.set(gui.PLAT_R3S)
                self.assertIn('No local record',root.local_history.get())
                self.assertIn('v0.3.0-rc5',root.title())
            finally: root.destroy()


if __name__=='__main__': unittest.main()
