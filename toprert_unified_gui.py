# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 xvlqwz <xvlqwz@users.noreply.github.com>
# Copyright (C) 2026 rocketman2654 <rocketman2654@users.noreply.github.com>

#!/usr/bin/env python3
r"""
TopreRT Unified GUI v0.3.0-rc2 — GUI layout preview

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
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

APP_DIR = Path(__file__).resolve().parent
R3S_DIR = APP_DIR / "backends" / "r3s"
HHKB_DIR = APP_DIR / "backends" / "hhkb"

# Import frozen backends without renaming their internal imports.
sys.path.insert(0, str(R3S_DIR))
import toprert_common as R3C
import toprert as R3P

sys.path.insert(0, str(HHKB_DIR))
import hhkb_toprert_engine_v0_6 as HHE
import firmware_detection as FW_DETECT
import firmware_inspection as FW_INSPECT
import device_discovery as DEVICE_DISCOVERY
from firmware_identity import generation as HH_ID, registry as BUILD_REGISTRY
import device_diagnostics as DEVICE_DIAG
import install_history as INSTALL_HISTORY

# v0.13 generic-HOLD custom-slot builder.
try:
    import hhkb_v013_generic_hold_builder_v0_2_rc2 as HHSLOT
except ImportError:
    sys.path.insert(0, str(APP_DIR))
    import hhkb_v013_generic_hold_builder_v0_2_rc2 as HHSLOT

APP_TITLE = "TopreRT GUI — v0.3.0-rc6"
APP_BUILD = "v0.3.0-rc6"
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


def flash_transfer_text(done, total, elapsed, rate):
    """Shared RT/HOLD display. ETA covers packet transfer, not reconnect."""
    def clock(seconds):
        minutes, seconds = divmod(max(0, int(round(seconds))), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
    ready = elapsed >= 1 and done > 1 and rate is not None and rate > 0
    eta = clock(max(0, total - done) / rate) if ready else "estimating..."
    speed = f"{rate:.1f} pkt/s" if ready else "measuring..."
    return (f"Writing {done * 100 / total:.1f}% · Packets {done:,} / {total:,}\n"
            f"Elapsed {clock(elapsed)} · Transfer ETA {eta} · {speed}")


def local_history_summary(records, platform, *, model=None):
    """PC history is supplementary; never an installed-firmware conclusion."""
    event = "generated" if platform == PLAT_R3S else "installed"
    relevant = [r for r in records if r["event"] == event and
                (r["model"].startswith("R3S") if platform == PLAT_R3S else r["model"].startswith("PD-KB8"))
                and (not model or r["model"] == model)]
    if not relevant:
        return "No local record for this model / keyboard family. Current firmware is not inferred from history."
    r = relevant[0]
    mode = {"rt": "RT", "hold": "HOLD", "stock": "Stock"}[r["intended_mode"]]
    action = "Last file generated" if event == "generated" else "Last completed installation"
    stamp = r["timestamp_utc"].replace("T", " ").split(".", 1)[0] + " UTC"
    note = ("File creation only; installation with official REALFORCE software is not recorded."
            if event == "generated" else "PC record only; connected device not matched and firmware not read back.")
    return (f"{action}: {mode} · {r['model']} · {stamp}\n"
            f"App build: {r['application_build']} · File SHA-256: {r['firmware_sha256'][:12]}…\n{note}")


def hold_history_settings(report):
    """Retain intended public slot labels, never a path or raw response."""
    try:
        keys = ("source_name", "tap_name", "hold_name", "threshold_ms")
        return {"slots": [{k: slot[k] for k in keys} for slot in report["slots"]]}
    except (TypeError, KeyError):
        return {}


class UnifiedGUI(tk.Tk):
    def destroy(self):
        # Cancel this interpreter's queued callbacks before deleting their Tcl
        # commands. This also keeps sequential Development GUI tests clean.
        for token in self.tk.splitlist(self.tk.call('after', 'info')):
            try:
                self.after_cancel(token)
            except tk.TclError:
                pass
        super().destroy()

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x790")
        self.minsize(960, 580)

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

        # HHKB v0.13 generic-HOLD custom-slot path.
        self.hh_slot_baseline_path = None
        self.hh_slot_baseline_status = tk.StringVar(value="No exact stock A0.48 selected")
        self.hh_validated_build_path = None
        self.hh_validated_build_sha = None
        self.hh_validated_build_report = None
        self.hh_slot_enabled = []
        self.hh_slot_source = []
        self.hh_slot_tap = []
        self.hh_slot_hold = []
        self.hh_slot_hold_status = []
        self.hh_slot_threshold = []
        self._syncing_profile = False

        self.source_status = tk.StringVar(value="No firmware selected")
        self.validation_status = tk.StringVar(value="")
        self.status_line = tk.StringVar(value="Ready")
        self.action_status = tk.StringVar(value="")
        self.observer_state = tk.StringVar(value="Observer idle")
        self.installed_firmware = tk.StringVar(value="Not queried — USB only; manual read-only check")
        self.firmware_identification = None
        self._inspection_epoch = 0
        self.local_history = tk.StringVar(value="No local operation recorded.")
        self.detect_detail = tk.StringVar(value="Legacy detection is experimental; no flashing performed.")
        self.progress_text = tk.StringVar(value="")

        self.worker = None
        self.flash_active = False
        self._closing = False
        self._flash_widget_states = []
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.r3_observer_proc = None
        self.r3_stop_file = None

        self.flash_t0 = None
        self.flash_rate = None

        self._build_ui()
        self._install_wheel_bindings()
        self.update_idletasks()  # Complete initial widget geometry before fitting tab height.
        self._fit_active_tab_height()
        self._hh_slots_try_bundled_baseline()
        self.release.trace_add("write", self._profile_text_changed)
        self.repress.trace_add("write", self._profile_text_changed)
        self.platform.trace_add("write", self._platform_changed)
        self.after(80, self._poll)
        self.after(150, self._detect_platform)

    # ---------------- UI ----------------
    def _build_ui(self):
        # Keep firmware operations visible even at modest desktop resolutions.
        # Only the content pane scrolls; firmware code and safety checks are unchanged.
        self.footer = ttk.Frame(self, padding=(12, 8, 12, 10))
        self.footer.pack(side="bottom", fill="x")
        content_area = ttk.Frame(self)
        content_area.pack(side="top", fill="both", expand=True)
        self.content_canvas = tk.Canvas(content_area, borderwidth=0, highlightthickness=0)
        hscroll = ttk.Scrollbar(content_area, orient="horizontal", command=self.content_canvas.xview)
        hscroll.pack(side="bottom", fill="x")
        vscroll = ttk.Scrollbar(content_area, orient="vertical", command=self.content_canvas.yview)
        vscroll.pack(side="right", fill="y")
        self.content_canvas.pack(side="left", fill="both", expand=True)
        self.content_canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        main = ttk.Frame(self.content_canvas, padding=12)
        self._content_window = self.content_canvas.create_window((0, 0), window=main, anchor="nw")
        main.bind("<Configure>", self._update_content_scrollregion)
        self.content_canvas.bind("<Configure>", self._resize_content_viewport)
        # Wheel routing is scoped to the content pane; never use bind_all here.
        # Windows ttk combobox popdowns are separate Tk windows, and the old
        # global binding scrolled the whole GUI behind an open selection menu.

        top = ttk.Frame(main)
        top.pack(fill="x")
        ttk.Label(top, text="TopreRT GUI", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(top, text="Keyboard").pack(side="left", padx=(30, 7))
        combo = ttk.Combobox(
            top, textvariable=self.platform,
            values=[PLAT_R3S, PLAT_HHKB], state="readonly", width=30
        )
        combo.pack(side="left")
        self.detect_btn = ttk.Button(top, text="Detect", command=self._detect_platform)
        self.detect_btn.pack(side="left", padx=(8, 0))

        self.platform_note = ttk.Label(main, text="")
        self.platform_note.pack(anchor="w", pady=(2, 10))

        inspect_box = ttk.LabelFrame(main, text="Installed firmware · Last inspection", padding=8)
        inspect_box.pack(fill="x", pady=(0, 8))
        inspect_header = ttk.Frame(inspect_box)
        inspect_header.pack(fill="x")
        ttk.Label(inspect_header, textvariable=self.installed_firmware, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.inspect_btn = ttk.Button(inspect_header, text="Inspect firmware", command=self.inspect_installed_firmware)
        self.inspect_btn.pack(side="right", padx=(8, 0))
        self.diagnostics_btn = ttk.Button(inspect_header, text="Device diagnostics", command=self.inspect_device_diagnostics)
        self.diagnostics_btn.pack(side="right", padx=(8, 0))
        self.firmware_report_btn = ttk.Button(inspect_box, text="Save identification report…",
            command=self.save_firmware_identification, state="disabled")
        self.firmware_report_btn.pack(anchor="e", pady=(4, 0))
        ttk.Label(inspect_box, textvariable=self.detect_detail, foreground="#526171", wraplength=875).pack(anchor="w", pady=(5, 0))

        history_box = ttk.LabelFrame(main, text="Local history on this PC · not device identification", padding=8)
        history_box.pack(fill="x", pady=(0, 8))
        ttk.Label(history_box, textvariable=self.local_history, wraplength=875,
                  justify="left", foreground="#526171").pack(anchor="w")

        self.stock_firmware_frame = ttk.LabelFrame(main, text="Stock firmware", padding=9)
        f1 = self.stock_firmware_frame
        f1.pack(fill="x")
        row = ttk.Frame(f1)
        row.pack(fill="x")
        self.source_entry = ttk.Entry(row, state="readonly")
        self.source_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self.browse_source).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Validate Stock File", command=self.full_validation).pack(side="left", padx=(8, 0))
        ttk.Label(f1, textvariable=self.source_status).pack(anchor="w", pady=(6, 0))


        # Explicit, high-contrast mode selector. Native Notebook tabs can be tiny
        # and almost invisible under Windows theme / DPI scaling, so hide them and
        # use two large regular Tk buttons with reliable background colors instead.
        ttk.Style(self).layout("ModeHidden.TNotebook.Tab", [])
        self.mode_switch = ttk.LabelFrame(
            main, text="FIRMWARE TO INSTALL — selection does not change the keyboard", padding=(10, 8)
        )
        self.mode_switch.pack(fill="x", pady=(10, 3))
        mode_row = ttk.Frame(self.mode_switch)
        mode_row.pack(fill="x")
        self.rt_mode_btn = tk.Button(
            mode_row, text="RAPID TRIGGER   (RT-only)",
            font=("Segoe UI", 11, "bold"), borderwidth=1, relief="solid",
            cursor="hand2", padx=10, pady=12,
            command=lambda: self._choose_mode("rt")
        )
        self.rt_mode_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.hold_mode_btn = tk.Button(
            mode_row, text="SPACEFN / GENERIC HOLD",
            font=("Segoe UI", 11, "bold"), borderwidth=1, relief="solid",
            cursor="hand2", padx=10, pady=12,
            command=lambda: self._choose_mode("hold")
        )
        self.hold_mode_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.firmware_tabs = ttk.Notebook(main, style="ModeHidden.TNotebook")
        self.firmware_tabs.pack(fill="x", pady=(2, 0))
        self.rt_tab = ttk.Frame(self.firmware_tabs, padding=(3, 8))
        self.hold_tab = ttk.Frame(self.firmware_tabs, padding=(3, 8))
        self.firmware_tabs.add(self.rt_tab, text="Rapid Trigger (RT-only)")
        self.firmware_tabs.add(self.hold_tab, text="SpaceFn / Generic HOLD")
        self.firmware_tabs.bind("<<NotebookTabChanged>>", self._mode_changed)
        self.mode_note = ttk.Label(main, text="", foreground="#526171", wraplength=880)
        self.mode_note.pack(anchor="w", pady=(6, 0))

        f2 = ttk.LabelFrame(self.rt_tab, text="Rapid Trigger profile", padding=9)
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
        ttk.Button(r, text="Check Settings", command=self.preview).pack(side="left")

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

        ttk.Label(f2, text="Observer: use the profile installed on the keyboard. Values here are expected settings, not read back from firmware.",
                  wraplength=880).pack(anchor="w", pady=(5, 0))

        # HHKB v0.12 custom-slot panel. Hidden on R3S.
        self.hh_slots_frame = ttk.LabelFrame(
            self.hold_tab, text="SpaceFn / Generic HOLD settings", padding=8
        )

        self.hh_slots_frame.pack(fill="x", pady=(8, 0))
        info = ttk.Frame(self.hh_slots_frame)
        info.pack(fill="x")
        ttk.Label(
            info,
            text="Input: exact stock A0.48 · CTRL/LALT/V/SPACE validated · SpaceFn validated special case"
        ).pack(side="left")
        ttk.Button(info, text="Load SpaceFn preset", command=self._hh_slots_load_spacefn).pack(side="right")
        ttk.Button(info, text="Load A/C/V preset", command=self._hh_slots_load_acv).pack(side="right", padx=(0, 8))

        ttk.Label(
            self.hh_slots_frame,
            text="Uses the stock firmware selected above. RT-only and HOLD are ALTERNATIVE builds, not a combined firmware.",
            foreground="#785a25", wraplength=920, justify="left"
        ).pack(anchor="w", pady=(7, 5))
        ttk.Label(self.hh_slots_frame, textvariable=self.hh_slot_baseline_status).pack(anchor="w", pady=(0, 5))

        grid = ttk.Frame(self.hh_slots_frame)
        grid.pack(fill="x")
        headers = ["Slot", "Enabled", "Source", "Tap", "Hold", "Threshold [ms]"]
        for c, text in enumerate(headers):
            ttk.Label(grid, text=text, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=c, sticky="w", padx=(0, 8), pady=(0, 3)
            )

        # LSHIFT source/tap remains blocked because its tap path is not proven.
        # HOLD uses the generic rev2 engine. Shift HOLD targets remain blocked.
        # FN is exposed, but the builder accepts it only for SPACE -> SPACE / FN.
        key_values = [k for k in HHSLOT.KEY_MAP.keys() if k != "LSHIFT"]
        hold_values = [
            k for k, idx in HHSLOT.KEY_MAP.items()
            if idx not in HHSLOT.BLOCKED_HOLD
        ]
        for i in range(8):
            en = tk.BooleanVar(value=(i < 3))
            srcv = tk.StringVar(value=["A", "C", "V"][i] if i < 3 else "A")
            tapv = tk.StringVar(value=["A", "C", "V"][i] if i < 3 else "A")
            holdv = tk.StringVar(value="CTRL")
            holdsv = tk.StringVar(value=HHSLOT.hold_support_status("CTRL"))
            thv = tk.StringVar(value="250")
            self.hh_slot_enabled.append(en)
            self.hh_slot_source.append(srcv)
            self.hh_slot_tap.append(tapv)
            self.hh_slot_hold.append(holdv)
            self.hh_slot_hold_status.append(holdsv)
            self.hh_slot_threshold.append(thv)

            ttk.Label(grid, text=f"SLOT{i}").grid(row=i+1, column=0, sticky="w", padx=(0, 8), pady=2)
            cb = ttk.Checkbutton(grid, variable=en, command=lambda n=i: (self._hh_slots_update_hold_status(n), self._hh_slots_changed()))
            cb.grid(row=i+1, column=1, sticky="w", padx=(0, 8), pady=2)
            sc = ttk.Combobox(grid, textvariable=srcv, values=key_values, state="readonly", width=12)
            sc.grid(row=i+1, column=2, sticky="w", padx=(0, 8), pady=2)
            tc = ttk.Combobox(grid, textvariable=tapv, values=key_values, state="readonly", width=12)
            tc.grid(row=i+1, column=3, sticky="w", padx=(0, 8), pady=2)
            hc = ttk.Combobox(grid, textvariable=holdv, values=hold_values, state="readonly", width=12)
            hc.grid(row=i+1, column=4, sticky="w", padx=(0, 8), pady=2)
            te = ttk.Entry(grid, textvariable=thv, width=12)
            te.grid(row=i+1, column=5, sticky="w", padx=(0, 8), pady=2)
            hs = ttk.Label(grid, textvariable=holdsv, width=26)
            hs.grid(row=i+1, column=6, sticky="w", pady=2)

            srcv.trace_add("write", self._hh_slots_changed)
            tapv.trace_add("write", self._hh_slots_changed)
            holdv.trace_add("write", self._hh_slots_changed)
            holdv.trace_add("write", lambda *_args, n=i: self._hh_slots_update_hold_status(n))
            thv.trace_add("write", self._hh_slots_changed)
            self._hh_slots_update_hold_status(i)

        srow = ttk.Frame(self.hh_slots_frame)
        srow.pack(fill="x", pady=(7, 0))
        self.hh_slot_summary = tk.StringVar(value="")
        ttk.Label(srow, textvariable=self.hh_slot_summary, wraplength=820).pack(side="left", fill="x", expand=True)
        ttk.Button(srow, text="Self-test HOLD", command=self._hh_slots_self_test).pack(side="right")

        self.safety_frame = ttk.LabelFrame(main, text="Safety / activity", padding=7)
        self.safety_frame.pack(fill="both", expand=True, pady=(10, 0))
        f3 = self.safety_frame
        self.log = tk.Text(f3, wrap="word", state="disabled", font=("Consolas", 9), height=10)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(f3, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

        prow = ttk.LabelFrame(self.footer, text="Firmware progress", padding=8)
        prow.pack(fill="x", pady=(8, 0))
        self.progress = ttk.Progressbar(prow, maximum=100)
        self.progress.pack(fill="x")
        progress_detail = ttk.Label(prow, textvariable=self.progress_text, justify="left", wraplength=850)
        progress_detail.pack(anchor="w", fill="x", pady=(6, 0))
        prow.bind("<Configure>", lambda event: progress_detail.configure(wraplength=max(200, event.width - 24)))

        actions = ttk.Frame(self.footer)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Software Self-test", command=self.self_test).pack(side="left")
        ttk.Button(actions, text="Open Output Folder", command=self.open_output).pack(side="left", padx=(8, 0))
        self.recovery_btn = ttk.Button(actions, text="Recovery / Restore", command=self.recovery_action)
        self.recovery_btn.pack(side="left", padx=(8, 0))

        ttk.Label(actions, textvariable=self.action_status).pack(side="left", padx=(14, 0))
        self.apply_btn = ttk.Button(actions, text="Build Firmware", command=self.apply)
        self.apply_btn.pack(side="right")
        self.hh_slots_flash_btn = ttk.Button(
            actions, text="2. Install HOLD", command=self._hh_slots_flash, state="disabled"
        )
        self.hh_slots_build_btn = ttk.Button(
            actions, text="1. Create HOLD File", command=self._hh_slots_build, state="disabled"
        )
        ttk.Label(self.footer, textvariable=self.status_line).pack(anchor="w", pady=(6, 0))

        self._platform_changed()

    def _update_content_scrollregion(self, _event=None):
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_content_viewport(self, event):
        # Width follows viewport when possible, avoiding clipped right-side fields.
        natural_width = self.content_canvas.nametowidget(
            self.content_canvas.itemcget(self._content_window, "window")
        ).winfo_reqwidth()
        self.content_canvas.itemconfigure(self._content_window, width=max(event.width, natural_width))
        self._update_content_scrollregion()

    def _install_wheel_bindings(self):
        """Scope scrolling to the content pane, not the entire Tk application.

        Each content widget gets a dedicated *binding tag* rather than a global
        MouseWheel binding. This prevents scrolling the outer Canvas behind an
        open ttk Combobox popdown (a separate Toplevel/Listbox on Windows).
        """
        content_tag = "TopreRTContentWheel"
        self.bind_class(content_tag, "<MouseWheel>", self._on_content_mousewheel)
        self.bind_class(content_tag, "<Button-4>", self._on_content_mousewheel)
        self.bind_class(content_tag, "<Button-5>", self._on_content_mousewheel)

        def visit(widget):
            for child in widget.winfo_children():
                visit(child)
            if isinstance(widget, ttk.Combobox):
                # A CLOSED Combobox must never change its selection merely
                # because the pointer is over it while scrolling the page.
                # Its popup Listbox remains independently scrollable when open.
                for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    widget.bind(sequence, lambda _event: "break")
                return
            if isinstance(widget, (tk.Text, tk.Listbox, tk.Scrollbar,
                                   ttk.Scrollbar, ttk.Notebook)):
                # Text / Listbox / Scrollbar owns its own scrolling.
                # The Notebook is navigable via explicit mode buttons only.
                return
            if content_tag not in widget.bindtags():
                widget.bindtags((content_tag,) + widget.bindtags())

        visit(self.content_canvas)
        # Prevent any ttk Notebook class-level wheel navigation even when
        # the (hidden) Notebook itself receives a synthetic wheel event.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.firmware_tabs.bind(sequence, lambda _event: "break")

    def _on_content_mousewheel(self, event):
        # Only content widgets carry the custom bindtag. Dropdown popup
        # Listboxes and the activity log deliberately do not.
        if getattr(event, "num", None) == 4:
            units = -1
        elif getattr(event, "num", None) == 5:
            units = 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            units = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        # Tk Canvas can scroll into NEGATIVE coordinates when its content is
        # shorter than the viewport. yview() still reports (0, 1), hiding
        # the overscroll and exposing a large blank area above the GUI.
        # Do not scroll an already fully visible page in either direction.
        canvas = self.content_canvas
        bbox = canvas.bbox(self._content_window)
        if not bbox or bbox[3] - bbox[1] <= canvas.winfo_height():
            canvas.yview_moveto(0)
            return "break"
        # When the content is taller than the viewport, Canvas clamps the
        # normal scrolling range correctly. Also reset any stale negative
        # offset left over from a prior resize or mode change.
        if canvas.canvasy(0) < bbox[1]:
            canvas.yview_moveto(0)
        canvas.yview_scroll(units, "units")
        return "break"

    def _choose_mode(self, mode):
        if self.platform.get() != PLAT_HHKB and mode != "rt":
            return
        self.firmware_tabs.select(self.hold_tab if mode == "hold" else self.rt_tab)
        self._update_mode_selector()

    def _update_mode_selector(self):
        # Tk buttons (instead of theme-dependent ttk tabs) keep the selection
        # visible on Windows at both 100% and high-DPI scaling.
        is_hh = self.platform.get() == PLAT_HHKB
        if is_hh:
            if not self.mode_switch.winfo_manager():
                self.mode_switch.pack(before=self.firmware_tabs, fill="x", pady=(10, 3))
        else:
            self.mode_switch.pack_forget()
        is_hold = is_hh and self.firmware_tabs.select() == str(self.hold_tab)
        for btn, selected in ((self.rt_mode_btn, not is_hold), (self.hold_mode_btn, is_hold)):
            btn.configure(
                bg="#146b50" if selected else "#e4e9ef",
                fg="#ffffff" if selected else "#28384a",
                activebackground="#10533f" if selected else "#cdd8e2",
                activeforeground="#ffffff" if selected else "#182631",
                highlightbackground="#146b50" if selected else "#a5b2c1",
            )

    def _mode_changed(self, _event=None):
        if not hasattr(self, "apply_btn"):
            return
        self._update_mode_selector()
        is_hh = self.platform.get() == PLAT_HHKB
        is_hold = is_hh and self.firmware_tabs.select() == str(self.hold_tab)
        self.apply_btn.pack_forget()
        self.hh_slots_build_btn.pack_forget()
        self.hh_slots_flash_btn.pack_forget()
        if is_hold:
            self.hh_slots_flash_btn.pack(side="right")
            self.hh_slots_build_btn.pack(side="right", padx=(0, 8))
            self.mode_note.configure(text="HOLD / SpaceFn: 1. Create a file. 2. Install it on HHKB. This replaces the RT-only build.")
        else:
            self.apply_btn.pack(side="right")
            self.mode_note.configure(text=(
                "HHKB: Create & Install RT writes to the keyboard after confirmation. Changing settings alone does not apply them."
                if is_hh else "R3S: Create a file, then open Output Folder and install the generated .rfb with official REALFORCE software."
            ))
        self.after_idle(self._fit_active_tab_height)
        self.content_canvas.yview_moveto(0)

    def _fit_active_tab_height(self):
        active = self.hold_tab if (
            self.platform.get() == PLAT_HHKB
            and self.firmware_tabs.select() == str(self.hold_tab)
        ) else self.rt_tab
        self.firmware_tabs.configure(height=active.winfo_reqheight())
        self._update_content_scrollregion()

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
        if b or self.flash_active:
            self.apply_btn.configure(state="disabled")
        else:
            self._live_validate()

    def _operation_available(self):
        if self._closing or self.flash_active or (self.worker and self.worker.is_alive()) or (
            self.r3_observer_proc is not None and self.r3_observer_proc.poll() is None
        ):
            messagebox.showinfo(APP_TITLE, "Another operation is already running.")
            return False
        return True

    def _lock_flash_controls(self):
        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Toplevel):
                    continue  # Read-only snapshot windows may close independently.
                if child.winfo_class() in {
                    "TButton", "TEntry", "TCombobox", "TCheckbutton", "TRadiobutton",
                    "TSpinbox", "Button", "Entry", "Checkbutton", "Radiobutton", "Spinbox",
                }:
                    self._flash_widget_states.append((child, child.cget("state")))
                    child.configure(state="disabled")
                visit(child)
        visit(self)

    def _finish_flash(self):
        # The queue notification precedes actual thread exit by a few instructions.
        if self.worker and self.worker.is_alive():
            self.after(20, self._finish_flash)
            return
        self.flash_active = False
        for widget, state in self._flash_widget_states:
            widget.configure(state=state)
        self._flash_widget_states.clear()
        self._hh_slots_changed()  # Disarm even after a failed/partial attempt.
        self._live_validate()

    def _on_close(self):
        if self.flash_active:
            messagebox.showinfo(APP_TITLE,
                "HHKB update is still running. Keep USB connected and wait for completion.\n"
                "The window cannot close until the update worker has stopped.")
            return
        self.stop_event.set()
        self._closing = True
        if self.r3_observer_proc is not None and self.r3_observer_proc.poll() is None:
            self.stop_observer()
        self._close_when_idle()

    def _close_when_idle(self):
        if (self.worker and self.worker.is_alive()) or (
            self.r3_observer_proc is not None and self.r3_observer_proc.poll() is None
        ):
            self.after(100, self._close_when_idle)
            return
        self.destroy()

    def _worker(self, fn, *, flash=False):
        if not self._operation_available():
            return False
        if flash:
            # Invalidate before saving widget states so unlocking cannot restore
            # export of an identification captured before this update attempt.
            self._inspection_epoch = getattr(self, "_inspection_epoch", 0) + 1
            self.firmware_identification = None
            self.firmware_report_btn.configure(state="disabled")
            self.installed_firmware.set("Not verified after update attempt")
            self.detect_detail.set("After the update stops, select Inspect firmware to query the connected keyboard again.")
            self.flash_active = True
            self._lock_flash_controls()
        self.worker = threading.Thread(target=self._worker_wrap, args=(fn, flash), daemon=not flash)
        try:
            self.worker.start()
        except Exception:
            if flash:
                self._finish_flash()
            raise
        return True

    def _worker_wrap(self, fn, flash=False):
        try:
            fn()
        except Exception as e:
            self.q.put(("error", str(e)))
        finally:
            if flash:
                self.q.put(("flash_finished", None))

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "flash_finished":
                    self._finish_flash()
                elif kind == "device_diagnostics":
                    self.diagnostics_btn.configure(state="normal")
                    if not self._closing:
                        self._show_device_diagnostics(payload)
                elif kind == "error":
                    self._append("ERROR: " + payload)
                    messagebox.showerror(APP_TITLE, payload)
                    self.status_line.set("Error — see activity")
                    if hasattr(self, "hh_slots_build_btn"):
                        self.hh_slots_build_btn.configure(state="normal")
                    if hasattr(self, "hh_slots_flash_btn"):
                        self.hh_slots_flash_btn.configure(state="disabled")
                    self.diagnostics_btn.configure(state="normal")
                    self._busy(False)
                elif kind == "progress":
                    value, label = payload
                    self.progress["value"] = value
                    self.progress_text.set(label)
                elif kind == "status":
                    self.status_line.set(payload)
                elif kind == "history_changed":
                    self._refresh_local_history()
                elif kind == "busy_off":
                    self._busy(False)
                elif kind == "hh_flash_done":
                    self.hh_validated_build_path = None
                    self.hh_validated_build_sha = None
                    self.hh_validated_build_report = None
                    self.hh_slots_flash_btn.configure(state="disabled")
                    self.hh_slots_build_btn.configure(state="normal")
                elif kind == "platform_detect_result":
                    epoch, result = payload
                    self.detect_btn.configure(state="normal")
                    if self._closing or epoch != self._inspection_epoch:
                        continue
                    target = {"r3s": PLAT_R3S, "hhkb": PLAT_HHKB}.get(result.selected)
                    if target is not None and target != self.platform.get():
                        self.platform.set(target)
                    self.status_line.set(result.message)
                elif kind in ("fw_detect_result", "fw_inspection_result"):
                    if kind == "fw_inspection_result":
                        epoch, payload = payload
                        self.inspect_btn.configure(state="normal")
                        if self._closing or epoch != self._inspection_epoch or self.platform.get() != PLAT_HHKB:
                            continue
                    self.firmware_identification = payload
                    self.installed_firmware.set(FW_DETECT.display_title(payload) + (f"  ·  {payload.device}" if payload.device else ""))
                    self.detect_detail.set(FW_DETECT.format_details(payload))
                    self.firmware_report_btn.configure(state="normal")
                    self.inspect_btn.configure(state="normal")
                    self._refresh_local_history()
                elif kind in ("fw_detect_error", "fw_inspection_error"):
                    if kind == "fw_inspection_error":
                        epoch, payload = payload
                        self.inspect_btn.configure(state="normal")
                        if self._closing or epoch != self._inspection_epoch or self.platform.get() != PLAT_HHKB:
                            continue
                    self.installed_firmware.set("Unknown")
                    self.detect_detail.set(str(payload))
                    self.inspect_btn.configure(state="normal")
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
        if self.flash_active:
            for widget, _ in self._flash_widget_states:
                widget.configure(state="disabled")
        self.after(80, self._poll)

    # ---------------- Installed firmware, conservative probe ----------------
    @property
    def history_path(self):
        # Reading an absent history must not create output directories.
        return APP_DIR / "output" / "install_history.json"

    def _refresh_local_history(self):
        platform = self.platform.get()
        model = None
        if platform == PLAT_HHKB and self.firmware_identification is not None:
            model = self.firmware_identification.device or None
        elif platform == PLAT_R3S and self.source_meta:
            model = self.source_meta.get("source_model") or self.source_meta.get("model")
        self.local_history.set(local_history_summary(
            INSTALL_HISTORY.load_history(self.history_path), platform, model=model))

    def _record_operation_history(self, *, event, model, mode, sha, settings=None):
        # History failure cannot turn a completed flash into an error/retry.
        try:
            saved = INSTALL_HISTORY.record_event(self.history_path, event=event, model=model,
                firmware_sha256=sha, application_build=APP_BUILD, application_title=APP_TITLE,
                application_channel="release", intended_mode=mode, settings=settings,
                reconnect_status="verified" if event == "installed" else "not_applicable")
        except Exception:
            saved = False
        if saved:
            self.q.put(("history_changed", None))
        else:
            self.q.put(("log", "Operation completed; supplementary local history could not be saved."))
        return saved

    def inspect_device_diagnostics(self):
        if not self._operation_available():
            return
        if self.platform.get() != PLAT_HHKB:
            messagebox.showinfo(APP_TITLE, "Device diagnostics currently supports HHKB over USB. Select HHKB first.")
            return
        self.diagnostics_btn.configure(state="disabled")
        def work():
            self.q.put(("device_diagnostics", DEVICE_DIAG.collect_hhkb(HHE)))
        try:
            if not self._worker(work):
                self.diagnostics_btn.configure(state="normal")
        except Exception:
            self.diagnostics_btn.configure(state="normal")
            raise

    def _show_device_diagnostics(self, snapshot):
        report = snapshot["report"]
        display = snapshot["display"]
        window = tk.Toplevel(self)
        window.title("HHKB device diagnostics — read-only snapshot")
        window.geometry("720x490")
        window.transient(self)
        body = ttk.Frame(window, padding=16)
        body.pack(fill="both", expand=True)
        text = tk.Text(body, wrap="word", height=20, font=("Segoe UI", 10))
        text.pack(fill="both", expand=True)
        text.insert("1.0", "\n".join([
            "HHKB device diagnostics", f"Captured (UTC): {report['captured_at']}", "",
            f"Model: {report['model']}",
            f"Reported firmware revision: {report['reported_revision']}",
            "Firmware variant: not determined by identity query",
            "The reported revision alone does not distinguish stock / RT / HOLD.", "",
            f"USB serial (masked): {display['usb_serial']}",
            f"Device serial (masked): {display['firmware_serial']}",
            f"Normal-mode identity: {report['normal_identity_check']}",
            f"Update-mode identity: {report['updater_identity_check']}", "",
            report["detail"], "",
            "This is a snapshot, not an update approval. No update commands were sent.",
            "Shared reports omit serial numbers, USB paths and raw responses.",
        ]))
        text.configure(state="disabled")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        def save():
            path = filedialog.asksaveasfilename(parent=window, title="Save shared diagnostics",
                defaultextension=".json", initialfile="TopreRT_HHKB_diagnostics.json",
                filetypes=[("JSON report", "*.json")])
            if not path:
                return
            try:
                Path(path).write_text(DEVICE_DIAG.shared_report(snapshot), encoding="utf-8")
            except OSError:
                messagebox.showerror(APP_TITLE, "Could not save report. Choose a writable folder.", parent=window)
                return
            messagebox.showinfo(APP_TITLE, "Report saved without serial numbers or USB paths.", parent=window)
        ttk.Button(buttons, text="Save shared report…", command=save).pack(side="left")
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")

    def inspect_installed_firmware(self):
        if not self._operation_available():
            return
        if self.platform.get() != PLAT_HHKB:
            self.installed_firmware.set("Not supported for R3S yet")
            self.detect_detail.set("R3S firmware query requires a separate validated read-only protocol.")
            return
        if self.worker is not None and self.worker.is_alive():
            self.detect_detail.set("Stop Observer / wait for the running operation before inspecting firmware.")
            return
        self.installed_firmware.set("Inspecting HHKB USB device...")
        self.firmware_identification = None
        self.firmware_report_btn.configure(state="disabled")
        self._inspection_epoch = getattr(self, "_inspection_epoch", 0) + 1
        epoch = self._inspection_epoch
        self.detect_detail.set("Read-only commands only; no updater or firmware write command.")
        self.inspect_btn.configure(state="disabled")
        def work():
            try:
                result = FW_INSPECT.inspect_hhkb(HHE)
                self.q.put(("fw_inspection_result", (epoch, result)))
            except Exception:
                self.q.put(("fw_inspection_error", (epoch, "Firmware query failed. Check USB connection and close other keyboard tools; exact version remains unknown.")))
        try:
            started = self._worker(work)
        except Exception:
            self.inspect_btn.configure(state="normal")
            self.installed_firmware.set("Query did not start")
            raise
        if not started:
            self.inspect_btn.configure(state="normal")
            self.installed_firmware.set("Query did not start")

    def save_firmware_identification(self):
        if self.firmware_identification is None:
            return
        path = filedialog.asksaveasfilename(parent=self, title="Save firmware identification",
            initialfile="TopreRT_firmware_identification.json", defaultextension=".json",
            filetypes=[("JSON report", "*.json")])
        if path:
            try:
                Path(path).write_text(FW_DETECT.shared_report(self.firmware_identification), encoding="utf-8")
            except OSError:
                messagebox.showerror(APP_TITLE, "Could not save identification report.")

    # ---------------- Platform ----------------
    def _detect_platform(self):
        if not self._operation_available():
            return
        self._inspection_epoch += 1
        epoch = self._inspection_epoch
        self.firmware_identification = None
        self.firmware_report_btn.configure(state="disabled")
        self.installed_firmware.set("Not queried — select Inspect firmware")
        self.detect_detail.set("Detect finds USB keyboards. Inspect firmware reads the installed family and build information.")
        self.status_line.set("Detecting USB keyboards...")
        self.detect_btn.configure(state="disabled")
        def work():
            result = DEVICE_DISCOVERY.scan()
            self.q.put(("platform_detect_result", (epoch, result)))
        try:
            started = self._worker(work)
        except Exception:
            self.detect_btn.configure(state="normal")
            self.status_line.set("USB detection did not start.")
            raise
        if not started:
            self.detect_btn.configure(state="normal")
            self.status_line.set("USB detection did not start.")

    def _platform_changed(self, *_):
        self._inspection_epoch += 1
        self.firmware_identification = None
        self.firmware_report_btn.configure(state="disabled")
        self.installed_firmware.set("Not queried — select Inspect firmware")
        plat = self.platform.get()
        self.detect_detail.set("Inspect firmware reads available build information. Older firmware may provide only legacy identification.")
        self.source_path = None
        self.source_valid = False
        self._set_source_entry("")
        self.source_status.set("No firmware selected")
        self.progress["value"] = 0
        self.progress_text.set("")

        if plat == PLAT_R3S:
            self.firmware_tabs.tab(self.hold_tab, state="hidden")
            self.firmware_tabs.select(self.rt_tab)
            self.stock_firmware_frame.configure(text="Stock firmware (R3S A0.12)")
            self.platform_note.configure(
                text="REALFORCE R3S A0.12 · File creation here → installation in official REALFORCE software"
            )
            self.profile_combo.configure(values=list(R3_PROFILES))
            self.profile.set(next(iter(R3_PROFILES)))
            self.apply_btn.configure(text="Create Firmware File")
            self.recovery_btn.configure(text="Recovery Instructions")
            self.release.set("0.60")
            self.repress.set("0.80")
        else:
            self.firmware_tabs.tab(self.hold_tab, state="normal")
            self.stock_firmware_frame.configure(text="Stock firmware (shared by RT & HOLD · A0.48)")
            self.platform_note.configure(
                text="HHKB PD-KB800W · A0.48 · Installation runs inside this app"
            )
            self.profile_combo.configure(values=list(HH_PROFILES))
            self.profile.set(next(iter(HH_PROFILES)))
            self.apply_btn.configure(text="Create & Install RT")
            self.recovery_btn.configure(text="Restore Stock")
            self.release.set("0.10")
            self.repress.set("0.15")
            self._auto_find_hhkb_stock()

        self._sync_hhkb_stock_for_hold()
        self._mode_changed()
        self.preview()
        self._live_validate()
        self._refresh_local_history()

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

    # ---------------- HHKB v0.13 generic-HOLD custom slots ----------------
    def _sync_hhkb_stock_for_hold(self):
        # The RT and HOLD builders share the same exact, validated stock file.
        self.hh_slot_baseline_path = (
            self.source_path
            if self.platform.get() == PLAT_HHKB and self.source_valid and self.source_path
            else None
        )
        if self.hh_slot_baseline_path:
            self.hh_slot_baseline_status.set("PASS — shared stock A0.48 validated")
        else:
            self.hh_slot_baseline_status.set("Select exact stock A0.48 above")
        self._hh_slots_changed()

    def _hh_slots_try_bundled_baseline(self):
        self._sync_hhkb_stock_for_hold()

    def _hh_slots_browse_baseline(self):
        # Legacy callsite kept for compatibility with existing integrations.
        self.browse_source()

    def _hh_slots_load_acv(self):
        vals = [("A", "A", "CTRL", "250"), ("C", "C", "CTRL", "250"), ("V", "V", "CTRL", "250")]
        for i in range(8):
            self.hh_slot_enabled[i].set(i < 3)
            if i < 3:
                s, tap, hold, th = vals[i]
                self.hh_slot_source[i].set(s)
                self.hh_slot_tap[i].set(tap)
                self.hh_slot_hold[i].set(hold)
                self.hh_slot_threshold[i].set(th)
            else:
                self.hh_slot_source[i].set("A")
                self.hh_slot_tap[i].set("A")
                self.hh_slot_hold[i].set("CTRL")
                self.hh_slot_threshold[i].set("250")
        self._hh_slots_changed()

    def _hh_slots_load_spacefn(self):
        for i in range(8):
            self.hh_slot_enabled[i].set(i == 0)
            if i == 0:
                self.hh_slot_source[i].set("SPACE")
                self.hh_slot_tap[i].set("SPACE")
                self.hh_slot_hold[i].set("FN")
                self.hh_slot_threshold[i].set("250")
            else:
                self.hh_slot_source[i].set("A")
                self.hh_slot_tap[i].set("A")
                self.hh_slot_hold[i].set("CTRL")
                self.hh_slot_threshold[i].set("250")
        self._hh_slots_changed()

    def _hh_slots_update_hold_status(self, slot_no):
        try:
            if not self.hh_slot_enabled[slot_no].get():
                self.hh_slot_hold_status[slot_no].set("—")
                return
            name = self.hh_slot_hold[slot_no].get().strip().upper()
            self.hh_slot_hold_status[slot_no].set(HHSLOT.hold_support_status(name))
        except Exception:
            self.hh_slot_hold_status[slot_no].set("UNKNOWN")

    def _hh_slots_collect(self):
        slots = []
        for i in range(8):
            if not self.hh_slot_enabled[i].get():
                continue
            src_name = self.hh_slot_source[i].get().strip().upper()
            tap_name = self.hh_slot_tap[i].get().strip().upper()
            hold_name = self.hh_slot_hold[i].get().strip().upper()
            if src_name not in HHSLOT.KEY_MAP:
                raise HHSLOT.Reject(f"SLOT{i}: unknown source {src_name!r}")
            if tap_name not in HHSLOT.KEY_MAP:
                raise HHSLOT.Reject(f"SLOT{i}: unknown tap {tap_name!r}")
            if hold_name not in HHSLOT.KEY_MAP:
                raise HHSLOT.Reject(f"SLOT{i}: unknown hold {hold_name!r}")
            try:
                threshold = int(self.hh_slot_threshold[i].get().strip(), 0)
            except Exception:
                raise HHSLOT.Reject(f"SLOT{i}: threshold must be an integer milliseconds value")
            if not 1 <= threshold <= 0xFFFF:
                raise HHSLOT.Reject(f"SLOT{i}: threshold must be 1..65535 ms")
            slots.append({
                "label": f"SLOT{i}",
                "source_name": src_name,
                "tap_name": tap_name,
                "hold_name": hold_name,
                "source": HHSLOT.KEY_MAP[src_name],
                "tap": HHSLOT.KEY_MAP[tap_name],
                "hold": HHSLOT.KEY_MAP[hold_name],
                "threshold_ms": threshold,
            })
        HHSLOT.validate_slots(slots)
        return slots

    def _hh_slots_changed(self, *_args):
        if hasattr(self, "hh_slots_flash_btn"):
            self.hh_validated_build_path = None
            self.hh_validated_build_sha = None
            self.hh_validated_build_report = None
            self.hh_slots_flash_btn.configure(state="disabled")
        if not hasattr(self, "hh_slot_summary"):
            return
        try:
            slots = self._hh_slots_collect()
            self.hh_slot_summary.set(f"VALID · {len(slots)}/8 HOLD slots enabled")
            ready = bool(self.hh_slot_baseline_path)
            if hasattr(self, "hh_slots_build_btn"):
                self.hh_slots_build_btn.configure(state="normal" if ready else "disabled")
            return True
        except Exception as e:
            self.hh_slot_summary.set("INVALID · " + str(e))
            if hasattr(self, "hh_slots_build_btn"):
                self.hh_slots_build_btn.configure(state="disabled")
            return False

    def _hh_slots_self_test(self):
        try:
            if not self.hh_slot_baseline_path:
                raise HHSLOT.Reject("Select your exact stock A0.48 HFB first.")
            baseline = self.hh_slot_baseline_path.read_bytes()
            HHSLOT.validate_stock(baseline)
            slots = [HHSLOT.parse_slot("A>A>LALT:250")]
            out, report = HHSLOT.build(baseline, slots)
            got = HHSLOT.sha256(out)
            if got != HHSLOT.GENERIC_CORE_REFERENCE_SHA256:
                raise HHSLOT.Reject(
                    f"generic-HOLD reconstruction regression SHA mismatch: {got}"
                )
            self._set_log(
                "HHKB GENERIC-HOLD SELF-TEST PASS\n\n"
                "A tap A / hold LALT @250 reproduces the hardware-tested "
                "rev2.2 baseline byte-for-byte.\n"
                f"SHA-256  {got}\n"
                f"Table    {report['descriptor_table_hex']}\n\n"
                "No USB/HID access was performed."
            )
            self.status_line.set("HHKB generic-HOLD self-test passed")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def _hh_slots_build(self):
        if not self._operation_available():
            return
        self._hh_slots_changed()
        if not self.hh_slot_baseline_path:
            messagebox.showerror(APP_TITLE, "Select exact stock A0.48 first.")
            return
        try:
            baseline = self.hh_slot_baseline_path.read_bytes()
            HHSLOT.validate_stock(baseline)
            slots = self._hh_slots_collect()
            out, report = HH_ID.build_hold(baseline, slots)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return

        names = "-".join(s["source_name"] for s in slots) if slots else "NONE"
        build_id = report['identity']['build_id']
        target = self.output_dir / f"TopreRT_Development_HOLD_{build_id:08X}_{names}.hfb"
        n = 2
        while target.exists():
            target = self.output_dir / f"TopreRT_Development_HOLD_{build_id:08X}_{names}_{n}.hfb"
            n += 1
        manifest = Path(str(target) + ".manifest.json")
        try:
            BUILD_REGISTRY.write_build(target, out, report, baseline, self.output_dir/'identity')
        except Exception:
            self._hh_slots_changed()
            messagebox.showerror(APP_TITLE, "Could not save and validate the Development build/catalog. Installation remains disabled.")
            return

        self.progress["value"] = 100
        self.progress_text.set("Build ready")
        self._set_log(
            "BUILD PASS — HHKB GENERIC HOLD\n\n"
            f"Firmware  {target}\n"
            f"Manifest  {manifest}\n"
            f"SHA-256   {report['output_sha256']}\n"
            f"Build ID  {build_id:08X} · Development\n"
            f"Main CRC  {report['main_crc']}\n"
            f"Global CRC {report['global_crc']}\n\n"
            + "\n".join(
                f"SLOT{s['slot']}: {s['source_name']}({s['source']}) "
                f"→ tap {s['tap_name']}({s['tap']}) · hold {s['hold_name']}({s['hold']}) "
                f"[{s['hold_support']}] · {s['threshold_ms']}ms · {s['descriptor_hex']}"
                for s in report["slots"]
            )
            + "\n\nHOLD SUPPORT STATUS\n"
              "  HW VALIDATED: CTRL, LALT, V, SPACE\n"
              "  HW VALIDATED SPECIAL CASE: SPACE -> tap SPACE / hold FN\n"
              "  GENERIC / LIMITED TESTING: other selectable HOLD targets\n"
              "  BLOCKED: LSHIFT, RSHIFT\n"
              "\nBuild policy: audited HOLD core/table plus exact metadata sections and refreshed CRC.\n"
              "Build is SHA-locked before Flash is enabled."
        )
        # Lock the exact bytes that passed the builder audit. Any later slot edit
        # invalidates this state in _hh_slots_changed().
        built_bytes = target.read_bytes()
        built_sha = HHSLOT.sha256(built_bytes)
        if built_sha != report["output_sha256"]:
            raise HHSLOT.Reject("Post-write SHA mismatch; refusing to enable Flash.")
        # Re-run baseline + candidate audit from disk, not from the in-memory image.
        try:
            baseline_disk = self.hh_slot_baseline_path.read_bytes()
            HHSLOT.validate_stock(baseline_disk)
            HH_ID.validate(baseline_disk, built_bytes, report, family='hold')
        except Exception:
            self._hh_slots_changed()
            messagebox.showerror(APP_TITLE, "Fresh file validation failed. HOLD installation remains disabled.")
            return

        self.hh_validated_build_path = target
        self.hh_validated_build_sha = built_sha
        self.hh_validated_build_report = report
        self.hh_slots_flash_btn.configure(state="normal")
        self.status_line.set("HHKB build validated — ready to flash")
        messagebox.showinfo(
            APP_TITLE,
            "File creation & validation PASS. The keyboard has not been updated.\n\n"
            "Select 2. Install HOLD to write this validated file to the keyboard.\n"
            "Changing any slot setting will disable Flash again.\n\n"
            f"SHA-256: {built_sha}\n\n{target}"
        )

    def _hh_slots_flash(self):
        if not self._operation_available():
            return
        path = self.hh_validated_build_path
        sha = self.hh_validated_build_sha
        if not path or not sha:
            messagebox.showerror(APP_TITLE, "No validated custom-slot build is armed.")
            return
        path = Path(path)
        if not path.exists():
            self._hh_slots_changed()
            messagebox.showerror(APP_TITLE, "Validated HFB no longer exists.")
            return
        current_sha = HHSLOT.sha256(path.read_bytes())
        if current_sha != sha:
            self._hh_slots_changed()
            messagebox.showerror(
                APP_TITLE,
                "Validated HFB changed on disk. Flash has been disarmed."
            )
            return

        token = "FLASH-" + sha[:12].upper()
        prompt = (
            "REAL HHKB FIRMWARE UPDATE\n\n"
            "The exact validated HFB below will be flashed.\n"
            "Do not disconnect USB or let the PC sleep.\n\n"
            f"SHA-256: {sha}\n\n"
            f"Type exactly:\n{token}"
        )
        typed = simpledialog.askstring(APP_TITLE, prompt, parent=self)
        if typed != token:
            if typed is not None:
                messagebox.showinfo(APP_TITLE, "Confirmation did not match. Flash cancelled.")
            return

        self.hh_slots_flash_btn.configure(state="disabled")
        self.hh_slots_build_btn.configure(state="disabled")
        self.status_line.set("HHKB flash armed — preflight starting")
        baseline = self.hh_slot_baseline_path
        history_settings = hold_history_settings(self.hh_validated_build_report)
        self._worker(lambda: self._hh_slots_flash_worker(path, sha, token, baseline, history_settings), flash=True)

    def _hh_slots_flash_worker(self, path, sha, token, baseline, history_settings=None):
        helper = APP_DIR / "hhkb_metadata_flasher.py"
        if not helper.exists():
            raise RuntimeError(f"Validated flasher helper missing: {helper}")
        if baseline is None or not baseline.exists():
            raise RuntimeError("Exact stock A0.48 input is no longer available.")

        cmd = [
            sys.executable, "-u", str(helper), str(path),
            "--baseline", str(baseline),
            "--manifest", str(path) + ".manifest.json",
            "--expected-sha", sha,
            "--confirm-token", token,
            "--flash",
        ]
        self.q.put(("log", "FLASH PREFLIGHT — exact SHA/diff/CRC validation will run again."))
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        flash_t0 = None
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                self.q.put(("log", line))

                # Hardware-tested writer reports E2 as: "  201/4960    4.1%"
                m = re.search(r"(\d+)\s*/\s*(\d+)\s+(\d+(?:\.\d+)?)%$", line)
                if m:
                    done = int(m.group(1))
                    total = int(m.group(2))
                    pct = float(m.group(3))
                    now = time.monotonic()
                    if flash_t0 is None:
                        flash_t0 = now
                    elapsed = max(0.0, now - flash_t0)
                    rate = (done - 1) / elapsed if elapsed > 0 and done > 1 else 0.0
                    detail = flash_transfer_text(done, total, elapsed, rate)
                    self.q.put(("progress", (15 + 70 * done / total, detail)))
            rc = proc.wait()
        finally:
            # Keep the protection until the child exits, including output-read failures.
            # Drain remaining output to avoid a full pipe blocking the writer.
            if proc.poll() is None:
                try:
                    proc.communicate()
                finally:
                    proc.wait()
            if proc.stdout:
                proc.stdout.close()

        if rc != 0:
            raise RuntimeError(f"HHKB validated flasher exited with code {rc}")

        self._record_operation_history(event="installed", model="PD-KB800W", mode="hold",
                                       sha=sha, settings=history_settings)
        self.q.put(("progress", (100, "HHKB flash complete")))
        self.q.put(("status", "HHKB custom v0.13 flash completed — reconnect verified"))
        self.q.put(("log", "FLASH PASS — E3 completed and normal firmware reconnect was verified."))
        # Do not leave a stale build armed after a real flash.
        self.q.put(("hh_flash_done", None))

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
        self._sync_hhkb_stock_for_hold()
        self._live_validate()
        self._refresh_local_history()

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
        self._refresh_local_history()

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
        if self.flash_active:
            self.apply_btn.configure(state="disabled")
            return False
        try:
            rmm, pmm, rr, pr = self._profile_values()
            self.validation_status.set(
                f"VALID ✓   Release {rmm:g} mm → {rr} raw   |   Re-press {pmm:g} mm → {pr} raw"
            )
            ready = self.source_valid
            self.action_status.set("Ready to create / install" if ready else "Select supported original stock file")
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
                    "Settings check only. To apply: create a file and install the generated .rfb with official REALFORCE software." +
                    (
                        f"\n\nModel       {self.source_meta['model']}"
                        f"\nRT core     {self.source_meta['rt_core_status']}"
                        f"\nObserver    {self.source_meta['observer_status']}"
                        if self.source_meta else ""
                    )
                )
            else:
                self._set_log(
                    "SETTINGS CHECK — not applied to the keyboard\nCore validation history is shown below; this is not a test of this device.\n\n"
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
        if not self._operation_available():
            return
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
        self._record_operation_history(event="generated", model=meta["source_model"], mode="rt",
            sha=HHE.sha256(out), settings={"release_raw": rr, "repress_raw": pr,
                                         "release_mm": rmm, "repress_mm": pmm})

        messagebox.showinfo(
            APP_TITLE,
            "R3S firmware build completed.\n\n"
            "Next: Open Output Folder and select the generated .rfb in official REALFORCE software. The keyboard has not been updated.\n\n"
            f"{target}"
        )

    def _apply_hhkb(self):
        try:
            stock = self.source_path.read_bytes()
            HHE.validate_stock(stock)
            rmm, pmm, rr, pr = self._profile_values()
            image, metadata_report = HH_ID.build_rt(stock, rr, pr)
            build_id = metadata_report['identity']['build_id']
            target = self.output_dir / f"TopreRT_Development_RT_{build_id:08X}_R{rr}_P{pr}.hfb"
            n = 2
            while target.exists():
                target = self.output_dir / f"TopreRT_Development_RT_{build_id:08X}_R{rr}_P{pr}_{n}.hfb"
                n += 1
            BUILD_REGISTRY.write_build(target, image, metadata_report, stock, self.output_dir/'identity')
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return

        if not messagebox.askyesno(
            APP_TITLE,
            "Create and install RT firmware on the connected HHKB?\n\n"
            f"Development build: {build_id:08X}\n"
            f"Release: {rr} raw (~{HHE.raw_to_mm(rr):.3f} mm estimated)\n"
            f"Re-press: {pr} raw (~{HHE.raw_to_mm(pr):.3f} mm estimated)\n\n"
            "Do not disconnect USB or let the PC sleep during the update."
        ):
            return

        self._busy(True)
        self.progress["value"] = 0
        self.progress_text.set("Preparing...")

        def work():
            self.q.put(("log", ""))
            self.q.put(("log", "BUILD PASS — HHKB"))
            self.q.put(("log", f"Firmware: {target}"))
            self.q.put(("log", f"SHA-256: {HHE.sha256(image)}"))
            self.q.put(("log", "Whitelist / helper / CRC: PASS"))
            HH_ID.validate(stock, image, metadata_report, family='rt_only')
            model = self._hhkb_flash(image)
            self._record_operation_history(event="installed", model=model, mode="rt", sha=HHE.sha256(image),
                settings={"release_raw": rr, "repress_raw": pr, "release_mm": rmm, "repress_mm": pmm})
            self.q.put(("status", "HHKB TopreRT applied — reconnect verified"))
            self.q.put(("busy_off", None))
        self._worker(work, flash=True)

    def _hhkb_flash(self, image):
        from hhkb_update_identity import DeviceBinding
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
            binding = DeviceBinding.capture(desc, dev, ident1[0])
            self.q.put(("progress", (7, "Entering updater")))
            HHE.req(dev, HHE.packet(0xE0), bytes([0x55,0x55,0xE0,0,0,0]))
        finally:
            dev.close()

        self.q.put(("progress", (10, "Waiting for updater")))
        time.sleep(10)
        desc = HHE.wait_one(hid, 10)
        dev = HHE.open_dev(hid, desc)
        try:
            binding.verify_usb(desc, dev, "Updater before E1", lambda: HHE.query(dev, 0x02))
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
                    avg = (completed - 1) / elapsed
                    if elapsed >= 1 and completed > 1:
                        self.flash_rate = avg if self.flash_rate is None else 0.25*avg + 0.75*self.flash_rate
                    pct = 15 + (completed/total)*70
                    self.q.put(("progress", (pct, flash_transfer_text(completed, total, elapsed, self.flash_rate))))
                if n % 500 == 0 or n == total-1:
                    self.q.put(("log", f"  {completed}/{total}  {completed*100/total:5.1f}%"))
            self.q.put(("progress", (88, "Finalizing")))
            HHE.req(dev, e3, bytes([0x55,0x55,0xE3,0,0,0]))
        finally:
            dev.close()

        self.q.put(("progress", (92, "Reconnecting · up to ~10s")))
        time.sleep(10)
        desc = HHE.wait_one(hid, 10)
        dev = HHE.open_dev(hid, desc)
        try:
            final_info = HHE.identity(dev)[0]
            binding.verify_usb(desc, dev, "Normal reconnect", lambda: final_info)
            binding.verify_firmware(final_info)
        finally:
            dev.close()
        self.q.put(("progress", (100, "Reconnect PASS")))
        self.q.put(("log", "Reconnect: PASS"))
        return HHE.decode_identity(final_info)

    # ---------------- Observer ----------------
    def start_observer(self):
        if not self._operation_available():
            return
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
        self.stop_event.set()
        if self.r3_observer_proc is not None and self.r3_observer_proc.poll() is None:
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
        if not self._operation_available():
            return
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
        if not messagebox.askyesno(APP_TITLE, "Install original HHKB A0.48?\n\nThis writes firmware and removes RT/HOLD features. It is not a settings reset.\nKeep USB connected until completion."):
            return
        self._busy(True)
        self.progress["value"] = 0
        self.progress_text.set("Restore preparing...")
        def work():
            self.q.put(("log", "RESTORE PREFLIGHT: PASS"))
            model = self._hhkb_flash(stock)
            self._record_operation_history(event="installed", model=model, mode="stock", sha=HHE.sha256(stock))
            self.q.put(("status", "HHKB stock A0.48 restored — reconnect verified"))
            self.q.put(("busy_off", None))
        self._worker(work, flash=True)

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
                    o, meta = R3P.build(data, 306, 408)
                    if R3C.sha256(o) != R3C.STABLE_OUTPUT_SHA256_BY_MODEL[meta["source_model"]]:
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
                if self.hh_slot_baseline_path:
                    baseline = self.hh_slot_baseline_path.read_bytes()
                    HHSLOT.validate_stock(baseline)
                    slot_img, _slot_report = HHSLOT.build(
                        baseline, [HHSLOT.parse_slot("A>A>LALT:250")]
                    )
                    if HHSLOT.sha256(slot_img) != HHSLOT.GENERIC_CORE_REFERENCE_SHA256:
                        raise HHSLOT.Reject("v0.13 generic-HOLD descriptor regression SHA mismatch")
                    lines += ["v0.13 generic-HOLD builder regression: PASS"]
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
