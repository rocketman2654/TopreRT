"""Windows indexed-string access primitives copied from the reviewed reader.

No product-string query or CLI is included. Metadata uses its own index7 request.
"""
import ctypes
import sys
VID, PID = 0x04FE, 0x0021
IOCTL = 0x000B01E2
BUFFER_SIZE = 252
REQUEST = b'\x02\x00\x09\x04'  # Reference value only; no product query implementation.


class AccessError(Exception):
    pass

def decode_product(data):
    """Complete counted UTF-16LE string including final NUL; no truncation repair."""
    if not isinstance(data, bytes) or not 2 <= len(data) <= BUFFER_SIZE or len(data) % 2:
        raise ValueError('product_string_size')
    if data[-2:] != b'\0\0':
        raise ValueError('product_string_termination')
    text = data[:-2].decode('utf-16-le', errors='strict')
    if '\0' in text:
        raise ValueError('product_string_embedded_nul')
    return text

class WindowsApi:
    def __init__(self, kernel=None):
        if kernel is None:
            if sys.platform != 'win32': raise AccessError('platform_unavailable')
            kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True, winmode=0x800)
        self.kernel = kernel
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                      ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                          ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                                          ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        kernel.DeviceIoControl.restype = ctypes.c_int32
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int32
