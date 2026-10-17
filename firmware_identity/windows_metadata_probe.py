"""Development-only, one-shot HHKB metadata reader; default CLI does no IO.

Only index7/language0409, no reports, updater, scan, fallback or query retry.
An observed metadata claim is not authentication, settings or physical identity.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from firmware_identity import identity_catalog as catalog
from firmware_identity import windows_access as product

INDEX, LANGUAGE = 7, 0x0409
REQUEST = b'\x07\x00\x09\x04'
STATUSES = frozenset(('metadata_response', 'dependency_unavailable', 'platform_unavailable',
    'enumeration_failed', 'no_normal_vendor_interface', 'ambiguous_normal_vendor_interface',
    'connection_changed', 'open_failed', 'metadata_unavailable', 'invalid_metadata_response'))
_UNREAPED = []


DIAGNOSTIC_STATUS = {'create_file_failed':'open_failed',
    'ioctl_failed':'metadata_unavailable', 'returned_length':'invalid_metadata_response',
    'metadata_decode':'invalid_metadata_response', 'python_exception':'metadata_unavailable'}


def valid_diagnostic(value, status):
    if value is None: return True
    if type(value) is not dict or set(value) != {'stage','win32_error','returned_bytes'}:
        return False
    stage=value['stage']; code=value['win32_error']; count=value['returned_bytes']
    if type(stage) is not str or DIAGNOSTIC_STATUS.get(stage)!=status: return False
    if any(v is not None and (type(v) is not int or not 0<=v<=0xFFFFFFFF) for v in (code,count)):
        return False
    if stage=='create_file_failed': return count is None
    if stage=='ioctl_failed': return type(count) is int
    if code is not None: return False
    if stage=='returned_length': return type(count) is int and count!=110
    if stage=='metadata_decode': return type(count) is int and count==110
    return count is None


def message(status, text=None, diagnostic=None):
    return {'schema': 2, 'status': status, 'metadata_text': text, 'diagnostic':diagnostic}


def win32_error():
    getter=getattr(ctypes,'get_last_error',None)
    value=getter() if getter is not None else None
    return value if type(value) is int and 0<=value<=0xFFFFFFFF else None


def clear_win32_error():
    setter=getattr(ctypes,'set_last_error',None)
    if setter is not None: setter(0)


class MetadataAccessError(product.AccessError):
    def __init__(self,status,stage,*,code=None,count=None):
        super().__init__(status)
        self.diagnostic={'stage':stage,'win32_error':code,'returned_bytes':count}


class WindowsApi(product.WindowsApi):
    def metadata(self, path):
        clear_win32_error()
        handle = self.kernel.CreateFileW(path, 0, 3, None, 3, 0x80, None)
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise MetadataAccessError('open_failed','create_file_failed',code=win32_error())
        try:
            request = ctypes.create_string_buffer(REQUEST, 4)
            output = ctypes.create_string_buffer(product.BUFFER_SIZE)
            count = ctypes.c_uint32(0)
            clear_win32_error()
            success = self.kernel.DeviceIoControl(handle, product.IOCTL, request, 4,
                output, product.BUFFER_SIZE, ctypes.byref(count), None)
            if not success:
                # Capture the thread's ctypes error immediately, before closing
                # the handle can replace it. Never retain exception text/path.
                raise MetadataAccessError('metadata_unavailable','ioctl_failed',
                                          code=win32_error(),count=count.value)
            # 54 UTF-16 characters plus exactly one terminating NUL. Driver
            # output has no USB descriptor header; don't strip/repair text.
            if count.value != 110:
                raise MetadataAccessError('invalid_metadata_response','returned_length',count=count.value)
            try:
                text = product.decode_product(output.raw[:count.value])
                catalog.envelope.parse_text(text, expected_product=1)
            except (UnicodeError, ValueError) as error:
                raise MetadataAccessError('invalid_metadata_response','metadata_decode',count=count.value) from error
            return text
        finally:
            self.kernel.CloseHandle(handle)


def selected(hid):
    rows = []
    for row in hid.enumerate(product.VID, product.PID):
        if row.get('vendor_id') != product.VID or row.get('product_id') != product.PID:
            continue
        path = row.get('path')
        if isinstance(path, bytes): path = path.decode('utf-8', errors='strict')
        if not isinstance(path, str) or not path: continue
        interface = row.get('interface_number')
        if interface is not None and (type(interface) is not int or interface < -1):
            raise ValueError('invalid_interface_type')
        # Missing interface may use the Windows path marker. Conflicting
        # positive interface numbers are rejected rather than trusted by OR.
        if type(interface) is int and interface >= 0:
            if interface != 2: continue
            if 'mi_' in path.lower() and 'mi_02' not in path.lower(): continue
        elif 'mi_02' not in path.lower(): continue
        serial = row.get('serial_number')
        if serial is not None and not isinstance(serial, str):
            raise ValueError('invalid_serial_type')
        rows.append((path, serial))
    return rows


def collect(hid, api):
    try: before = selected(hid)
    except Exception: return message('enumeration_failed')
    if len(before) != 1:
        return message('no_normal_vendor_interface' if not before else 'ambiguous_normal_vendor_interface')
    try:
        value = api.metadata(before[0][0])
        # Revalidate injected API results too, before any IPC or report output.
        catalog.envelope.parse_text(value, expected_product=1)
    except MetadataAccessError as error:
        status=str(error)
        if status in STATUSES and valid_diagnostic(error.diagnostic,status):
            return message(status,diagnostic=error.diagnostic)
        return message('metadata_unavailable')
    except product.AccessError as error:
        status = str(error)
        return message(status if status in ('open_failed', 'metadata_unavailable', 'invalid_metadata_response')
                       else 'metadata_unavailable')
    except (ValueError, TypeError, UnicodeError): return message('invalid_metadata_response')
    except Exception:
        return message('metadata_unavailable',diagnostic={
            'stage':'python_exception','win32_error':None,'returned_bytes':None})
    try: after = selected(hid)
    except Exception: return message('connection_changed')
    if before != after: return message('connection_changed')
    # Same observed path/serial is only a continuity check, not proof that a
    # reconnect with identical enumeration data did not happen inside the read.
    return message('metadata_response', value)


def _worker_command():
    return [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--worker']


def _bounded_stop(process):
    try: process.kill()
    except OSError: pass
    try:
        process.communicate(timeout=1.0)
        return 'terminated'
    except (subprocess.TimeoutExpired, OSError):
        _UNREAPED.append(process)
        return 'termination_unconfirmed'


def _cleanup_pending():
    for process in tuple(_UNREAPED):
        try:
            if process.poll() is None: continue
            process.communicate(timeout=0)
        except (subprocess.TimeoutExpired, OSError): continue
        _UNREAPED.remove(process)
    return bool(_UNREAPED)


def probe_metadata(*, timeout_s=3.0, catalog_path=catalog.HERE / 'build_catalog.json'):
    if type(timeout_s) not in (int, float) or not 0.1 <= timeout_s <= 10:
        raise ValueError('timeout_outside_bounds')
    started = time.monotonic()
    result = {'schema': 2, 'scope': 'development_metadata_claim_one_shot',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'index': INDEX,
        'language_requested': LANGUAGE, 'request_input_hex': REQUEST.hex(), 'ioctl': product.IOCTL,
        'status': 'worker_start_failed', 'worker_cleanup': 'not_started', 'resolution': None,
        'diagnostic': None,
        'metadata_claim_received': False, 'device_identity_verified': False,
        'firmware_authenticated': False, 'image_integrity_verified': False, 'settings_verified': False,
        'fresh_wire_read_proven': False, 'wire_language_observed': False, 'query_retried': False,
        'timeout_s': float(timeout_s), 'device_side_cancellation_proven': False,
        'mode_switch_performed': False, 'firmware_written': False}

    def done():
        result['elapsed_s'] = round(time.monotonic() - started, 3)
        return result

    if _cleanup_pending():
        result['status'] = 'worker_cleanup_pending'
        return done()
    try: document = catalog.load_catalog(catalog_path)
    except (OSError, ValueError, TypeError):
        result['status'] = 'catalog_unavailable'
        return done()
    pinned = json.dumps(document, sort_keys=True, separators=(',', ':'))
    try:
        process = subprocess.Popen(_worker_command(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception: return done()
    try: raw, _ = process.communicate(timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError, KeyboardInterrupt) as error:
        result['status'] = ('parent_timeout' if isinstance(error, subprocess.TimeoutExpired) else
                            'parent_interrupted' if isinstance(error, KeyboardInterrupt) else 'worker_io_error')
        result['worker_cleanup'] = _bounded_stop(process)
        return done()
    result.update(status='worker_protocol_error', worker_cleanup='reaped')
    if process.returncode != 0 or len(raw) > 512: return done()
    try:
        response = json.loads(raw.decode('ascii'), object_pairs_hook=catalog._unique_object)
        if (type(response) is not dict or set(response) != {'schema', 'status', 'metadata_text','diagnostic'}
                or type(response['schema']) is not int or response['schema'] != 2
                or not isinstance(response['status'], str) or response['status'] not in STATUSES
                or not valid_diagnostic(response['diagnostic'],response['status'])):
            return done()
        status, text = response['status'], response['metadata_text']
        if status != 'metadata_response':
            if text is None: result.update(status=status,diagnostic=response['diagnostic'])
            return done()
        resolution = catalog.resolve_text(text, expected_product=1, catalog_document=document)
    except (UnicodeError, ValueError, TypeError): return done()
    try:
        current = catalog.load_catalog(catalog_path)
        if pinned != json.dumps(current, sort_keys=True, separators=(',', ':')):
            result['status'] = 'catalog_changed'
            return done()
    except (UnicodeError, ValueError, TypeError, OSError):
        result['status'] = 'catalog_changed'
        return done()
    result.update(status=resolution['status'], resolution=resolution, metadata_claim_received=True)
    return done()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--read-metadata', action='store_true')
    group.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try: import hid
        except ImportError: response = message('dependency_unavailable')
        else:
            try: api = WindowsApi()
            except Exception: response = message('platform_unavailable')
            else: response = collect(hid, api)
        print(json.dumps(response, separators=(',', ':')))
        return
    if not args.read_metadata:
        print('No device accessed. Development only: --read-metadata requests index7/language0409 once.')
        return
    result = probe_metadata()
    directory = Path(__file__).resolve().parent / 'reports'
    directory.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = directory / f'metadata_development_{stamp}_{uuid.uuid4().hex[:8]}.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('Result: ' + result['status'])
    if result['diagnostic']:
        print('Diagnostic: ' + json.dumps(result['diagnostic'],separators=(',',':')))
    if result['resolution'] and result['resolution']['catalog_match']:
        print('Claim: ' + result['resolution']['build_label'])
    print('Report saved: ' + str(target))


if __name__ == '__main__': main()
