"""USB enumeration only. No handles, reports, firmware queries or writes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Discovery:
    r3s: int = 0
    hhkb: int = 0
    hhkb_updater: int = 0
    available: bool = True

    @property
    def selected(self):
        if self.hhkb_updater or not self.available:
            return None
        if self.r3s == 1 and self.hhkb == 0:
            return 'r3s'
        if self.hhkb == 1 and self.r3s == 0:
            return 'hhkb'
        return None

    @property
    def message(self):
        if not self.available:
            return 'USB detection unavailable. Check setup and try again.'
        if self.hhkb_updater:
            return 'HHKB update-mode device detected — normal-mode selection is unavailable. No update commands sent.'
        if self.r3s and self.hhkb:
            return 'Both keyboard families detected — select the intended keyboard above.'
        if self.r3s > 1 or self.hhkb > 1:
            return 'Multiple keyboards detected — connect only the intended keyboard for inspection or installation.'
        if self.selected == 'r3s':
            return 'Detected REALFORCE R3S'
        if self.selected == 'hhkb':
            return 'Detected HHKB Professional Hybrid (USB)'
        return 'No supported keyboard detected over USB. The selection above is unchanged.'


def _vendor_interface(row):
    interface = row.get('interface_number')
    path = row.get('path')
    if isinstance(path, bytes):
        path = path.decode('utf-8', errors='strict')
    path = path.lower() if isinstance(path, str) else ''
    if type(interface) is int and interface >= 0:
        return interface == 2 and ('mi_' not in path or 'mi_02' in path)
    if interface is not None and (type(interface) is not int or interface != -1):
        return False
    return 'mi_02' in path


def scan(hid=None):
    try:
        if hid is None:
            import hid
        def count(rows, vid, pid):
            return sum(row.get('vendor_id') == vid and row.get('product_id') == pid
                       and _vendor_interface(row) for row in rows)
        r3 = list(hid.enumerate(0x0853, 0x0311))
        hh = list(hid.enumerate(0x04FE, 0))
        return Discovery(count(r3, 0x0853, 0x0311), count(hh, 0x04FE, 0x0021),
                         count(hh, 0x04FE, 0x0020))
    except Exception:
        # Exception text can contain private USB paths/serials.
        return Discovery(available=False)
