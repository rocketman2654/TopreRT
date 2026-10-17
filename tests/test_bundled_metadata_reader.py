import copy
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from firmware_identity import codec, windows_metadata_probe as probe
class Function:
    def __init__(self, callback): self.callback = callback
    def __call__(self, *args): return self.callback(*args)

class Kernel:
    def __init__(self, *, handle=123, success=True, data=None, count=None):
        self.calls = []
        self.handle, self.success = handle, success
        self.data = ('HHKB-Hybrid\0'.encode('utf-16-le') if data is None else data)
        self.count = len(self.data) if count is None else count
        self.CreateFileW = Function(self.open)
        self.DeviceIoControl = Function(self.query)
        self.CloseHandle = Function(self.close)

    def open(self, *args):
        self.calls.append(('open', args))
        return self.handle

    def query(self, handle, code, data, size, output, output_size, count, overlapped):
        self.calls.append(('query', handle, code, ctypes.string_at(data, size), size, output_size, overlapped))
        ctypes.memmove(output, self.data, min(len(self.data), output_size))
        count._obj.value = self.count
        return self.success

    def close(self, handle):
        self.calls.append(('close', handle))
        return 1

def hid_rows(*rows):
    hid = mock.Mock()
    hid.enumerate.return_value = list(rows)
    return hid

def vendor(path=b'private-device-path'):
    return dict(vendor_id=probe.product.VID, product_id=probe.product.PID, interface_number=2, path=path)


def text_for(family='rt_only', identifier=0x9284344A, product=1, stock=1):
    return probe.catalog.envelope.encode_identity(codec.Identity(product, stock, family, identifier))[2:].decode('utf-16-le')


def process_response(message, *, code=0):
    process = mock.Mock(returncode=code)
    raw = json.dumps(message).encode() if not isinstance(message, bytes) else message
    process.communicate.return_value = (raw, None)
    return process


class MetadataProbeTests(unittest.TestCase):
    def scratch(self):
        root = Path(probe.__file__).resolve().parents[2] / '.test-tmp'
        root.mkdir(exist_ok=True)
        return tempfile.TemporaryDirectory(prefix='metadata_', dir=root)

    def test_native_api_one_exact_index7_language0409_query_and_close(self):
        text = text_for(); kernel = Kernel(data=(text + '\0').encode('utf-16-le'))
        self.assertEqual(probe.WindowsApi(kernel).metadata('PRIVATE'), text)
        self.assertEqual(kernel.calls[0], ('open', ('PRIVATE', 0, 3, None, 3, 0x80, None)))
        self.assertEqual(kernel.calls[1], ('query', 123, 0xB01E2, b'\x07\0\x09\x04', 4, 252, None))
        self.assertEqual(kernel.calls[2], ('close', 123))
        self.assertEqual(probe.product.REQUEST, b'\x02\0\x09\x04')
        self.assertEqual(ctypes.sizeof(kernel.CreateFileW.restype), ctypes.sizeof(ctypes.c_void_p))

    def test_invalid_handle_does_not_query_or_close(self):
        for handle in (None, 0, ctypes.c_void_p(-1).value):
            kernel = Kernel(handle=handle)
            with self.assertRaisesRegex(probe.product.AccessError, 'open_failed'):
                probe.WindowsApi(kernel).metadata('PRIVATE')
            self.assertEqual([row[0] for row in kernel.calls], ['open'])

    def test_driver_failure_count_utf16_crc_and_other_product_are_rejected_without_retry(self):
        text = text_for()
        other = text_for(product=2, stock=2)
        cases = ({'success':False}, {'count':0}, {'count':108}, {'count':109}, {'count':112},
                 {'count':254}, {'data':(text + 'X').encode('utf-16-le')},
                 {'data':b'\x00\xd8' + bytes(108)},
                 {'data':(text[:-1] + ('0' if text[-1] != '0' else '1') + '\0').encode('utf-16-le')},
                 {'data':(other + '\0').encode('utf-16-le')})
        for kwargs in cases:
            args = {'data':(text + '\0').encode('utf-16-le'), **kwargs}
            kernel = Kernel(**args)
            with self.subTest(kwargs=kwargs), self.assertRaises(probe.product.AccessError):
                probe.WindowsApi(kernel).metadata('PRIVATE')
            self.assertEqual([row[0] for row in kernel.calls], ['open', 'query', 'close'])

    def test_missing_or_ambiguous_interface_never_queries(self):
        for rows, status in (([], 'no_normal_vendor_interface'),
                             ([vendor(), vendor(b'OTHER')], 'ambiguous_normal_vendor_interface')):
            api = mock.Mock()
            self.assertEqual(probe.collect(hid_rows(*rows), api), probe.message(status))
            api.metadata.assert_not_called()

    def test_wrong_device_conflicting_interface_and_malformed_interface_are_rejected(self):
        for changes in ({'product_id':0xFFFF}, {'vendor_id':0xFFFF},
                        {'interface_number':1, 'path':b'usb#mi_02#PRIVATE'},
                        {'interface_number':2, 'path':b'usb#mi_01#PRIVATE'}):
            row = dict(vendor(), **changes); api = mock.Mock()
            self.assertEqual(probe.collect(hid_rows(row), api)['status'], 'no_normal_vendor_interface')
            api.metadata.assert_not_called()
        for invalid in (True, '2', -2, []):
            row = dict(vendor(), interface_number=invalid); api = mock.Mock()
            self.assertEqual(probe.collect(hid_rows(row), api)['status'], 'enumeration_failed')
            api.metadata.assert_not_called()

    def test_single_response_checks_connection_again_and_omits_private_identifiers(self):
        row = dict(vendor(), serial_number='PRIVATE-SERIAL')
        api = mock.Mock(); api.metadata.return_value = text_for()
        hid = hid_rows(row)
        self.assertEqual(probe.collect(hid, api), probe.message('metadata_response', text_for()))
        self.assertEqual(hid.enumerate.call_count, 2)
        api.metadata.assert_called_once_with('private-device-path')
        self.assertNotIn('PRIVATE', json.dumps(probe.collect(hid, api)))

    def test_disconnect_replacement_or_second_device_discards_response(self):
        row = dict(vendor(), serial_number='one')
        for after in ([], [dict(row, path=b'other')], [dict(row, serial_number='two')], [row, vendor(b'other')]):
            hid = mock.Mock(); hid.enumerate.side_effect = [[row], after]
            api = mock.Mock(); api.metadata.return_value = text_for()
            self.assertEqual(probe.collect(hid, api), probe.message('connection_changed'))
            api.metadata.assert_called_once()

    def test_enumeration_and_access_failures_and_invalid_text_never_leak(self):
        hid = mock.Mock(); hid.enumerate.side_effect = RuntimeError('PRIVATE')
        self.assertEqual(probe.collect(hid, mock.Mock()), probe.message('enumeration_failed'))
        hid.enumerate.side_effect = [[vendor()], RuntimeError('PRIVATE')]
        api = mock.Mock(); api.metadata.return_value = text_for()
        self.assertEqual(probe.collect(hid, api), probe.message('connection_changed'))
        for error in (RuntimeError('PRIVATE'), probe.product.AccessError('PRIVATE')):
            api.metadata.side_effect = error
            result=probe.collect(hid_rows(vendor()), api)
            self.assertEqual(result['status'],'metadata_unavailable')
            self.assertNotIn('PRIVATE',json.dumps(result))
            if isinstance(error,RuntimeError): self.assertEqual(result['diagnostic']['stage'],'python_exception')
            else: self.assertIsNone(result['diagnostic'])
        api.metadata.side_effect = None; api.metadata.return_value = 'PRIVATE bad response'
        self.assertEqual(probe.collect(hid_rows(vendor()), api), probe.message('invalid_metadata_response'))

    def test_parent_registered_rt_hold_claims_are_development_and_not_authentication(self):
        for family, identifier in (('rt_only', 0x9284344A), ('hold', 0xF4E7EB1F)):
            process = process_response(probe.message('metadata_response', text_for(family, identifier)))
            with mock.patch.object(probe.subprocess, 'Popen', return_value=process) as spawn:
                result = probe.probe_metadata()
            self.assertEqual(result['status'], 'registered_build_claim')
            self.assertEqual(result['resolution']['claimed_family'], family)
            self.assertEqual(result['resolution']['channel'], 'development')
            self.assertIsNone(result['resolution']['registered_patch_version'])
            self.assertTrue(result['metadata_claim_received'])
            self.assertEqual(result['request_input_hex'], '07000904')
            self.assertEqual(result['worker_cleanup'], 'reaped')
            self.assertIn('-I', spawn.call_args.args[0])
            for field in ('device_identity_verified', 'firmware_authenticated', 'image_integrity_verified',
                          'settings_verified', 'fresh_wire_read_proven', 'wire_language_observed',
                          'query_retried', 'device_side_cancellation_proven', 'mode_switch_performed', 'firmware_written'):
                self.assertIs(result[field], False)

    def test_unregistered_and_family_mismatch_never_inherit_registered_version(self):
        for text, status in ((text_for(identifier=0x02030405), 'unregistered_build_claim'),
                             (text_for('hold'), 'catalog_identity_mismatch')):
            with mock.patch.object(probe.subprocess, 'Popen', return_value=process_response(probe.message('metadata_response', text))):
                result = probe.probe_metadata()
            self.assertEqual(result['status'], status)
            self.assertIsNone(result['resolution']['channel'])
            self.assertIsNone(result['resolution']['registered_patch_version'])
            self.assertIsNone(result['resolution']['build_label'])

    def test_parent_ipc_rejects_duplicate_keys_bad_types_extra_fields_and_bad_text(self):
        valid = probe.message('metadata_response', text_for())
        bad = (b'not json', b'x' * 513, b'{"schema":0,"schema":1,"status":"metadata_unavailable","metadata_text":null}',
               dict(valid, schema=True), dict(valid, path='PRIVATE'), dict(valid, status='unknown'),
               dict(valid, metadata_text=42), dict(valid, metadata_text=text_for().lower()),
               dict(valid, metadata_text=text_for() + '\n'), dict(valid, metadata_text=text_for(product=2, stock=2)),
               probe.message('metadata_unavailable', 'PRIVATE'))
        for response in bad:
            with mock.patch.object(probe.subprocess, 'Popen', return_value=process_response(response)):
                result = probe.probe_metadata()
            self.assertEqual(result['status'], 'worker_protocol_error')
            self.assertIsNone(result['resolution'])
            self.assertNotIn('PRIVATE', json.dumps(result))
        with mock.patch.object(probe.subprocess, 'Popen', return_value=process_response(valid, code=1)):
            self.assertEqual(probe.probe_metadata()['status'], 'worker_protocol_error')

    def test_failed_query_never_means_stock_or_retains_previous_success(self):
        good = process_response(probe.message('metadata_response', text_for()))
        failed = process_response(probe.message('metadata_unavailable'))
        with mock.patch.object(probe.subprocess, 'Popen', side_effect=[good, failed]) as spawn:
            first = probe.probe_metadata(); saved = copy.deepcopy(first)
            second = probe.probe_metadata()
        self.assertEqual(first, saved)
        self.assertEqual(second['status'], 'metadata_unavailable')
        self.assertFalse(second['metadata_claim_received'])
        self.assertIsNone(second['resolution'])
        self.assertEqual(spawn.call_count, 2)  # Two explicit calls, no internal retry.
        self.assertNotIn('stock', second['status'])

    def test_timeout_interrupt_and_io_error_kill_once_without_retry(self):
        for error, status in ((subprocess.TimeoutExpired('own child', 3), 'parent_timeout'),
                              (KeyboardInterrupt(), 'parent_interrupted'), (OSError(), 'worker_io_error')):
            process = mock.Mock(); process.communicate.side_effect = [error, (b'', None)]
            with mock.patch.object(probe.subprocess, 'Popen', return_value=process) as spawn:
                result = probe.probe_metadata()
            self.assertEqual((result['status'], result['worker_cleanup']), (status, 'terminated'))
            self.assertIsNone(result['resolution'])
            process.kill.assert_called_once(); spawn.assert_called_once()

    def test_unconfirmed_cleanup_blocks_next_probe_until_process_is_reaped(self):
        process = mock.Mock(); process.communicate.side_effect = subprocess.TimeoutExpired('own child', 3)
        process.poll.return_value = None
        try:
            with mock.patch.object(probe.subprocess, 'Popen', return_value=process) as spawn:
                first = probe.probe_metadata(); second = probe.probe_metadata()
            self.assertEqual(first['worker_cleanup'], 'termination_unconfirmed')
            self.assertEqual(second['status'], 'worker_cleanup_pending')
            spawn.assert_called_once()
            process.stdout.close.assert_not_called()
            process.poll.return_value = 0; process.communicate.side_effect = None
            process.communicate.return_value = (b'', None)
            self.assertFalse(probe._cleanup_pending())
        finally:
            if process in probe._UNREAPED: probe._UNREAPED.remove(process)

    def test_actual_own_busy_child_stops_after_deadline(self):
        with self.scratch() as folder:
            ready = Path(folder) / 'ready'
            code = "import pathlib,sys\npathlib.Path(sys.argv[1]).write_text('ready')\nwhile True:\n pass\n"
            command = [sys.executable, '-I', '-B', '-c', code, str(ready)]
            started = time.monotonic()
            with mock.patch.object(probe, '_worker_command', return_value=command):
                result = probe.probe_metadata(timeout_s=1.0)
            self.assertEqual(ready.read_text(), 'ready')
            self.assertEqual((result['status'], result['worker_cleanup']), ('parent_timeout', 'terminated'))
            self.assertLess(time.monotonic() - started, 4.0)

    def test_bad_catalog_stops_before_worker_and_catalog_edit_discards_claim(self):
        with self.scratch() as folder:
            path = Path(folder) / 'catalog.json'; path.write_text('invalid')
            with mock.patch.object(probe.subprocess, 'Popen') as spawn:
                self.assertEqual(probe.probe_metadata(catalog_path=path)['status'], 'catalog_unavailable')
            spawn.assert_not_called()
            document = probe.catalog.load_catalog()
            for changed in ('invalid', json.dumps({'schema':1, 'entries':[]})):
                path.write_text(json.dumps(document))
                process = process_response(probe.message('metadata_response', text_for()))
                def edit_then_respond(**kwargs):
                    path.write_text(changed)
                    return (json.dumps(probe.message('metadata_response', text_for())).encode(), None)
                process.communicate.side_effect = edit_then_respond
                with mock.patch.object(probe.subprocess, 'Popen', return_value=process):
                    result = probe.probe_metadata(catalog_path=path)
                self.assertEqual(result['status'], 'catalog_changed')
                self.assertIsNone(result['resolution'])

    def test_worker_start_failure_is_empty_result(self):
        with mock.patch.object(probe.subprocess, 'Popen', side_effect=OSError('PRIVATE')):
            result = probe.probe_metadata()
        self.assertEqual(result['status'], 'worker_start_failed')
        self.assertIsNone(result['resolution'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_timeout_configuration_is_bounded_and_strict(self):
        for value in (True, False, None, '3', 0, 11, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'timeout_outside_bounds'):
                probe.probe_metadata(timeout_s=value)

    def test_default_cli_has_no_device_io_or_worker(self):
        run = subprocess.run([sys.executable, '-I', '-B', probe.__file__],
            capture_output=True, text=True, check=True, timeout=5)
        self.assertIn('No device accessed', run.stdout)
        self.assertNotIn('Report saved', run.stdout)

    def test_ioctl_error_is_captured_before_close_overwrites_last_error(self):
        kernel=Kernel(success=False,count=0)
        state={'error':0}; query=kernel.query; close=kernel.close
        def fail(*args):
            result=query(*args);state['error']=31;return result
        def cleanup(handle):
            result=close(handle);state['error']=6;return result
        kernel.DeviceIoControl.callback=fail;kernel.CloseHandle.callback=cleanup
        with mock.patch.object(probe,'win32_error',side_effect=lambda:state['error']):
            result=probe.collect(hid_rows(vendor()),probe.WindowsApi(kernel))
        self.assertEqual(result['diagnostic'],{'stage':'ioctl_failed','win32_error':31,'returned_bytes':0})
        self.assertEqual(state['error'],6)
        self.assertEqual([row[0] for row in kernel.calls],['open','query','close'])
        self.assertNotIn('private',json.dumps(result).lower())

    def test_open_error_has_code_and_never_queries(self):
        kernel=Kernel(handle=ctypes.c_void_p(-1).value)
        with mock.patch.object(probe,'win32_error',return_value=5):
            result=probe.collect(hid_rows(vendor()),probe.WindowsApi(kernel))
        self.assertEqual(result['status'],'open_failed')
        self.assertEqual(result['diagnostic'],{'stage':'create_file_failed','win32_error':5,'returned_bytes':None})
        self.assertEqual([row[0] for row in kernel.calls],['open'])

    def test_driver_success_bad_length_or_decode_has_no_stale_win32_code(self):
        for kernel,stage,count in ((Kernel(count=108),'returned_length',108),
                                   (Kernel(data=b'\0'*110),'metadata_decode',110)):
            with mock.patch.object(probe,'win32_error',side_effect=AssertionError('stale code must not be read')):
                result=probe.collect(hid_rows(vendor()),probe.WindowsApi(kernel))
            self.assertEqual(result['status'],'invalid_metadata_response')
            self.assertEqual(result['diagnostic'],{'stage':stage,'win32_error':None,'returned_bytes':count})
            self.assertEqual([row[0] for row in kernel.calls],['open','query','close'])

    def test_parent_preserves_only_valid_failure_diagnostic_without_claim(self):
        diagnostics=(('open_failed',{'stage':'create_file_failed','win32_error':5,'returned_bytes':None}),
            ('metadata_unavailable',{'stage':'ioctl_failed','win32_error':31,'returned_bytes':0}),
            ('invalid_metadata_response',{'stage':'returned_length','win32_error':None,'returned_bytes':254}),
            ('invalid_metadata_response',{'stage':'metadata_decode','win32_error':None,'returned_bytes':110}),
            ('metadata_unavailable',{'stage':'python_exception','win32_error':None,'returned_bytes':None}))
        for status,diagnostic in diagnostics:
            child=process_response(probe.message(status,diagnostic=diagnostic))
            with mock.patch.object(probe.subprocess,'Popen',return_value=child) as spawn:
                result=probe.probe_metadata()
            self.assertEqual(result['status'],status)
            self.assertEqual(result['diagnostic'],diagnostic)
            self.assertFalse(result['metadata_claim_received'])
            self.assertIsNone(result['resolution']);spawn.assert_called_once()

    def test_parent_rejects_private_malformed_or_inconsistent_diagnostics(self):
        base={'stage':'ioctl_failed','win32_error':31,'returned_bytes':0}
        variants=['PRIVATE',{},dict(base,path='PRIVATE'),dict(base,stage='PRIVATE'),
            dict(base,win32_error=True),dict(base,win32_error=-1),dict(base,win32_error=2**32),
            dict(base,returned_bytes=True),dict(base,returned_bytes=None),
            dict(base,stage='metadata_decode'),dict(base,stage='python_exception')]
        for diagnostic in variants:
            child=process_response(probe.message('metadata_unavailable',diagnostic=diagnostic))
            with mock.patch.object(probe.subprocess,'Popen',return_value=child): result=probe.probe_metadata()
            self.assertEqual(result['status'],'worker_protocol_error')
            self.assertIsNone(result['diagnostic']);self.assertIsNone(result['resolution'])
            self.assertNotIn('PRIVATE',json.dumps(result))
        child=process_response(probe.message('metadata_response',text_for(),base))
        with mock.patch.object(probe.subprocess,'Popen',return_value=child):
            self.assertEqual(probe.probe_metadata()['status'],'worker_protocol_error')

    def test_new_success_or_nondiagnostic_failure_never_inherits_previous_error(self):
        bad=process_response(probe.message('metadata_unavailable',diagnostic={
            'stage':'ioctl_failed','win32_error':31,'returned_bytes':0}))
        good=process_response(probe.message('metadata_response',text_for()))
        unknown=process_response(probe.message('metadata_unavailable'))
        with mock.patch.object(probe.subprocess,'Popen',side_effect=[bad,good,unknown]):
            first=probe.probe_metadata();second=probe.probe_metadata();third=probe.probe_metadata()
        self.assertEqual(first['diagnostic']['win32_error'],31)
        self.assertIsNone(second['diagnostic']);self.assertIsNone(third['diagnostic'])
        self.assertFalse(third['metadata_claim_received'])


if __name__ == '__main__': unittest.main()
