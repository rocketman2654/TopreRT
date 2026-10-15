"""Fail-closed device binding across HHKB updater re-enumeration.

USB paths and PIDs may change. Never substitute them for a persistent serial.
This detects accidental replacement, not a device spoofing another serial.
"""
from dataclasses import dataclass


class IdentityMismatch(RuntimeError):
    pass


def _usb_serial(desc, dev, phase, optional=False):
    try:
        serial = dev.get_serial_number_string()
    except Exception as exc:
        if optional and not desc.get("serial_number"):
            return None
        raise IdentityMismatch(f"{phase}: cannot read USB serial; update stopped") from exc
    if not isinstance(serial, str) or not serial.strip():
        if optional and not desc.get("serial_number"):
            return None
        raise IdentityMismatch(f"{phase}: missing USB serial; update stopped")
    advertised = desc.get("serial_number")
    if advertised and advertised != serial:
        raise IdentityMismatch(f"{phase}: descriptor/handle serial mismatch; update stopped")
    return serial


def _firmware_identity(payload):
    if len(payload) < 40:
        raise IdentityMismatch("Incomplete HHKB identity; update stopped")
    try:
        model = payload[:20].split(b"\0", 1)[0].decode("ascii")
        serial = payload[24:40].split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise IdentityMismatch("Invalid HHKB identity; update stopped") from exc
    if not model.startswith("PD-KB8") or not serial.strip():
        raise IdentityMismatch("Missing or unsupported HHKB identity; update stopped")
    return model, serial


@dataclass(frozen=True)
class DeviceBinding:
    usb_serial: str | None
    model: str
    firmware_serial: str

    @classmethod
    def capture(cls, desc, dev, payload):
        model, serial = _firmware_identity(payload)
        return cls(_usb_serial(desc, dev, "Preflight", optional=True), model, serial)

    def verify_usb(self, desc, dev, phase, read_info=None):
        if self.usb_serial is None:
            # Never use port/PID/path alone as proof. Query the same persistent
            # vendor identity before E1; timeout/unsupported replies stop writing.
            if read_info is None:
                raise IdentityMismatch(f"{phase}: device identity query required; update stopped")
            try:
                payload = read_info()
                self.verify_firmware(payload)
            except Exception as exc:
                raise IdentityMismatch(f"{phase}: device identity could not be verified; no further update commands will be sent") from exc
            return
        if _usb_serial(desc, dev, phase) != self.usb_serial:
            raise IdentityMismatch(f"{phase}: a different keyboard reconnected; update stopped")

    def verify_firmware(self, payload):
        # Revision is intentionally excluded: an update may change it.
        if _firmware_identity(payload) != (self.model, self.firmware_serial):
            raise IdentityMismatch("Reconnect identity mismatch; update completion NOT verified")
