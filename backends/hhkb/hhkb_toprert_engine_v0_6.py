#!/usr/bin/env python3
"""
HHKB TopreRT engine v0.6 FINAL CLI

Platform:
  HHKB Professional Hybrid / Hybrid Type-S
Source:
  exact A0.48 HFB only

This module contains:
- fail-closed A0.48 patch/build validation
- application-firmware writer (E0/E1/E2/E3 only)
- stock A0.48 restore writer
- read-only Observer telemetry
- device status query

v0.6 FINAL CLI keeps the hardware-tested RT core and the hardware-verified
multi-key telemetry capture path so one of the known Observer keys can be followed
through press, partial release, re-press, and final release.

The multi-key telemetry extension has been hardware-verified on the supported Observer key set.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import time

VERSION = "0.6.0"

VID = 0x04FE
PIDS = {0x0020, 0x0021, 0x0022}
PID_NORMAL = 0x0021

EXPECTED_SIZE = 282672
STOCK_SHA256 = "635b995eb5a15aa50c2cedc60da7d8998fcca8285a09d41d984c07fffcaf9d43"

MCU_OFF = 4
MCU_SIZE = 65536
POLY = 0x8408
TIMEOUT_MS = 60000

CAL_FULL_RAW_SPAN = 2394.5
CAL_FULL_TRAVEL_MM = 4.0
RAW_PER_MM = CAL_FULL_RAW_SPAN / CAL_FULL_TRAVEL_MM
MM_PER_RAW = 1.0 / RAW_PER_MM

KEY_MAP = {
    "R": 34,
    "E": 18,
    "W": 10,
    "A": 27,
    "S": 11,
    "D": 19,
    "SPACE": 48,
}

HOOK_A = (19724, 19728)
HOOK_B = (20008, 20012)
CMD99 = (44248, 44254)

HELPER_START = 59772
V04_HELPER_END = 60052
V05_HELPER_END = 60112

REPRESS_IMM = 59860
RELEASE_IMM = 59866

# Existing pre-helper call at helper+0x62:
# old BL -> C-only capture @ helper+0xB4
# new BL -> sticky any-key capture @ helper+0x118
CAPTURE_CALL = HELPER_START + 0x62
CAPTURE_CALL_OLD = bytes.fromhex("00f027f8")
CAPTURE_CALL_V05 = bytes.fromhex("00f059f8")
V05_CAPTURE_START = HELPER_START + 0x118

STOCK_HOOK_A = bytes.fromhex("0646a642")
STOCK_HOOK_B = bytes.fromhex("0e480f49")

DIAG_HOOK_A = bytes.fromhex("09f036fe")
DIAG_HOOK_B = bytes.fromhex("09f0e2fd")
DIAG_CMD99 = bytes.fromhex("03f0c2fe00bf")

# Known v0.4 telemetry-enabled helper, including historical C-only capture
# and 0x99 response sender. Config immediates are patched at build time.
V04_DIAG_HELPER = bytes.fromhex(
    "06460fb5194801781948425c9308002b27d03146091b09112031012900da01213f2900dd3f2103200240002a03d0994204dd0b4602e0994200da0b4699000a430a4801780a4842540320024020201b1a1b01e318002a02d120331c4601e0203b1c4600f027f80fbca64200bde90000201a180020"
    "0cb50d4801780d48425c9308002b0cd1032d0ad13246121b12112032012a00da01223f2a00dd3f221346032215409b001d43024800490cbde90000201a180020"
    "0fb50848017823290bd1074806814481064a525c02739308437303231a408273c1730fbde9000020aa0900201a180020"
    "10b50a49552008704870992088700020c8700b20087152204871542088710120c87140220248f7f717fd10bdaa0900208c190020"
)

# New capture routine appended after the v0.4 helper.
#
# Behavior:
# - any non-released physical key may become the telemetry target;
# - once selected, its state==0 samples continue to be captured while its
#   index matches txbuf[15], so release-complete remains observable;
# - other released keys do not overwrite the active target.
V05_STICKY_CAPTURE = bytes.fromhex(
    "0fb50b4801780b48425c03231a4203d10948c37b994209d10748068144810273"
    "9308437303231a408273c1730fbd0000e90000201a180020aa090020"
)

class Reject(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crc16(data: bytes) -> int:
    c = 0xFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ POLY if c & 1 else c >> 1
            c &= 0xFFFF
    return c


def raw_to_mm(raw: int) -> float:
    return raw * MM_PER_RAW


def mm_to_raw(mm: float) -> int:
    if mm <= 0:
        raise Reject(f"distance must be > 0 mm; got {mm}")
    raw = int(mm * RAW_PER_MM + 0.5)
    if not 1 <= raw <= 255:
        raise Reject(
            f"{mm} mm converts to {raw} raw; supported estimated range is "
            f"~{MM_PER_RAW:.4f}..{255*MM_PER_RAW:.4f} mm"
        )
    return raw


def validate_distance(name: str, value: int) -> None:
    if not 1 <= value <= 255:
        raise Reject(f"{name} must be 1..255 raw; got {value}")


def validate_stock(data: bytes) -> None:
    if len(data) != EXPECTED_SIZE:
        raise Reject(f"stock size mismatch: {len(data)}")
    if sha256(data) != STOCK_SHA256:
        raise Reject("stock SHA-256 mismatch; exact HHKB A0.48 is required")
    if crc16(data[MCU_OFF:MCU_OFF+MCU_SIZE]) != int.from_bytes(data[2:4], "little"):
        raise Reject("stock main CRC invalid")
    if crc16(data[2:]) != int.from_bytes(data[0:2], "little"):
        raise Reject("stock global CRC invalid")
    if data[HOOK_A[0]:HOOK_A[1]] != STOCK_HOOK_A:
        raise Reject("stock Hook A mismatch")
    if data[HOOK_B[0]:HOOK_B[1]] != STOCK_HOOK_B:
        raise Reject("stock Hook B mismatch")
    if data[HELPER_START:V05_HELPER_END] != b"\xff" * (V05_HELPER_END-HELPER_START):
        raise Reject("required helper cave is not empty")


def expected_v05_helper(release_raw: int, repress_raw: int) -> bytes:
    validate_distance("release", release_raw)
    validate_distance("re-press", repress_raw)

    h = bytearray(V04_DIAG_HELPER)

    rel = RELEASE_IMM - HELPER_START
    rep = REPRESS_IMM - HELPER_START
    if h[rel+1] != 0x3B or h[rep+1] != 0x33:
        raise Reject("internal RT immediate opcodes do not match expected helper")

    h[rel] = release_raw
    h[rep] = repress_raw

    call = CAPTURE_CALL - HELPER_START
    if bytes(h[call:call+4]) != CAPTURE_CALL_OLD:
        raise Reject("internal capture BL regression mismatch")
    h[call:call+4] = CAPTURE_CALL_V05

    return bytes(h) + V05_STICKY_CAPTURE


def build(stock: bytes, release_raw: int, repress_raw: int) -> bytes:
    validate_stock(stock)
    helper = expected_v05_helper(release_raw, repress_raw)

    out = bytearray(stock)
    out[HOOK_A[0]:HOOK_A[1]] = DIAG_HOOK_A
    out[HOOK_B[0]:HOOK_B[1]] = DIAG_HOOK_B
    out[CMD99[0]:CMD99[1]] = DIAG_CMD99
    out[HELPER_START:V05_HELPER_END] = helper

    tail_before = stock[MCU_OFF+MCU_SIZE:]
    scatter_a = MCU_OFF + (0x0801E7A0 - 0x08010000)
    scatter_b = MCU_OFF + (0x0801E7C0 - 0x08010000)
    scatter_before = stock[scatter_a:scatter_b]

    out[2:4] = crc16(out[MCU_OFF:MCU_OFF+MCU_SIZE]).to_bytes(2, "little")
    out[0:2] = crc16(out[2:]).to_bytes(2, "little")

    if bytes(out[MCU_OFF+MCU_SIZE:]) != tail_before:
        raise Reject("tail/footer changed")
    if bytes(out[scatter_a:scatter_b]) != scatter_before:
        raise Reject("startup/scatter table changed")

    changed = {i for i, (a, b) in enumerate(zip(stock, out)) if a != b}
    allowed = (
        set(range(0, 4))
        | set(range(*HOOK_A))
        | set(range(*HOOK_B))
        | set(range(*CMD99))
        | set(range(HELPER_START, V05_HELPER_END))
    )
    if not changed <= allowed:
        raise Reject("changes escaped CRC/hooks/helper whitelist")

    if crc16(out[MCU_OFF:MCU_OFF+MCU_SIZE]) != int.from_bytes(out[2:4], "little"):
        raise Reject("output main CRC verification failed")
    if crc16(out[2:]) != int.from_bytes(out[0:2], "little"):
        raise Reject("output global CRC verification failed")

    return bytes(out)


def validate_candidate(stock: bytes, cand: bytes):
    validate_stock(stock)
    if len(cand) != EXPECTED_SIZE:
        raise Reject("candidate size mismatch")
    if crc16(cand[MCU_OFF:MCU_OFF+MCU_SIZE]) != int.from_bytes(cand[2:4], "little"):
        raise Reject("candidate main CRC invalid")
    if crc16(cand[2:]) != int.from_bytes(cand[0:2], "little"):
        raise Reject("candidate global CRC invalid")

    if cand[-16:-10] != b"AHUX01" or cand[-8:-6] != bytes([0x04, 0x08]):
        raise Reject("candidate footer is not HHKB A0.48")

    if cand[HOOK_A[0]:HOOK_A[1]] != DIAG_HOOK_A:
        raise Reject("Hook A mismatch")
    if cand[HOOK_B[0]:HOOK_B[1]] != DIAG_HOOK_B:
        raise Reject("Hook B mismatch")
    if cand[CMD99[0]:CMD99[1]] != DIAG_CMD99:
        raise Reject("0x99 telemetry command patch mismatch")

    helper = cand[HELPER_START:V05_HELPER_END]
    rel = RELEASE_IMM - HELPER_START
    rep = REPRESS_IMM - HELPER_START
    release = helper[rel]
    repress = helper[rep]

    expected = expected_v05_helper(release, repress)
    if helper != expected:
        raise Reject("helper differs from approved v0.5 structure")

    changed = {i for i, (a, b) in enumerate(zip(stock, cand)) if a != b}
    allowed = (
        set(range(0, 4))
        | set(range(*HOOK_A))
        | set(range(*HOOK_B))
        | set(range(*CMD99))
        | set(range(HELPER_START, V05_HELPER_END))
    )
    if not changed <= allowed:
        raise Reject("candidate differs from stock outside whitelist")

    return release, repress


def write_manifest(path: Path, output: bytes, release_raw: int, repress_raw: int,
                   requested_release_mm=None, requested_repress_mm=None):
    info = {
        "toolkit_version": VERSION,
        "release_channel": "final-cli-before-gui",
        "platform": "HHKB Professional Hybrid / Hybrid Type-S",
        "source_firmware": "A0.48 exact",
        "source_sha256": STOCK_SHA256,
        "output_sha256": sha256(output),
        "release_raw": release_raw,
        "repress_raw": repress_raw,
        "release_mm_estimated": raw_to_mm(release_raw),
        "repress_mm_estimated": raw_to_mm(repress_raw),
        "requested_release_mm": requested_release_mm,
        "requested_repress_mm": requested_repress_mm,
        "mm_conversion": {
            "status": "estimated",
            "full_raw_span": CAL_FULL_RAW_SPAN,
            "full_travel_mm": CAL_FULL_TRAVEL_MM,
            "raw_per_mm": RAW_PER_MM,
            "assumption": "linear full-travel normalization; intermediate linearity not established",
        },
        "rt_core": "v0.4 hardware-tested core retained",
        "telemetry": "multi-key sticky capture — hardware verified",
        "observer_keys": KEY_MAP,
        "environment": {
            "Windows_DIP": "recommended / tested",
            "low_power": "supported / tested",
            "Mac_DIP": "not recommended / not validated",
        },
        "main_crc": f"{int.from_bytes(output[2:4], 'little'):04X}",
        "global_crc": f"{int.from_bytes(output[0:2], 'little'):04X}",
    }
    Path(str(path) + ".manifest.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------- USB writer ----------------

def packet(c, body=b""):
    p = bytearray(64)
    p[0] = 0xAA
    p[1] = 0xAA
    p[2] = c
    p[3] = 0
    p[4] = len(body)
    p[5:5+len(body)] = body
    return bytes(p)


def build_packets(image: bytes):
    e1 = packet(0xE1, len(image).to_bytes(4, "little") + image[0:2] + b"\0\0")
    payload = image[2:]
    chunks = [payload[i:i+57] for i in range(0, len(payload), 57)]
    e2 = [packet(0xE2, n.to_bytes(2, "little") + chunk)
          for n, chunk in enumerate(chunks)]
    return e1, e2, packet(0xE3)


def load_hid():
    try:
        import hid
    except ImportError as e:
        raise Reject("hidapi missing. Install with: py -m pip install hidapi") from e
    return hid


def enum_vendor(hid):
    rows = []
    for d in hid.enumerate(VID, 0):
        if d.get("product_id") not in PIDS:
            continue
        p = d["path"]
        s = p.decode(errors="ignore") if isinstance(p, bytes) else str(p)
        if d.get("interface_number") == 2 or "mi_02" in s.lower():
            rows.append(d)
    return rows


def wait_one(hid, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        ds = enum_vendor(hid)
        if len(ds) == 1:
            return ds[0]
        if len(ds) > 1:
            raise Reject("multiple HHKB vendor interfaces found")
        time.sleep(0.25)
    raise Reject("HHKB vendor interface did not appear")


def open_dev(hid, desc):
    dev = hid.device()
    dev.open_path(desc["path"])
    return dev


def tx(dev, p):
    if dev.write(bytes([0]) + p) <= 0:
        raise Reject("HID write failed")


def rx(dev, timeout=TIMEOUT_MS):
    r = bytes(dev.read(64, timeout))
    if not r:
        raise Reject("HID timeout")
    return r


def req(dev, p, prefix):
    tx(dev, p)
    r = rx(dev)
    if not r.startswith(prefix):
        raise Reject("unexpected HID response: " + r.hex(" "))
    return r


def query(dev, c):
    r = req(dev, packet(c), bytes([0x55, 0x55, c, 0, 0]))
    n = r[5]
    return bytes(r[6:6+n])


def identity(dev):
    req(dev, packet(0x01, b"\0"), bytes([0x55, 0x55, 1, 0, 0, 0]))
    return query(dev, 0x02), query(dev, 0x05), query(dev, 0x06)


def decode_identity(info: bytes):
    typ = info[0:20].split(b"\0", 1)[0].decode("ascii", "replace")
    return typ


def device_status():
    hid = load_hid()
    desc = wait_one(hid, 5)
    dev = open_dev(hid, desc)
    try:
        ident1 = identity(dev)
        ident2 = (query(dev, 0x02), query(dev, 0x05), query(dev, 0x06))
        if ident1 != ident2:
            raise Reject("identity changed during status query")
        typ = decode_identity(ident1[0])
        return {
            "type": typ,
            "pid": desc.get("product_id"),
            "info": ident1[0],
            "dips": ident1[1],
            "mode": ident1[2],
        }
    finally:
        dev.close()


def flash_image(image: bytes, confirmation: str, label: str):
    # image must already have been fail-closed validated by caller.
    e1, e2, e3 = build_packets(image)
    hid = load_hid()
    desc = wait_one(hid, 5)
    dev = open_dev(hid, desc)

    try:
        ident1 = identity(dev)
        ident2 = (query(dev, 0x02), query(dev, 0x05), query(dev, 0x06))
        if ident1 != ident2:
            raise Reject("identity changed during preflight")
        typ = decode_identity(ident1[0])
        if not typ.startswith("PD-KB8"):
            raise Reject("connected device does not look like HHKB 800-series")

        print("Connected :", typ)
        print("DIP data  :", ident1[1].hex(" "))
        print("Mode data :", ident1[2].hex(" "))
        print("WARNING   : do not disconnect USB or allow the PC to sleep.")

        phrase = input(f'Type exactly "{confirmation}" to continue: ')
        if phrase != confirmation:
            print("Cancelled.")
            return False

        print(f"E0: entering update state for {label}...")
        req(dev, packet(0xE0), bytes([0x55, 0x55, 0xE0, 0, 0, 0]))
    finally:
        dev.close()

    print("Waiting 10 seconds...")
    time.sleep(10)
    desc = wait_one(hid, 10)
    dev = open_dev(hid, desc)

    try:
        print("E1: start...")
        req(dev, e1, bytes([0x55, 0x55, 0xE1, 0, 0, 0]))
        print("E2: sending", len(e2), "packets...")
        for n, p in enumerate(e2):
            r = req(dev, p, bytes([0x55, 0x55, 0xE2, 0, 0, 2]))
            if r[6:8] != n.to_bytes(2, "little"):
                raise Reject(f"E2 ACK mismatch at packet {n}")
            if n % 100 == 0 or n == len(e2)-1:
                print(f"  {n+1:4d}/{len(e2)} {(n+1)*100/len(e2):5.1f}%")

        print("E3: finalize...")
        req(dev, e3, bytes([0x55, 0x55, 0xE3, 0, 0, 0]))
    finally:
        dev.close()

    print("Waiting 10 seconds for reconnect...")
    time.sleep(10)
    desc = wait_one(hid, 10)
    dev = open_dev(hid, desc)
    try:
        identity(dev)
    finally:
        dev.close()

    print("FLASH SEQUENCE COMPLETED.")
    return True


def install_toprert(stock: bytes, cand: bytes):
    release, repress = validate_candidate(stock, cand)
    print("Candidate SHA :", sha256(cand))
    print(f"Release       : {release} raw (~{raw_to_mm(release):.3f} mm estimated)")
    print(f"Re-press      : {repress} raw (~{raw_to_mm(repress):.3f} mm estimated)")
    print("Main CRC      : %04X" % int.from_bytes(cand[2:4], "little"))
    print("Global CRC    : %04X" % int.from_bytes(cand[0:2], "little"))
    print("Whitelist     : PASS")
    print("Helper config : PASS")
    print("Telemetry     : multi-key sticky capture — HARDWARE VERIFIED")
    return release, repress


def restore_preflight(stock: bytes):
    validate_stock(stock)
    print("Stock SHA     :", sha256(stock))
    print("Main CRC      : %04X" % int.from_bytes(stock[2:4], "little"))
    print("Global CRC    : %04X" % int.from_bytes(stock[0:2], "little"))
    print("Exact A0.48   : PASS")


# ---------------- Observer ----------------

def parse_diag(r: bytes, release_raw: int, repress_raw: int):
    if r[:8] != bytes([0x55, 0x55, 0x99, 0, 11, 0x52, 0x54, 1]):
        raise Reject("TopreRT telemetry signature not found")

    raw = int.from_bytes(r[8:10], "little")
    dyn = int.from_bytes(r[10:12], "little")
    packed = r[12]
    anchor = r[13]
    state = r[14]
    idx = r[15]

    if anchor:
        if state == 0:
            anchor_raw = dyn - repress_raw
        else:
            anchor_raw = dyn + release_raw
        stock = anchor_raw - (anchor - 32) * 16
    else:
        anchor_raw = None
        stock = dyn

    return {
        "raw": raw,
        "dyn": dyn,
        "packed": packed,
        "anchor": anchor,
        "state": state,
        "index": idx,
        "anchor_raw": anchor_raw,
        "stock": stock,
    }
