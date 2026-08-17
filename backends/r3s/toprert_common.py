// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
// Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
"""Shared constants/utilities for TopreRT Toolkit v0.4."""

from __future__ import annotations
import hashlib

TOOLKIT_VERSION = "0.8.0"

RAW_PER_MM = 510.0
MIN_RAW = 104
MAX_RAW = 510

EXPECTED_SIZE = 65568
# Exact A0.12 images supplied/compared for the R3S A/B/C/D family.
# R3SB is hardware-verified in this project. A/C/D are byte-structure verified:
# their stock images differ from R3SB only in outer CRC and the model tag byte.
SUPPORTED_STOCKS = {
    "45be872b38e66f1974dcc0018e654c6c828936a807e819a988e898f2d853a64d": {"model": "R3SA", "rt_core": "BINARY VERIFIED", "observer": "NOT HARDWARE VALIDATED"},
    "7f475139d6585afa6c3079f0139ceb76f880b9718885bfd1e180d81ee08f531d": {"model": "R3SB", "rt_core": "HARDWARE VERIFIED", "observer": "HARDWARE VERIFIED"},
    "90e0ec8edd3eba758ff0785ddeee52fafa4fb95bb7466cce22ebc40a848b07e3": {"model": "R3SC", "rt_core": "BINARY VERIFIED", "observer": "NOT HARDWARE VALIDATED"},
    "5025fceec277fc001721cee9a7ed8891d9a7f4e4797d2412b4382be2be76da40": {"model": "R3SD", "rt_core": "BINARY VERIFIED", "observer": "NOT HARDWARE VALIDATED"},
}
EXPECTED_STOCK_SHA256 = "7f475139d6585afa6c3079f0139ceb76f880b9718885bfd1e180d81ee08f531d"  # legacy alias
STABLE_OUTPUT_SHA256 = "b6b3fbb299fca64e0bf01d5febd2bbeb5d25ccd6adbeae0c6ef935d62eb6e246"  # legacy R3SB alias
STABLE_OUTPUT_SHA256_BY_MODEL = {
    "R3SA": "a8281c66ae9fbc2c283c00e142d3d741f012a200bd10e91cd82243e7a109c0ec",
    "R3SB": "b6b3fbb299fca64e0bf01d5febd2bbeb5d25ccd6adbeae0c6ef935d62eb6e246",
    "R3SC": "ce7339bd615661a576a3853b4b88d5bd96524b4c72da3abc6fd5cd0598484eac",
    "R3SD": "2522155deba10f791c66a9e54314b52f442f790a8ebf211604832137b31706e6",
}
MODEL_TAG_OFFSET = 0x10010
MODEL_TAG_LENGTH = 8

MCU_SIZE = 65536
MCU_FILE_OFFSET = 4
HOOK_OFFSET = 0x6614
HOOK_EXPECT = bytes.fromhex("70 b5 05 46 09 48")
HOOK_PATCH = bytes.fromhex("08 b5 08 f0 a3 f8")
CAVE_OFFSET = 0xE760

BASE_HELPER = bytes.fromhex(
    "019b02b09e46f0b50646254f41014300c91ac9198c88234a3301d21815785688"
    "012d10d0022d11d0002d12d0b44201d954802646331b5b08992b02d354800020"
    "f0bd0120f0bd54800120f0bd54800020f0bd002e18d0134b1046c01a00093c28"
    "08d0cb8840339c4204d89e4202d80023538012e0a31b01d254800ee05b08cc2b"
    "0bd354800120f0bd143f798a7b89c9188c4202d954800120f0bd0020f0bd0000"
    "242b0020ac110020"
)
RELEASE_IMM_OFFSET = 56
REPRESS_IMM_OFFSET = 126

DEFAULT_RELEASE = 306
DEFAULT_REPRESS = 408
SPACE_INDEX = 60
DISARM_REST = 64

POLY = 0x8408

# Status reflects what was actually exercised on hardware during this project.
PROFILE_STATUS = {
    (306, 408): ("HARDWARE VERIFIED", "all-key stable candidate"),
    (306, 358): ("HARDWARE VERIFIED", "R-key transition validation"),
    (256, 358): ("HARDWARE VERIFIED", "R-key transition validation"),
}

PRESETS = {
    "stable": (306, 408, "Recommended: balanced general typing + gaming"),
    "responsive": (306, 358, "Faster re-press; hardware-verified on R-key transitions"),
    "fast-release": (256, 358, "Faster release; hardware-verified on R-key transitions"),
    # Historical/advanced aliases retained for reproducibility.
    "060-070": (306, 358, "alias of responsive"),
    "050-070": (256, 358, "alias of fast-release"),
    "040-060": (208, 306, "historical experimental profile"),
    "040-040": (208, 208, "historical symmetric profile"),
    "030-030": (156, 156, "historical symmetric profile"),
    "020-020": (104, 104, "historical first RT profile"),
}

class Reject(RuntimeError):
    pass

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def crc16(data: bytes) -> int:
    c = 0xFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ POLY if (c & 1) else c >> 1
    return c & 0xFFFF

def raw_to_mm(raw: int) -> float:
    return raw / RAW_PER_MM

def mm_to_raw(value: float) -> int:
    """Nearest even raw count; exact half rounds upward."""
    if value <= 0:
        raise Reject("distance must be > 0 mm")
    raw = int(((value * RAW_PER_MM) + 1.0) // 2.0) * 2
    if raw < MIN_RAW or raw > MAX_RAW:
        raise Reject(
            f"{value:g} mm converts to {raw} raw; supported range is "
            f"~{raw_to_mm(MIN_RAW):.3f}..{raw_to_mm(MAX_RAW):.3f} mm"
        )
    return raw

def validate_raw(name: str, raw: int) -> int:
    if raw < MIN_RAW or raw > MAX_RAW:
        raise Reject(f"{name}={raw} outside supported range {MIN_RAW}..{MAX_RAW} raw")
    if raw & 1:
        raise Reject(f"{name}={raw} is odd; current validated helper accepts even raw values only")
    imm = raw // 2
    if not 0 <= imm <= 255:
        raise Reject(f"{name} cannot be represented by the validated helper")
    return imm

def profile_status(release_raw: int, repress_raw: int):
    return PROFILE_STATUS.get(
        (release_raw, repress_raw),
        ("EXPERIMENTAL", "structurally supported but not hardware-qualified as a profile"),
    )

def sampling_quality(width_raw: int):
    # This is only a readability heuristic for C5 sampling density.
    if width_raw <= 80:
        return "GOOD"
    if width_raw <= 160:
        return "FAIR"
    return "COARSE"


# Hardware-observed R3S key mapping subset bundled with Toolkit v0.7.
# Full keyboard map is intentionally NOT inferred from partial data.
BUNDLED_KEYMAP = {
    "W": 17,
    "E": 18,
    "R": 19,
    "A": 30,
    "S": 31,
    "D": 32,
    "Space": 60,
}

def observer_key_map():
    """Return only hardware-observed key-name -> internal-index mappings."""
    return dict(BUNDLED_KEYMAP)
