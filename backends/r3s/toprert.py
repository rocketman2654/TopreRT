# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
# Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
"""TopreRT Patcher v0.5 — fail-closed local R3S A0.12 patcher."""

from __future__ import annotations
from pathlib import Path
import argparse
import json
import sys

import toprert_common as C

def validate_source(data: bytes):
    checks = []

    if len(data) != C.EXPECTED_SIZE:
        raise C.Reject(f"unsupported file size: {len(data)} (expected {C.EXPECTED_SIZE})")
    checks.append(("File size", "PASS"))

    got = C.sha256(data)
    variant = C.SUPPORTED_STOCKS.get(got)
    if variant is None:
        supported = "\n".join(
            f"  {v['model']}: {sha}" for sha, v in C.SUPPORTED_STOCKS.items()
        )
        raise C.Reject(
            "unsupported R3S A0.12 firmware SHA-256\n"
            f"  got: {got}\n"
            "Supported exact images:\n" + supported
        )
    model = variant["model"]
    expected_tag = (model + "####").encode("ascii")
    actual_tag = data[C.MODEL_TAG_OFFSET:C.MODEL_TAG_OFFSET+C.MODEL_TAG_LENGTH]
    if actual_tag != expected_tag:
        raise C.Reject(
            f"model tag mismatch: SHA identifies {model}, tag={actual_tag!r}"
        )
    checks.append(("Source SHA-256", "PASS"))
    checks.append((f"Model tag {model}", "PASS"))

    outer_stored = int.from_bytes(data[0:2], "little")
    inner_stored = int.from_bytes(data[2:4], "little")
    outer_calc = C.crc16(data[2:])
    inner_calc = C.crc16(data[4:4+C.MCU_SIZE])
    if outer_stored != outer_calc:
        raise C.Reject(f"source outer CRC invalid: stored={outer_stored:04X} calc={outer_calc:04X}")
    if inner_stored != inner_calc:
        raise C.Reject(f"source inner CRC invalid: stored={inner_stored:04X} calc={inner_calc:04X}")
    checks.append(("Source CRCs", "PASS"))

    fw = data[4:4+C.MCU_SIZE]
    if fw[C.HOOK_OFFSET:C.HOOK_OFFSET+len(C.HOOK_EXPECT)] != C.HOOK_EXPECT:
        raise C.Reject("stock hook bytes do not match")
    checks.append(("Stock hook", "PASS"))

    if fw[C.CAVE_OFFSET:C.CAVE_OFFSET+len(C.BASE_HELPER)] != b"\xff"*len(C.BASE_HELPER):
        raise C.Reject("required code cave is not empty")
    checks.append(("Code cave", "PASS"))

    return {
        "sha256": got,
        "model": model,
        "rt_core_status": variant["rt_core"],
        "observer_status": variant["observer"],
        "outer_crc": outer_stored,
        "inner_crc": inner_stored,
        "checks": checks,
    }

def make_helper(release_raw: int, repress_raw: int) -> bytes:
    rel = C.validate_raw("release", release_raw)
    rep = C.validate_raw("re-press", repress_raw)
    h = bytearray(C.BASE_HELPER)
    if h[C.RELEASE_IMM_OFFSET+1] != 0x2B or h[C.REPRESS_IMM_OFFSET+1] != 0x2B:
        raise C.Reject("internal helper signature mismatch")
    h[C.RELEASE_IMM_OFFSET] = rel
    h[C.REPRESS_IMM_OFFSET] = rep
    return bytes(h)

def build(data: bytes, release_raw: int, repress_raw: int):
    src_meta = validate_source(data)
    helper = make_helper(release_raw, repress_raw)

    fw = bytearray(data[4:4+C.MCU_SIZE])
    trailer = data[4+C.MCU_SIZE:]
    fw[C.HOOK_OFFSET:C.HOOK_OFFSET+len(C.HOOK_PATCH)] = C.HOOK_PATCH
    fw[C.CAVE_OFFSET:C.CAVE_OFFSET+len(helper)] = helper

    inner = C.crc16(fw)
    tmp = inner.to_bytes(2, "little") + bytes(fw) + trailer
    outer = C.crc16(tmp)
    out = outer.to_bytes(2, "little") + tmp

    if len(out) != C.EXPECTED_SIZE:
        raise C.Reject("internal error: output size changed")
    if out[4+C.MCU_SIZE:] != trailer:
        raise C.Reject("internal error: trailer changed")
    if C.crc16(out[2:]) != int.from_bytes(out[0:2], "little"):
        raise C.Reject("internal error: output outer CRC failed")
    if C.crc16(out[4:4+C.MCU_SIZE]) != int.from_bytes(out[2:4], "little"):
        raise C.Reject("internal error: output inner CRC failed")

    src_fw = data[4:4+C.MCU_SIZE]
    out_fw = out[4:4+C.MCU_SIZE]
    changed = {i for i,(a,b) in enumerate(zip(src_fw,out_fw)) if a != b}
    allowed = (
        set(range(C.HOOK_OFFSET, C.HOOK_OFFSET + len(C.HOOK_PATCH)))
        | set(range(C.CAVE_OFFSET, C.CAVE_OFFSET + len(helper)))
    )
    if not changed <= allowed:
        raise C.Reject("internal error: bytes changed outside hook/helper whitelist")

    stable_regression = None
    if (release_raw, repress_raw) == (C.DEFAULT_RELEASE, C.DEFAULT_REPRESS):
        got = C.sha256(out)
        expected = C.STABLE_OUTPUT_SHA256_BY_MODEL[src_meta["model"]]
        if got != expected:
            raise C.Reject(
                "STABLE REGRESSION FAILED\n"
                f"  model   : {src_meta['model']}\n"
                f"  got     : {got}\n"
                f"  expected: {expected}"
            )
        stable_regression = "PASS"

    status, note = C.profile_status(release_raw, repress_raw)
    meta = {
        "toolkit_version": C.TOOLKIT_VERSION,
        "source_sha256": src_meta["sha256"],
        "source_model": src_meta["model"],
        "rt_core_status": src_meta["rt_core_status"],
        "observer_status": src_meta["observer_status"],
        "output_sha256": C.sha256(out),
        "release_raw": release_raw,
        "release_mm_actual": C.raw_to_mm(release_raw),
        "repress_raw": repress_raw,
        "repress_mm_actual": C.raw_to_mm(repress_raw),
        "profile_status": status,
        "profile_note": note,
        "inner_crc": f"{int.from_bytes(out[2:4], 'little'):04X}",
        "outer_crc": f"{int.from_bytes(out[0:2], 'little'):04X}",
        "stable_regression": stable_regression,
        "space_policy": "NO-DISARM",
        "non_space_policy": "two-pass DISARM64",
    }
    return out, meta

def resolve_settings(args):
    using_raw = args.release is not None or args.repress is not None
    using_mm = args.release_mm is not None or args.repress_mm is not None
    if args.preset and (using_raw or using_mm):
        raise C.Reject("use --preset OR direct raw/mm settings, not both")
    if using_raw and using_mm:
        raise C.Reject("do not mix raw and mm settings in one command")

    if args.preset:
        r,p,_ = C.PRESETS[args.preset]
        return r,p,"preset"
    if using_mm:
        r = C.DEFAULT_RELEASE if args.release_mm is None else C.mm_to_raw(args.release_mm)
        p = C.DEFAULT_REPRESS if args.repress_mm is None else C.mm_to_raw(args.repress_mm)
        return r,p,"mm"
    if using_raw:
        r = C.DEFAULT_RELEASE if args.release is None else args.release
        p = C.DEFAULT_REPRESS if args.repress is None else args.repress
        return r,p,"raw"
    return None,None,"interactive"

def print_checks(meta):
    print("\nSAFETY VALIDATION")
    for name, status in meta["checks"]:
        print(f"  {name:.<26} {status}")

def interactive_settings():
    print("\nNo RT settings supplied; entering guided profile mode.")
    print()
    print("Choose RT profile:")
    print("  1. Stable        0.60 / 0.80 mm   [Recommended]")
    print("     Balanced general typing + gaming; all-key stable candidate.")
    print("  2. Responsive    0.60 / 0.70 mm   [Hardware verified]")
    print("     Same release, faster re-press.")
    print("  3. Fast Release  0.50 / 0.70 mm   [Hardware verified]")
    print("     Faster release while retaining the 0.70 mm re-press.")
    print("  4. Custom")
    try:
        choice = input("\nSelection [1]: ").strip() or "1"
    except EOFError:
        raise C.Reject("interactive input unavailable; supply --preset or --release-mm/--repress-mm")

    choices = {
        "1": ("stable", 306, 408),
        "2": ("responsive", 306, 358),
        "3": ("fast-release", 256, 358),
    }
    if choice in choices:
        name, r, p = choices[choice]
        return r, p, "guided-preset", name, None

    if choice != "4":
        raise C.Reject("profile selection must be 1, 2, 3, or 4")

    print("\nCustom profile. Enter values in millimetres.")
    try:
        rs = input("Release distance (0.20-1.00 mm) [0.60]: ").strip()
        ps = input("Re-press distance (0.20-1.00 mm) [0.80]: ").strip()
    except EOFError:
        raise C.Reject("interactive input unavailable; supply --release-mm/--repress-mm")
    rmm = 0.60 if not rs else float(rs)
    pmm = 0.80 if not ps else float(ps)
    return C.mm_to_raw(rmm), C.mm_to_raw(pmm), "guided-custom", "custom", (rmm, pmm)

def self_test(input_path=None):
    print(f"TopreRT Toolkit v{C.TOOLKIT_VERSION} self-test")
    tests = []

    expected = {0.50:256, 0.60:306, 0.70:358, 0.80:408, 1.00:510}
    for mm, raw in expected.items():
        got = C.mm_to_raw(mm)
        if got != raw:
            raise C.Reject(f"self-test mm conversion failed: {mm} -> {got}, expected {raw}")
    tests.append("mm conversion")

    for r,p in [(306,408),(306,358),(256,358),(104,104),(510,510)]:
        make_helper(r,p)
    tests.append("helper generation")

    if input_path:
        data = Path(input_path).read_bytes()
        validate_source(data)
        out, _ = build(data, 306, 408)
        if C.sha256(out) != C.STABLE_OUTPUT_SHA256:
            raise C.Reject("self-test stable image SHA mismatch")
        tests.append("stock validation")
        tests.append("stable byte regression")

    for t in tests:
        print(f"  {t:.<28} PASS")
    print("SELF-TEST PASS")

def main():
    ap = argparse.ArgumentParser(description="TopreRT Patcher v0.5")
    ap.add_argument("input", nargs="?", help="user-supplied stock R3S A0.12 .rfb")
    ap.add_argument("-o","--output")
    ap.add_argument("--release", type=int)
    ap.add_argument("--repress", type=int)
    ap.add_argument("--release-mm", type=float)
    ap.add_argument("--repress-mm", type=float)
    ap.add_argument("--preset", choices=sorted(C.PRESETS))
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--list-presets", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--yes", action="store_true", help="skip confirmation in interactive mode")
    args = ap.parse_args()

    try:
        if args.list_presets:
            print(f"TopreRT Patcher v{C.TOOLKIT_VERSION}")
            for k,(r,p,note) in C.PRESETS.items():
                status,_ = C.profile_status(r,p)
                print(f" {k:8s} {C.raw_to_mm(r):.3f}/{C.raw_to_mm(p):.3f} mm "
                      f"({r}/{p} raw)  [{status}]  {note}")
            if not args.input and not args.self_test:
                return

        if args.self_test:
            self_test(args.input)
            return

        if not args.input:
            ap.error("input .rfb is required")
        path = Path(args.input)
        if not path.is_file():
            raise C.Reject(f"input file not found: {path}")

        data = path.read_bytes()
        src_meta = validate_source(data)

        r,p,mode = resolve_settings(args)
        requested_mm = None
        selected_profile = None
        if mode == "interactive":
            r, p, mode, selected_profile, requested_mm = interactive_settings()
        C.validate_raw("release", r)
        C.validate_raw("re-press", p)

        status,note = C.profile_status(r,p)
        print(f"\nTopreRT Patcher v{C.TOOLKIT_VERSION}")
        print(f"MODEL            REALFORCE R3S / A0.12 exact supported image")
        print(f"PROFILE STATUS   {status} — {note}")
        print(f"\nCONFIG")
        if selected_profile:
            print(f"  Profile   {selected_profile}")
        if requested_mm:
            print(f"  Release   requested {requested_mm[0]:g} mm -> {r} raw "
                  f"(~{C.raw_to_mm(r):.3f} mm actual)")
            print(f"  Re-press  requested {requested_mm[1]:g} mm -> {p} raw "
                  f"(~{C.raw_to_mm(p):.3f} mm actual)")
        elif mode == "mm":
            if args.release_mm is not None:
                print(f"  Release   requested {args.release_mm:g} mm -> {r} raw "
                      f"(~{C.raw_to_mm(r):.3f} mm actual)")
            else:
                print(f"  Release   default -> {r} raw (~{C.raw_to_mm(r):.3f} mm)")
            if args.repress_mm is not None:
                print(f"  Re-press  requested {args.repress_mm:g} mm -> {p} raw "
                      f"(~{C.raw_to_mm(p):.3f} mm actual)")
            else:
                print(f"  Re-press  default -> {p} raw (~{C.raw_to_mm(p):.3f} mm)")
        else:
            print(f"  Release   {r} raw (~{C.raw_to_mm(r):.3f} mm)")
            print(f"  Re-press  {p} raw (~{C.raw_to_mm(p):.3f} mm)")
        print("  Non-Space two-pass DISARM64")
        print("  Space #60 NO-DISARM")

        print_checks(src_meta)

        if args.validate_only:
            print("\nNo output created (--validate-only).")
            return

        if mode in ("guided-preset", "guided-custom") and not args.yes:
            ans = input("\nCreate patched firmware? [y/N]: ").strip().lower()
            if ans not in ("y","yes"):
                print("Cancelled. No output created.")
                return

        out, meta = build(data,r,p)
        suffix = f"_TopreRT_v{C.TOOLKIT_VERSION}_R{r}_P{p}.rfb"
        outp = Path(args.output) if args.output else path.with_name(path.stem + suffix)
        if outp.resolve() == path.resolve():
            raise C.Reject("refusing to overwrite source firmware")
        if outp.exists():
            raise C.Reject(f"refusing to overwrite existing output: {outp}")

        outp.write_bytes(out)
        manifest_path = outp.with_suffix(outp.suffix + ".manifest.json")
        if manifest_path.exists():
            outp.unlink()
            raise C.Reject(f"refusing to overwrite existing manifest: {manifest_path}")
        manifest_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        print("\nOUTPUT")
        print(f"  Firmware  {outp}")
        print(f"  Manifest  {manifest_path}")
        print(f"  SHA-256   {meta['output_sha256']}")
        print(f"  Inner CRC {meta['inner_crc']}")
        print(f"  Outer CRC {meta['outer_crc']}")
        print("  Whitelist PASS")
        print("  Trailer   PASS")
        if meta["stable_regression"]:
            print("  Stable regression PASS — byte-identical known stable image")
        print("\nThis tool does not flash the keyboard.")

    except (C.Reject, ValueError) as e:
        print("REJECTED:", e, file=sys.stderr)
        raise SystemExit(1)

if __name__ == "__main__":
    main()
