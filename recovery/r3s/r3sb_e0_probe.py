# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
# Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
"""
REALFORCE R3SB31 E0-only updater-entry probe.

Safety model:
- Default mode is READ-ONLY discovery. It does not send anything.
- --send explicitly transmits ONLY the 64-byte E0 RebootForUpdate command.
- It never sends E1/E2/E3, so it does not intentionally start firmware erase/write.

Requirements on Windows:
    py -m pip install hidapi

Usage:
    py r3sb_e0_probe.py
    py r3sb_e0_probe.py --send

Expected device from the captured R3SB31:
    VID 0x0853, PID 0x0311, interface 2
"""

import argparse
import sys
import time

VID = 0x0853
PID = 0x0311
TARGET_IFACE = 2

E0 = bytes([0xAA, 0xAA, 0xE0, 0x00, 0x00] + [0x00] * 59)
EXPECTED_ACK_PREFIX = bytes([0x55, 0x55, 0xE0, 0x00, 0x00])

def load_hid():
    try:
        import hid
        return hid
    except Exception as e:
        print("ERROR: Python package 'hidapi' is required.", file=sys.stderr)
        print("Install with:  py -m pip install hidapi", file=sys.stderr)
        print(f"Import error: {e}", file=sys.stderr)
        sys.exit(2)

def norm(v):
    if isinstance(v, bytes):
        try:
            return v.decode(errors="replace")
        except Exception:
            return repr(v)
    return v

def enumerate_candidates(hid):
    devs = hid.enumerate(VID, PID)
    rows = []
    for d in devs:
        rows.append({
            "path": d.get("path"),
            "interface_number": d.get("interface_number"),
            "usage_page": d.get("usage_page"),
            "usage": d.get("usage"),
            "manufacturer_string": norm(d.get("manufacturer_string")),
            "product_string": norm(d.get("product_string")),
            "serial_number": norm(d.get("serial_number")),
        })
    return rows

def show(rows):
    if not rows:
        print(f"No HID device found for {VID:04X}:{PID:04X}.")
        return
    print(f"Found {len(rows)} HID interface(s) for {VID:04X}:{PID:04X}:")
    for i, r in enumerate(rows):
        print(
            f"[{i}] iface={r['interface_number']!r} "
            f"usage_page={r['usage_page']!r} usage={r['usage']!r} "
            f"manufacturer={r['manufacturer_string']!r} "
            f"product={r['product_string']!r}"
        )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--send",
        action="store_true",
        help="Actually send ONLY E0 RebootForUpdate. Without this flag the script is read-only."
    )
    ap.add_argument(
        "--iface",
        type=int,
        default=TARGET_IFACE,
        help=f"HID interface number to use (default: {TARGET_IFACE})"
    )
    ap.add_argument(
        "--ack-timeout-ms",
        type=int,
        default=1500,
        help="ACK read timeout before the device reboots (default: 1500 ms)"
    )
    args = ap.parse_args()

    hid = load_hid()
    rows = enumerate_candidates(hid)
    show(rows)

    matching = [r for r in rows if r["interface_number"] == args.iface]
    if not args.send:
        print("\nREAD-ONLY mode: no USB command was sent.")
        print(f"Expected vendor/updater interface from capture: interface {args.iface}.")
        print("Use --send only after confirming the listed device is your R3SB31.")
        return 0

    if len(matching) != 1:
        print(
            f"\nREFUSING TO SEND: expected exactly one interface {args.iface}, "
            f"found {len(matching)}.",
            file=sys.stderr
        )
        return 3

    path = matching[0]["path"]
    print("\nAbout to send ONLY E0 (RebootForUpdate).")
    print("No E1/E2/E3 firmware-write commands are implemented in this program.")

    dev = hid.device()
    try:
        dev.open_path(path)
        dev.set_nonblocking(False)

        # HIDAPI requires a leading report-ID byte. 0 means "no numbered report ID".
        out = bytes([0x00]) + E0
        written = dev.write(out)
        print(f"hid.write returned: {written}")

        ack = bytes(dev.read(64, timeout_ms=args.ack_timeout_ms))
        if not ack:
            print("No ACK received before timeout/device reboot.")
            return 4

        print("ACK:", ack.hex(" "))
        if ack.startswith(EXPECTED_ACK_PREFIX):
            print("E0 ACK matches captured REALFORCE response.")
            print("The keyboard should now disconnect and re-enumerate in updater mode.")
            return 0

        print("WARNING: response does not match expected E0 ACK.", file=sys.stderr)
        return 5

    finally:
        try:
            dev.close()
        except Exception:
            pass

if __name__ == "__main__":
    raise SystemExit(main())
