# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
# Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
"""TopreRT Observer v0.4 — read-only C5 RT crossing validator."""

from __future__ import annotations
import argparse
from pathlib import Path
import time
import sys

import toprert_common as C

try:
    import r3sb_c5_live_probe_v5 as probe
except Exception:
    print("ERROR: r3sb_c5_live_probe_v5.py must be in the same folder.", file=sys.stderr)
    raise

def bracket_text(lo,hi):
    return f"({lo}, {hi}] raw (~{C.raw_to_mm(lo):.2f}..{C.raw_to_mm(hi):.2f} mm)"

def main():
    ap=argparse.ArgumentParser(description="TopreRT Observer v0.4")
    ap.add_argument("--key",type=lambda s:int(s,0),default=19)
    ap.add_argument("--expect-release",type=int)
    ap.add_argument("--expect-repress",type=int)
    ap.add_argument("--expect-release-mm",type=float)
    ap.add_argument("--expect-repress-mm",type=float)
    ap.add_argument("--disarm-rest",type=int,default=C.DISARM_REST)
    ap.add_argument("--interval",type=float,default=0.0)
    ap.add_argument("--stop-file", default=None, help=argparse.SUPPRESS)
    args=ap.parse_args()

    raw_mode=args.expect_release is not None or args.expect_repress is not None
    mm_mode=args.expect_release_mm is not None or args.expect_repress_mm is not None
    if raw_mode and mm_mode:
        ap.error("do not mix raw and mm expectation options")
    if args.expect_release_mm is not None:
        args.expect_release=C.mm_to_raw(args.expect_release_mm)
    if args.expect_repress_mm is not None:
        args.expect_repress=C.mm_to_raw(args.expect_repress_mm)

    hid=probe.load_hid()
    dev=probe.open_device(hid)

    print("READ-ONLY: sending only C5 status requests.")
    print("No firmware-update or configuration-write commands are present.")
    print(f"TopreRT Observer v{C.TOOLKIT_VERSION}: key {args.key}")
    if args.expect_release is not None:
        print(f"Expected release : {args.expect_release} raw (~{C.raw_to_mm(args.expect_release):.3f} mm)")
    if args.expect_repress is not None:
        print(f"Expected re-press: {args.expect_repress} raw (~{C.raw_to_mm(args.expect_repress):.3f} mm)")
    print(f"DISARM detector : state 0 and delta <= {args.disarm_rest}")
    print("Press -> partial release to state 0 -> pause -> slowly re-press. Ctrl+C to stop.\n")

    last=last_delta=press_peak=None
    saw_3_to_2=False
    rt_armed=False
    zero_min=None
    disarmed=True
    rel_n=rel_pass=rep_n=rep_pass=stock_first_n=0
    rel_quality={"GOOD":0,"FAIR":0,"COARSE":0}
    rep_quality={"GOOD":0,"FAIR":0,"COARSE":0}
    t0=time.perf_counter()

    try:
        while True:
            if args.stop_file and Path(args.stop_file).exists():
                raise KeyboardInterrupt
            x=probe.c5_read(dev,args.key)
            st,d=x["state"],x["delta"]
            ms=(time.perf_counter()-t0)*1000

            if last is None:
                last,last_delta=st,d
                if st==3: press_peak=d
                continue

            if st==3:
                press_peak=d if press_peak is None else max(press_peak,d)

            if st==0 and rt_armed:
                zero_min=d if zero_min is None else min(zero_min,d)
                if d<=args.disarm_rest:
                    rt_armed=False; disarmed=True; zero_min=None
                    print(f"[{ms/1000:8.3f}s] DISARM near rest: delta={d}; next 0->3 = STOCK-FIRST")

            if st!=last:
                print(f"[{ms/1000:8.3f}s] STATE {last}->{st}  prev={last_delta:5d} now={d:5d}")

                if last==3 and st==2:
                    saw_3_to_2=True
                    if press_peak is not None:
                        a=max(0,press_peak-last_delta); b=max(0,press_peak-d)
                        lo,hi=min(a,b),max(a,b); width=hi-lo
                        q=C.sampling_quality(width); rel_quality[q]+=1; rel_n+=1
                        print(f"             RELEASE crossing = {bracket_text(lo,hi)}  quality={q}")
                        if args.expect_release is not None:
                            ok=lo<=args.expect_release<=hi; rel_pass+=int(ok)
                            print(f"             expected {args.expect_release}: "
                                  f"{'BRACKETED ✓' if ok else 'NOT BRACKETED'}")

                elif last==2 and st==0 and saw_3_to_2:
                    rt_armed=d>args.disarm_rest; disarmed=not rt_armed
                    zero_min=d if rt_armed else None; saw_3_to_2=False
                    print("             RT RE-PRESS ARMED" if rt_armed
                          else "             FULL RETURN/DISARM; next press STOCK-FIRST")

                elif last==0 and st==3:
                    if rt_armed and not disarmed and zero_min is not None:
                        prev_move=max(0,last_delta-zero_min); now_move=max(0,d-zero_min)
                        lo,hi=min(prev_move,now_move),max(prev_move,now_move); width=hi-lo
                        q=C.sampling_quality(width); rep_quality[q]+=1; rep_n+=1
                        print(f"*** MID-STROKE RE-PRESS #{rep_n}")
                        print(f"    observed anchor≈{zero_min} raw")
                        print(f"    crossing bracket  = {bracket_text(lo,hi)}  quality={q}")
                        if args.expect_repress is not None:
                            ok=lo<args.expect_repress<=hi; rep_pass+=int(ok)
                            print(f"    expected {args.expect_repress}: "
                                  f"{'BRACKETED ✓' if ok else 'NOT BRACKETED — repeat more slowly'}")
                        print()
                    else:
                        stock_first_n+=1
                        print(f"             STOCK-FIRST #{stock_first_n} (excluded)")
                    rt_armed=False; disarmed=False; zero_min=None; press_peak=d

                if st==3: press_peak=d
                last=st

            last_delta=d
            if args.interval: time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nStopped.\n")
        print("=== OBSERVATION SUMMARY ===")
        if args.expect_release is not None:
            print(f"Release {args.expect_release}: {rel_pass}/{rel_n} bracketed")
        else:
            print(f"Release crossings: {rel_n}")
        print(f"  sampling quality: GOOD={rel_quality['GOOD']} FAIR={rel_quality['FAIR']} COARSE={rel_quality['COARSE']}")
        if args.expect_repress is not None:
            print(f"Mid-stroke re-press {args.expect_repress}: {rep_pass}/{rep_n} bracketed")
        else:
            print(f"Mid-stroke re-press crossings: {rep_n}")
        print(f"  sampling quality: GOOD={rep_quality['GOOD']} FAIR={rep_quality['FAIR']} COARSE={rep_quality['COARSE']}")
        print(f"Stock-first presses excluded: {stock_first_n}")
        print("Quality is only a C5 sampling-density heuristic, not a firmware pass/fail grade.")

    finally:
        try: dev.close()
        except Exception: pass

if __name__=="__main__":
    main()
