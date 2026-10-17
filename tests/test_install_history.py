"""Offline development checks; these tests never access a keyboard."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_history as history


class InstallHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix=".install-history-test-",
                                                      dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "output" / "install_history.json"
        self.sha = hashlib.sha256(b"exact firmware bytes").hexdigest()

    def record(self, **overrides):
        values = dict(event="installed", model="PD-KB800W", firmware_sha256=self.sha,
                      application_build="after-v0.3.0-rc3", application_title="TopreRT GUI — Development",
                      application_channel="development", intended_mode="rt",
                      reconnect_status="verified", settings={"release_raw": 16, "repress_raw": 8})
        values.update(overrides)
        return history.record_event(self.path, **values)

    def raw(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_install_records_exact_hash_utc_build_and_evidence_limits(self):
        self.assertTrue(self.record())
        record = history.load_history(self.path)[0]
        self.assertEqual(record["firmware_sha256"], self.sha)
        self.assertRegex(record["timestamp_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
        self.assertEqual(record["application_channel"], "development")
        self.assertEqual(record["application_build"], "after-v0.3.0-rc3")
        self.assertEqual(record["completion_status"], "completed")
        self.assertEqual(record["reconnect_status"], "verified")
        self.assertEqual(record["match_scope"], "model_only")
        self.assertEqual(record["evidence_scope"], "pc_operation_history")
        self.assertFalse(record["device_firmware_verified"])

    def test_r3s_generation_cannot_become_installation(self):
        for model in ("R3SA", "R3SB", "R3SC", "R3SD"):
            self.assertTrue(self.record(event="generated", model=model, reconnect_status="not_applicable"))
            self.assertFalse(self.record(event="installed", model=model))
            self.assertIsNone(history.latest_record_for_model(self.path, model, event="installed"))
            self.assertEqual(history.latest_record_for_model(self.path, model)["event"], "generated")
        self.assertFalse(self.record(event="generated", reconnect_status="not_applicable"))
        self.assertFalse(self.record(event="generated", model="R3SB", reconnect_status="verified"))

    def test_only_successful_reconnected_installs_are_accepted(self):
        for completion in ("failed", "started", "unknown"):
            self.assertFalse(self.record(completion_status=completion))
        for reconnect in ("pending", "failed", "not_applicable", None):
            self.assertFalse(self.record(reconnect_status=reconnect))
        self.assertFalse(self.path.exists())

    def test_stock_and_hold_intent_are_distinct(self):
        self.assertTrue(self.record(intended_mode="stock", settings={}))
        slot = {"source_name": "SPACE", "tap_name": "SPACE", "hold_name": "FN", "threshold_ms": 250}
        self.assertTrue(self.record(intended_mode="hold", settings={"slots": [slot]}))
        record = history.latest_record_for_model(self.path, "PD-KB800W")
        self.assertEqual(record["intended_mode"], "hold")
        self.assertEqual(record["settings"]["slots"], [slot])
        self.assertEqual(history.load_history(self.path)[1]["intended_mode"], "stock")

    def test_retention_is_bounded_newest_first(self):
        for value in range(7):
            self.assertTrue(self.record(settings={"release_raw": value}, max_records=3))
        records = history.load_history(self.path)
        self.assertEqual([r["settings"]["release_raw"] for r in records], [6, 5, 4])
        self.assertEqual(len(self.raw()["records"]), 3)
        self.assertFalse(self.record(max_records=0))
        self.assertFalse(self.record(max_records=history.MAX_RECORDS + 1))

    def test_lookup_matches_model_only_and_skips_newer_other_model(self):
        self.assertTrue(self.record())
        self.assertTrue(self.record(event="generated", model="R3SB", reconnect_status="not_applicable"))
        record = history.latest_record_for_model(self.path, " pd-kb800w ", event="installed")
        self.assertEqual(record["model"], "PD-KB800W")
        self.assertEqual(record["match_scope"], "model_only")
        self.assertIsNone(history.latest_record_for_model(self.path, "PD-KB800B"))
        self.assertIsNone(history.latest_record_for_model(self.path, "PRIVATE-SERIAL"))

    def test_private_and_unknown_settings_are_rejected_without_writing(self):
        for settings in ({"serial": "PRIVATE"}, {"usb_path": "PRIVATE"}, {"source_path": "C:/PRIVATE"},
                         {"profile": "PRIVATE"}, {"slots": [{"serial": "PRIVATE"}]}):
            self.assertFalse(self.record(settings=settings))
        self.assertFalse(self.record(model="PD-KB800W PRIVATE-SERIAL"))
        self.assertFalse(self.record(application_build="C:/PRIVATE/source"))
        self.assertFalse(self.path.exists())

    def test_settings_reject_nonfinite_bool_excessive_and_wrong_mode_values(self):
        for settings in ({"release_raw": True}, {"release_raw": 65536}, {"release_mm": float("nan")},
                         {"repress_mm": float("inf")}, {"release_mm": 11}, {"release_raw": -1}):
            self.assertFalse(self.record(settings=settings))
        self.assertFalse(self.record(intended_mode="stock"))
        slot = {"source_name": "A", "tap_name": "A", "hold_name": "CTRL", "threshold_ms": 250}
        self.assertFalse(self.record(intended_mode="hold", settings={"slots": [slot] * 9}))
        self.assertFalse(self.record(intended_mode="hold", settings={"slots": [dict(slot, threshold_ms=0)]}))
        self.assertFalse(self.record(intended_mode="hold", settings={"slots": [dict(slot, hold_name="PRIVATE-SERIAL")]}))

    def test_invalid_required_values_do_not_modify_existing_file(self):
        self.assertTrue(self.record())
        original = self.path.read_bytes()
        for values in ({"firmware_sha256": "bad"}, {"application_title": "bad\ntext"},
                       {"application_channel": "rc3"}, {"intended_mode": "unknown"}, {"event": "probe"}):
            self.assertFalse(self.record(**values))
            self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(self.record(firmware_sha256=self.sha.upper()))
        self.assertEqual(history.load_history(self.path)[0]["firmware_sha256"], self.sha)

    def test_missing_malformed_oversized_and_unknown_schema_are_empty(self):
        self.assertEqual(history.load_history(self.path), [])
        self.path.parent.mkdir()
        for raw in (b"not json", b"[]", b'{}', b'{"schema_version": 2, "records": []}',
                    b'{"schema_version": true, "records": []}', b"\xff",
                    b" " * (history.MAX_FILE_BYTES + 1)):
            self.path.write_bytes(raw)
            self.assertEqual(history.load_history(self.path), [])
            self.assertIsNone(history.latest_record_for_model(self.path, "PD-KB800W"))

    def test_invalid_entries_and_forged_verification_are_discarded(self):
        self.assertTrue(self.record())
        valid = self.raw()["records"][0]
        bad = [None, {}, dict(valid, timestamp_utc="yesterday"), dict(valid, serial="PRIVATE"),
               dict(valid, device_firmware_verified=True), dict(valid, match_scope="same_device")]
        self.path.write_text(json.dumps({"schema_version": 1, "records": bad + [valid]}), encoding="utf-8")
        self.assertEqual(history.load_history(self.path), [valid])

    def test_atomic_replace_failure_preserves_previous_history_and_cleans_temp(self):
        self.assertTrue(self.record())
        original = self.path.read_bytes()
        with patch.object(history.os, "replace", side_effect=PermissionError("busy")):
            self.assertFalse(self.record(intended_mode="stock", settings={}))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".install-history-*.tmp")), [])

    def test_write_failure_never_raises_to_firmware_caller(self):
        with patch.object(history.tempfile, "NamedTemporaryFile", side_effect=OSError("disk full")):
            self.assertFalse(self.record())
        self.assertFalse(self.path.exists())
        blocker = Path(self.directory.name) / "file"
        blocker.write_text("not a directory")
        self.path = blocker / "history.json"
        self.assertFalse(self.record())

    def test_successful_atomic_write_has_no_temp_or_sensitive_path_fields(self):
        self.assertTrue(self.record())
        serialized = self.path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.directory.name), serialized)
        self.assertNotIn("serial", serialized)
        self.assertNotIn("usb_path", serialized)
        self.assertEqual(list(self.path.parent.glob(".install-history-*.tmp")), [])
        first = history.load_history(self.path)
        first[0]["settings"]["release_raw"] = 999
        self.assertEqual(history.load_history(self.path)[0]["settings"]["release_raw"], 16)


if __name__ == "__main__":
    unittest.main()
