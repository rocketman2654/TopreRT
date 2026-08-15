#!/usr/bin/env python3
"""
REALFORCE R3SB31 C5 live sensor probe V2.

READ-ONLY safety:
- Sends ONLY command 0xC5.
- Does not send E0/E1/E2/E3.
- Does not write firmware/configuration.
- C5 was identified in A0.12 firmware as a status/read handler:
    request key index -> copies 16-byte per-key runtime state
                      -> copies 30-byte per-key sensor structure
                      -> returns selected fields.

Requirements:
    py -m pip install hidapi

Examples:
    py r3sb_c5_live_probe.py --key 0
    py r3sb_c5_live_probe.py --scan
    py r3sb_c5_live_probe.py --watch
"""

import argparse
import time
import sys

VID = 0x0853
PID = 0x0311
IFACE = 2

def load_hid():
    try:
        import hid
        return hid
    except Exception as e:
        print("ERROR: hidapi is required.", file=sys.stderr)
        print("Install with: py -m pip install hidapi", file=sys.stderr)
        print("Import error:", e, file=sys.stderr)
        raise SystemExit(2)

def open_device(hid):
    rows = [d for d in hid.enumerate(VID, PID)
            if d.get("interface_number") == IFACE]
    if len(rows) != 1:
        print(f"REFUSING: expected exactly one {VID:04X}:{PID:04X} interface {IFACE}, found {len(rows)}.")
        raise SystemExit(3)
    d = rows[0]
    print(f"Device: {VID:04X}:{PID:04X}, interface={IFACE}")
    print("Product:", d.get("product_string"))
    dev = hid.device()
    dev.open_path(d["path"])
    dev.set_nonblocking(False)
    return dev

def be16(b, i):
    return (b[i] << 8) | b[i+1]

def c5_read(dev, key):
    if not 0 <= key <= 0x7F:
        raise ValueError("key index must be 0..127")

    # Handler sees command at byte 2 and key index at command-relative +3,
    # therefore the wire request is AA AA C5 00 00 <key>.
    cmd = bytes([0xAA, 0xAA, 0xC5, 0x00, 0x00, key] + [0x00] * 58)
    n = dev.write(bytes([0x00]) + cmd)
    if n != 65:
        raise RuntimeError(f"hid.write returned {n}, expected 65")

    reply = bytes(dev.read(64, timeout_ms=1000))
    if not reply:
        raise RuntimeError(f"C5 key {key}: no response")

    if len(reply) < 6 or reply[0:3] != bytes([0x55,0x55,0xC5]):
        raise RuntimeError(f"C5 key {key}: unexpected reply: {reply.hex(' ')}")

    status = reply[3]
    reserved = reply[4]
    ln = reply[5]
    payload = reply[6:6+ln]
    if status != 0:
        raise RuntimeError(f"C5 key {key}: device status={status}, reply={reply.hex(' ')}")
    if len(payload) < 24:
        raise RuntimeError(f"C5 key {key}: payload too short ({len(payload)}): {reply.hex(' ')}")

    # Confirmed from the A0.12 C5 handler:
    # payload[0]      = key runtime state byte (+0)
    # payload[1]      = literal zero
    # payload[2:4]    = sensor structure +0x04
    # payload[4:6]    = sensor structure +0x06
    # payload[6:8]    = sensor structure +0x08
    # payload[8:24]   = eight halfwords from sensor +0x0A..+0x18
    state = payload[0]
    aux = payload[1]
    current = be16(payload, 2)
    baseline = be16(payload, 4)
    scale = be16(payload, 6)
    thresholds = [be16(payload, 8 + 2*i) for i in range(8)]

    return {
        "key": key,
        "state": state,
        "aux": aux,
        "current": current,
        "baseline": baseline,
        "delta": current - baseline,
        "scale": scale,
        "thresholds": thresholds,
        "raw_reply": reply,
    }

def fmt(x):
    return (
        f"k={x['key']:3d} state={x['state']:3d} "
        f"cur={x['current']:5d} base={x['baseline']:5d} "
        f"delta={x['delta']:5d} scale={x['scale']:5d}"
    )

def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--key", type=lambda s:int(s,0),
                      help="continuously watch one internal key index (0..127)")
    mode.add_argument("--scan", action="store_true",
                      help="read all 128 keys once and print largest deltas")
    mode.add_argument("--watch", action="store_true",
                      help="continuously scan all 128 keys and show largest deltas")
    mode.add_argument("--discover", action="store_true",
                      help="baseline scan, then compare against a press-and-hold scan to identify a key index")
    mode.add_argument("--trace-state", type=lambda s:int(s,0),
                      metavar="KEY",
                      help="poll one key as fast as possible and print every state transition with delta")
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--raw", action="store_true",
                    help="with --key, also print the raw 64-byte reply")
    args = ap.parse_args()

    if args.key is None and not args.scan and not args.watch and not args.discover and args.trace_state is None:
        args.watch = True

    hid = load_hid()
    dev = open_device(hid)
    print("READ-ONLY: sending only C5 status requests.")
    print("No firmware-update or configuration-write commands are present.\n")

    try:
        if args.trace_state is not None:
            from collections import deque
            key = args.trace_state
            print(f"FAST STATE TRACE V5: key {key}")
            print("Captures 4 samples before and after each state transition.")
            print("Move the key slowly across actuation/release. Ctrl+C to stop.\n")

            history = deque(maxlen=5)
            last_state = None
            seq = 0
            t0 = time.perf_counter()
            pending_after = 0

            def row(x, mark=" "):
                ms = x["_ms"]
                b0 = x["state"] & 1
                b1 = (x["state"] >> 1) & 1
                th = x["thresholds"]
                nearest_i = min(range(len(th)), key=lambda i: abs(th[i]-x["delta"]))
                return (
                    f"{mark} {ms:10.3f} ms seq={x['_seq']:6d} "
                    f"state={x['state']:3d} bits={b1}{b0} "
                    f"delta={x['delta']:5d} cur={x['current']:5d} "
                    f"base={x['baseline']:5d} scale={x['scale']:5d} "
                    f"nearest=T{nearest_i}({th[nearest_i]})"
                )

            while True:
                x = c5_read(dev, key)
                seq += 1
                x["_seq"] = seq
                x["_ms"] = (time.perf_counter() - t0) * 1000.0

                changed = last_state is not None and x["state"] != last_state
                if last_state is None:
                    print(row(x, "I"), flush=True)
                    last_state = x["state"]

                if changed:
                    print("\n--- STATE TRANSITION ---")
                    for h in list(history)[-4:]:
                        print(row(h, " "))
                    print(row(x, ">"))
                    print("thresholds:", ",".join(map(str, x["thresholds"])))
                    pending_after = 4
                    last_state = x["state"]
                elif pending_after > 0:
                    print(row(x, "+"))
                    pending_after -= 1
                    if pending_after == 0:
                        print("--- END CONTEXT ---\n", flush=True)

                history.append(x)

        elif args.key is not None:
            while True:
                x = c5_read(dev, args.key)
                print("\r" + fmt(x) +
                      " thresholds=" + ",".join(map(str,x["thresholds"])) +
                      "     ", end="", flush=True)
                if args.raw:
                    print("\nRAW:", x["raw_reply"].hex(" "))
                time.sleep(args.interval)

        elif args.discover:
            print("Taking IDLE baseline scan. Do not press the target key...")
            idle = [c5_read(dev, k) for k in range(128)]
            idle_by_key = {x["key"]: x for x in idle}

            print("\nNow press and HOLD the target key.")
            for n in (3, 2, 1):
                print(f"Second scan in {n}...", flush=True)
                time.sleep(1.0)

            print("Scanning while the key should still be held...")
            held = [c5_read(dev, k) for k in range(128)]

            rows = []
            for h in held:
                i = idle_by_key[h["key"]]
                rows.append({
                    "key": h["key"],
                    "state0": i["state"],
                    "state1": h["state"],
                    "delta0": i["delta"],
                    "delta1": h["delta"],
                    "d_delta": h["delta"] - i["delta"],
                    "cur0": i["current"],
                    "cur1": h["current"],
                    "d_cur": h["current"] - i["current"],
                    "base0": i["baseline"],
                    "base1": h["baseline"],
                    "d_base": h["baseline"] - i["baseline"],
                })

            rows.sort(key=lambda r: abs(r["d_delta"]), reverse=True)
            print("\nLargest changes between idle and held scans:")
            print(" key  state   delta0 -> delta1    change    current change   baseline change")
            for r in rows[:args.top]:
                print(
                    f"{r['key']:4d}   {r['state0']}->{r['state1']}   "
                    f"{r['delta0']:6d} -> {r['delta1']:6d}   "
                    f"{r['d_delta']:+7d}   "
                    f"{r['d_cur']:+7d}          {r['d_base']:+7d}"
                )
            print("\nYou can release the key now.")

        elif args.scan:
            xs = [c5_read(dev, k) for k in range(128)]
            valid = [x for x in xs if x["current"] != 0]
            valid.sort(key=lambda x: x["delta"], reverse=True)
            print(f"Active-looking keys: {len(valid)}/128 (current != 0)")
            for x in valid[:args.top]:
                print(fmt(x))

        else:
            while True:
                xs = [c5_read(dev, k) for k in range(128)]
                # Unpopulated matrix slots return current=0 with default-ish
                # calibration values (e.g. 1500/1400), which dominated the V1
                # abs(delta) ranking. Ignore those slots.
                valid = [x for x in xs if x["current"] != 0]
                valid.sort(key=lambda x: x["delta"], reverse=True)
                print("\x1b[2J\x1b[H", end="")
                print("Top active-looking keys by current-baseline  (Ctrl+C to stop)")
                print(f"Valid slots: {len(valid)}/128 (filter: current != 0)")
                print("Press one key; its delta/state should rise near the top.\n")
                for x in valid[:args.top]:
                    print(fmt(x))
                time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            dev.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
