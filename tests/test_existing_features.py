import contextlib
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import toprert_unified_gui as gui


class ExistingFeaturesTests(unittest.TestCase):
    def test_hold_presets_and_threshold_limits(self):
        builder = gui.HHSLOT
        for preset in ("A>A>LALT:250", "SPACE>SPACE>FN:250"):
            cfg = builder.parse_slot(preset)
            builder.validate_slots([cfg])
            for threshold in (1, 65535):
                builder.validate_slots([{**cfg, "threshold_ms": threshold}])
            for threshold in (0, -1, 65536, True, "250"):
                with self.subTest(threshold=threshold), self.assertRaises(builder.Reject):
                    builder.validate_slots([{**cfg, "threshold_ms": threshold}])

    def test_hold_unknown_indices_rejected(self):
        cfg = gui.HHSLOT.parse_slot("A>A>LALT:250")
        for field in ("source", "tap", "hold"):
            with self.subTest(field=field), self.assertRaises(gui.HHSLOT.Reject):
                gui.HHSLOT.validate_slots([{**cfg, field: 255}])

    def test_r3s_cli_and_gui_selftest_use_selected_model(self):
        for model, digest in gui.R3C.STABLE_OUTPUT_SHA256_BY_MODEL.items():
            with self.subTest(model=model), contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(gui.R3P, "validate_source"))
                stack.enter_context(patch.object(gui.R3P, "build", return_value=(b"output", {"source_model": model})))
                stack.enter_context(patch.object(gui.R3C, "sha256", return_value=digest))
                stack.enter_context(patch.object(Path, "read_bytes", return_value=b"stock"))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                gui.R3P.self_test("stock.rfb")
                app = types.SimpleNamespace(platform=Mock(), source_valid=True,
                    source_path=Path("stock.rfb"), _append=Mock(), status_line=Mock(), _set_log=Mock())
                app.platform.get.return_value = gui.PLAT_R3S
                error = stack.enter_context(patch.object(gui.messagebox, "showerror"))
                stack.enter_context(patch.object(gui.messagebox, "showinfo"))
                gui.UnifiedGUI.self_test(app)
                error.assert_not_called()
