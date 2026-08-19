# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
# Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
"""
HHKB TopreRT v0.13 generic HOLD descriptor builder v0.2

OFFLINE / FAIL-CLOSED:
  - no HID access
  - no USB commands
  - no flashing

The executable/core/hooks/wrappers are SHA-locked to the hardware-tested
v0.13 rev2.2 generic-HOLD baseline.

Only:
  HFB[0:4]              CRC fields
  HFB[0xEEA8:0xEEE8]    8 x 8-byte descriptor table
may differ from the baseline.

Descriptor:
  +0 flags        bit0 enabled
  +1 source       physical internal index
  +2 tap          physical/internal key index
  +3 hold         physical/internal key index
  +4/+5 threshold milliseconds, little-endian
  +6 slot number metadata
  +7 reserved 0

Safety constraints for the first public generic-HOLD engine:
  - duplicate Source values are rejected
  - Hold must not equal its Source
  - Hold must not be ANY enabled dual-role Source
  - LSHIFT/RSHIFT remain blocked as HOLD targets
  - FN is accepted only for SPACE -> tap SPACE / hold FN (hardware-verified special case)
  - LSHIFT remains excluded as a Source/Tap because its tap semantics are not proven

Hardware-validated representative HOLD targets:
  V, CTRL/LeftCtrl, LALT, SPACE.
Hardware-validated special case:
  SPACE -> tap SPACE / hold FN.
Other non-blocked targets use the same stock emitter path but remain less-tested.
"""

from __future__ import annotations
import hashlib
from pathlib import Path
import importlib.util

PATCH_MODULE_PATH=Path(__file__).resolve().parent/"backends"/"hhkb"/"hhkb_v013_generic_hold_core_patch_v0_1.py"
_spec=importlib.util.spec_from_file_location("hhkb_v013_generic_hold_core_patch_v0_1",PATCH_MODULE_PATH)
HHPATCH=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(HHPATCH)
STOCK_SHA256=HHPATCH.STOCK_SHA256
GENERIC_CORE_REFERENCE_SHA256=HHPATCH.GENERIC_CORE_REFERENCE_SHA256
EXPECTED_SIZE = 0x45030
MAIN_SIZE = 0x10000
TABLE_RUNTIME = 0x0801EEA4
MAIN_RUNTIME_BASE = 0x08010000
TABLE_HFB_OFFSET = 4 + (TABLE_RUNTIME - MAIN_RUNTIME_BASE)
SLOT_SIZE = 8
SLOT_COUNT = 8
TABLE_SIZE = SLOT_SIZE * SLOT_COUNT
FIRM_TYPE = b"AHUX01"

KEY_MAP = {
    'ESC': 1, '1': 25, '2': 9, '3': 17, '4': 33, '5': 41, '6': 49, '7': 57,
    '8': 89, '9': 65, '0': 73, 'MINUS': 81, 'EQUAL': 97, 'BACKSLASH': 113,
    'GRAVE': 105, 'TAB': 2, 'Q': 26, 'W': 10, 'E': 18, 'R': 34, 'T': 42,
    'Y': 58, 'U': 90, 'I': 66, 'O': 74, 'P': 82, 'LBRACKET': 98,
    'RBRACKET': 114, 'BACKSPACE': 106, 'CTRL': 3, 'A': 27, 'S': 11, 'D': 19,
    'F': 40, 'G': 50, 'H': 59, 'J': 91, 'K': 67, 'L': 75, 'SEMICOLON': 83,
    'QUOTE': 99, 'ENTER': 115, 'LSHIFT': 0, 'Z': 8, 'X': 16, 'C': 35,
    'V': 43, 'B': 51, 'N': 56, 'M': 88, 'COMMA': 64, 'DOT': 72,
    'SLASH': 96, 'RSHIFT': 112, 'FN': 107, 'LALT': 24, 'LGUI': 32,
    'SPACE': 48, 'RGUI': 80, 'RALT': 104,
}
INDEX_TO_NAME = {v: k for k, v in KEY_MAP.items()}
BLOCKED_SOURCE_TAP = {KEY_MAP["LSHIFT"]}
BLOCKED_HOLD = {KEY_MAP["LSHIFT"], KEY_MAP["RSHIFT"]}
SPACEFN_SOURCE = KEY_MAP["SPACE"]
SPACEFN_TAP = KEY_MAP["SPACE"]
SPACEFN_HOLD = KEY_MAP["FN"]

HW_VALIDATED_HOLD_NAMES = {"CTRL", "LALT", "V", "SPACE"}

def hold_support_status(name: str) -> str:
    key = name.strip().upper()
    if key not in KEY_MAP:
        return "UNKNOWN"
    if KEY_MAP[key] in BLOCKED_HOLD:
        return "BLOCKED"
    if key == "FN":
        return "HW VALIDATED — SPACEFN ONLY"
    if key in HW_VALIDATED_HOLD_NAMES:
        return "HW VALIDATED"
    return "GENERIC / LIMITED TESTING"

class Reject(RuntimeError):
    pass

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def crc16_ref(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8408) if (crc & 1) else (crc >> 1)
            crc &= 0xFFFF
    return crc

def parse_key(text: str) -> int:
    s = text.strip().upper()
    if s in KEY_MAP:
        return KEY_MAP[s]
    try:
        value = int(s, 0)
    except ValueError:
        raise Reject(f"unknown key name/index: {text!r}")
    if not 0 <= value <= 255:
        raise Reject(f"key index out of range 0..255: {value}")
    return value

def parse_slot(spec: str) -> dict:
    # SOURCE>TAP>HOLD:MS ; tap may equal source.
    if ":" not in spec:
        raise Reject("slot must use SOURCE>TAP>HOLD:THRESHOLD_MS")
    keypart, ms_text = spec.rsplit(":", 1)
    parts = [x.strip() for x in keypart.split(">")]
    if len(parts) != 3:
        raise Reject("slot must use SOURCE>TAP>HOLD:THRESHOLD_MS")
    try:
        threshold = int(ms_text, 0)
    except ValueError:
        raise Reject(f"invalid threshold: {ms_text!r}")
    if not 1 <= threshold <= 0xFFFF:
        raise Reject(f"threshold must be 1..65535 ms, got {threshold}")
    src_name, tap_name, hold_name = [x.upper() for x in parts]
    return {
        "label": src_name,
        "source_name": src_name,
        "tap_name": tap_name,
        "hold_name": hold_name,
        "source": parse_key(src_name),
        "tap": parse_key(tap_name),
        "hold": parse_key(hold_name),
        "threshold_ms": threshold,
    }

def validate_stock(data: bytes):
    if len(data)!=EXPECTED_SIZE: raise Reject(f"wrong HFB size: {len(data)}; expected {EXPECTED_SIZE}")
    got=sha256(data)
    if got!=STOCK_SHA256:
        raise Reject(f"stock A0.48 SHA mismatch; got {got}; expected {STOCK_SHA256}")
    if data[-16:-10]!=FIRM_TYPE: raise Reject("unexpected AHUX01 footer")
    if data[-8:-6]!=bytes([0x04,0x08]): raise Reject("expected A0.48 footer bytes 04 08")
    if crc16_ref(data[4:4+MAIN_SIZE])!=int.from_bytes(data[2:4],"little"): raise Reject("stock main CRC mismatch")
    if crc16_ref(data[2:])!=int.from_bytes(data[0:2],"little"): raise Reject("stock global CRC mismatch")

def validate_slots(slots: list[dict]):
    if len(slots) > SLOT_COUNT:
        raise Reject(f"maximum {SLOT_COUNT} enabled slots")
    sources = [x["source"] for x in slots]
    if len(set(sources)) != len(sources):
        raise Reject("duplicate source key/index across enabled slots")
    source_set = set(sources)

    for n, cfg in enumerate(slots):
        source = cfg["source"]
        tap = cfg["tap"]
        hold = cfg["hold"]

        if source in BLOCKED_SOURCE_TAP:
            raise Reject(f"SLOT{n}: LSHIFT source is not supported")
        if tap in BLOCKED_SOURCE_TAP:
            raise Reject(f"SLOT{n}: LSHIFT tap is not supported")

        if hold in BLOCKED_HOLD:
            name = INDEX_TO_NAME.get(hold, str(hold))
            raise Reject(f"SLOT{n}: HOLD {name} is reserved/unsupported in this engine")

        # Hardware-verified FN exception is deliberately narrow:
        # only SPACE -> tap SPACE / hold FN is accepted.
        if hold == SPACEFN_HOLD:
            if source != SPACEFN_SOURCE or tap != SPACEFN_TAP:
                raise Reject(
                    f"SLOT{n}: HOLD FN is hardware-verified only for "
                    "SPACE>SPACE>FN; other FN HOLD sources remain unsupported"
                )

        if hold == source:
            raise Reject(f"SLOT{n}: HOLD must not equal Source")
        if hold in source_set:
            other = INDEX_TO_NAME.get(hold, str(hold))
            raise Reject(
                f"SLOT{n}: HOLD {other} is also an enabled dual-role Source; "
                "this ownership combination is intentionally blocked"
            )

def make_descriptor(slot_no: int, cfg: dict) -> bytes:
    return bytes([
        0x01,
        cfg["source"],
        cfg["tap"],
        cfg["hold"],
        cfg["threshold_ms"] & 0xFF,
        (cfg["threshold_ms"] >> 8) & 0xFF,
        slot_no & 0xFF,
        0x00,
    ])

def build(stock_hfb: bytes, slots: list[dict]) -> tuple[bytes, dict]:
    validate_stock(stock_hfb); validate_slots(slots)
    try: core=HHPATCH.apply_generic_hold_core(stock_hfb)
    except HHPATCH.PatchReject as exc: raise Reject(str(exc)) from exc
    out=bytearray(core); table=bytearray(TABLE_SIZE); report_slots=[]
    for n,cfg in enumerate(slots):
        desc=make_descriptor(n,cfg); table[n*SLOT_SIZE:(n+1)*SLOT_SIZE]=desc
        report_slots.append({"slot":n,**cfg,"hold_support":hold_support_status(cfg["hold_name"]),"descriptor_hex":desc.hex(" ")})
    out[TABLE_HFB_OFFSET:TABLE_HFB_OFFSET+TABLE_SIZE]=table
    main_crc=crc16_ref(bytes(out[4:4+MAIN_SIZE])); out[2:4]=main_crc.to_bytes(2,"little")
    global_crc=crc16_ref(bytes(out[2:])); out[0:2]=global_crc.to_bytes(2,"little")
    result=bytes(out)
    allowed=set(range(4))|set(range(TABLE_HFB_OFFSET,TABLE_HFB_OFFSET+TABLE_SIZE))
    bad=[i for i,(a,b) in enumerate(zip(core,result)) if a!=b and i not in allowed]
    if bad: raise Reject(f"internal safety failure outside CRC/table: {bad[:8]}")
    if crc16_ref(result[4:4+MAIN_SIZE])!=int.from_bytes(result[2:4],"little"): raise Reject("output main CRC verification failed")
    if crc16_ref(result[2:])!=int.from_bytes(result[0:2],"little"): raise Reject("output global CRC verification failed")
    return result,{
        "stock_sha256":sha256(stock_hfb),"generic_core_reference_sha256":GENERIC_CORE_REFERENCE_SHA256,
        "output_sha256":sha256(result),"size":len(result),"main_crc":f"0x{main_crc:04X}",
        "global_crc":f"0x{global_crc:04X}","descriptor_table_hex":bytes(table).hex(" "),"slots":report_slots,
        "policy":{"hold_not_source":True,"hold_not_enabled_source":True,"blocked_hold_names":["LSHIFT","RSHIFT"],
                  "hw_validated_hold_names":sorted(HW_VALIDATED_HOLD_NAMES),"generic_allowed_status":"GENERIC / LIMITED TESTING","spacefn_status":"HARDWARE VERIFIED","spacefn_rule":"SPACE>SPACE>FN with configurable threshold"}}
