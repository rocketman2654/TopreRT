// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
// Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
r"""
TopreRT Unified GUI v0.2

One front-end, two frozen backends:
- REALFORCE R3S A0.12: build/validate here, update with official REALFORCE software
- HHKB Professional Hybrid / Hybrid Type-S A0.48: build/validate/write/restore here

The GUI intentionally shares validation, profile, observer, and safety semantics
while preserving each platform's correct firmware-update path.
"""

from __future__ import annotations

import importlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = Path(__file__).resolve().parent
R3S_DIR = APP_DIR / "backends" / "r3s"
HHKB_DIR = APP_DIR / "backends" / "hhkb"

# Import frozen backends without renaming their internal imports.
sys.path.insert(0, str(R3S_DIR))
import toprert_common as R3C
import toprert as R3P

sys.path.insert(0, str(HHKB_DIR))
import hhkb_toprert_engine_v0_6 as HHE

APP_TITLE = "TopreRT Unified GUI v0.2"
PLAT_R3S = "REALFORCE R3S"
PLAT_HHKB = "HHKB Professional Hybrid"

R3_PROFILES = {
    "Stable — 0.60 / 0.80 mm": (0.60, 0.80),
    "Responsive — 0.60 / 0.70 mm": (0.60, 0.70),
    "Fast Release — 0.50 / 0.70 mm": (0.50, 0.70),
    "Custom": None,
}
HH_PROFILES = {
    "Stable — 0.10 / 0.15 mm": (0.10, 0.15),
    "Golden — ~0.053 / 0.053 mm": (32 * HHE.MM_PER_RAW, 32 * HHE.MM_PER_RAW),
    "Custom": None,
}
KEYS = ["R", "E", "W", "A", "S", "D", "SPACE"]

R3_KEYMAP = {k.upper(): v for k, v in R3C.observer_key_map().items()}
HH_KEYMAP = dict(HHE.KEY_MAP)


class UnifiedGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1010x790")
        self.minsize(920, 700)

        self.platform = tk.StringVar(value=PLAT_R3S)
        self.source_path = None
        self.source_valid = False
        self.source_meta = None
        self.source_meta = None
        self.profile = tk.StringVar()
        self.release = tk.StringVar()
        self.repress = tk.StringVar()
        self.key = tk.StringVar(value="R")
        self.observer_mode = tk.StringVar(value="Detailed")
        self._syncing_profile = False

        self.source_status = tk.StringVar(value="No firmware selected")
        self.validation_status = tk.StringVar(value="")
        self.status_line = tk.StringVar(value="Ready")
        self.action_status = tk.StringVar(value="")
        self.observer_state = tk.StringVar(value="Observer idle")
        self.progress_text = tk.StringVar(value="")

        self.worker = None
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.r3_observer_proc = None
        self.r3_stop_file = None

        self.flash_t0 = None
        self.flash_rate = None

        self._build_ui()
        self.release.trace_add("write", self._profile_text_changed)
        self.repress.trace_add("write", self._profile_text_changed)
        self.platform.trace_add("write", self._platform_changed)
        self.after(80, self._poll)
        self.after(150, self._detect_platform)

    # ---------------- UI ----------------
    def _build_ui(self):
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)

        top = ttk.Frame(main)
        top.pack(fill="x")
        ttk.Label(top, text="TopreRT GUI", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(top, text="Keyboard").pack(side="left", padx=(30, 7))
        combo = ttk.Combobox(
            top, textvariable=self.platform,
            values=[PLAT_R3S, PLAT_HHKB], state="readonly", width=30
        )
        combo.pack(side="left")
        ttk.Button(top, text="Detect", command=self._detect_platform).pack(side="left", padx=(8, 0))

        self.platform_note = ttk.Label(main, text="")
        self.platform_note.pack(anchor="w", pady=(2, 10))

        f1 = ttk.LabelFrame(main, text="1. Stock firmware", padding=9)
        f1.pack(fill="x")
        row = ttk.Frame(f1)
        row.pack(fill="x")
        self.source_entry = ttk.Entry(row, state="readonly")
        self.source_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self.browse_source).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Full Validation", command=self.full_validation).pack(side="left", padx=(8, 0))
        ttk.Label(f1, textvariable=self.source_status).pack(anchor="w", pady=(6, 0))

        f2 = ttk.LabelFrame(main, text="2. Rapid Trigger profile", padding=9)
        f2.pack(fill="x", pady=(10, 0))
        r = ttk.Frame(f2)
        r.pack(fill="x")
        ttk.Label(r, text="Profile").pack(side="left")
        self.profile_combo = ttk.Combobox(r, textvariable=self.profile, state="readonly", width=34)
        self.profile_combo.pack(side="left", padx=(8, 18))
        self.profile_combo.bind("<<ComboboxSelected>>", self._profile_changed)

        ttk.Label(r, text="Release [mm]").pack(side="left")
        ttk.Entry(r, textvariable=self.release, width=10).pack(side="left", padx=(6, 18))
        ttk.Label(r, text="Re-press [mm]").pack(side="left")
        ttk.Entry(r, textvariable=self.repress, width=10).pack(side="left", padx=(6, 10))
        ttk.Button(r, text="Preview", command=self.preview).pack(side="left")

        self.validation_label = ttk.Label(f2, textvariable=self.validation_status)
        self.validation_label.pack(anchor="w", pady=(5, 0))

        orow = ttk.Frame(f2)
        orow.pack(fill="x", pady=(8, 0))
        ttk.Label(orow, text="Observer key").pack(side="left")
        ttk.Combobox(orow, textvariable=self.key, values=KEYS, state="readonly", width=9).pack(side="left", padx=(8, 8))
        self.obs_start = ttk.Button(orow, text="Start Observer", command=self.start_observer)
        self.obs_start.pack(side="left")
        self.obs_stop = ttk.Button(orow, text="Stop Observer", command=self.stop_observer, state="disabled")
        self.obs_stop.pack(side="left", padx=(8, 0))
        ttk.Label(orow, text="Mode").pack(side="left", padx=(16, 5))
        ttk.Combobox(
            orow, textvariable=self.observer_mode,
            values=["Simple", "Detailed"], state="readonly", width=10
        ).pack(side="left")
        ttk.Label(orow, textvariable=self.observer_state).pack(side="left", padx=(16, 0))

        f3 = ttk.LabelFrame(main, text="3. Safety / activity", padding=7)
        f3.pack(fill="both", expand=True, pady=(10, 0))
        self.log = tk.Text(f3, wrap="word", state="disabled", font=("Consolas", 9), height=20)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(f3, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

        prow = ttk.Frame(main)
        prow.pack(fill="x", pady=(8, 0))
        self.progress = ttk.Progressbar(prow, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Label(prow, textvariable=self.progress_text, width=30).pack(side="left", padx=(10, 0))

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Run self-test", command=self.self_test).pack(side="left")
        ttk.Button(actions, text="Open Output Folder", command=self.open_output).pack(side="left", padx=(8, 0))
        self.recovery_btn = ttk.Button(actions, text="Recovery / Restore", command=self.recovery_action)
        self.recovery_btn.pack(side="left", padx=(8, 0))

        ttk.Label(actions, textvariable=self.action_status).pack(side="right", padx=(0, 10))
        self.apply_btn = ttk.Button(actions, text="Build Firmware", command=self.apply)
        self.apply_btn.pack(side="right")

        ttk.Label(main, textvariable=self.status_line).pack(anchor="w", pady=(6, 0))

        self._platform_changed()

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", str(text).rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_log(self, text):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("1.0", text)
        self.log.configure(state="disabled")

    def _set_source_entry(self, path):
        self.source_entry.configure(state="normal")
        self.source_entry.delete(0, "end")
        if path:
            self.source_entry.insert(0, str(path))
        self.source_entry.configure(state="readonly")

    def _busy(self, b):
        if b:
            self.apply_btn.configure(state="disabled")
        else:
            self._live_validate()

    def _worker(self, fn):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "Another operation is already running.")
            return
        self.worker = threading.Thread(target=self._worker_wrap, args=(fn,), daemon=True)
        self.worker.start()

    def _worker_wrap(self, fn):
        try:
            fn()
        except Exception as e:
            self.q.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "error":
                    self._append("ERROR: " + payload)
                    messagebox.showerror(APP_TITLE, payload)
                    self.status_line.set("Error — see activity")
                    self._busy(False)
                elif kind == "progress":
                    value, label = payload
                    self.progress["value"] = value
                    self.progress_text.set(label)
                elif kind == "status":
                    self.status_line.set(payload)
                elif kind == "busy_off":
                    self._busy(False)
                elif kind == "observer_on":
                    self.observer_state.set(payload)
                    self.obs_start.configure(state="disabled")
                    self.obs_stop.configure(state="normal")
                elif kind == "observer_off":
                    self.observer_state.set("Observer idle")
                    self.obs_start.configure(state="normal")
                    self.obs_stop.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ---------------- Platform ----------------
    def _detect_platform(self):
        try:
            import hid
            r3 = [d for d in hid.enumerate(0x0853, 0x0311) if d.get("interface_number") == 2]
            hh = []
            for d in hid.enumerate(0x04FE, 0):
                p = d["path"]
                ps = p.decode(errors="ignore") if isinstance(p, bytes) else str(p)
                if d.get("product_id") in HHE.PIDS and (d.get("interface_number") == 2 or "mi_02" in ps.lower()):
                    hh.append(d)
            if len(r3) == 1 and not hh:
                self.platform.set(PLAT_R3S)
                self.status_line.set("Detected REALFORCE R3S")
            elif len(hh) == 1 and not r3:
                self.platform.set(PLAT_HHKB)
                self.status_line.set("Detected HHKB Professional Hybrid")
            elif r3 and hh:
                self.status_line.set("Both supported keyboards detected — select one above")
            else:
                self.status_line.set("No supported keyboard auto-detected")
        except Exception as e:
            self.status_line.set("Detection unavailable: " + str(e))

    def _platform_changed(self, *_):
        plat = self.platform.get()
        self.source_path = None
        self.source_valid = False
        self._set_source_entry("")
        self.source_status.set("No firmware selected")
        self.progress["value"] = 0
        self.progress_text.set("")

        if plat == PLAT_R3S:
            self.platform_note.configure(
                text="REALFORCE R3S A0.12 · Build here → install with official REALFORCE software (recommended)"
            )
            self.profile_combo.configure(values=list(R3_PROFILES))
            self.profile.set(next(iter(R3_PROFILES)))
            self.apply_btn.configure(text="Build Firmware")
            self.recovery_btn.configure(text="Recovery / Restore")
            self.release.set("0.60")
            self.repress.set("0.80")
        else:
            self.platform_note.configure(
                text="HHKB Professional Hybrid / Type-S (PD-KB800W) · A0.48 · built-in validated Writer"
            )
            self.profile_combo.configure(values=list(HH_PROFILES))
            self.profile.set(next(iter(HH_PROFILES)))
            self.apply_btn.configure(text="Apply TopreRT")
            self.recovery_btn.configure(text="Restore Stock")
            self.release.set("0.10")
            self.repress.set("0.15")
            self._auto_find_hhkb_stock()

        self.preview()
        self._live_validate()

    def _auto_find_hhkb_stock(self):
        candidates = [
            APP_DIR / "HHKB800_FW_A048.hfb",
            Path.cwd() / "HHKB800_FW_A048.hfb",
        ]
        for p in candidates:
            if not p.is_file():
                continue
            try:
                HHE.validate_stock(p.read_bytes())
                self.source_path = p
                self.source_valid = True
                self.source_meta = {
                    "model": "PD-KB800W",
                    "rt_core_status": "HARDWARE VERIFIED",
                    "observer_status": "HARDWARE VERIFIED",
                }
                self._set_source_entry(p)
                self.source_status.set("AUTO-CHECK PASS — exact HHKB A0.48")
                return
            except Exception:
                pass

    # ---------------- Source validation ----------------
    def browse_source(self):
        if self.platform.get() == PLAT_R3S:
            types = [("REALFORCE firmware", "*.rfb"), ("All files", "*.*")]
        else:
            types = [("HHKB firmware", "*.hfb"), ("All files", "*.*")]
        fn = filedialog.askopenfilename(title="Select stock firmware", filetypes=types)
        if not fn:
            return
        p = Path(fn)
        self.source_path = p
        try:
            self.source_meta = self._validate_source_bytes(p.read_bytes())
            self.source_valid = True
            self._set_source_entry(p)
            model = self.source_meta.get("model", "supported")
            core = self.source_meta.get("rt_core_status", "VERIFIED")
            self.source_status.set(f"AUTO-CHECK PASS — {model} · RT core {core}")
            self._append(f"Source auto-check: PASS — {p}")
        except Exception as e:
            self.source_valid = False
            self._set_source_entry(p)
            self.source_status.set("REJECTED")
            messagebox.showerror(APP_TITLE, str(e))
        self._live_validate()

    def _validate_source_bytes(self, data):
        if self.platform.get() == PLAT_R3S:
            return R3P.validate_source(data)
        HHE.validate_stock(data)
        return {
            "model": "PD-KB800W",
            "rt_core_status": "HARDWARE VERIFIED",
            "observer_status": "HARDWARE VERIFIED",
            "sha256": HHE.sha256(data),
        }

    def full_validation(self):
        if not self.source_path or not self.source_path.is_file():
            messagebox.showerror(APP_TITLE, "Select the stock firmware first.")
            return
        try:
            data = self.source_path.read_bytes()
            meta = self._validate_source_bytes(data)
            self.source_meta = meta
            self.source_valid = True
            model = meta.get("model", "supported")
            self.source_status.set(f"FULL VALIDATION PASS — {model}")
            if self.platform.get() == PLAT_R3S:
                lines = [
                    f"FULL VALIDATION PASS — REALFORCE {meta['model']} A0.12",
                    f"RT core      {meta['rt_core_status']}",
                    f"Observer     {meta['observer_status']}",
                    "",
                ]
                for name, status in meta["checks"]:
                    lines.append(f"{name:.<28} {status}")
                lines += ["", f"SHA-256  {meta['sha256']}"]
                self._set_log("\n".join(lines))
            else:
                self._set_log(
                    "FULL VALIDATION PASS — HHKB PD-KB800W exact A0.48\n"
                    "RT core      HARDWARE VERIFIED\n"
                    "Observer     HARDWARE VERIFIED\n"
                    f"SHA-256  {HHE.sha256(data)}\n"
                    f"Main CRC {int.from_bytes(data[2:4],'little'):04X}\n"
                    f"Global CRC {int.from_bytes(data[0:2],'little'):04X}"
                )
            self._live_validate()
        except Exception as e:
            self.source_valid = False
            self.source_status.set("REJECTED")
            messagebox.showerror(APP_TITLE, str(e))

    # ---------------- Profile ----------------
    def _profile_text_changed(self, *_args):
        if not self._syncing_profile:
            self._sync_profile_from_values()
        self._live_validate()

    def _sync_profile_from_values(self):
        """
        Keep the visible preset honest:
        editing either mm field changes Profile to Custom unless the values
        exactly match a known preset again.
        """
        try:
            r = float(self.release.get().strip())
            p = float(self.repress.get().strip())
        except Exception:
            target = "Custom"
        else:
            profiles = R3_PROFILES if self.platform.get() == PLAT_R3S else HH_PROFILES
            target = "Custom"
            for name, pair in profiles.items():
                if pair is None:
                    continue
                if abs(r - pair[0]) < 0.0005 and abs(p - pair[1]) < 0.0005:
                    target = name
                    break
        if self.profile.get() != target:
            self._syncing_profile = True
            try:
                self.profile.set(target)
            finally:
                self._syncing_profile = False

    def _profile_changed(self, _event=None):
        profiles = R3_PROFILES if self.platform.get() == PLAT_R3S else HH_PROFILES
        val = profiles[self.profile.get()]
        if val is not None:
            self._syncing_profile = True
            try:
                self.release.set(f"{val[0]:.3f}".rstrip("0").rstrip("."))
                self.repress.set(f"{val[1]:.3f}".rstrip("0").rstrip("."))
            finally:
                self._syncing_profile = False
        self.preview()

    def _profile_values(self):
        try:
            rmm = float(self.release.get().strip())
            pmm = float(self.repress.get().strip())
        except Exception:
            raise ValueError("Release and re-press must be numeric mm values.")

        if self.platform.get() == PLAT_R3S:
            # Preserve the R3S typo guard (e.g. 40 instead of 0.40).
            if rmm > 1.0 and 0.20 <= rmm / 100.0 <= 1.0:
                raise R3C.Reject(f"{rmm:g} mm is out of range. Did you mean {rmm/100.0:.2f} mm?")
            if pmm > 1.0 and 0.20 <= pmm / 100.0 <= 1.0:
                raise R3C.Reject(f"{pmm:g} mm is out of range. Did you mean {pmm/100.0:.2f} mm?")
            rr = R3C.mm_to_raw(rmm)
            pr = R3C.mm_to_raw(pmm)
            R3C.validate_raw("release", rr)
            R3C.validate_raw("re-press", pr)
        else:
            rr = HHE.mm_to_raw(rmm)
            pr = HHE.mm_to_raw(pmm)
            HHE.validate_distance("release", rr)
            HHE.validate_distance("re-press", pr)
        return rmm, pmm, rr, pr

    def _live_validate(self, *_):
        try:
            rmm, pmm, rr, pr = self._profile_values()
            self.validation_status.set(
                f"VALID ✓   Release {rmm:g} mm → {rr} raw   |   Re-press {pmm:g} mm → {pr} raw"
            )
            ready = self.source_valid
            self.action_status.set("Ready" if ready else "Select valid stock firmware")
            self.apply_btn.configure(state="normal" if ready else "disabled")
            return True
        except Exception as e:
            if self.platform.get() == PLAT_R3S:
                lo, hi = R3C.raw_to_mm(R3C.MIN_RAW), R3C.raw_to_mm(R3C.MAX_RAW)
            else:
                lo, hi = HHE.MM_PER_RAW, 255 * HHE.MM_PER_RAW
            self.validation_status.set(
                f"OUT OF RANGE / INVALID — supported estimated range: ~{lo:.3f}–{hi:.3f} mm"
            )
            self.action_status.set("Invalid profile — Apply locked")
            self.apply_btn.configure(state="disabled")
            return False

    def preview(self):
        try:
            rmm, pmm, rr, pr = self._profile_values()
            if self.platform.get() == PLAT_R3S:
                status, note = R3C.profile_status(rr, pr)
                self._set_log(
                    f"PROFILE STATUS    {status}\n{note}\n\n"
                    f"Release    requested {rmm:g} mm -> {rr} raw (~{R3C.raw_to_mm(rr):.3f} mm actual)\n"
                    f"Re-press   requested {pmm:g} mm -> {pr} raw (~{R3C.raw_to_mm(pr):.3f} mm actual)\n\n"
                    "Non-Space  two-pass DISARM64\n"
                    "Space #60  NO-DISARM\n\n"
                    "Update path: official REALFORCE software is recommended." +
                    (
                        f"\n\nModel       {self.source_meta['model']}"
                        f"\nRT core     {self.source_meta['rt_core_status']}"
                        f"\nObserver    {self.source_meta['observer_status']}"
                        if self.source_meta else ""
                    )
                )
            else:
                self._set_log(
                    "PROFILE STATUS    HARDWARE VERIFIED CORE\n\n"
                    f"Release    requested {rmm:g} mm -> {rr} raw (~{HHE.raw_to_mm(rr):.3f} mm estimated)\n"
                    f"Re-press   requested {pmm:g} mm -> {pr} raw (~{HHE.raw_to_mm(pr):.3f} mm estimated)\n\n"
                    "HHKB RT core     HARDWARE VERIFIED\n"
                    "Observer keys    R / E / W / A / S / D / SPACE\n"
                    "Windows DIP      RECOMMENDED / TESTED\n"
                    "Low-power        SUPPORTED / TESTED\n"
                    "Mac DIP          NOT RECOMMENDED / NOT VALIDATED"
                )
        except Exception as e:
            self._set_log("INVALID CONFIG\n" + str(e))
        self._live_validate()

    # ---------------- Build / Apply ----------------
    @property
    def output_dir(self):
        d = APP_DIR / "output"
        d.mkdir(exist_ok=True)
        return d

    def apply(self):
        if not self.source_valid or not self.source_path:
            messagebox.showerror(APP_TITLE, "Select a valid supported stock firmware first.")
            return
        if not self._live_validate():
            return
        if self.platform.get() == PLAT_R3S:
            self._build_r3s()
        else:
            self._apply_hhkb()

    def _build_r3s(self):
        try:
            data = self.source_path.read_bytes()
            R3P.validate_source(data)  # authoritative revalidation
            rmm, pmm, rr, pr = self._profile_values()
            out, meta = R3P.build(data, rr, pr)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return

        target = self.output_dir / f"{self.source_path.stem}_TopreRT_R{rr}_P{pr}.rfb"
        n = 2
        while target.exists():
            target = self.output_dir / f"{self.source_path.stem}_TopreRT_R{rr}_P{pr}_{n}.rfb"
            n += 1
        target.write_bytes(out)
        mp = Path(str(target) + ".manifest.json")
        mp.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        self.progress["value"] = 100
        self.progress_text.set("Firmware ready")
        self._append("")
        self._append(f"BUILD PASS — REALFORCE {meta.get('source_model','R3S')}")
        self._append(f"RT core: {meta.get('rt_core_status','VERIFIED')}")
        self._append(f"Observer: {meta.get('observer_status','UNKNOWN')}")
        self._append(f"Firmware: {target}")
        self._append(f"SHA-256: {meta['output_sha256']}")
        self._append("Whitelist / CRC / trailer: PASS")
        self._append("No firmware was flashed by TopreRT.")
        self.status_line.set("R3S firmware ready — install it with official REALFORCE software")

        messagebox.showinfo(
            APP_TITLE,
            "R3S firmware build completed.\n\n"
            "Recommended next step: update the generated .rfb with the official REALFORCE software.\n\n"
            f"{target}"
        )

    def _apply_hhkb(self):
        try:
            stock = self.source_path.read_bytes()
            HHE.validate_stock(stock)
            rmm, pmm, rr, pr = self._profile_values()
            image = HHE.build(stock, rr, pr)
            HHE.validate_candidate(stock, image)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return

        if not messagebox.askyesno(
            APP_TITLE,
            "Apply TopreRT to the connected HHKB?\n\n"
            f"Release: {rr} raw (~{HHE.raw_to_mm(rr):.3f} mm estimated)\n"
            f"Re-press: {pr} raw (~{HHE.raw_to_mm(pr):.3f} mm estimated)\n\n"
            "Do not disconnect USB or let the PC sleep during the update."
        ):
            return

        target = self.output_dir / f"HHKB800_FW_A048_TopreRT_R{rr}_P{pr}.hfb"
        n = 2
        while target.exists():
            target = self.output_dir / f"HHKB800_FW_A048_TopreRT_R{rr}_P{pr}_{n}.hfb"
            n += 1
        target.write_bytes(image)
        HHE.write_manifest(target, image, rr, pr, rmm, pmm)

        self._busy(True)
        self.progress["value"] = 0
        self.progress_text.set("Preparing...")

        def work():
            self.q.put(("log", ""))
            self.q.put(("log", "BUILD PASS — HHKB"))
            self.q.put(("log", f"Firmware: {target}"))
            self.q.put(("log", f"SHA-256: {HHE.sha256(image)}"))
            self.q.put(("log", "Whitelist / helper / CRC: PASS"))
            self._hhkb_flash(image)
            self.q.put(("status", "HHKB TopreRT applied — reconnect verified"))
            self.q.put(("busy_off", None))
        self._worker(work)

    def _hhkb_flash(self, image):
        self.flash_t0 = None
        self.flash_rate = None
        e1, e2, e3 = HHE.build_packets(image)
        hid = HHE.load_hid()
        desc = HHE.wait_one(hid, 5)
        dev = HHE.open_dev(hid, desc)
        try:
            ident1 = HHE.identity(dev)
            ident2 = (HHE.query(dev, 0x02), HHE.query(dev, 0x05), HHE.query(dev, 0x06))
            if ident1 != ident2:
                raise HHE.Reject("identity changed during preflight")
            typ = HHE.decode_identity(ident1[0])
            if not typ.startswith("PD-KB8"):
                raise HHE.Reject("connected device is not an HHKB 800-series")
            self.q.put(("log", f"Connected: {typ}"))
            self.q.put(("progress", (7, "Entering updater")))
            HHE.req(dev, HHE.packet(0xE0), bytes([0x55,0x55,0xE0,0,0,0]))
        finally:
            dev.close()

        self.q.put(("progress", (10, "Waiting for updater")))
        time.sleep(10)
        dev = HHE.open_dev(hid, HHE.wait_one(hid, 10))
        try:
            self.q.put(("progress", (15, "Starting transfer")))
            HHE.req(dev, e1, bytes([0x55,0x55,0xE1,0,0,0]))
            total = len(e2)
            self.q.put(("log", f"E2: sending {total} packets..."))
            for n, p in enumerate(e2):
                r = HHE.req(dev, p, bytes([0x55,0x55,0xE2,0,0,2]))
                if r[6:8] != n.to_bytes(2, "little"):
                    raise HHE.Reject(f"E2 ACK mismatch at packet {n}")
                completed = n + 1
                if n % 50 == 0 or n == total - 1:
                    now = time.perf_counter()
                    if self.flash_t0 is None:
                        self.flash_t0 = now
                    elapsed = max(now - self.flash_t0, 1e-6)
                    avg = completed / elapsed
                    if completed >= 250:
                        self.flash_rate = avg if self.flash_rate is None else 0.25*avg + 0.75*self.flash_rate
                        eta = (total-completed) / max(self.flash_rate, 1e-6)
                        eta_text = f"ETA {eta:.0f}s" if eta < 60 else f"ETA {int(eta//60)}m {int(eta%60):02d}s"
                    else:
                        eta_text = "ETA estimating..."
                    pct = 15 + (completed/total)*70
                    self.q.put(("progress", (pct, f"Writing {completed*100/total:.0f}% · {eta_text}")))
                if n % 500 == 0 or n == total-1:
                    self.q.put(("log", f"  {completed}/{total}  {completed*100/total:5.1f}%"))
            self.q.put(("progress", (88, "Finalizing")))
            HHE.req(dev, e3, bytes([0x55,0x55,0xE3,0,0,0]))
        finally:
            dev.close()

        self.q.put(("progress", (92, "Reconnecting · up to ~10s")))
        time.sleep(10)
        dev = HHE.open_dev(hid, HHE.wait_one(hid, 10))
        try:
            HHE.identity(dev)
        finally:
            dev.close()
        self.q.put(("progress", (100, "Reconnect PASS")))
        self.q.put(("log", "Reconnect: PASS"))

    # ---------------- Observer ----------------
    def start_observer(self):
        if not self._live_validate():
            messagebox.showerror(APP_TITLE, "Fix the RT profile first.")
            return
        if self.platform.get() == PLAT_R3S:
            self._start_r3_observer()
        else:
            self._start_hhkb_observer()

    def _start_r3_observer(self):
        if self.source_meta and self.source_meta.get("observer_status") != "HARDWARE VERIFIED":
            if not messagebox.askyesno(
                APP_TITLE,
                f"{self.source_meta.get('model','This model')} Observer key mapping is "
                "binary-compatible but has not been hardware-validated.\n\n"
                "Continue with the R3SB-derived key map?"
            ):
                return
        if self.r3_observer_proc is not None and self.r3_observer_proc.poll() is None:
            messagebox.showinfo(APP_TITLE, "Observer is already running.")
            return
        rmm, pmm, _, _ = self._profile_values()
        key = self.key.get()
        idx = R3_KEYMAP[key]
        observer = R3S_DIR / "observer.py"
        self.r3_stop_file = self.output_dir / f".r3_observer_stop_{os.getpid()}.flag"
        try:
            self.r3_stop_file.unlink(missing_ok=True)
        except Exception:
            pass

        cmd = [
            sys.executable, "-u", str(observer),
            "--key", str(idx),
            "--expect-release-mm", f"{rmm:.2f}",
            "--expect-repress-mm", f"{pmm:.2f}",
            "--stop-file", str(self.r3_stop_file),
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        self.r3_observer_proc = subprocess.Popen(
            cmd, cwd=str(R3S_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, creationflags=flags
        )
        self.obs_start.configure(state="disabled")
        self.obs_stop.configure(state="normal")
        self.observer_state.set(f"Monitoring {key}")
        self._append("")
        self._append(f"Starting Observer — {key} (internal index {idx})")
        self._append(f"Expected: release {rmm:.2f} mm / re-press {pmm:.2f} mm")

        def reader():
            for line in self.r3_observer_proc.stdout:
                line = line.rstrip()
                if self.observer_mode.get() == "Simple":
                    keep = (
                        "STATE " in line
                        or "BRACKETED" in line
                        or "OBSERVATION SUMMARY" in line
                        or "Release " in line
                        or "Mid-stroke re-press" in line
                    )
                    if not keep:
                        continue
                self.q.put(("log", line))
            code = self.r3_observer_proc.wait()
            self.q.put(("log", f"Observer stopped (exit code {code})."))
            self.q.put(("observer_off", None))
            self.r3_observer_proc = None
        threading.Thread(target=reader, daemon=True).start()

    def _hhkb_sampling_quality(self, width_raw):
        width_mm = HHE.raw_to_mm(width_raw)
        if width_mm <= 0.16:
            return "GOOD"
        if width_mm <= 0.31:
            return "FAIR"
        return "COARSE"

    def _hhkb_bracket(self, lo, hi):
        return (
            f"({lo}, {hi}] raw "
            f"(~{HHE.raw_to_mm(lo):.3f}..{HHE.raw_to_mm(hi):.3f} mm)"
        )

    def _start_hhkb_observer(self):
        key = self.key.get()
        idx = HH_KEYMAP[key]
        _, _, rr, pr = self._profile_values()
        self.stop_event.clear()

        def work():
            hid = HHE.load_hid()
            # Use the same HHKB enumeration policy as Detect/Writer.
            # A connected HHKB can expose any supported PID in HHE.PIDS;
            # restricting Observer to PID_NORMAL (0x0021) makes a valid
            # wired-mode device invisible to the Observer.
            rows = HHE.enum_vendor(hid)
            if len(rows) != 1:
                raise HHE.Reject(f"Expected one HHKB MI_02, found {len(rows)}")

            dev = hid.device()
            dev.open_path(rows[0]["path"])

            last = None
            prev = None
            transitions = 0
            rel_n = rel_pass = rep_n = rep_pass = stock_first = 0
            rel_quality = {"GOOD":0, "FAIR":0, "COARSE":0}
            rep_quality = {"GOOD":0, "FAIR":0, "COARSE":0}
            t0 = time.perf_counter()

            self.q.put(("observer_on", f"Monitoring {key}"))
            self.q.put(("log", ""))
            self.q.put(("log", f"Starting Observer — {key} (internal index {idx})"))
            self.q.put(("log", f"Expected release : {rr} raw (~{HHE.raw_to_mm(rr):.3f} mm)"))
            self.q.put(("log", f"Expected re-press: {pr} raw (~{HHE.raw_to_mm(pr):.3f} mm)"))
            if self.observer_mode.get() == "Detailed":
                self.q.put(("log", "Detailed HHKB telemetry: RAW / DynT / AnchorRaw / crossing brackets"))

            try:
                HHE.tx(dev, HHE.packet(0x01, b"\0"))
                r = HHE.rx(dev, 1000)
                if r[:6] != bytes([0x55,0x55,1,0,0,0]):
                    raise HHE.Reject("Unexpected open response")

                while not self.stop_event.is_set():
                    HHE.tx(dev, HHE.packet(0x99))
                    s = HHE.parse_diag(HHE.rx(dev, 1000), rr, pr)
                    if s["index"] != idx:
                        time.sleep(.02)
                        continue

                    now = time.perf_counter() - t0
                    st = s["state"]

                    if prev is None:
                        prev = s
                        last = st
                        time.sleep(.02)
                        continue

                    if st != last:
                        transitions += 1
                        names = {
                            (0,3): "PRESS / RE-PRESS",
                            (3,2): "RELEASE START",
                            (2,0): "RELEASE COMPLETE",
                            (3,0): "FULL RELEASE",
                        }
                        self.q.put(("log", f"[{now:7.3f}s] STATE {last}->{st}  {names.get((last,st),'transition')}"))

                        if self.observer_mode.get() == "Detailed":
                            par = prev.get("anchor_raw")
                            car = s.get("anchor_raw")
                            self.q.put((
                                "log",
                                f"             prev RAW={prev['raw']} DynT={prev['dyn']} "
                                f"AnchorRaw={par if par is not None else '-'}"
                            ))
                            self.q.put((
                                "log",
                                f"             now  RAW={s['raw']} DynT={s['dyn']} "
                                f"AnchorRaw={car if car is not None else '-'}"
                            ))

                        if last == 3 and st == 2:
                            # Release is measured from the pressed-side running maximum.
                            if prev["anchor_raw"] is not None:
                                anchor = prev["anchor_raw"]
                                a = max(0, anchor - prev["raw"])
                                b = max(0, anchor - s["raw"])
                                lo, hi = sorted((a,b))
                                width = hi-lo
                                q = self._hhkb_sampling_quality(width)
                                rel_quality[q] += 1
                                rel_n += 1
                                ok = lo <= rr <= hi
                                rel_pass += int(ok)
                                if self.observer_mode.get() == "Detailed":
                                    self.q.put(("log", f"             RELEASE crossing = {self._hhkb_bracket(lo,hi)}  quality={q}"))
                                    self.q.put(("log", f"             expected {rr}: {'BRACKETED ✓' if ok else 'NOT BRACKETED'}"))

                        elif last == 0 and st == 3:
                            # A state-0 sample with anchor_raw means a mid-stroke
                            # re-press anchor exists. anchor_raw=None is stock-first.
                            if prev["anchor_raw"] is not None:
                                anchor = prev["anchor_raw"]
                                a = max(0, prev["raw"] - anchor)
                                b = max(0, s["raw"] - anchor)
                                lo, hi = sorted((a,b))
                                width = hi-lo
                                q = self._hhkb_sampling_quality(width)
                                rep_quality[q] += 1
                                rep_n += 1
                                ok = lo < pr <= hi
                                rep_pass += int(ok)
                                if self.observer_mode.get() == "Detailed":
                                    self.q.put(("log", f"*** MID-STROKE RE-PRESS #{rep_n}"))
                                    self.q.put(("log", f"    observed anchor≈{anchor} raw"))
                                    self.q.put(("log", f"    crossing bracket  = {self._hhkb_bracket(lo,hi)}  quality={q}"))
                                    self.q.put(("log", f"    expected {pr}: {'BRACKETED ✓' if ok else 'NOT BRACKETED — repeat more slowly'}"))
                            else:
                                stock_first += 1
                                if self.observer_mode.get() == "Detailed":
                                    self.q.put(("log", f"             STOCK-FIRST #{stock_first} (excluded)"))

                        last = st

                    prev = s
                    time.sleep(.02)

            finally:
                dev.close()
                self.q.put(("log", ""))
                self.q.put(("log", "=== OBSERVATION SUMMARY ==="))
                self.q.put(("log", f"Release {rr}: {rel_pass}/{rel_n} bracketed"))
                self.q.put(("log", f"  sampling quality: GOOD={rel_quality['GOOD']} FAIR={rel_quality['FAIR']} COARSE={rel_quality['COARSE']}"))
                self.q.put(("log", f"Mid-stroke re-press {pr}: {rep_pass}/{rep_n} bracketed"))
                self.q.put(("log", f"  sampling quality: GOOD={rep_quality['GOOD']} FAIR={rep_quality['FAIR']} COARSE={rep_quality['COARSE']}"))
                self.q.put(("log", f"Stock-first presses excluded: {stock_first}"))
                self.q.put(("log", "Quality is a sampling-density heuristic, not a firmware pass/fail grade."))
                self.q.put(("log", f"Observer stopped — {transitions} transitions"))
                self.q.put(("observer_off", None))
        def guarded_work():
            try:
                work()
            except Exception:
                # work() only posts observer_off from its inner device-session
                # finally block.  Failures during enumeration/open_path happen
                # before that block, so explicitly restore the Observer UI.
                self.q.put(("observer_off", None))
                raise

        self._worker(guarded_work)

    def stop_observer(self):
        if self.platform.get() == PLAT_R3S:
            proc = self.r3_observer_proc
            if proc is not None and proc.poll() is None:
                try:
                    self.r3_stop_file.parent.mkdir(exist_ok=True)
                    self.r3_stop_file.write_text("stop", encoding="ascii")
                    self.observer_state.set("Stopping...")
                except Exception:
                    proc.terminate()
        else:
            self.stop_event.set()
            if self.worker is not None and self.worker.is_alive():
                self.observer_state.set("Stopping...")
            else:
                self.observer_state.set("Observer idle")
                self.obs_start.configure(state="normal")
                self.obs_stop.configure(state="disabled")

    # ---------------- Recovery / tests ----------------
    def recovery_action(self):
        if self.platform.get() == PLAT_R3S:
            messagebox.showinfo(
                APP_TITLE,
                "REALFORCE R3S recovery/update policy\n\n"
                "TopreRT does not flash the R3S.\n"
                "Use the official REALFORCE software for normal firmware updates.\n\n"
                "Low-level STM32 DFU recovery is intentionally not exposed in the consumer GUI."
            )
            return
        if not self.source_valid or not self.source_path:
            messagebox.showerror(APP_TITLE, "Select the exact stock A0.48 first.")
            return
        stock = self.source_path.read_bytes()
        try:
            HHE.validate_stock(stock)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        if not messagebox.askyesno(APP_TITLE, "Restore exact stock HHKB A0.48?"):
            return
        self._busy(True)
        self.progress["value"] = 0
        self.progress_text.set("Restore preparing...")
        def work():
            self.q.put(("log", "RESTORE PREFLIGHT: PASS"))
            self._hhkb_flash(stock)
            self.q.put(("status", "HHKB stock A0.48 restored — reconnect verified"))
            self.q.put(("busy_off", None))
        self._worker(work)

    def self_test(self):
        try:
            if self.platform.get() == PLAT_R3S:
                expected = {0.50:256, 0.60:306, 0.70:358, 0.80:408, 1.00:510}
                for mm, raw in expected.items():
                    if R3C.mm_to_raw(mm) != raw:
                        raise R3C.Reject("R3S mm conversion regression")
                for r,p in [(306,408),(306,358),(256,358),(104,104),(510,510)]:
                    R3P.make_helper(r,p)
                lines = ["SELF-TEST PASS — REALFORCE R3S", "mm conversion: PASS", "helper generation: PASS"]
                if self.source_valid and self.source_path:
                    data = self.source_path.read_bytes()
                    R3P.validate_source(data)
                    o, _ = R3P.build(data, 306, 408)
                    if R3C.sha256(o) != R3C.STABLE_OUTPUT_SHA256:
                        raise R3C.Reject("stable regression SHA mismatch")
                    lines += ["stock validation: PASS", "stable regression: PASS"]
            else:
                if not self.source_valid or not self.source_path:
                    raise HHE.Reject("Select exact stock A0.48 first.")
                stock = self.source_path.read_bytes()
                HHE.validate_stock(stock)
                _, _, rr, pr = self._profile_values()
                img = HHE.build(stock, rr, pr)
                HHE.validate_candidate(stock, img)
                lines = [
                    "SELF-TEST PASS — HHKB",
                    "stock SHA: PASS", "build/CRC: PASS",
                    "whitelist/helper config: PASS", f"profile: R{rr}/P{pr}"
                ]
            self._set_log("\n".join(lines))
            self.status_line.set("Self-test passed")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def open_output(self):
        self.output_dir.mkdir(exist_ok=True)
        try:
            os.startfile(self.output_dir.resolve())
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))


if __name__ == "__main__":
    UnifiedGUI().mainloop()
