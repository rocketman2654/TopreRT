# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
# Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
"""
HHKB A0.48 TopreRT v0.13 generic-HOLD validated updater

DEFAULT: dry-run only. No USB commands are sent.
ACTUAL FLASH: requires --flash and an interactive confirmation phrase.

This script is intentionally locked to the audited GUI-generated v0.12 S-only HFB SHA-256.
It implements only the application firmware path 0x01 / 0x02 / 0x05 /
0x06 / 0xE0 / 0xE1 / 0xE2 / 0xE3. Boot-firmware commands E4-E7 are
not implemented.
"""

import argparse
import hashlib
import struct
import sys
import time
from pathlib import Path
import hhkb_v013_generic_hold_core_patch_v0_1 as HHPATCH

VID = 0x04FE
PIDS = {0x0020, 0x0021, 0x0022}
STOCK_SHA256 = HHPATCH.STOCK_SHA256
ALLOWED_TABLE_START = 0xEEA8
ALLOWED_TABLE_END = 0xEEE8
EXPECTED_HFB_SIZE = 0x45030
EXPECTED_FIRM_TYPE = b"AHUX01"
MAIN_SIZE = 0x10000
TIMEOUT_MS = 60000

def crc16_ref(data, init=0xFFFF):
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8408) if (crc & 1) else (crc >> 1)
            crc &= 0xFFFF
    return crc

def parse_hfb(path: Path, expected_sha: str, stock_path: Path):
    data=path.read_bytes()
    if len(data)!=EXPECTED_HFB_SIZE: raise RuntimeError(f"Unexpected HFB size: {len(data)}")
    sha=hashlib.sha256(data).hexdigest()
    if sha!=expected_sha: raise RuntimeError(f"Refusing: candidate SHA changed; got {sha}; expected {expected_sha}")
    stock=stock_path.read_bytes()
    if len(stock)!=EXPECTED_HFB_SIZE: raise RuntimeError("Stock A0.48 size mismatch")
    if hashlib.sha256(stock).hexdigest()!=STOCK_SHA256: raise RuntimeError("Stock A0.48 SHA-256 mismatch")
    core=HHPATCH.apply_generic_hold_core(stock)
    illegal=[i for i,(a,b) in enumerate(zip(core,data)) if a!=b and not (i<4 or ALLOWED_TABLE_START<=i<ALLOWED_TABLE_END)]
    if illegal: raise RuntimeError(f"Refusing: change outside CRC/descriptor whitelist at 0x{illegal[0]:X}")
    stored_global=int.from_bytes(data[0:2],"little"); stored_main=int.from_bytes(data[2:4],"little"); main=data[4:4+MAIN_SIZE]
    if crc16_ref(main)!=stored_main: raise RuntimeError("Main CRC16 mismatch")
    if crc16_ref(data[2:])!=stored_global: raise RuntimeError("Global CRC16 mismatch")
    footer=data[-16:]
    if footer[:6]!=EXPECTED_FIRM_TYPE: raise RuntimeError(f"Unexpected firmware type footer: {footer!r}")
    if footer[8:10]!=bytes([0x04,0x08]): raise RuntimeError("Expected A0.48 footer version 04 08")
    return {"data":data,"sha":sha,"global_crc":stored_global,"main_crc":stored_main,
            "main_crc_bytes":data[2:4],"global_crc_bytes":data[0:2],"main":main,"firm_raw":data,"firm_size":len(data)}

def make_packet(cmd, body=b""):
    if len(body) > 59:
        raise ValueError("Body too large for 64-byte HHKB HID payload")
    p = bytearray(64)
    p[0] = 0xAA
    p[1] = 0xAA
    p[2] = cmd
    p[3] = 0
    p[4] = len(body)
    p[5:5+len(body)] = body
    return bytes(p)

def build_packets(fw):
    # PFU application-update container protocol:
    # E1 carries FULL HFB size and Global CRC (HFB[0:2]).
    # FirmupSend then streams FirmRawData.Skip(2) = HFB[2:].
    e1_body = (
        fw["firm_size"].to_bytes(4, "little")
        + fw["global_crc_bytes"]
        + b"\x00\x00"
    )
    e1 = make_packet(0xE1, e1_body)

    payload = fw["firm_raw"][2:]
    chunks = [payload[i:i+57] for i in range(0, len(payload), 57)]
    e2 = []
    for n, chunk in enumerate(chunks):
        body = n.to_bytes(2, "little") + chunk
        e2.append(make_packet(0xE2, body))

    e3 = make_packet(0xE3)

    if b"".join(chunks) != payload:
        raise RuntimeError("Internal E2 reassembly check failed")

    expected = (len(payload) + 56) // 57
    if len(e2) != expected:
        raise RuntimeError(
            f"Unexpected E2 packet count: got {len(e2)}, expected {expected}"
        )

    return e1, e2, e3

def print_dry_run(fw, e1, e2, e3):
    print("=== HHKB TopreRT v0.13 GUI-validated generic-HOLD updater DRY RUN ===")
    print("NO USB I/O WILL OCCUR.")
    print()
    print("HFB SHA256 :", fw["sha"])
    print("HFB size   :", len(fw["data"]))
    print("FirmSize   :", fw["firm_size"], f"(0x{fw['firm_size']:08X})")
    print("Main image :", len(fw["main"]))
    print("Main CRC   :", f"{fw['main_crc']:04X}",
          "bytes", fw["main_crc_bytes"].hex(" "))
    print("Global CRC :", f"{fw['global_crc']:04X}",
          "bytes", fw["global_crc_bytes"].hex(" "))
    print("E2 payload :", len(fw["firm_raw"]) - 2, "bytes (HFB[2:])")
    print()
    print("E1        :", e1[:16].hex(" "))
    print("E2 #0     :", e2[0][:16].hex(" "))
    print("E2 #1     :", e2[1][:16].hex(" "))
    print("E2 #256   :", e2[256][:16].hex(" "))
    print("E2 last   :", e2[-1][:16].hex(" "))
    print("E3        :", e3[:16].hex(" "))
    print()
    print("E2 count  :", len(e2))
    print("Final data:", e2[-1][4] - 2, "bytes")
    print()
    print("Expected crucial values:")
    print(f"  FirmSize {fw['firm_size']} -> {fw['firm_size'].to_bytes(4,'little').hex(' ')}")
    print(f"  Global CRC        -> {fw['global_crc_bytes'].hex(' ')}")
    print("  E2 #1 counter     -> 01 00")
    print("  E2 #256 counter   -> 00 01")

# -------- HID functions exist only below this line --------

def load_hid():
    try:
        import hid
    except ImportError:
        raise RuntimeError("hidapi missing. Install with: py -m pip install hidapi")
    return hid

def enumerate_vendor(hid):
    found = []
    for d in hid.enumerate(VID, 0):
        if d.get("product_id") not in PIDS:
            continue
        path = d["path"]
        s = path.decode(errors="ignore") if isinstance(path, bytes) else str(path)
        # Match the exact same interface family used by PFU's HardwareIdPattern.
        if d.get("interface_number") == 2 or "mi_02" in s.lower():
            found.append(d)
    return found

def wait_for_one_vendor(hid, timeout_s=20):
    deadline = time.time() + timeout_s
    last_count = None
    while time.time() < deadline:
        ds = enumerate_vendor(hid)
        last_count = len(ds)
        if len(ds) == 1:
            return ds[0]
        if len(ds) > 1:
            raise RuntimeError(f"Multiple HHKB vendor interfaces found: {len(ds)}")
        time.sleep(0.25)
    raise RuntimeError(f"HHKB vendor interface did not appear (last count={last_count})")

def open_device(hid, desc):
    dev = hid.device()
    dev.open_path(desc["path"])
    return dev

def tx(dev, payload):
    # Windows hidapi: prepend report-ID byte 0 to the 64-byte payload.
    n = dev.write(bytes([0]) + payload)
    if n <= 0:
        raise RuntimeError("HID write failed")

def rx(dev, timeout=TIMEOUT_MS):
    r = bytes(dev.read(64, timeout))
    if not r:
        raise TimeoutError("HID read timeout")
    return r

def request(dev, payload, expected_prefix):
    tx(dev, payload)
    r = rx(dev)
    if not r.startswith(expected_prefix):
        raise RuntimeError(
            "Unexpected response\n"
            f"expected prefix: {expected_prefix.hex(' ')}\n"
            f"received       : {r.hex(' ')}"
        )
    return r

def cmd_open():
    return make_packet(0x01, b"\x00")

def _query_declared(dev, command):
    """
    Send a simple query and validate only the common PFU response envelope:
      55 55 CMD 00 00 LEN ...
    Return the declared payload bytes. This avoids assuming model-specific
    response lengths before flash mode begins.
    """
    r = request(dev, make_packet(command), bytes([0x55,0x55,command,0,0]))
    n = r[5]
    if n > 58:
        raise RuntimeError(f"Command {command:02X}: invalid declared length {n}")
    if 6+n > len(r):
        raise RuntimeError(f"Command {command:02X}: truncated response")
    return bytes(r[6:6+n]), r

def query_info(dev):
    payload, raw = _query_declared(dev, 0x02)

    # Observed Hybrid A0.48 info layout begins with:
    # 20-byte type, 4-byte revision, 16-byte serial, then binary metadata.
    if len(payload) < 40:
        raise RuntimeError(f"Info response too short: {len(payload)}")

    typ = payload[0:20].split(b"\0",1)[0].decode("ascii","replace")
    rev = payload[20:24].split(b"\0",1)[0].decode("ascii","replace")
    serial = payload[24:40].split(b"\0",1)[0].decode("ascii","replace")
    tail = payload[40:]

    return {
        "type": typ,
        "revision": rev,
        "serial": serial,
        "tail": tail,
        "payload": payload,
        "raw": raw,
    }

def query_dips(dev):
    payload, raw = _query_declared(dev, 0x05)
    return {"payload": payload, "raw": raw}

def query_mode(dev):
    payload, raw = _query_declared(dev, 0x06)
    return {"payload": payload, "raw": raw}

def capture_identity(dev):
    request(dev, cmd_open(), bytes([0x55,0x55,0x01,0,0,0]))
    return (query_info(dev), query_dips(dev), query_mode(dev))

def do_flash(fw, e1, e2_packets, e3):
    hid = load_hid()

    desc = wait_for_one_vendor(hid, 5)
    print(f"Connected VID={desc.get('vendor_id'):04X} PID={desc.get('product_id'):04X}")
    dev = open_device(hid, desc)

    try:
        ident1 = capture_identity(dev)

        # Re-read immediately. Compare raw payload bytes, not guessed field layouts.
        ident2 = (query_info(dev), query_dips(dev), query_mode(dev))

        def identity_bytes(identity):
            info, dips, mode = identity
            return (
                info["payload"],
                dips["payload"],
                mode["payload"],
            )

        if identity_bytes(ident1) != identity_bytes(ident2):
            raise RuntimeError("Keyboard identity/state changed during preflight")

        info, dips, mode = ident1
        print("Type       :", info["type"])
        print("Revision   :", info["revision"])
        print("Serial     :", info["serial"])
        print("Info tail  :", info["tail"].hex(" "))
        print("DIP payload:", dips["payload"].hex(" "))
        print("Mode data  :", mode["payload"].hex(" "))

        if not info["type"].startswith("PD-KB8"):
            raise RuntimeError("Refusing: device does not look like an HHKB 800-series keyboard")

        # GUI already required an exact SHA-derived confirmation phrase.
        # E0: enter application firmware-update state.
        print("E0: entering firmware-update state...")
        request(dev, make_packet(0xE0), bytes([0x55,0x55,0xE0,0,0,0]))
    finally:
        dev.close()

    print("Waiting 10 seconds, matching PFU updater...")
    time.sleep(10)

    desc = wait_for_one_vendor(hid, 10)
    print(f"Updater interface PID={desc.get('product_id'):04X}")
    dev = open_device(hid, desc)
    try:
        print("E1: start...")
        request(dev, e1, bytes([0x55,0x55,0xE1,0,0,0]))

        print(f"E2: sending {len(e2_packets)} packets...")
        for n, p in enumerate(e2_packets):
            r = request(dev, p, bytes([0x55,0x55,0xE2,0,0,2]))
            expected = n.to_bytes(2, "little")
            if r[6:8] != expected:
                raise RuntimeError(
                    f"E2 ACK counter mismatch at packet {n}: "
                    f"got {r[6:8].hex(' ')}, expected {expected.hex(' ')}"
                )
            if n % 50 == 0 or n == len(e2_packets)-1:
                pct = (n+1)*100/len(e2_packets)
                print(f"  {n+1:4d}/{len(e2_packets)}  {pct:5.1f}%")

        print("E3: finalize...")
        request(dev, e3, bytes([0x55,0x55,0xE3,0,0,0]))
    finally:
        dev.close()

    print("Waiting 10 seconds for normal firmware to return...")
    time.sleep(10)

    desc = wait_for_one_vendor(hid, 10)
    dev = open_device(hid, desc)
    try:
        # Do not require the UI version to change; DIAG is still A0.48.
        request(dev, cmd_open(), bytes([0x55,0x55,0x01,0,0,0]))
        info = query_info(dev)
        print("Reconnect OK.")
        print("Type     :", info["type"])
        print("Revision :", info["revision"])
        print("Serial   :", info["serial"])
        print("Info tail:", info["tail"].hex(" "))
    finally:
        dev.close()

    print()
    print("FLASH SEQUENCE COMPLETED.")
    print("GUI-validated custom-slot firmware installed. Verify ordinary typing and configured tap/hold behavior.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hfb")
    ap.add_argument("--baseline", required=True, help="exact stock A0.48 HFB")
    ap.add_argument("--expected-sha", required=True)
    ap.add_argument("--confirm-token", required=True)
    ap.add_argument("--flash", action="store_true")
    args = ap.parse_args()

    expected_sha = args.expected_sha.lower().strip()
    required_token = "FLASH-" + expected_sha[:12].upper()
    if args.confirm_token != required_token:
        raise RuntimeError("Confirmation token mismatch")

    fw = parse_hfb(Path(args.hfb), expected_sha, Path(args.baseline))
    e1, e2, e3 = build_packets(fw)
    print_dry_run(fw, e1, e2, e3)

    if not args.flash:
        return

    print()
    print("WARNING: real application firmware update starting.")
    print("Do not disconnect USB or let the PC sleep during E1/E2/E3.")
    do_flash(fw, e1, e2, e3)

if __name__ == "__main__":
    main()
